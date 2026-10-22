# ============================================================
# 文件功能：后台订单管理（技术开发文档 §5.3.5 / §4.5 状态机）
#   列表/新增/详情/编辑/状态流转
#   要点：订单保存产品快照；金额 Decimal 自动计算；状态机后端强制校验
# ============================================================

import json
from decimal import Decimal
from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Cake, Order, utcnow
from app.schemas import OrderCreate, OrderStatusUpdate
from app.utils.order_no import gen_order_no
from app.utils.response import BizError, bad_request, not_found, ok

router = APIRouter()


def mask_phone(phone: str) -> str:
    """手机号脱敏：138****6321（技术文档 §5.1.6）"""
    if len(phone) == 11:
        return phone[:3] + "****" + phone[7:]
    return phone


def build_snapshot(cake: Cake, spec_name: str) -> dict:
    """生成订单快照：{cake_id, cake_name, spec_name, price}（技术文档 §7.8）

    金额一律 Decimal 计算（价格来自 NUMERIC 列，避免浮点误差）。
    产品必须上架，否则抛 40001"产品已下架"。
    """
    if not cake.is_active:
        raise bad_request("产品已下架")
    spec = next((s for s in cake.specs if s.name == spec_name), None)
    if not spec:
        raise bad_request("所选规格不存在")
    price = Decimal(str(spec.price))
    return {
        "cake_id": cake.id,
        "cake_name": cake.name,
        "spec_name": spec.name,
        "price": price,
    }


def parse_snapshot(order: Order) -> dict:
    """解析订单快照 JSON（容错返回空 dict）"""
    try:
        return json.loads(order.cake_snapshot)
    except (json.JSONDecodeError, TypeError):
        return {}


# ============================================================
# ① 订单列表
# ============================================================
@router.get("/orders", summary="订单列表")
def list_orders(
    keyword: str | None = Query(None, description="客户姓名/订单号 模糊搜索"),
    status: str | None = Query(None, description="pending/confirmed/completed/cancelled"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """订单列表：customer_phone 脱敏；cake_name/spec_name 取快照"""
    q = db.query(Order)
    if keyword:
        kw = keyword.strip()
        q = q.filter(
            (Order.customer_name.contains(kw)) | (Order.order_no.contains(kw))
        )
    if status:
        q = q.filter(Order.status == status)

    q = q.order_by(Order.created_at.desc(), Order.id.desc())
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = []
    for o in rows:
        snap = parse_snapshot(o)
        items.append({
            "id": o.id,
            "order_no": o.order_no,
            "customer_name": o.customer_name,
            "customer_phone": mask_phone(o.customer_phone),
            "cake_name": snap.get("cake_name", ""),
            "spec_name": snap.get("spec_name", ""),
            "quantity": o.quantity,
            "amount": float(o.amount),
            "pickup_type": o.pickup_type,
            "status": o.status,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        })
    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    })


