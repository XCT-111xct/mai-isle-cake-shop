# ============================================================
# 文件功能：FastAPI 应用入口（技术开发文档 §7.2 / §7.3）
#   1. 注册全部业务路由（前台 + 后台）
#   2. 全局异常处理（BizError / RequestValidationError / 兜底 500）
#   3. CORS + 静态图片目录 + 启动时建表
# ============================================================

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.database import init_db
from app.routers import (
    auth,
    cakes,
    captcha,
    content,
    dashboard,
    front,
    messages,
    orders,
    stores,
    upload,
    users,
)
from app.utils.response import BizError

# ---------- 启动/关闭事件 ----------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动：首次运行自动建表（幂等）
    init_db()
    yield
    # 关闭：暂无清理逻辑


# ---------- 创建 FastAPI 实例 ----------
# docs_url / redoc_url / openapi_url 三处控制"接口文档页"是否公开：
#   开发环境：开放，方便调试（FastAPI 默认行为）
#   生产环境：关闭，避免把全部接口清单、参数结构、字段说明对外公开
#            —— 这等于把后台管理系统的完整地图送给陌生人
app = FastAPI(
    title="麦屿手作 Mai-Isle API",
    version="1.0.0",
    description="麦屿手作蛋糕店官网前台 + 后台管理系统 API（技术开发文档 §5）",
    lifespan=lifespan,
    docs_url=None if settings.IS_PROD else "/docs",
    redoc_url=None if settings.IS_PROD else "/redoc",
    openapi_url=None if settings.IS_PROD else "/openapi.json",
)


# ---------- CORS 中间件 ----------
# 作用：允许"浏览器跨域"访问后端（前端与后端不同域名时必须注册，否则请求会被浏览器拦掉）
# 说明：线上用 Nginx 同域反代（/api 与 /uploads 都代理到后端），同域请求不触发跨域检查；
#      但以下三种场景离不开 CORS，所以必须注册：
#        ① 前后台分域名部署（如 admin.xxx.com 调用 www.xxx.com/api）
#        ② 手机/平板通过局域网 IP 在真机上调试
#        ③ 将来接入小程序或第三方系统调用开放接口
# 白名单来源：settings.CORS_ORIGINS，线上用环境变量 MAI_ISLE_CORS 覆盖
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,   # 只放行白名单里的域名（不能用 * 配合 credentials）
    allow_credentials=True,                # 允许携带 Cookie/认证头
    allow_methods=["*"],                   # 允许的 HTTP 方法：本项目用到 GET/POST/PUT/PATCH/DELETE
    allow_headers=["*"],                   # 允许的请求头：Authorization、Content-Type 等
)


# ---------- 全局异常处理 ----------

@app.exception_handler(BizError)
async def biz_error_handler(request: Request, exc: BizError):
    """业务异常：按携带的 HTTP 状态码与业务 code 返回"""
    return JSONResponse(
        status_code=exc.http_status,
        content={"code": exc.code, "message": exc.message, "data": None},
    )


# Pydantic 内置错误英文 → 中文映射（自定义 field_validator 已是中文，直接透传）
_BUILTIN_MSG_MAP = {
    "Field required": "缺少必填参数",
    "Input should be a valid integer": "参数类型不正确",
    "Input should be a valid boolean": "参数类型不正确",
    "String should have at least 1 character": "参数不能为空",
    "String should have at most 50 characters": "参数超出长度限制",
}


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """参数校验失败统一映射：HTTP 400 + code 40001 + 中文提示

    取第一条错误的中文提示作为 message；
    data.errors 携带字段级错误（{字段: 提示}）便于前端字段下方提示（技术文档 §5.2.7）。
    """
    errors = exc.errors()
    first = errors[0] if errors else {}
    raw_msg = str(first.get("msg", "参数校验失败"))
    msg = _BUILTIN_MSG_MAP.get(raw_msg, raw_msg)

    field_errors: dict = {}
    for err in errors:
        loc = err.get("loc", [])
        field = str(loc[-1]) if loc else "body"
        err_msg = str(err.get("msg", msg))
        err_msg = _BUILTIN_MSG_MAP.get(err_msg, err_msg)
        if field not in field_errors:
            field_errors[field] = err_msg

    return JSONResponse(
        status_code=400,
        content={"code": 40001, "message": msg, "data": {"errors": field_errors}},
    )


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception):
    """兜底异常：不向客户端泄露内部细节（技术文档 §7.10）"""
    return JSONResponse(
        status_code=500,
        content={"code": 50000, "message": "操作失败，请稍后重试", "data": None},
    )


# ---------- 静态图片目录 ----------
# 前端直接通过 /uploads/cakes/xxx.jpg 访问上传的图片
# 挂载前确保根目录与子目录存在（StaticFiles 要求目录存在）
upload_root = Path(settings.UPLOAD_DIR)
upload_root.mkdir(parents=True, exist_ok=True)
for d in settings.UPLOAD_DIRS:
    (upload_root / d).mkdir(parents=True, exist_ok=True)

app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


# ---------- 路由注册（前台 /api/v1，后台 /api/v1/admin） ----------
# 前台（无需登录）
app.include_router(front.router, prefix="/api/v1")
app.include_router(captcha.router, prefix="/api/v1")
# 后台（需登录）
app.include_router(auth.router, prefix="/api/v1/admin")
app.include_router(dashboard.router, prefix="/api/v1/admin")
app.include_router(cakes.router, prefix="/api/v1/admin")
app.include_router(orders.router, prefix="/api/v1/admin")
app.include_router(stores.router, prefix="/api/v1/admin")
app.include_router(content.router, prefix="/api/v1/admin")
app.include_router(messages.router, prefix="/api/v1/admin")
app.include_router(users.router, prefix="/api/v1/admin")
app.include_router(upload.router, prefix="/api/v1/admin")


# ---------- 健康检查 ----------
@app.get("/health")
def health_check():
    """健康检查：前端/部署脚本用来确认后端是否存活"""
    return {"status": "ok", "service": "mai-isle-api"}
