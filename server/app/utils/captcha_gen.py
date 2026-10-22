# ============================================================
# 文件功能：图形验证码生成与内存存储（技术开发文档 §7.7）
# 说明：
#   1. 130×44，cream 底（#F0E1B9）、棕字（#6B5238）、2-3 条干扰线
#   2. 字符集去掉易混淆 0/O/1/I
#   3. 明文存内存字典 CAPTCHA_STORE，5 分钟有效、一次性（pop 即删）
#      与部署方案"单 worker"一致（多进程会跨进程失效，见技术文档 §9.2）
# ============================================================

import io
import random
import string
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageDraw, ImageFont

from app.config import settings

# 去掉易混淆字符 0/O/1/I 的字符集（大写字母 + 数字）
CHARS = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# 背景色 / 字色 / 干扰线色（对齐 UI-UX 文档 Design Token）
BG_COLOR = "#F0E1B9"      # --cream
TEXT_COLOR = "#6B5238"    # --brown-deep
LINE_COLOR = "#D9C6A8"    # 干扰线（奶油棕浅调）

# 内存验证码存储：{ captcha_id: {"text": 小写明文, "expire": datetime} }
CAPTCHA_STORE: dict = {}


def _load_font(size: int):
    """加载验证码字体。
    生产环境应自托管 Cormorant 字体（技术文档 §9.4 #6）；开发环境回退系统字体。"""
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",      # Windows Arial Bold（接近斜体装饰感）
        "C:/Windows/Fonts/arial.ttf",        # Windows Arial
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",     # macOS
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def gen_captcha():
    """生成验证码图片。

    返回: (png_bytes, text)
      png_bytes: PNG 图片二进制（直接作为响应体）
      text:      4 位验证码明文（存入内存缓存，不区分大小写比对）
    """
    img = Image.new("RGB", (130, 44), BG_COLOR)
    draw = ImageDraw.Draw(img)
    text = "".join(random.choices(CHARS, k=settings.CAPTCHA_LENGTH))
    font = _load_font(26)

    # 逐字符绘制（横向排开，微随机 y 偏移增加辨识难度）
    x = 10
    for ch in text:
        y = random.randint(6, 10)
        draw.text((x, y), ch, font=font, fill=TEXT_COLOR)
        x += 28

    # 2-3 条干扰线
    for _ in range(random.randint(2, 3)):
        y1, y2 = random.randint(5, 40), random.randint(5, 40)
        draw.line([(0, y1), (130, y2)], fill=LINE_COLOR, width=1)

    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue(), text


def save_captcha(text: str) -> str:
    """生成 captcha_id 并存入内存缓存。

    返回: captcha_id（响应头 X-Captcha-Id 使用）
    """
    import uuid

    captcha_id = str(uuid.uuid4())
    CAPTCHA_STORE[captcha_id] = {
        "text": text.lower(),
        "expire": _now() + timedelta(minutes=settings.CAPTCHA_EXPIRE_MINUTES),
    }
    _cleanup()  # 顺带清理过期项，防止内存无限增长
    return captcha_id


def verify_captcha(captcha_id: str, captcha_text: str) -> str:
    """校验验证码：一次性（pop 即删），不区分大小写。

    返回三态：
      'ok'      — 校验通过
      'expired' — id 不存在或已过期（前端提示"验证码已过期，请重新输入"）
      'wrong'   — 内容不匹配（前端提示"验证码错误，请重新输入"）

    注意：无论成功失败都会删除该 captcha_id（技术文档 §5.2.7：
    验证码错误时后端删除该 captcha_id，前端必须刷新验证码）。
    """
    item = CAPTCHA_STORE.pop(captcha_id, None)
    if not item or item["expire"] < _now():
        return "expired"
    if item["text"] == captcha_text.strip().lower():
        return "ok"
    return "wrong"


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _cleanup():
    """清理过期验证码（简单遍历，量小直接忽略性能）"""
    expired = [k for k, v in CAPTCHA_STORE.items() if v["expire"] < _now()]
    for k in expired:
        CAPTCHA_STORE.pop(k, None)
