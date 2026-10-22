# ============================================================
# 文件功能：图片上传（技术开发文档 §5.3.10 / §7.9）
#   POST /api/v1/admin/upload
#   商品图 / Banner 图 / 门店图 / 品牌配图统一入口
# ============================================================

import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.utils.response import BizError, bad_request, ok

router = APIRouter()

# MIME 白名单（技术文档 §7.9）
ALLOWED_MIME = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}


@router.post("/upload", summary="图片上传")
async def upload_image(
    file: UploadFile,
    dir: str = "cakes",
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """统一图片上传入口。

    - 类型：jpg/png/webp（MIME 校验 + 扩展名按 MIME 决定，防伪装）
    - 大小：≤5MB
    - 文件名：{原文件名去扩展}_{uuid4().hex[:8]}.{ext}（防同秒并发覆盖）
    - 存储：server/uploads/{dir}/，URL 前缀 /uploads/
    """
    # ---- 类型校验 ----
    ext = ALLOWED_MIME.get(file.content_type or "")
    if not ext:
        raise bad_request("图片格式仅支持 jpg/png/webp")

    # ---- 大小校验 ----
    data = await file.read()
    if len(data) > settings.MAX_UPLOAD_SIZE:
        raise bad_request("图片大小不能超过 5MB")

    # ---- 目录白名单（防路径穿越） ----
    safe_dir = dir if dir in settings.UPLOAD_DIRS else "cakes"

    # ---- 文件名重写：uuid 片段防重名 ----
    stem = Path(file.filename or "image").stem
    # 过滤可能引起路径穿越/异常字符
    stem = "".join(c for c in stem if c.isalnum() or c in "-_")
    filename = f"{stem or 'image'}_{uuid.uuid4().hex[:8]}{ext}"

    upload_path = Path(settings.UPLOAD_DIR) / safe_dir
    os.makedirs(upload_path, exist_ok=True)
    try:
        with open(upload_path / filename, "wb") as f:
            f.write(data)
    except OSError:
        raise BizError(500, 50000, "上传失败，请重试")

    return ok({"url": f"/uploads/{safe_dir}/{filename}"})
