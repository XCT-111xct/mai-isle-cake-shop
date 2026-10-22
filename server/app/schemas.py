# ============================================================
# 文件功能：Pydantic 请求/响应模型（技术开发文档 §5）
# 说明：
#   1. 请求模型负责字段校验（规则与技术文档 §5 校验表一致）
#   2. 校验失败由 main.py 全局处理器统一转 400/40001
# ============================================================

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator

# ---------- 通用字段校验工具 ----------


def _check_name(v: str) -> str:
    """姓名/门店名等 2-20 字通用校验"""
    v = v.strip()
    if not (2 <= len(v) <= 20):
        raise ValueError("姓名需为 2-20 个字符")
    return v


def _check_phone(v: str) -> str:
    """11 位手机号校验"""
    import re

    v = v.strip()
    if not re.fullmatch(r"1[3-9]\d{9}", v):
        raise ValueError("请输入 11 位有效手机号")
    return v


# ============================================================
# 前台
# ============================================================

class MessageCreate(BaseModel):
    """提交留言（前台联系我们）"""

    name: str
    phone: str
    content: str
    captcha: str
    captcha_id: str

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 20):
            raise ValueError("姓名需为 2-20 个字符")
        return v

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str) -> str:
        import re

        v = v.strip()
        if not re.fullmatch(r"1[3-9]\d{9}", v):
            raise ValueError("请输入 11 位有效手机号")
        return v

    @field_validator("content")
    @classmethod
    def _v_content(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 500):
            raise ValueError("留言内容不能为空，且不超过 500 字")
        return v

    @field_validator("captcha")
    @classmethod
    def _v_captcha(cls, v: str) -> str:
        v = v.strip()
        if len(v) != 4:
            raise ValueError("验证码为 4 位字符")
        return v


# ============================================================
# 认证
# ============================================================

class LoginRequest(BaseModel):
    """后台登录"""

    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)
    captcha: str = Field(min_length=4, max_length=4, description="图形验证码（4 位）")
    captcha_id: str = Field(min_length=1, description="验证码 id（来自 X-Captcha-Id 响应头）")


# ============================================================
# 商品管理
# ============================================================

