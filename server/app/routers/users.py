# ============================================================
# 文件功能：后台管理员管理（技术开发文档 §5.3.9，仅超级管理员）
#   列表/新增/编辑/重置密码/启用停用/删除
#   保护规则：
#     - 所有接口 require_super（运营管理员 → 403/40300）
#     - 超管账号不可删除；系统至少保留 1 名超管
# ============================================================

from math import ceil

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_super
from app.models import AdminUser
from app.schemas import PasswordReset, UserCreate, UserStatusUpdate, UserUpdate
from app.security import hash_password
from app.utils.response import BizError, bad_request, conflict, not_found, ok

router = APIRouter()


def _super_count(db: Session) -> int:
    """当前启用超管数量（保护"至少保留 1 名超管"）"""
    return (
        db.query(func.count(AdminUser.id))
        .filter(AdminUser.role == "super", AdminUser.is_active == True)  # noqa: E712
        .scalar()
        or 0
    )


def _ensure_last_super(db: Session, user: AdminUser):
    """若操作为：停用/降级最后一名启用超管 → 40001"""
    if user.role == "super" and user.is_active:
        if _super_count(db) <= 1:
            raise bad_request("系统至少保留一名超级管理员")


@router.get("/users", summary="管理员列表（仅超管）")
def list_users(
    role: str | None = Query(None, description="super/ops"),
    page: int = Query(1, ge=1),
    page_size: int = Query(12, ge=1, le=50),
    current_user=Depends(require_super),
    db: Session = Depends(get_db),
):
    """管理员列表：角色筛选 + 分页（不返回密码哈希）"""
    q = db.query(AdminUser)
    if role:
        q = q.filter(AdminUser.role == role)
    q = q.order_by(AdminUser.id.asc())

    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()

    items = [
        {
            "id": u.id,
            "username": u.username,
            "name": u.name,
            "role": u.role,
            "is_active": bool(u.is_active),
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in rows
    ]
    return ok({
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size) if total else 0,
    })


@router.post("/users", summary="新增管理员（仅超管）")
def create_user(payload: UserCreate, current_user=Depends(require_super), db: Session = Depends(get_db)):
    """新增管理员：账号唯一（DB UNIQUE + 40900）"""
    if db.query(AdminUser).filter(AdminUser.username == payload.username.strip()).first():
        raise conflict("用户名已存在")
    user = AdminUser(
        username=payload.username.strip(),
        name=payload.name.strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return ok({"id": user.id})


@router.put("/users/{user_id}", summary="编辑管理员（仅超管）")
def update_user(
    user_id: int,
    payload: UserUpdate,
    current_user=Depends(require_super),
    db: Session = Depends(get_db),
):
    """编辑管理员：name/role/is_active（不含密码）"""
    user = db.get(AdminUser, user_id)
    if not user:
        raise not_found("管理员不存在")

    # 降级最后一名启用超管 → 拒绝
    if user.role == "super" and payload.role == "ops" and user.is_active:
        if _super_count(db) <= 1:
            raise bad_request("系统至少保留一名超级管理员")

    user.name = payload.name.strip()
    user.role = payload.role
    user.is_active = payload.is_active
    db.commit()
    return ok({"id": user.id})


@router.patch("/users/{user_id}/password", summary="重置密码（仅超管）")
def reset_password(
    user_id: int,
    payload: PasswordReset,
    current_user=Depends(require_super),
    db: Session = Depends(get_db),
):
    """重置密码：new_password 6-20 位"""
    user = db.get(AdminUser, user_id)
    if not user:
        raise not_found("管理员不存在")
    user.password_hash = hash_password(payload.new_password)
    # 重置失败计数与锁定（密码已改，旧的锁定状态应解除）
    user.failed_attempts = 0
    user.locked_until = None
    db.commit()
    return ok(None, "success")


@router.patch("/users/{user_id}/status", summary="启用/停用（仅超管）")
def update_user_status(
    user_id: int,
    payload: UserStatusUpdate,
    current_user=Depends(require_super),
    db: Session = Depends(get_db),
):
    """启用/停用管理员（停用最后一名启用超管 → 拒绝）"""
    user = db.get(AdminUser, user_id)
    if not user:
        raise not_found("管理员不存在")

    # 停用启用超管时检查末位保护
    if user.role == "super" and user.is_active and not payload.is_active:
        if _super_count(db) <= 1:
            raise bad_request("系统至少保留一名超级管理员")

    user.is_active = payload.is_active
    db.commit()
    return ok({"id": user.id, "is_active": bool(user.is_active)})


@router.delete("/users/{user_id}", summary="删除管理员（仅超管）")
def delete_user(user_id: int, current_user=Depends(require_super), db: Session = Depends(get_db)):
    """删除管理员：超管账号不可删除（40001）；不能删除自己（避免自锁）"""
    user = db.get(AdminUser, user_id)
    if not user:
        raise not_found("管理员不存在")
    if user.role == "super":
        raise bad_request("超级管理员账号不可删除")
    if user.id == current_user.id:
        raise bad_request("不能删除当前登录账号")
    db.delete(user)
    db.commit()
    return ok(None, "success")
