# ============================================================
# 文件功能：后台商品管理 + 分类管理（技术开发文档 §5.3.3 / §5.3.4）
#   商品：列表/新增/详情/编辑/上下架（无 DELETE——产品不支持删除）
#   分类：列表/新增/编辑/迁移删除（move_to_id 走 Query 参数）
# ============================================================

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Cake, CakeSpec, Category
from app.schemas import CakeCreate, CategoryCreate
from app.utils.response import BizError, bad_request, conflict, not_found, ok

router = APIRouter()


def _price_from_subquery():
    """最低规格价子查询（后台列表"起价"列）"""
    return (
        select(CakeSpec.price)
        .where(CakeSpec.cake_id == Cake.id)
        .order_by(CakeSpec.sort_order.asc(), CakeSpec.price.asc())
        .limit(1)
        .scalar_subquery()
    )


def _check_name_unique(db: Session, name: str, exclude_id: int | None = None):
    """商品/分类重名校验（40900）"""
    q = db.query(Cake).filter(Cake.name == name.strip())
    if exclude_id is not None:
        q = q.filter(Cake.id != exclude_id)
    if q.first():
        raise conflict("产品名称已存在，请更换")


# ============================================================
# 商品管理
# ============================================================

@router.get("/cakes", summary="商品列表")
def list_cakes(
    keyword: str | None = Query(None, description="按名称模糊搜索"),
    category_id: int | None = Query(None, description="按分类筛选"),
    is_active: int | None = Query(None, description="0=下架 1=上架（不传=全部）"),
    is_featured: int | None = Query(None, description="1=首页推荐"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """商品列表（含全部状态，区别于前台仅上架）"""
    price_subq = _price_from_subquery()
    q = db.query(Cake).add_columns(price_subq.label("price_from"))

    if keyword:
        q = q.filter(Cake.name.contains(keyword.strip()))
    if category_id is not None:
        q = q.filter(Cake.category_id == category_id)
    if is_active is not None:
        q = q.filter(Cake.is_active == bool(is_active))
    if is_featured == 1:
        q = q.filter(Cake.is_featured == True)  # noqa: E712

    q = q.order_by(Cake.sort_order.asc(), Cake.id.asc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": cake.id,
            "name": cake.name,
            "category": cake.category.name,
            "category_id": cake.category_id,
            "image_url": cake.image_url,
            "spec_count": len(cake.specs),
            "price_from": float(pf) if pf is not None else 0.0,
            "sort_order": cake.sort_order,
            "is_featured": bool(cake.is_featured),
            "is_active": bool(cake.is_active),
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


@router.post("/cakes", summary="新增商品")
def create_cake(payload: CakeCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """新增商品：cake + specs 同一事务写入（任一失败整体回滚）"""
    # 分类必须存在
    if not db.get(Category, payload.category_id):
        raise bad_request("分类不存在")
    # 重名校验（DB UNIQUE 兜底 + 应用层友好提示）
    _check_name_unique(db, payload.name)

    cake = Cake(
        name=payload.name.strip(),
        category_id=payload.category_id,
        description=payload.description,
        image_url=payload.image_url.strip(),
        is_featured=payload.is_featured,
        is_active=payload.is_active,
        sort_order=payload.sort_order,
    )
    db.add(cake)
    db.flush()  # 先拿到 cake.id

    for i, spec in enumerate(payload.specs):
        db.add(CakeSpec(
            cake_id=cake.id,
            name=spec.name.strip(),
            price=spec.price,
            sort_order=i,
        ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise BizError(500, 50000, "保存失败，请重试")
    db.refresh(cake)
    return ok({"id": cake.id})


@router.get("/cakes/{cake_id}", summary="商品详情（编辑回填）")
def get_cake(cake_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """商品详情：编辑回填用（含 specs + 全部管理字段）"""
    cake = db.get(Cake, cake_id)
    if not cake:
        raise not_found("产品不存在")
    return ok({
        "id": cake.id,
        "name": cake.name,
        "category_id": cake.category_id,
        "description": cake.description or "",
        "image_url": cake.image_url,
        "is_featured": bool(cake.is_featured),
        "is_active": bool(cake.is_active),
        "sort_order": cake.sort_order,
        "specs": [{"name": s.name, "price": float(s.price)} for s in cake.specs],
    })


@router.put("/cakes/{cake_id}", summary="编辑商品")
def update_cake(
    cake_id: int,
    payload: CakeCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑商品：规格整体覆盖（先删后插，同一事务）"""
    cake = db.get(Cake, cake_id)
    if not cake:
        raise not_found("产品不存在")
    if not db.get(Category, payload.category_id):
        raise bad_request("分类不存在")
    # 重名校验排除自身
    _check_name_unique(db, payload.name, exclude_id=cake_id)

    cake.name = payload.name.strip()
    cake.category_id = payload.category_id
    cake.description = payload.description
    cake.image_url = payload.image_url.strip()
    cake.is_featured = payload.is_featured
    cake.is_active = payload.is_active
    cake.sort_order = payload.sort_order

    # 规格整体覆盖：先删旧规格，再写新规格（事务内）
    db.query(CakeSpec).filter(CakeSpec.cake_id == cake_id).delete()
    for i, spec in enumerate(payload.specs):
        db.add(CakeSpec(
            cake_id=cake_id,
            name=spec.name.strip(),
            price=spec.price,
            sort_order=i,
        ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise BizError(500, 50000, "保存失败，请重试")
    return ok({"id": cake.id})


@router.patch("/cakes/{cake_id}/status", summary="商品上下架")
def update_cake_status(
    cake_id: int,
    payload: dict,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """上下架：仅允许 { is_active: bool } 一个字段（无 DELETE——产品不支持删除）"""
    is_active = payload.get("is_active")
    if not isinstance(is_active, bool):
        raise bad_request("is_active 必须为布尔值")
    cake = db.get(Cake, cake_id)
    if not cake:
        raise not_found("产品不存在")
    cake.is_active = is_active
    db.commit()
    return ok({"id": cake.id, "is_active": bool(cake.is_active)})


# ============================================================
# 分类管理
# ============================================================

@router.get("/categories", summary="全部分类（含产品总数）")
def list_categories(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """后台分类管理列表：含各分类产品总数（含下架）"""
    rows = (
        db.query(
            Category.id,
            Category.name,
            Category.sort_order,
            func.count(Cake.id).label("cnt"),
        )
        .outerjoin(Cake, Cake.category_id == Category.id)
        .group_by(Category.id)
        .order_by(Category.sort_order.asc())
        .all()
    )
    items = [
        {"id": r.id, "name": r.name, "sort_order": r.sort_order, "count": r.cnt}
        for r in rows
    ]
    return ok({"items": items})


@router.post("/categories", summary="新增分类")
def create_category(payload: CategoryCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """新增分类：重名 40900"""
    name = payload.name.strip()
    if db.query(Category).filter(Category.name == name).first():
        raise conflict("分类名称已存在，请更换")
    cat = Category(name=name, sort_order=payload.sort_order)
    db.add(cat)
    db.commit()
    db.refresh(cat)
    return ok({"id": cat.id})


@router.put("/categories/{category_id}", summary="编辑分类")
def update_category(
    category_id: int,
    payload: CategoryCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑分类：重名 40900（排除自身）"""
    cat = db.get(Category, category_id)
    if not cat:
        raise not_found("分类不存在")
    name = payload.name.strip()
    dup = (
        db.query(Category)
        .filter(Category.name == name, Category.id != category_id)
        .first()
    )
    if dup:
        raise conflict("分类名称已存在，请更换")
    cat.name = name
    cat.sort_order = payload.sort_order
    db.commit()
    return ok({"id": cat.id})


@router.delete("/categories/{category_id}", summary="删除分类（迁移）")
def delete_category(
    category_id: int,
    move_to_id: int | None = Query(None, description="该分类下产品迁移到的目标分类 id（Query 参数，不用 body）"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """删除分类：
    - 该分类下产品数 > 0 时，move_to_id 必填（产品迁移后删除）
    - 迁移约束：move_to_id 必须存在且 ≠ 自身
    - move_to_id 走 Query 参数（技术文档 §5.3.4：DELETE 带请求体可能被代理剥离）
    """
    cat = db.get(Category, category_id)
    if not cat:
        raise not_found("分类不存在")

    product_count = (
        db.query(func.count(Cake.id)).filter(Cake.category_id == category_id).scalar() or 0
    )

    if product_count > 0:
        if move_to_id is None:
            raise bad_request(f"该分类下有 {product_count} 个产品，请选择迁移目标分类")
        if move_to_id == category_id:
            raise bad_request("迁移目标分类不能是当前分类")
        target = db.get(Category, move_to_id)
        if not target:
            raise bad_request("迁移目标分类不存在")

    try:
        # 事务内：先迁移产品，再删除分类
        if product_count > 0:
            db.query(Cake).filter(Cake.category_id == category_id).update(
                {Cake.category_id: move_to_id}
            )
        db.delete(cat)
        db.commit()
    except Exception:
        db.rollback()
        raise BizError(500, 50000, "删除失败，请重试")
    return ok(None, "success")
