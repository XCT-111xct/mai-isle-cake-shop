# ============================================================
# 文件功能：后台认证接口（技术开发文档 §5.3.1 / §7.6）
#   POST /login   登录（含 5 次错误锁 15 分钟）
#   POST /logout  登出（JWT 无状态，前端清 token 即可）
#   GET  /me      当前用户（刷新登录态 / 角色渲染菜单）
# ============================================================

from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.models import AdminUser, utcnow
from app.schemas import LoginRequest
from app.security import create_token, verify_password
from app.utils.captcha_gen import verify_captcha
from app.utils.response import BizError, ok, unauthorized

router = APIRouter()


def do_login(username: str, password: str, db: Session) -> dict:
    """登录核心逻辑（独立函数便于 pytest 单测，技术文档 §7.6）。

    锁定规则：
      - 用户不存在或密码错误：failed_attempts + 1
      - failed_attempts >= 5 → 锁定 15 分钟（locked_until）
      - 锁定期间返回 40103；到期自动解锁（重置 failed_attempts）
      - 停用账号返回 40102
    """
    user = db.query(AdminUser).filter_by(username=username).first()
    if not user:
        # 不区分"用户不存在/密码错误"，防账号枚举（技术文档 §7.10 #7 思路）
        raise BizError(401, 40101, "账号或密码错误")

    now = utcnow()

    # ---- 锁定校验 ----
    if user.locked_until and user.locked_until > now:
        raise BizError(401, 40103, "账号已锁定，请 15 分钟后再试")
    if user.locked_until and user.locked_until <= now:
        # 锁定到期：重置失败计数与锁定时间
        user.failed_attempts = 0
        user.locked_until = None

    # ---- 密码校验 ----
    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.LOGIN_MAX_FAIL:
            user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCK_MINUTES)
            db.commit()
            raise BizError(401, 40103, "账号已锁定，请 15 分钟后再试")
        db.commit()
        raise BizError(401, 40101, "账号或密码错误")

    # ---- 停用校验 ----
    if not user.is_active:
        raise BizError(401, 40102, "账号已停用")

    # ---- 成功：重置计数 + 记录登录时间 + 签发 JWT ----
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()

    token = create_token(user.id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {"id": user.id, "username": user.username, "name": user.name, "role": user.role},
    }


@router.post("/login", summary="管理员登录")
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """登录：先校验图形验证码（40002），再校验账号密码（40101/40102/40103）"""
    # ---- 验证码校验（在 do_login 之前，避免对错误密码账号泄露线索） ----
    # 开发演示模式（仅 settings.DEBUG=True 生效，生产 DEBUG=False 自动失效）：
    # 固定 DEMO/8888 直通，供 seed_demo.py 等本地演示脚本灌数据用
    is_demo = settings.DEBUG and payload.captcha_id == "DEMO" and payload.captcha == "8888"
    if not is_demo and verify_captcha(payload.captcha_id, payload.captcha) != "ok":
        raise BizError(400, 40002, "验证码错误或已过期，请重新输入")
    return ok(do_login(payload.username.strip(), payload.password, db))


@router.post("/logout", summary="管理员登出")
def logout():
    """JWT 无状态，服务端不维护黑名单（技术文档 §5.3.1）；前端清除本地 token 即可"""
    return ok(None, "success")


@router.get("/me", summary="当前登录用户")
def me(current_user: AdminUser = Depends(get_current_user)):
    """应用刷新后恢复登录态：校验 token + 返回角色渲染菜单"""
    return ok({
        "id": current_user.id,
        "username": current_user.username,
        "name": current_user.name,
        "role": current_user.role,
    })