# ============================================================
# ② 新增订单
# ============================================================
@router.post("/orders", summary="新增订单")
def create_order(payload: OrderCreate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """后台手动录入电话订单：
    1. 查产品+规格（必须上架）→ 生成快照
    2. amount = Decimal(快照价) × quantity（忽略前端任何 amount）
    3. 订单号 = YYYYMMDD + 当日 3 位序号
    """
    # 配送方式校验：delivery 时地址必填
    if payload.pickup_type == "delivery" and not (payload.delivery_address or "").strip():
        raise bad_request("配送订单必须填写配送地址")

    cake = db.get(Cake, payload.cake_id)
    if not cake:
        raise bad_request("产品不存在")
    snap = build_snapshot(cake, payload.spec_name)

    amount = snap["price"] * Decimal(payload.quantity)
    order = Order(
        order_no=gen_order_no(db, utcnow()),
        customer_name=payload.customer_name.strip(),
        customer_phone=payload.customer_phone.strip(),
        cake_snapshot=json.dumps(
            {**snap, "price": float(snap["price"])},
            ensure_ascii=False,
        ),
        quantity=payload.quantity,
        amount=amount,
        pickup_type=payload.pickup_type,
        delivery_address=payload.delivery_address,
        custom_note=payload.custom_note,
        remark=payload.remark,
        status="pending",
    )
    db.add(order)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise BizError(500, 50000, "保存失败，请重试")
    db.refresh(order)
    return ok({
        "id": order.id,
        "order_no": order.order_no,
        "amount": float(order.amount),
        "status": order.status,
    })


# ============================================================
# ③ 订单详情
# ============================================================
@router.get("/orders/{order_id}", summary="订单详情")
def get_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """订单详情：完整信息（含快照、不脱敏手机号、备注）"""
    order = db.get(Order, order_id)
    if not order:
        raise not_found("订单不存在")
    snap = parse_snapshot(order)
    return ok({
        "id": order.id,
        "order_no": order.order_no,
        "customer_name": order.customer_name,
        "customer_phone": order.customer_phone,  # 详情不脱敏（有权限的后台用户）
        "cake_snapshot": snap,
        "quantity": order.quantity,
        "amount": float(order.amount),
        "pickup_type": order.pickup_type,
        "delivery_address": order.delivery_address,
        "custom_note": order.custom_note,
        "remark": order.remark,
        "status": order.status,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "updated_at": order.updated_at.isoformat() if order.updated_at else None,
    })


# ============================================================
# ④ 编辑订单
# ============================================================
@router.put("/orders/{order_id}", summary="编辑订单")
def update_order(
    order_id: int,
    payload: OrderCreate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑订单：
    - 已完成/已取消订单不可编辑（40001）
    - 修改产品/规格/数量 → 重新构建快照 + 重算金额
    - 仅改备注/地址等 → 保留原快照与金额
    """
    order = db.get(Order, order_id)
    if not order:
        raise not_found("订单不存在")
    if order.status in ("completed", "cancelled"):
        raise bad_request("该状态订单不可编辑")

    if payload.pickup_type == "delivery" and not (payload.delivery_address or "").strip():
        raise bad_request("配送订单必须填写配送地址")

    old_snap = parse_snapshot(order)
    # 判断产品/规格/数量是否变化
    product_changed = (
        old_snap.get("cake_id") != payload.cake_id
        or old_snap.get("spec_name") != payload.spec_name
        or order.quantity != payload.quantity
    )

    if product_changed:
        cake = db.get(Cake, payload.cake_id)
        if not cake:
            raise bad_request("产品不存在")
        snap = build_snapshot(cake, payload.spec_name)
        order.cake_snapshot = json.dumps(
            {**snap, "price": float(snap["price"])},
            ensure_ascii=False,
        )
        order.quantity = payload.quantity
        order.amount = snap["price"] * Decimal(payload.quantity)
    # else：仅更新基础信息，金额/快照不变

    order.customer_name = payload.customer_name.strip()
    order.customer_phone = payload.customer_phone.strip()
    order.pickup_type = payload.pickup_type
    order.delivery_address = payload.delivery_address
    order.custom_note = payload.custom_note
    order.remark = payload.remark

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise BizError(500, 50000, "保存失败，请重试")
    return ok({"id": order.id, "amount": float(order.amount)})


# ============================================================
# ⑤ 状态流转
# ============================================================
@router.patch("/orders/{order_id}/status", summary="订单状态流转")
def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """状态流转：严格按状态机（技术文档 §4.5）校验，非法流转 40001"""
    order = db.get(Order, order_id)
    if not order:
        raise not_found("订单不存在")

    allowed = Order.ALLOWED_TRANSITIONS.get(order.status, set())
    if payload.status not in allowed:
        raise bad_request(
            f"非法状态流转：{order.status} 不能直接变为 {payload.status}"
        )

    order.status = payload.status
    db.commit()
    return ok({"id": order.id, "status": order.status})
