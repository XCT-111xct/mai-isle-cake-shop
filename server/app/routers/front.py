# ============================================================
# 文件功能：前台接口（无需登录，技术开发文档 §5.2）
#   蛋糕列表/详情、分类、门店、内容区块、提交留言
# ============================================================

import json
from math import ceil
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cake, CakeSpec, Category, Content, Message, Store
from app.schemas import MessageCreate
from app.utils import publish as publish_svc
from app.utils.attribution import hash_phone, mask_phone
from app.utils.captcha_gen import verify_captcha
from app.utils.content_rules import ALL_KEYS, JSON_KEYS, MARKDOWN_KEYS, deserialize
from app.utils.response import BizError, bad_request, not_found, ok

router = APIRouter()


# ---------- 工具：最低规格价子查询 ----------
def price_from_subquery():
    """最低规格价子查询：按 sort_order 取最小，价格相同取第一个（技术文档 §5.2.1）"""
    return (
        select(CakeSpec.price)
        .where(CakeSpec.cake_id == Cake.id)
        .order_by(CakeSpec.sort_order.asc(), CakeSpec.price.asc())
        .limit(1)
        .scalar_subquery()
    )


# ============================================================
# 蛋糕列表 GET /api/v1/cakes
# ============================================================
@router.get("/cakes")
def list_cakes(
    category_id: int | None = Query(None, description="不传=全部；传=仅该分类上架产品"),
    featured: int | None = Query(None, description="1=仅首页推荐产品"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    sort: str = Query("recommend", description="recommend/price_asc/price_desc/newest"),
    db: Session = Depends(get_db),
):
    """蛋糕展示页产品网格：分类筛选 + 分页 + 四种排序（排序在 SQL 层完成）"""
    # 排序白名单校验
    if sort not in ("recommend", "price_asc", "price_desc", "newest"):
        raise bad_request("排序参数不合法")

    price_subq = price_from_subquery()
    q = db.query(Cake).add_columns(price_subq.label("price_from"))

    # 过滤条件：仅上架（前台永远看不到下架产品）
    q = q.filter(Cake.is_active == True)  # noqa: E712
    if category_id is not None:
        q = q.filter(Cake.category_id == category_id)
    if featured == 1:
        q = q.filter(Cake.is_featured == True)  # noqa: E712

    # 排序规则（技术文档 §5.2.1 排序表）
    if sort == "price_asc":
        q = q.order_by(price_subq.asc())
    elif sort == "price_desc":
        q = q.order_by(price_subq.desc())
    elif sort == "newest":
        q = q.order_by(Cake.created_at.desc())
    else:  # recommend 默认：sort_order 升序 → created_at 倒序
        q = q.order_by(Cake.sort_order.asc(), Cake.created_at.desc())

    # 分页
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": cake.id,
            "name": cake.name,
            "category": cake.category.name,
            "image_url": cake.image_url,
            "price_from": float(pf) if pf is not None else 0.0,
            "is_featured": bool(cake.is_featured),
        }
        for cake, pf in rows
    ]
    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    })


# ============================================================
# 蛋糕详情 GET /api/v1/cakes/{id}
# ============================================================
@router.get("/cakes/{cake_id}")
def get_cake(cake_id: int, db: Session = Depends(get_db)):
    """蛋糕详情：规格 + 相关推荐 + 定制说明；不存在或下架 → 404/40400"""
    cake = db.get(Cake, cake_id)
    # 产品不存在或已下架：详情不可访问（PRD F3）
    if not cake or not cake.is_active:
        raise not_found("产品不存在或已下架")

    # 规格按 sort_order 升序（ORM relationship 已 order_by）
    specs = [
        {"name": s.name, "price": float(s.price)}
        for s in cake.specs
    ]

    # 相关推荐：同分类其他上架产品，最多 4 个（同样带最低价）
    price_subq = price_from_subquery()
    related_rows = (
        db.query(Cake)
        .add_columns(price_subq.label("price_from"))
        .filter(
            Cake.category_id == cake.category_id,
            Cake.id != cake.id,
            Cake.is_active == True,  # noqa: E712
        )
        .order_by(Cake.sort_order.asc())
        .limit(4)
        .all()
    )
    related = [
        {
            "id": c.id,
            "name": c.name,
            "price_from": float(pf) if pf is not None else 0.0,
            "image_url": c.image_url,
        }
        for c, pf in related_rows
    ]

    # 定制说明：来自 content.key='custom_tips'，空则返回 ""
    custom_tips = ""
    ct = db.query(Content).filter(Content.key == "custom_tips").first()
    if ct and ct.value:
        custom_tips = ct.value

    return ok({
        "id": cake.id,
        "name": cake.name,
        "category": cake.category.name,
        "description": cake.description or "",
        "image_url": cake.image_url,
        "specs": specs,
        "related": related,
        "custom_tips": custom_tips,
    })


