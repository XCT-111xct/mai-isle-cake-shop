# ============================================================
# 文件功能：认证与权限依赖注入（技术开发文档 §7.5）
# 说明：
#   get_current_user  ：解析 JWT → 返回当前用户（失败抛 401/40100）
#   require_super     ：仅超级管理员可访问（用户管理模块）
#   get_db            ：请求级数据库会话（在 database.py）
# ============================================================

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AdminUser
from app.security import decode_token
from app.utils.response import BizError, forbidden, unauthorized

# auto_error=False：不自动返回 401，交给 get_current_user 统一处理
bearer = HTTPBearer(auto_error=False)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AdminUser:
    """解析 JWT → 返回当前用户；失败抛 401/40100"""
    if not cred:
        raise unauthorized("未登录")
    payload = decode_token(cred.credentials)
    if payload is None:
        raise unauthorized("登录已过期，请重新登录")
    user = db.get(AdminUser, int(payload["sub"]))
    # 用户被删除或停用 → 视为登录失效
    if not user or not user.is_active:
        raise unauthorized("登录已过期，请重新登录")
    return user


def require_super(user: AdminUser = Depends(get_current_user)) -> AdminUser:
    """仅超管可访问（用户管理模块）；运营管理员访问 → 403/40300"""
    if user.role != "super":
        raise forbidden("权限不足")
    return user
