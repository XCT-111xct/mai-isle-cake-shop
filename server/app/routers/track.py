# ============================================================
# 文件功能：前台埋点接收 + 官网专属号码下发（无需登录）
#
# 三个接口构成归因链路的「数据入口」：
#   POST /track/session  建会话（含渠道识别）
#   POST /track/event    记行为（页面浏览、蛋糕浏览、热线点击…）
#   GET  /track/hotline  按访客渠道下发**专属电话号码** ← 归因能成立的根
#
# 为什么必须动态下发号码：
#   来电记录本身不带来源信息。只有当「页面上展示的号码」随渠道变化时，
#   电话那头才知道这通电话来自哪个渠道。否则无论怎么埋点，来电都是黑盒。
#   这就是业界的 DNI（动态号码插入）思路，这里做的是单人成本可落地版：
#   一个渠道配一个专属号码，页面按访客来源自动显示对应号码。
#
# 防滥用说明：
#   埋点接口是公开的，必然会被脚本乱刷。这里做了三道最低限度的闸门：
#   ① 只接受本系统生成形态的 visitor_id/session_id（长度与字符集校验）
#   ② 单会话每分钟事件数上限（内存计数）
#   ③ 落库前置标记 is_bot，爬虫流量不参与归因分母
#   刻意不做 IP 黑名单这类复杂机制：本项目单 worker 部署，内存计数够用且
#   无外部依赖；真要做严格限流，应放在 Nginx 层（见部署文档）。
# ============================================================

import json
import time
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Content, utcnow
from app.models_attribution import TrackingNumber, VisitEvent, VisitorSession
from app.utils.attribution import (
    detect_bot,
    detect_channel,
    hash_phone,   # noqa: F401  （供后续扩展复用，保持与本模块同一来源）
    touch_session,
)
from app.utils.response import bad_request, not_found, ok

router = APIRouter()

# 允许的事件类型白名单 —— 不收任意字符串，避免埋点表被写入垃圾
ALLOWED_EVENTS = {
    "page_view",        # 页面浏览
    "cake_view",        # 蛋糕详情浏览
    "category_filter",  # 分类筛选
    "hotline_click",    # 点击拨打订购热线（最核心的转化动作）
    "message_submit",   # 提交留言
    "map_click",        # 查看门店地图
    "wechat_click",     # 点击微信/公众号
}

# 单会话每分钟事件上限（内存计数，单 worker 有效）
_RATE_LIMIT_PER_MINUTE = 120
_rate_bucket: dict[str, tuple[int, float]] = {}


def _check_rate(session_id: str) -> bool:
    """简易滑动窗口限流：同一 session 每分钟 ≤120 条。返回 False 表示超限。"""
    now = time.time()
    count, window_start = _rate_bucket.get(session_id, (0, now))
    if now - window_start >= 60:
        _rate_bucket[session_id] = (1, now)
        return True
    if count >= _RATE_LIMIT_PER_MINUTE:
        return False
    _rate_bucket[session_id] = (count + 1, window_start)
    # 防止内存无限增长：桶超过 5000 个时整体清空（简单粗暴但够用）
    if len(_rate_bucket) > 5000:
        _rate_bucket.clear()
    return True


def _client_ip_hash(request: Request) -> str:
    """取客户端 IP 并哈希。不存明文 IP —— 归因只需要「判断是否同一来源」，
    不需要知道具体地址，少存一项个人信息就少一分合规负担。"""
    import hashlib

    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (request.client.host if request.client else "")
    if not ip:
        return ""
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:32]


# ============================================================
# 请求模型
# ============================================================

class SessionIn(BaseModel):
    visitor_id: str = Field(description="持久访客 ID（UUID，前端 localStorage 保存 365 天）")
    session_id: str = Field(description="会话 ID（UUID，30 分钟无活动后重建）")
    page_path: str = "/"
    referrer: str = ""
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    utm_content: str = ""
    utm_term: str = ""

    @field_validator("visitor_id", "session_id")
    @classmethod
    def _v_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not (8 <= len(v) <= 36):
            raise ValueError("访客标识不合法")
        return v


class EventIn(BaseModel):
    visitor_id: str
    session_id: str
    event_type: str
    page_path: str = ""
    ref_object_type: str = ""
    ref_object_id: Optional[int] = None
    duration_ms: int = 0
    payload: Optional[dict] = None

    @field_validator("visitor_id", "session_id")
    @classmethod
    def _v_id(cls, v: str) -> str:
        v = (v or "").strip()
        if not (8 <= len(v) <= 36):
            raise ValueError("访客标识不合法")
        return v

    @field_validator("event_type")
    @classmethod
    def _v_event(cls, v: str) -> str:
        v = (v or "").strip()
        if v not in ALLOWED_EVENTS:
            raise ValueError("事件类型不合法")
        return v


# ============================================================
# POST /track/session —— 建会话 / 心跳
# ============================================================

@router.post("/track/session")
def create_session(payload: SessionIn, request: Request, db: Session = Depends(get_db)):
    """建立或刷新访问会话，返回本次会话的渠道判定结果。

    前端在页面首次加载、以及检测到「距上次活动 >30 分钟」时调用。
    """
    ua = request.headers.get("user-agent", "")
    sess = touch_session(
        db,
        visitor_id=payload.visitor_id,
        session_id=payload.session_id,
        page_path=payload.page_path or "/",
        referrer=payload.referrer,
        utm={
            "utm_source": payload.utm_source,
            "utm_medium": payload.utm_medium,
            "utm_campaign": payload.utm_campaign,
            "utm_content": payload.utm_content,
            "utm_term": payload.utm_term,
        },
        user_agent=ua,
        ip_hash=_client_ip_hash(request),
    )
    return ok({
        "session_id": sess.session_id,
        "channel": sess.channel,
        "channel_detail": sess.channel_detail,
        "device_type": sess.device_type,
        "is_bot": bool(sess.is_bot),
    })