# ============================================================
# 分类列表 GET /api/v1/categories
# ============================================================
@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """分类导航（含各分类上架产品数角标）；无产品分类也返回（count=0）"""
    from sqlalchemy import func

    # outerjoin：没有产品的分类也要返回（count=0）
    rows = (
        db.query(
            Category.id,
            Category.name,
            func.count(Cake.id).label("cnt"),
        )
        .outerjoin(Cake, (Cake.category_id == Category.id) & (Cake.is_active == True))  # noqa: E712
        .group_by(Category.id, Category.name)
        .order_by(Category.sort_order.asc())
        .all()
    )
    items = [{"id": r.id, "name": r.name, "count": r.cnt} for r in rows]
    return ok({"items": items})


# ============================================================
# 门店列表 GET /api/v1/stores
# ============================================================
@router.get("/stores")
def list_stores(db: Session = Depends(get_db)):
    """门店信息：仅启用，按 sort_order 升序（首页概览取前 3 条由前端截取）"""
    stores = (
        db.query(Store)
        .filter(Store.is_active == True)  # noqa: E712
        .order_by(Store.sort_order.asc(), Store.id.asc())
        .all()
    )
    items = [
        {
            "id": s.id,
            "name": s.name,
            "address": s.address,
            "phone": s.phone,
            "hours": s.hours or "",
            "image_url": s.image_url or "",
        }
        for s in stores
    ]
    return ok({"items": items})


# ============================================================
# 内容区块 GET /api/v1/content/{key}
# ============================================================
@router.get("/content/{key}")
def get_content(
    key: str,
    preview_token: Optional[str] = Query(None, description="预览令牌（后台生成，仅返回草稿内容）"),
    db: Session = Depends(get_db),
):
    """读取前台内容区块：JSON keys 解析为对象；Markdown keys 原样返回文本。

    预览语义（重要）：
      带合法 preview_token 时返回**草稿内容**，并标记 preview=true；
      token 非法/过期/超次时**降级返回线上内容**，并标记 preview=false。
      为什么不直接报错：预览链接过期是常态（默认 30 分钟），报错会让预览者
      只看到空白页而不知道发生了什么；降级 + 明确标记，前台可以横条提示
      「预览已失效，当前显示线上内容」，既不误导也不打断。
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")

    # ---------- 预览通道 ----------
    if preview_token:
        ver = publish_svc.resolve_preview_token(db, preview_token, key)
        if ver is not None:
            return ok({
                "key": key,
                "value": deserialize(key, ver.value),
                "preview": True,
                "preview_version": ver.version,
            })

    # ---------- 线上通道（也作为预览失效后的降级路径） ----------
    row = db.query(Content).filter(Content.key == key).first()
    if not row:
        # 记录不存在：按 key 类型返回空默认值（前端区块隐藏规则）
        value: object = {} if key in JSON_KEYS else ""
    else:
        value = row.value
        if key in JSON_KEYS:
            try:
                value = json.loads(row.value)
            except json.JSONDecodeError:
                value = {}

    # banners 特例：历史数据可能存 {"banners": [...]} 或裸数组，统一返回对象（技术文档 §5.2.5）
    if key == "banners" and isinstance(value, list):
        value = {"banners": value}

    return ok({
        "key": key,
        "value": value,
        "preview": False,
        "preview_invalid": bool(preview_token),   # 带了 token 却没生效 → 前台提示预览已失效
    })


# ============================================================
# 提交留言 POST /api/v1/messages
# ============================================================
@router.post("/messages")
def create_message(payload: MessageCreate, db: Session = Depends(get_db)):
    """联系我们留言提交：先字段格式（Pydantic 40001），后验证码（40002）"""
    # 验证码校验（一次性：无论结果如何都被删除，前端必须刷新）
    result = verify_captcha(payload.captcha_id, payload.captcha)
    if result == "expired":
        raise BizError(400, 40002, "验证码已过期，请重新输入")
    if result == "wrong":
        raise BizError(400, 40002, "验证码错误，请重新输入")

    msg = Message(
        name=payload.name.strip(),
        phone=payload.phone.strip(),
        content=payload.content.strip(),
        status="pending",
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)

    # ---------- 归因：建立「手机号 ↔ 访客」绑定 ----------
    # 这是 R3 跨设备归因的唯一可靠入口：用户主动填了手机号，我们才知道
    # 「这个号码对应屏幕前的这个人」。绑上之后，该号码来电即可精确归因。
    #
    # ⚠️ 必须容错：留言是主业务，归因是附属能力。绑定失败**绝不能**让
    #    用户看到「提交失败」——他明明已经留言成功了。
    if payload.visitor_id:
        try:
            _bind_visitor_identity(db, payload.visitor_id, payload.phone)
        except Exception:
            db.rollback()   # 只回滚失败的绑定，留言已经提交过了

    return ok({"id": msg.id})


def _bind_visitor_identity(db: Session, visitor_id: str, phone: str) -> None:
    """把访客与手机号绑定（幂等：同一对 visitor+phone 只存一条）"""
    from app.models_attribution import VisitorIdentity

    ph = hash_phone(phone)
    if not ph:
        return
    exists = (
        db.query(VisitorIdentity)
        .filter(
            VisitorIdentity.visitor_id == visitor_id,
            VisitorIdentity.phone_hash == ph,
        )
        .first()
    )
    if exists:
        return
    db.add(VisitorIdentity(
        visitor_id=visitor_id,
        phone_hash=ph,
        phone_mask=mask_phone(phone),
        bind_source="message",
    ))
    db.commit()

