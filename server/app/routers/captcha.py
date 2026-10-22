# ============================================================
# 文件功能：图形验证码接口（技术开发文档 §5.2.6 / §7.7）
#   GET /api/v1/captcha → PNG 图片 + X-Captcha-Id 响应头
# ============================================================

from fastapi import APIRouter
from fastapi.responses import Response

from app.utils.captcha_gen import gen_captcha, save_captcha

router = APIRouter()


@router.get("/captcha", summary="获取图形验证码")
def get_captcha():
    """生成 130×44 的 4 位图形验证码。

    响应头 X-Captcha-Id 为本次验证码的会话标识，
    提交留言时需回传 captcha_id + captcha（5 分钟有效、一次性）。
    """
    png_bytes, text = gen_captcha()
    captcha_id = save_captcha(text)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"X-Captcha-Id": captcha_id},
    )
