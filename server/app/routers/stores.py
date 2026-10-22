# ============================================================
# 文件功能：后台门店管理（技术开发文档 §5.3.6）
#   列表/新增/编辑/删除/启用停用（含 image_url，Q1 已确认）
# ============================================================

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Store
from app.schemas import StoreCreate, StoreStatusUpdate
from app.utils.response import bad_request, not_found, ok

router = APIRouter()


@router.get("/stores", summary="门店列表")
def list_stores(
    keyword: str | None = Query(None, description="按名称/地址搜索"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """门店列表：分页 + 关键字搜索（含停用门店，后台可见全部）"""
    q = db.query(Store)
    if keyword:
        kw = keyword.strip()
        q = q.filter((Store.name.contains(kw)) | (Store.address.contains(kw)))
    q = q.order_by(Store.sort_order.asc(), Store.id.asc())

    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": s.id,
            "name": s.name,
            "address": s.address,
            "phone": s.phone,
            "hours": s.hours or "",
            "image_url": s.image_url or "",
            "sort_order": s.sort_order,
            "is_active": bool(s.is_active),
        }
        for s in rows
    ]
    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    })


@router.post("/stores", summary="新增门店")
def create_store(payload: StoreCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """新增门店（名称可重复，无唯一约束）"""
    store = Store(
        name=payload.name.strip(),
        address=payload.address.strip(),
        phone=payload.phone.strip(),
        hours=payload.hours,
        image_url=payload.image_url,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
    )
    db.add(store)
    db.commit()
    db.refresh(store)
    return ok({"id": store.id})


@router.put("/stores/{store_id}", summary="编辑门店")
def update_store(
    store_id: int,
    payload: StoreCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑门店：整体覆盖"""
    store = db.get(Store, store_id)
    if not store:
        raise not_found("门店不存在")
    store.name = payload.name.strip()
    store.address = payload.address.strip()
    store.phone = payload.phone.strip()
    store.hours = payload.hours
    store.image_url = payload.image_url
    store.sort_order = payload.sort_order
    store.is_active = payload.is_active
    db.commit()
    return ok({"id": store.id})


@router.delete("/stores/{store_id}", summary="删除门店")
def delete_store(store_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """删除门店（直接删除，无产品关联）"""
    store = db.get(Store, store_id)
    if not store:
        raise not_found("门店不存在")
    db.delete(store)
    db.commit()
    return ok(None, "success")


@router.patch("/stores/{store_id}/status", summary="门店启用/停用")
def update_store_status(
    store_id: int,
    payload: StoreStatusUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """启用/停用门店"""
    store = db.get(Store, store_id)
    if not store:
        raise not_found("门店不存在")
    store.is_active = payload.is_active
    db.commit()
    return ok({"id": store.id, "is_active": bool(store.is_active)})