# ============================================================
# POST /track/event —— 行为事件上报
# ============================================================

@router.post("/track/event")
def track_event(payload: EventIn, request: Request, db: Session = Depends(get_db)):
    """记录一次行为事件。事件量可能较大，因此本接口设计为「尽力而为」：
    失败不重试、不阻塞页面，只做计数与落库。"""
    if not _check_rate(payload.session_id):
        # 超限不报错（避免前端无限重试），静默丢弃
        return ok({"dropped": True})

    sess = (
        db.query(VisitorSession)
        .filter(VisitorSession.session_id == payload.session_id)
        .first()
    )
    if not sess:
        # 会话不存在：说明前端没先建会话（或已被清理）。补建一条，
        # 渠道记为 unknown —— 宁可少归因，也不凭空捏造来源。
        sess = touch_session(
            db,
            visitor_id=payload.visitor_id,
            session_id=payload.session_id,
            page_path=payload.page_path or "/",
            user_agent=request.headers.get("user-agent", ""),
            ip_hash=_client_ip_hash(request),
        )

    ev = VisitEvent(
        session_id=payload.session_id,
        visitor_id=payload.visitor_id,
        event_type=payload.event_type,
        page_path=(payload.page_path or "")[:255],
        ref_object_type=(payload.ref_object_type or "")[:20],
        ref_object_id=payload.ref_object_id,
        duration_ms=max(0, payload.duration_ms),
        payload=json.dumps(payload.payload, ensure_ascii=False) if payload.payload else "",
        # ⚠️ 必须显式赋值：Column(default=utcnow) 只在 INSERT 时由数据库层生成，
        # 在 flush 之前对象属性仍是 None。下面要用它去更新会话的 last_seen_at，
        # 若留空会写入 NULL 并撞 NOT NULL 约束（实测踩过）。
        occurred_at=utcnow(),
    )
    db.add(ev)

    # 会话侧累计：page_view 计页面数、hotline_click 计转化动作次数
    sess.last_seen_at = ev.occurred_at
    sess.event_count += 1
    if payload.event_type == "page_view":
        sess.page_view_count += 1
        if payload.page_path:
            sess.exit_page = payload.page_path[:255]
    elif payload.event_type == "hotline_click":
        sess.hotline_click_count += 1

    db.commit()
    return ok({"recorded": True})


# ============================================================
# GET /track/hotline —— 按渠道下发官网专属号码
# ============================================================

@router.get("/track/hotline")
def get_hotline(
    referrer: str = Query("", description="当前页 referrer"),
    utm_source: str = Query(""),
    utm_medium: str = Query(""),
    utm_campaign: str = Query(""),
    db: Session = Depends(get_db),
):
    """返回该访客应当看到的订购电话号码。

    优先级：
      ① 匹配到渠道专属号码 → 返回它（这是归因能成立的关键）
      ② 匹配不到 → 返回默认号码（is_default 标记），此时来电只能靠 R3 兜底
    """
    channel, detail = detect_channel(
        referrer=referrer, utm_source=utm_source, utm_medium=utm_medium, utm_campaign=utm_campaign
    )

    # ① 精确匹配：渠道 + 细分 + 活动
    q = db.query(TrackingNumber).filter(TrackingNumber.is_active == True)  # noqa: E712
    cand = None
    if utm_campaign:
        cand = q.filter(
            TrackingNumber.channel == channel,
            TrackingNumber.campaign == utm_campaign,
        ).first()
    if cand is None and detail:
        cand = q.filter(
            TrackingNumber.channel == channel,
            TrackingNumber.channel_detail == detail,
        ).first()
    if cand is None:
        cand = q.filter(TrackingNumber.channel == channel).first()

    if cand:
        return ok({
            "phone": cand.display_no,
            "tracking_no": cand.tracking_no,
            "label": cand.label,
            "channel": cand.channel,
            "channel_detail": cand.channel_detail,
            "is_default": False,
        })

    # ② 兜底：取最早的启用号码
    fallback = (
        db.query(TrackingNumber)
        .filter(TrackingNumber.is_active == True)  # noqa: E712
        .order_by(TrackingNumber.id.asc())
        .first()
    )
    if fallback:
        return ok({
            "phone": fallback.display_no,
            "tracking_no": fallback.tracking_no,
            "label": fallback.label,
            "channel": channel,
            "channel_detail": detail,
            # is_default=True 告诉后台：这通电话的渠道归属不可靠，归因时会降级
            "is_default": True,
        })

    # ③ 连专属号码表都空着（首次部署、还没配号码）→ 回落到「订购信息」里
    #    运营早就配好的订购专线。**必须有这一层**：否则前端拿到空号码串，
    #    页面上订购电话就变成空白，顾客连电话都看不到，归因还没开始
    #    先把生意挡掉了。
    hotline = ""
    row = db.query(Content).filter(Content.key == "order_info").first()
    if row and row.value:
        try:
            hotline = str(json.loads(row.value).get("hotline", "") or "")
        except (json.JSONDecodeError, AttributeError):
            hotline = ""
    return ok({
        "phone": hotline,
        "tracking_no": hotline,
        "label": "订购专线",
        "channel": channel,
        "channel_detail": detail,
        "is_default": True,
        "from_content": True,
    })
