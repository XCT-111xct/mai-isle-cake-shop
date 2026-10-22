# ============================================================
# 文件功能：仪表盘统计接口（技术开发文档 §5.3.2 + Q2 已确认）
#   GET /api/v1/admin/dashboard/stats
#   实时计算（无缓存）：统计卡 + 最近订单 + 状态分布 + 最近留言
# ============================================================

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Cake, Message, Order, Store
from app.utils.response import ok

router = APIRouter()

# 手机号脱敏：中间 4 位掩码（技术文档 §5.1.6）
def mask_phone(phone: str) -> str:
    if len(phone) == 11:
        return phone[:3] + "****" + phone[7:]
    return phone


@router.get("/dashboard/stats", summary="仪表盘统计")
def dashboard_stats(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """统计卡 ×4 + 最近订单 + 状态分布 + 最近留言（Q2 已确认）"""
    now = datetime.now()
    month_prefix = now.strftime("%Y-%m")

    # ---- 统计卡 ----
    cake_count = db.query(func.count(Cake.id)).scalar() or 0
    month_order_count = (
        db.query(func.count(Order.id))
        .filter(func.strftime("%Y-%m", Order.created_at) == month_prefix)
        .scalar()
        or 0
    )
    store_count = (
        db.query(func.count(Store.id)).filter(Store.is_active == True).scalar() or 0  # noqa: E712
    )
    pending_message_count = (
        db.query(func.count(Message.id)).filter(Message.status == "pending").scalar() or 0
    )

    # ---- 最近订单（10 笔，created_at 倒序，cake_name 取快照） ----
    recent_orders = (
        db.query(Order).order_by(Order.created_at.desc()).limit(10).all()
    )
    recent_order_list = []
    for o in recent_orders:
        try:
            snap = json.loads(o.cake_snapshot)
            cake_name = snap.get("cake_name", "")
        except (json.JSONDecodeError, TypeError):
            cake_name = ""
        recent_order_list.append({
            "id": o.id,
            "order_no": o.order_no,
            "customer_name": o.customer_name,
            "cake_name": cake_name,
            "amount": float(o.amount),
            "status": o.status,
        })

    # ---- 订单状态分布 ----
    status_rows = (
        db.query(Order.status, func.count(Order.id))
        .group_by(Order.status)
        .all()
    )
    distribution = {"pending": 0, "confirmed": 0, "completed": 0, "cancelled": 0}
    for status, cnt in status_rows:
        if status in distribution:
            distribution[status] = cnt

    # ---- 最近留言（Q2：最近 5 条，id/name/phone 脱敏/内容预览/status/created_at） ----
    recent_messages = (
        db.query(Message).order_by(Message.created_at.desc()).limit(5).all()
    )
    recent_message_list = [
        {
            "id": m.id,
            "name": m.name,
            "phone": mask_phone(m.phone),
            "content_preview": m.content[:50],
            "status": m.status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in recent_messages
    ]

    return ok({
        "cake_count": cake_count,
        "month_order_count": month_order_count,
        "store_count": store_count,
        "pending_message_count": pending_message_count,
        "recent_orders": recent_order_list,
        "order_status_distribution": distribution,
        "recent_messages": recent_message_list,
    })
