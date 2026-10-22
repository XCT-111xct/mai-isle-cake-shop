# ============================================================
# 文件功能：导出前端演示所需的静态数据集
#
# 【为什么需要它】
#   前台官网是"前端 + 后端 API"的结构，而 GitHub Pages 只能托管静态文件，
#   跑不了 FastAPI。为了让面试官/HR 点开链接就能看效果，做一套"纯静态演示版"：
#   把数据库里的真实数据导出成 JSON，前端在演示模式下用本地数据渲染，
#   不再请求后端。数据是真的，只是不连后端。
#
# 【输出】
#   apps/web/src/api/demo-data.json —— 交给 demoAdapter.ts 使用
#
# 【用法】
#   在 server/.venv 环境下： python tools/export_demo_data.py
#   数据变化后重新跑一次即可。
# ============================================================

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "database" / "mai_isle.db"
OUT = ROOT / "apps" / "web" / "src" / "api" / "demo-data.json"

# 内容 key 中需要按 JSON 解析的（与后端 front.py 的 JSON_KEYS 保持一致）
JSON_KEYS = {
    "banners", "brand_chars", "brand_journey",
    "hardware", "software", "order_info", "contact_info",
}


def main() -> int:
    if not DB.exists():
        print(f"[错误] 数据库不存在：{DB}")
        return 1

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    # ---------- 分类（含上架产品数，与后端 list_categories 同构）----------
    categories = []
    for row in cur.execute(
        """
        SELECT c.id, c.name,
               (SELECT COUNT(*) FROM cake k
                 WHERE k.category_id = c.id AND k.is_active = 1) AS cnt
          FROM category c
         ORDER BY c.sort_order ASC
        """
    ):
        categories.append({"id": row["id"], "name": row["name"], "count": row["cnt"]})

    # ---------- 蛋糕（含规格、最低价、排序字段）----------
    # 注意：先把外层结果 fetchall 出来再循环。
    # 如果直接 for row in cur.execute(...) 循环，循环体里又用同一个 cursor 查规格，
    # 会把外层游标打断 —— 实测只会导出第一条，这是踩过的坑。
    cake_rows = cur.execute("SELECT * FROM cake ORDER BY sort_order ASC, created_at DESC").fetchall()
    cakes = []
    for row in cake_rows:
        cake_id = row["id"]
        specs = [
            {"name": s["name"], "price": float(s["price"])}
            for s in cur.execute(
                "SELECT name, price FROM cake_spec WHERE cake_id = ? "
                "ORDER BY sort_order ASC, price ASC",
                (cake_id,),
            )
        ]
        cat = cur.execute("SELECT name FROM category WHERE id = ?", (row["category_id"],)).fetchone()
        cakes.append(
            {
                "id": cake_id,
                "name": row["name"],
                "category_id": row["category_id"],
                "category": cat["name"] if cat else "",
                "description": row["description"] or "",
                "image_url": row["image_url"] or "",
                "specs": specs,
                # price_from = 最低规格价（后端按 sort_order 升序取第一个）
                "price_from": specs[0]["price"] if specs else 0.0,
                "is_featured": bool(row["is_featured"]),
                "is_active": bool(row["is_active"]),
                "sort_order": row["sort_order"] or 0,
                "created_at": str(row["created_at"] or ""),
            }
        )

    # ---------- 门店（仅启用，与后端 list_stores 一致）----------
    stores = []
    for row in cur.execute(
        "SELECT * FROM store WHERE is_active = 1 ORDER BY sort_order ASC, id ASC"
    ):
        stores.append(
            {
                "id": row["id"],
                "name": row["name"],
                "address": row["address"] or "",
                "phone": row["phone"] or "",
                "hours": row["hours"] or "",
                "image_url": row["image_url"] or "",
            }
        )

    # ---------- 内容区块 ----------
    contents = {}
    for row in cur.execute("SELECT key, value FROM content"):
        key = row["key"]
        raw = row["value"] or ""
        if key in JSON_KEYS:
            try:
                contents[key] = json.loads(raw)
            except json.JSONDecodeError:
                contents[key] = {}
        else:
            contents[key] = raw

    con.close()

    data = {
        "_comment": "由 tools/export_demo_data.py 从 database/mai_isle.db 导出，仅供静态演示使用",
        "categories": categories,
        "cakes": cakes,
        "stores": stores,
        "contents": contents,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"已导出 -> {OUT.relative_to(ROOT)}")
    print(f"  分类 {len(categories)} 个 / 蛋糕 {len(cakes)} 个 / 门店 {len(stores)} 个 / 内容 {len(contents)} 个 key")
    print(f"  文件大小 {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
