# ============================================================
# 文件功能：转化归因链路 ORM 模型（7 张表）
#
# 设计原则（重要）：
#   1. **不改动原有 8 张表**——已有数据库无需迁移，105 个既有用例不受影响。
#      订单与归因的关联通过独立的 order_attribution 表承载，而不是给 orders 加字段。
#   2. 金额从 orders 冗余到归因表，让报表聚合不必 join 业务表。
#   3. 手机号一律「哈希 + 掩码」双字段：哈希用于精确匹配，掩码用于人工核对。
#      **不存明文**，避免归因系统变成第二个个人信息泄漏源。
#
# 归因链路的三个环节（缺一不可）：
#   ① 官网访问行为  → visitor_session / visit_event（前端埋点写入）
#   ② 官网专属号码  → tracking_number（渠道标识的唯一锚点）
#   ③ 来电记录      → call_log（后台录入或电话系统导入，写入时触发归因）
#   归因 = 用「追踪号码 + 时间窗」或「手机号回溯」把 ③ 挂到 ① 上，再经
#   order_attribution 把成单接进来，形成「访问 → 来电 → 成单」全链路。
# ============================================================

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    Numeric,
    DateTime,
    ForeignKey,
    CheckConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import utcnow


# ============================================================
# 1. 官网专属号码表 tracking_number
#    每个渠道/活动配一个专属号码 —— 这是「渠道级归因」唯一的可靠锚点。
#    为什么必须有它：来电号码本身不含任何来源信息，只有「打的是哪个号」
#    能证明来源。真实企业中用 DNI（动态号码插入）做到访客级，本项目
#    简化为「一个渠道一个专属号 + 时间窗」达到可落地的最小闭环。
# ============================================================
class TrackingNumber(Base):
    __tablename__ = "tracking_number"
    __table_args__ = (
        CheckConstraint("channel IN ('direct','organic_search','social','paid','qr_offline','sms','referral','unknown')",
                        name="ck_tracking_channel"),
        Index("idx_tracking_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tracking_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # 追踪号码（唯一）
    display_no: Mapped[str] = mapped_column(String(20), nullable=False)                # 页面展示号码（通常同上）
    label: Mapped[str] = mapped_column(String(50), nullable=False)                     # 名称：官网主站专线
    channel: Mapped[str] = mapped_column(String(20), nullable=False)                   # 渠道枚举
    channel_detail: Mapped[str] = mapped_column(String(30), nullable=False, default="")  # 细分：wechat/baidu
    campaign: Mapped[str] = mapped_column(String(50), nullable=False, default="")      # 活动标识
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    remark: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ============================================================
# 2. 访问会话表 visitor_session
#    一个「会话」= 同一访客、30 分钟无活动内的一串行为。
#    归因的时间窗就是拿会话的 last_seen_at 跟来电时间比。
# ============================================================
class VisitorSession(Base):
    __tablename__ = "visitor_session"
    __table_args__ = (
        Index("idx_session_visitor", "visitor_id"),
        Index("idx_session_lastseen", "last_seen_at"),
        Index("idx_session_channel", "channel", "created_at"),
        Index("idx_session_bot", "is_bot", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visitor_id: Mapped[str] = mapped_column(String(36), nullable=False)   # 持久访客 ID（前端 localStorage，365 天）
    session_id: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)  # 会话 ID（30 分钟）

    first_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    landing_page: Mapped[str] = mapped_column(String(255), nullable=False, default="/")   # 落地页
    exit_page: Mapped[str] = mapped_column(String(255), nullable=False, default="/")      # 当前最后页面
    page_view_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    event_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hotline_click_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 热线点击次数（核心转化动作）

    referrer: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    utm_source: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    utm_medium: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    utm_campaign: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    utm_content: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    utm_term: Mapped[str] = mapped_column(String(50), nullable=False, default="")

    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")   # 一级渠道
    channel_detail: Mapped[str] = mapped_column(String(30), nullable=False, default="")    # 细分来源

    device_type: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")  # desktop/mobile/tablet
    is_bot: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    user_agent: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    ip_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")  # IP 哈希（不存明文）

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ============================================================
# 3. 行为事件表 visit_event
#    记「访客干了什么」，用于归因后回溯路径（他看了哪个蛋糕才打的电话）。
# ============================================================
class VisitEvent(Base):
    __tablename__ = "visit_event"
    __table_args__ = (
        Index("idx_event_session", "session_id", "occurred_at"),
        Index("idx_event_visitor", "visitor_id", "occurred_at"),
        Index("idx_event_type", "event_type", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False)
    visitor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)   # page_view/cake_view/hotline_click/message_submit
    page_path: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    ref_object_type: Mapped[str] = mapped_column(String(20), nullable=False, default="")  # cake/category/store
    ref_object_id: Mapped[Optional[int]] = mapped_column(Integer)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload: Mapped[str] = mapped_column(Text, nullable=False, default="")  # JSON 扩展
    occurred_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ============================================================
# 4. 来电记录表 call_log
#    写入即归因。match_* 四个字段把「凭什么这么归因」记录下来，可审计。
# ============================================================
class CallLog(Base):
    __tablename__ = "call_log"
    __table_args__ = (
        CheckConstraint("status IN ('answered','missed','wrong_number','test')", name="ck_call_status"),
        CheckConstraint("match_confidence IN ('high','medium','low','none')", name="ck_call_confidence"),
        Index("idx_call_time", "called_at"),
        Index("idx_call_phone", "caller_phone_hash"),
        Index("idx_call_tracking", "tracking_no"),
        Index("idx_call_visitor", "matched_visitor_id"),
        Index("idx_call_rule", "match_rule", "called_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    call_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # C + YYYYMMDD + 3 位序号

    tracking_no: Mapped[str] = mapped_column(String(20), nullable=False, default="")  # 被拨打的追踪号，空=打的是非官网号
    caller_phone_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    caller_phone_mask: Mapped[str] = mapped_column(String(20), nullable=False, default="")  # 138****8888

    called_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)   # 来电时间（归因时间锚）
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="answered")
    source_type: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")  # manual/import/api

    # 防虚高的关键闸门：打的不是官网专属号 → 不算官网带来的，直接不可归因
    is_attributable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # ---- 归因结果（写入时计算，之后不再变更；重新归因生成新记录并标记） ----
    matched_session_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    matched_visitor_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    match_rule: Mapped[str] = mapped_column(String(30), nullable=False, default="R4_UNMATCHED")
    match_confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="none")
    match_time_gap_sec: Mapped[Optional[int]] = mapped_column(Integer)   # 来电距会话最后活动的秒数
    candidate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 时间窗内的候选会话数（>1 说明有歧义，置信度自动降级）
    attribution_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    attribution_channel_detail: Mapped[str] = mapped_column(String(30), nullable=False, default="")

    operator: Mapped[str] = mapped_column(String(50), nullable=False, default="")   # 录入人
    remark: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ============================================================
# 5. 访客身份绑定表 visitor_identity
#    解决「跨设备 + 重号」问题：用户在留言表单填了手机号，就把该手机号
#    绑到他当前的 visitor_id 上。之后同一手机号来电，即使换了设备也能
#    精确归因（规则 R3）。留言表单在这里从「收集线索」升级为「身份回填」。
# ============================================================
class VisitorIdentity(Base):
    __tablename__ = "visitor_identity"
    __table_args__ = (
        UniqueConstraint("visitor_id", "phone_hash", name="uq_identity_visitor_phone"),
        Index("idx_identity_phone", "phone_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visitor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_mask: Mapped[str] = mapped_column(String(20), nullable=False, default="")
    bind_source: Mapped[str] = mapped_column(String(20), nullable=False, default="message")  # message/order/manual
    bind_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ============================================================
# 6. 订单归因表 order_attribution
#    把「成单金额」接到归因链上，才能算「官网带来的 GMV」。
#    通过 order_id 一对一关联 orders，不改动 orders 表结构。
# ============================================================
class OrderAttribution(Base):
    __tablename__ = "order_attribution"
    __table_args__ = (
        UniqueConstraint("order_id", name="uq_order_attr_order"),
        Index("idx_order_attr_channel", "attribution_channel", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    order_no: Mapped[str] = mapped_column(String(20), nullable=False)
    call_id: Mapped[Optional[int]] = mapped_column(Integer)        # 关联来电
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    visitor_id: Mapped[str] = mapped_column(String(36), nullable=False, default="")
    attribution_channel: Mapped[str] = mapped_column(String(20), nullable=False, default="unknown")
    attribution_channel_detail: Mapped[str] = mapped_column(String(30), nullable=False, default="")
    match_rule: Mapped[str] = mapped_column(String(30), nullable=False, default="R4_UNMATCHED")
    match_confidence: Mapped[str] = mapped_column(String(10), nullable=False, default="none")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ============================================================
# 7. 归因规则配置表 attribution_rule
#    时间窗这类参数不能硬编码在代码里 —— 运营要能自己调（比如大促期间
#    把窗口从 30 分钟放宽到 2 小时），调完要留痕。
# ============================================================
class AttributionRule(Base):
    __tablename__ = "attribution_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ---------- 归因规则默认值（首次启动写入，运营可在后台改） ----------
DEFAULT_ATTRIBUTION_RULES = [
    ("session_window_minutes", "30", "R1 强归因时间窗：来电时间往前推 N 分钟内有过官网活动，才算同一会话"),
    ("phone_lookback_days", "7", "R3 手机号回溯窗口：来电号码在 N 天内有官网访问记录才可归因"),
    ("bot_filter_enabled", "1", "是否过滤爬虫/监控流量（1=过滤，不计入分母）"),
    ("min_visit_seconds", "3", "有效访问最短停留秒数，低于此值不计入归因分母（防误点）"),
    ("max_time_gap_seconds", "86400", "R1 命中后允许记录的最大时间差，超出则降级为渠道级"),
]
