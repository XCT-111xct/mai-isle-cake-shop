# ============================================================
# 文件功能：后台留言管理（技术开发文档 §5.3.8）
#   列表/详情/状态切换/删除（后台不可新增留言，不提供 POST）
# ============================================================

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Message
from app.schemas import MessageStatusUpdate
from app.utils.response import not_found, ok

router = APIRouter()


def mask_phone(phone: str) -> str:
    if len(phone) == 11:
        return phone[:3] + "****" + phone[7:]
    return phone


@router.get("/messages", summary="留言列表")
def list_messages(
    status: str | None = Query(None, description="pending/done"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """留言列表：status 筛选 + 分页；手机号脱敏"""
    q = db.query(Message)
    if status:
        q = q.filter(Message.status == status)
    q = q.order_by(Message.created_at.desc(), Message.id.desc())

    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": m.id,
            "name": m.name,
            "phone": mask_phone(m.phone),
            "content": m.content,
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in rows
    ]
    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    })


@router.get("/messages/{message_id}", summary="留言详情")
def get_message(message_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """留言详情：完整内容 + 完整手机号"""
    msg = db.get(Message, message_id)
    if not msg:
        raise not_found("留言不存在")
    return ok({
        "id": msg.id,
        "name": msg.name,
        "phone": msg.phone,
        "content": msg.content,
        "status": msg.status,
        "created_at": msg.created_at.isoformat() if msg.created_at else None,
    })


@router.patch("/messages/{message_id}/status", summary="留言状态切换")
def update_message_status(
    message_id: int,
    payload: MessageStatusUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """留言状态：pending/done 双向切换"""
    msg = db.get(Message, message_id)
    if not msg:
        raise not_found("留言不存在")
    msg.status = payload.status
    db.commit()
    return ok({"id": msg.id, "status": msg.status})


@router.delete("/messages/{message_id}", summary="删除留言")
def delete_message(message_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """删除留言"""
    msg = db.get(Message, message_id)
    if not msg:
        raise not_found("留言不存在")
    db.delete(msg)
    db.commit()
    return ok(None, "success")
