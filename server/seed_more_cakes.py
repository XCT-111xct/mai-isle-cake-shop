# ============================================================
# 文件功能：补足演示蛋糕数据（一次性脚本）
# 背景：seed_demo.py 灌 8 个蛋糕，page_size=9 时 totalPages=1，
#       蛋糕展示页的分页器不会显示。补足到 18 个让 totalPages=2。
# 用法：python seed_more_cakes.py（需后端已启动）
# 注意：本脚本是**幂等可重跑**的（POST 会创建新的蛋糕条目），
#       如果数据库已经有 18 个蛋糕，再跑会产生重复条目。
#       建议流程：清库 → seed.py → seed_demo.py → seed_more_cakes.py
# ============================================================

import json
import urllib.request

BASE = "http://localhost:8000/api/v1"


def call(method, path, payload=None, token=None):
    url = BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def main():
    # 登录
    r = call("POST", "/admin/login", {"username": "admin", "password": "admin123", "captcha": "8888", "captcha_id": "DEMO"})
    token = r["data"]["access_token"]
    print("登录 OK")

    # 已有 8 个蛋糕，本次新增 10 个，让总数 = 18，page_size=9 时正好 2 页
    # 命名去重：避开已用名（醇香红丝绒/经典芝士蛋糕/抹茶千层/黑森林巧克力/草莓奶油蛋糕/芒果慕斯/节日翻糖礼盒/圣诞限定款）
    more_cakes = [
        # 红丝绒系列(1) - 1
        {"name": "心形红丝绒", "category_id": 1, "is_featured": False, "sort_order": 2,
         "specs": [{"name": "6 寸", "price": 178}, {"name": "8 寸", "price": 248}],
         "description": "心形造型红丝绒，浪漫表白专属。",
         "image_url": "https://images.unsplash.com/photo-1586788680434-30d324b2d46f?w=800&q=60"},
        # 慕斯系列(2) - 2 个
        {"name": "榴莲慕斯", "category_id": 2, "is_featured": True, "sort_order": 2,
         "specs": [{"name": "6 寸", "price": 198}, {"name": "8 寸", "price": 268}],
         "description": "马来西亚猫山王榴莲，浓郁醇厚，爱的人爱不释口。",
         "image_url": "https://images.unsplash.com/photo-1567306226416-28f0efdc88ce?w=800&q=60"},
        {"name": "经典提拉米苏", "category_id": 2, "is_featured": False, "sort_order": 3,
         "specs": [{"name": "6 寸", "price": 188}, {"name": "8 寸", "price": 258}],
         "description": "意式经典，浓缩咖啡与马斯卡彭的层次美味。",
         "image_url": "https://images.unsplash.com/photo-1571877227200-a0d98ea607e9?w=800&q=60"},
        # 芝士系列(3) - 1
        {"name": "柠檬芝士", "category_id": 3, "is_featured": False, "sort_order": 2,
         "specs": [{"name": "6 寸", "price": 168}, {"name": "8 寸", "price": 228}],
         "description": "清新柠檬与重芝士的酸甜平衡，夏日解腻首选。",
         "image_url": "https://images.unsplash.com/photo-1535920527002-b35e96722eb9?w=800&q=60"},
        # 抹茶系列(4) - 1
        {"name": "抹茶红豆", "category_id": 4, "is_featured": False, "sort_order": 3,
         "specs": [{"name": "6 寸", "price": 188}, {"name": "8 寸", "price": 258}],
         "description": "宇治抹茶配蜜渍红豆，经典日式搭配。",
         "image_url": "https://images.unsplash.com/photo-1551024506-0bccd828d307?w=800&q=60"},
        # 巧克力系列(5) - 1
        {"name": "榛子巧克力", "category_id": 5, "is_featured": False, "sort_order": 4,
         "specs": [{"name": "6 寸", "price": 198}, {"name": "8 寸", "price": 268}],
         "description": "费列罗榛子酱与 70% 黑巧的二重奏。",
         "image_url": "https://images.unsplash.com/photo-1606313564200-e75d5e30476c?w=800&q=60"},
        # 水果系列(6) - 2 个
        {"name": "蜜桃乌龙", "category_id": 6, "is_featured": True, "sort_order": 5,
         "specs": [{"name": "6 寸", "price": 178}, {"name": "8 寸", "price": 238}],
         "description": "水蜜桃果肉与乌龙茶香的清爽组合。",
         "image_url": "https://images.unsplash.com/photo-1464195244916-405fa0a82545?w=800&q=60"},
        {"name": "春日草莓", "category_id": 6, "is_featured": False, "sort_order": 6,
         "specs": [{"name": "6 寸", "price": 168}],
         "description": "当季新鲜草莓整颗镶嵌，颜值与美味并存。",
         "image_url": "https://images.unsplash.com/photo-1488477181946-6428a0291777?w=800&q=60"},
        # 翻糖系列(7) - 1
        {"name": "生肖翻糖", "category_id": 7, "is_featured": False, "sort_order": 2,
         "specs": [{"name": "小盒", "price": 288}, {"name": "大盒", "price": 488}],
         "description": "可定制属相的翻糖造型，生日宴焦点。",
         "image_url": "https://images.unsplash.com/photo-1557925923-cd4648e211a0?w=800&q=60"},
        # 节日限定(8) - 1
        {"name": "情人节限定", "category_id": 8, "is_featured": False, "sort_order": 2,
         "specs": [{"name": "6 寸", "price": 288}, {"name": "8 寸", "price": 388}],
         "description": "玫瑰造型与红丝绒的双重浪漫，告白首选。",
         "image_url": "https://images.unsplash.com/photo-1607478900766-efe13248b125?w=800&q=60"},
    ]
    for c in more_cakes:
        r = call("POST", "/admin/cakes", {**c, "is_active": True}, token)
        print("新增蛋糕:", c["name"], "code=", r["code"])

    # 校验总数
    r = call("GET", "/admin/cakes?page=1&page_size=100", None, token)
    print("== 当前蛋糕总数:", r["data"]["total"], " ==")


if __name__ == "__main__":
    main()
