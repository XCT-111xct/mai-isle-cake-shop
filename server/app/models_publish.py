# ============================================================
# 文件功能：内容版本化发布 ORM 模型（3 张表）
#
# 为什么需要这三张表（现状问题）：
#   原实现 PUT /content/{key} 直接把新值写进 content.value，**前台下一次
#   拉取就立刻生效**。这意味着运营改错一个 Banner、删错一段品牌故事，
#   顾客立刻就看到，而且**没有任何东西能还原**——没有历史快照，只能靠人
#   回忆重打一遍。这是纯展示型官网最要命的风险：它的价值 100% 来自内容。
#
# 三条核心约定：
#   1. **content.value 仍是前台唯一读取源**（向前兼容，前台业务代码零改动）。
#      发布 = 把某个版本的值写进 content.value；回滚 = 把旧版本的副本写成新版本
#      再写进 content.value。前台完全不知道版本系统的存在。
#   2. **版本只追加，绝不覆盖或删除**。回滚不是「把指针拨回去」，而是
#      「用旧内容创建一个新版本」。这样任意一次回滚本身也可被回滚，且审计
#      日志里能看出「谁在什么时候回滚到了哪一版」。
#   3. 同一 key 最多一个 is_current=1。发布/回滚是单事务：更新版本状态 +
#      更新 content.value + 写审计日志，三步要么全成要么全败。
# ============================================================

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String,
    Text,
    Integer,
    Boolean,
    DateTime,
    CheckConstraint,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models import utcnow


# ============================================================
# 1. 内容版本表 content_version
#    每次「保存草稿」产生一条 draft；发布后转 published；被新版本取代后
#    转 superseded；作为回滚目标被采用后，新版本标记 rolled_back（来源标识）。
# ============================================================
class ContentVersion(Base):
    __tablename__ = "content_version"
    __table_args__ = (
        UniqueConstraint("key", "version", name="uq_version_key_ver"),
        CheckConstraint(
            "status IN ('draft','published','superseded','rolled_back')",
            name="ck_version_status",
        ),
        Index("idx_version_key_ver", "key", "version"),
        Index("idx_version_current", "key", "is_current"),
        Index("idx_version_status", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(30), nullable=False)          # 内容 key
    version: Mapped[int] = mapped_column(Integer, nullable=False)         # 同一 key 内自增，从 1 开始
    value: Mapped[str] = mapped_column(Text, nullable=False)              # 完整快照（JSON 或 Markdown 原文）
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")  # SHA256，判重用

    status: Mapped[str] = mapped_column(String(15), nullable=False, default="draft")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)   # 1=当前线上版本

    change_summary: Mapped[str] = mapped_column(String(200), nullable=False, default="")  # 变更说明（发布必填）
    based_on_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)     # 基于哪个版本改的（乐观锁）
    rollback_from_version: Mapped[Optional[int]] = mapped_column(Integer)                 # 回滚来源版本号

    created_by_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    published_by_id: Mapped[Optional[int]] = mapped_column(Integer)
    published_by_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime)

    # 下线标记：某 key 被主动下线时，当前版本打上此标记，前台回落到隐藏区块
    is_offline: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ============================================================
# 2. 发布操作审计日志 content_publish_log
#    只记「发生了什么动作」，不存内容本身（内容在版本表里）。
#    失败也要留痕——失败的发布尝试恰恰是最需要复盘的（比如并发冲突被拒）。
# ============================================================
class ContentPublishLog(Base):
    __tablename__ = "content_publish_log"
    __table_args__ = (
        CheckConstraint(
            "action IN ('save_draft','preview','publish','rollback','offline','online')",
            name="ck_publish_action",
        ),
        CheckConstraint("result IN ('success','failed')", name="ck_publish_result"),
        Index("idx_publish_key_time", "key", "created_at"),
        Index("idx_publish_action", "action", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(30), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    from_version: Mapped[Optional[int]] = mapped_column(Integer)
    to_version: Mapped[Optional[int]] = mapped_column(Integer)
    operator_id: Mapped[Optional[int]] = mapped_column(Integer)
    operator_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    reason: Mapped[str] = mapped_column(String(300), nullable=False, default="")   # 回滚原因必填
    result: Mapped[str] = mapped_column(String(10), nullable=False, default="success")
    error_msg: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ============================================================
# 3. 预览令牌表 content_preview_token
#    预览必须「看得到但改不了线上」，所以走一次性短效 token：
#    后台生成 token → 带 token 打开前台页面 → 前台请求内容时带上 token
#    → 后端校验后返回草稿值。token 与 key 强绑定，防止拿 A 的 token 看 B。
# ============================================================
class ContentPreviewToken(Base):
    __tablename__ = "content_preview_token"
    __table_args__ = (
        Index("idx_preview_token", "token"),
        Index("idx_preview_expire", "expires_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    key: Mapped[str] = mapped_column(String(30), nullable=False)          # 与内容 key 强绑定
    version_id: Mapped[int] = mapped_column(Integer, nullable=False)      # 指向被预览的草稿版本
    created_by_id: Mapped[Optional[int]] = mapped_column(Integer)
    created_by_name: Mapped[str] = mapped_column(String(50), nullable=False, default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=50)  # 允许多次刷新，但有上限
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ---------- 发布保护相关默认参数 ----------
DEFAULT_PUBLISH_SETTINGS = [
    ("preview_token_ttl_minutes", "30", "预览链接有效期（分钟），过期自动失效"),
    ("preview_token_max_uses", "50", "单个预览链接最多可被请求次数"),
    ("publish_requires_summary", "1", "发布时是否必填变更说明（1=必填）"),
    ("rollback_requires_reason", "1", "回滚时是否必填原因（1=必填）"),
]