class SpecItem(BaseModel):
    """蛋糕规格（新增/编辑时传入）"""

    name: str
    price: Decimal

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 20):
            raise ValueError("规格名不超过 20 字")
        return v

    @field_validator("price")
    @classmethod
    def _v_price(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("价格需大于 0")
        # 两位小数校验：round 后不相等说明超过两位
        if v != v.quantize(Decimal("0.01")):
            raise ValueError("价格最多两位小数")
        return v


class CakeCreate(BaseModel):
    """新增商品"""

    name: str
    category_id: int
    specs: list[SpecItem] = Field(min_length=1, description="至少 1 个规格")
    description: Optional[str] = None
    image_url: str
    is_featured: bool = False
    is_active: bool = True
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 50):
            raise ValueError("产品名需为 2-50 个字符")
        return v

    @field_validator("description")
    @classmethod
    def _v_desc(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 2000:
            raise ValueError("描述不超过 2000 字")
        return v

    @field_validator("image_url")
    @classmethod
    def _v_image(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("请上传产品图")
        return v


class CakeStatusUpdate(BaseModel):
    """上下架"""

    is_active: bool


class CategoryCreate(BaseModel):
    """新增/编辑分类"""

    name: str
    sort_order: int = 0

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 30):
            raise ValueError("分类名需为 2-30 个字符")
        return v


# ============================================================
# 订单管理
# ============================================================

class OrderCreate(BaseModel):
    """新增订单（后台手动录入）"""

    customer_name: str
    customer_phone: str
    cake_id: int
    spec_name: str
    quantity: int = Field(ge=1, description="数量≥1")
    pickup_type: str
    delivery_address: Optional[str] = None
    custom_note: Optional[str] = None
    remark: Optional[str] = None

    @field_validator("customer_name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 20):
            raise ValueError("客户姓名需为 2-20 个字符")
        return v

    @field_validator("customer_phone")
    @classmethod
    def _v_phone(cls, v: str) -> str:
        import re

        v = v.strip()
        if not re.fullmatch(r"1[3-9]\d{9}", v):
            raise ValueError("请输入 11 位有效手机号")
        return v

    @field_validator("pickup_type")
    @classmethod
    def _v_pickup(cls, v: str) -> str:
        if v not in ("self", "delivery"):
            raise ValueError("取货方式不合法")
        return v

    @field_validator("custom_note")
    @classmethod
    def _v_note(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 500:
            raise ValueError("定制需求不超过 500 字")
        return v

    @field_validator("remark")
    @classmethod
    def _v_remark(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 500:
            raise ValueError("备注不超过 500 字")
        return v

    @field_validator("delivery_address")
    @classmethod
    def _v_addr(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 200:
            raise ValueError("配送地址不超过 200 字")
        return v


class OrderStatusUpdate(BaseModel):
    """订单状态流转"""

    status: str

    @field_validator("status")
    @classmethod
    def _v_status(cls, v: str) -> str:
        if v not in ("pending", "confirmed", "completed", "cancelled"):
            raise ValueError("订单状态不合法")
        return v


# ============================================================
# 门店管理
# ============================================================

class StoreCreate(BaseModel):
    """新增/编辑门店"""

    name: str
    address: str
    phone: str
    hours: Optional[str] = None
    image_url: Optional[str] = None
    sort_order: int = 0
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 30):
            raise ValueError("门店名需为 2-30 个字符")
        return v

    @field_validator("address")
    @classmethod
    def _v_addr(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 100):
            raise ValueError("地址不超过 100 字")
        return v

    @field_validator("phone")
    @classmethod
    def _v_phone(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 20):
            raise ValueError("电话不超过 20 字")
        return v

    @field_validator("hours")
    @classmethod
    def _v_hours(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) > 50:
            raise ValueError("营业时间不超过 50 字")
        return v


class StoreStatusUpdate(BaseModel):
    """门店启用/停用"""

    is_active: bool


# ============================================================
# 内容管理
# ============================================================

class ContentUpdate(BaseModel):
    """保存内容 key 的 value（JSON 对象或 Markdown 文本）"""

    value: object


class BannerItem(BaseModel):
    """单张 banner"""

    image_url: str
    slogan: Optional[str] = None
    subtitle: Optional[str] = None
    sort_order: int = 1
    is_active: bool = True

    @field_validator("image_url")
    @classmethod
    def _v_image(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("请上传 banner 图")
        return v


# ============================================================
# 留言管理
# ============================================================

class MessageStatusUpdate(BaseModel):
    """留言状态切换"""

    status: str

    @field_validator("status")
    @classmethod
    def _v_status(cls, v: str) -> str:
        if v not in ("pending", "done"):
            raise ValueError("留言状态不合法")
        return v


# ============================================================
# 管理员管理（仅超管）
# ============================================================

class UserCreate(BaseModel):
    """新增管理员"""

    username: str
    name: str
    password: str
    role: str = "ops"
    is_active: bool = True

    @field_validator("username")
    @classmethod
    def _v_username(cls, v: str) -> str:
        v = v.strip()
        if not (2 <= len(v) <= 50):
            raise ValueError("用户名需为 2-50 个字符")
        return v

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 50):
            raise ValueError("姓名需为 1-50 个字符")
        return v

    @field_validator("password")
    @classmethod
    def _v_password(cls, v: str) -> str:
        if not (6 <= len(v) <= 20):
            raise ValueError("密码需为 6-20 个字符")
        return v

    @field_validator("role")
    @classmethod
    def _v_role(cls, v: str) -> str:
        if v not in ("super", "ops"):
            raise ValueError("角色不合法")
        return v


class UserUpdate(BaseModel):
    """编辑管理员（不含密码）"""

    name: str
    role: str
    is_active: bool

    @field_validator("name")
    @classmethod
    def _v_name(cls, v: str) -> str:
        v = v.strip()
        if not (1 <= len(v) <= 50):
            raise ValueError("姓名需为 1-50 个字符")
        return v

    @field_validator("role")
    @classmethod
    def _v_role(cls, v: str) -> str:
        if v not in ("super", "ops"):
            raise ValueError("角色不合法")
        return v


class PasswordReset(BaseModel):
    """重置密码"""

    new_password: str

    @field_validator("new_password")
    @classmethod
    def _v_password(cls, v: str) -> str:
        if not (6 <= len(v) <= 20):
            raise ValueError("密码需为 6-20 个字符")
        return v


class UserStatusUpdate(BaseModel):
    """启用/停用管理员"""

    is_active: bool
