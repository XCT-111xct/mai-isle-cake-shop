# ============================================================
# 文件功能：图片批量优化脚本（PNG/JPG → WebP，等比缩放）
#
# 【为什么要做这件事】
#   项目原始图片是 AI 生图导出的 1024x1024 PNG，单张 1.2–1.5MB。
#   前台首页要加载 10 张蛋糕图 + 3 张门店图 + 3 张品牌图 + 1 张 logo，
#   合计 26MB。本地 localhost 看不出问题，别人用手机 4G 打开会卡很久。
#   WebP 在同等画质下人眼几乎看不出差别，体积却能小 85–95%。
#
# 【怎么用】
#   1. 先备份原图（脚本不会自动备份，请先手动复制到 .workbuddy/backup/）
#   2. 在 server/.venv 环境下运行： python tools/optimize_images.py
#   3. 脚本会打印每张图的前后体积对比
#
# 【注意】
#   本脚本只负责"生成 WebP 文件"，不删除原图、不改数据库。
#   删除原图与更新数据库由配套的 apply_image_optimization 步骤完成，
#   这样每一步都可见、可回滚。
# ============================================================

import os
import sys
from pathlib import Path

from PIL import Image

# 项目根目录（本文件在 tools/ 下，所以往上一级）
ROOT = Path(__file__).resolve().parent.parent

# ---------- 压缩规格 ----------
# 每项：(目录相对路径, 最长边像素, WebP 质量 1-100, 说明)
# 为什么按用途分规格：图片最终显示尺寸不同，按显示尺寸留 2 倍余量最经济
SPECS = [
    ("server/uploads/cakes", 900, 82, "蛋糕图（卡片最大 300px，留 3 倍余量）"),
    ("server/uploads/stores", 900, 82, "门店图（卡片约 400px）"),
    ("apps/web/public", 1000, 82, "品牌图（品牌故事/理念/特色，正文插图约 500px）"),
]

# logo 单独处理：显示尺寸只有 40–48px，256px 足够 2 倍屏使用
LOGO_SPEC = (256, 88, "LOGO（导航栏显示约 44px）")


def to_webp(src: Path, max_side: int, quality: int) -> tuple[Path, int, int]:
    """把单张图片转成 WebP，返回 (新路径, 原字节数, 新字节数)。

    处理要点：
      1. 等比缩放：只缩不放，最长边不超过 max_side
      2. 透明通道：RGBA/P 模式带透明的图，WebP 会自动保留 alpha（不用特殊处理）
      3. RGB 直接转，避免 PNG 调色板模式转出异常颜色
    """
    im = Image.open(src)

    # 统一成 RGBA（有透明）或 RGB（无透明）两种模式之一
    # 原因：P 模式（调色板）和 CMYK 模式转 WebP 容易出错，先归一化
    if im.mode in ("RGBA", "LA") or "transparency" in im.info:
        im = im.convert("RGBA")
    else:
        im = im.convert("RGB")

    # 等比缩放：算出缩放比例，长边对齐 max_side
    w, h = im.size
    longest = max(w, h)
    if longest > max_side:
        ratio = max_side / longest
        # 用 round 而不是 int，避免缩成 0 像素；最小保底 1px
        im = im.resize((max(1, round(w * ratio)), max(1, round(h * ratio))), Image.LANCZOS)

    dst = src.with_suffix(".webp")
    old_size = src.stat().st_size

    # quality 越高体积越大；method=6 是 Pillow 里压缩率最高的算法（慢一点但更小）
    im.save(dst, "WEBP", quality=quality, method=6)

    return dst, old_size, dst.stat().st_size


def main() -> int:
    total_old = total_new = 0
    count = 0

    print("=" * 78)
    print("图片压缩（PNG/JPG → WebP）")
    print("=" * 78)

    for rel_dir, max_side, quality, note in SPECS:
        folder = ROOT / rel_dir
        if not folder.is_dir():
            print(f"[跳过] 目录不存在：{rel_dir}")
            continue

        print(f"\n--- {rel_dir}  （最长边 {max_side}px / 质量 {quality}）---")
        print(f"    {note}")

        for name in sorted(os.listdir(folder)):
            src = folder / name
            ext = src.suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg"):
                continue
            # logo 单独用更小的规格处理（见下方 LOGO_SPEC），这里排除掉避免重复压缩
            if name.lower() == "logo.png":
                continue
            # 1KB 以下的文件（多为测试残留或占位符）不处理
            if src.stat().st_size < 1024:
                print(f"    [跳过] {name}（{src.stat().st_size} 字节，太小）")
                continue

            dst, old, new = to_webp(src, max_side, quality)
            total_old += old
            total_new += new
            count += 1
            print(f"    {name:<44} {old/1024:>7.0f}KB → {new/1024:>6.0f}KB  (省 {100-new/old*100:.0f}%)")

    # logo 单独一轮
    print(f"\n--- LOGO 专项（最长边 {LOGO_SPEC[0]}px / 质量 {LOGO_SPEC[1]}）---")
    for rel in ("apps/web/public/logo.png", "apps/admin/public/logo.png"):
        src = ROOT / rel
        if not src.exists():
            continue
        dst, old, new = to_webp(src, LOGO_SPEC[0], LOGO_SPEC[1])
        total_old += old
        total_new += new
        count += 1
        print(f"    {rel:<44} {old/1024:>7.0f}KB → {new/1024:>6.0f}KB  (省 {100-new/old*100:.0f}%)")

    print("\n" + "=" * 78)
    if count:
        print(f"共处理 {count} 张：{total_old/1048576:.1f} MB → {total_new/1048576:.2f} MB"
              f"（省 {100-total_new/total_old*100:.1f}%，约 {(total_old-total_new)/1048576:.1f} MB）")
    else:
        print("没有找到需要处理的图片")
    print("下一步：确认新生成的 .webp 文件观感正常后，再执行删原图 + 更新数据库")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    sys.exit(main())
