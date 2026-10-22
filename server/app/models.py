# ============================================================
# 文件功能：ORM 模型（8 张表，与技术开发文档 §4.3 DDL 严格一致）
# 说明：
#   1. 字段与 DDL 一一对应，DDL 为最终准绳
#   2. 金额（price/amount）用 Numeric(10,2)，读取返回 Decimal，
#      计算一律 Decimal 避免浮点精度误差（技术文档 §7.8）
#   3. 时间统一存 naive UTC（helper: utcnow()）
# ============================================================

from datetime import datetime, timezone
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    """返回 naive UTC 当前时间。
    Python 3.12+ 弃用 datetime.utcnow()，用带时区的 now 去掉 tzinfo 替代。"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ============================================================
# 1. 管理员表 admin_user
# ============================================================
class AdminUser(Base):
    __tablename__ = "admin_user"
    __table_args__ = (
        CheckConstraint("role IN ('super', 'ops')", name="ck_admin_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 登录账号，唯一
    name: Mapped[str] = mapped_column(String(50), nullable=False)                  # 姓名
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)        # 密码哈希（bcrypt）
    role: Mapped[str] = mapped_column(String(10), nullable=False, default="ops")   # super=超管 ops=运营
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 1=启用 0=停用
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 连续密码错误次数
    locked_until: Mapped[Optional[datetime]] = mapped_column(DateTime)              # 锁定截止时间（NULL=未锁定）
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime)             # 最后登录时间
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ============================================================
# 2. 分类表 category
# ============================================================
class Category(Base):
    __tablename__ = "category"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # 分类名（2-30 字，唯一）
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 排序，越小越靠前
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)

    # 反向关系：分类下的蛋糕（删除分类用迁移方式，故 cake 外键无 CASCADE）
    cakes: Mapped[list["Cake"]] = relationship(back_populates="category")


# ============================================================
# 3. 蛋糕表 cake
# ============================================================
class Cake(Base):
    __tablename__ = "cake"
    __table_args__ = (
        # 与 DDL 索引对齐：分类筛选、上架+排序
        Index("idx_cake_category", "category_id"),
        Index("idx_cake_active_sort", "is_active", "sort_order"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)  # 产品名（2-50 字，唯一）
    category_id: Mapped[int] = mapped_column(ForeignKey("category.id"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)                     # 描述（≤2000 字）
    image_url: Mapped[str] = mapped_column(String(255), nullable=False)          # 产品图 URL
    is_featured: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 1=首页推荐
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)     # 1=上架 0=下架
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    category: Mapped["Category"] = relationship(back_populates="cakes")
    # 多规格：删除蛋糕时级联删除规格（DDL: ON DELETE CASCADE）
    specs: Mapped[list["CakeSpec"]] = relationship(
        back_populates="cake",
        cascade="all, delete-orphan",
        order_by="CakeSpec.sort_order",
    )


# ============================================================
# 4. 蛋糕规格表 cake_spec
# ============================================================
class CakeSpec(Base):
    __tablename__ = "cake_spec"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_spec_price_positive"),
        Index("idx_spec_cake", "cake_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cake_id: Mapped[int] = mapped_column(
        ForeignKey("cake.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(20), nullable=False)                 # 规格名（≤20 字）
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)        # 价格（>0，两位小数）
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cake: Mapped["Cake"] = relationship(back_populates="specs")


# ============================================================
# 5. 订单表 orders（电话订单，后台手动录入）
# ============================================================
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint("pickup_type IN ('self', 'delivery')", name="ck_order_pickup"),
        CheckConstraint(
            "status IN ('pending','confirmed','completed','cancelled')",
            name="ck_order_status",
        ),
        CheckConstraint("quantity >= 1", name="ck_order_quantity"),
        Index("idx_orders_status", "status"),
        Index("idx_orders_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_no: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)  # 订单号 YYYYMMDD+序号
    customer_name: Mapped[str] = mapped_column(String(20), nullable=False)          # 客户姓名（2-20 字）
    customer_phone: Mapped[str] = mapped_column(String(11), nullable=False)         # 联系电话（11 位）
    cake_snapshot: Mapped[str] = mapped_column(Text, nullable=False)                # JSON 快照
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)                  # 数量
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)         # 金额 = 快照价 × 数量
    pickup_type: Mapped[str] = mapped_column(String(10), nullable=False)            # self=自提 delivery=配送
    delivery_address: Mapped[Optional[str]] = mapped_column(String(200))            # 配送地址（配送时必填）
    custom_note: Mapped[Optional[str]] = mapped_column(String(500))                 # 定制需求（≤500 字）
    remark: Mapped[Optional[str]] = mapped_column(String(500))                      # 备注（≤500 字）
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    # 订单状态机（技术文档 §4.5）——后端 PATCH 强制校验
    ALLOWED_TRANSITIONS = {
        "pending": {"confirmed", "cancelled"},
        "confirmed": {"completed", "cancelled"},
        "completed": set(),
        "cancelled": set(),
    }


# ============================================================
# 6. 门店表 store
# ============================================================
class Store(Base):
    __tablename__ = "store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(30), nullable=False)        # 门店名（2-30 字）
    address: Mapped[str] = mapped_column(String(100), nullable=False)    # 地址（≤100 字）
    phone: Mapped[str] = mapped_column(String(20), nullable=False)       # 电话（≤20 字）
    hours: Mapped[Optional[str]] = mapped_column(String(50))             # 营业时间（≤50 字）
    image_url: Mapped[Optional[str]] = mapped_column(String(255))        # 门店图 URL（Q1 已确认，可空）
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # 1=启用 0=停用
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)


# ============================================================
# 7. 留言表 message（前台联系我们表单产生）
# ============================================================
class Message(Base):
    __tablename__ = "message"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'done')", name="ck_message_status"),
        Index("idx_message_status", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(20), nullable=False)        # 姓名（2-20 字）
    phone: Mapped[str] = mapped_column(String(11), nullable=False)       # 电话（11 位手机号）
    content: Mapped[str] = mapped_column(Text, nullable=False)           # 留言内容（1-500 字）
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="pending")  # pending=未处理 done=已处理
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)


# ============================================================
# 8. 内容表 content（key-value，前台内容区块）
# ============================================================
class Content(Base):
    __tablename__ = "content"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # 内容键（10 个 key）
    value: Mapped[str] = mapped_column(Text, nullable=False)                   # JSON 或 Markdown 文本
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow, onupdate=utcnow)

