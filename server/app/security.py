# ============================================================
# 文件功能：认证与安全模块（技术开发文档 §7.5）
# 说明：
#   1. 密码哈希：passlib + bcrypt（固定 bcrypt 4.0.x，见 requirements.txt）
#   2. JWT：python-jose 签发 HS256，payload 含 sub/role/exp（签发后 30 分钟固定过期）
#   3. "30 分钟无操作失效"（滑动过期）由前端拦截器实现，后端不做会话续期
# ============================================================

from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from passlib.context import CryptContext

from app.config import settings

# ---------- 密码哈希 ----------
# deprecated="auto"：自动处理旧哈希格式
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """明文密码 → bcrypt 哈希（入库前调用）"""
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """校验明文密码与哈希是否匹配"""
    return pwd_context.verify(plain, hashed)


# ---------- JWT 签发与校验 ----------
def _now() -> datetime:
    """naive UTC 当前时间（JWT 用）"""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_token(user_id: int, role: str) -> str:
    """签发 JWT：payload { sub, role, exp }，exp = now + 30 分钟固定值"""
    expire = _now() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str):
    """解析 JWT → payload 字典；无效/过期返回 None（调用方抛 401）"""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except (JWTError, ExpiredSignatureError):
        return None
