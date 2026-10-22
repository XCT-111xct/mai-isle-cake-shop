# ============================================================
# 文件功能：演示数据灌入脚本（阶段 2 验收用，非交付物）
# 说明：通过后台 API 写入蛋糕/门店/banner 演示数据，
#       让前台 6 个页面有内容可看。图片用 unsplash 占位。
# 用法：python seed_demo.py（需后端已启动）
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
    # 登录（开发演示模式：DEMO/8888，需后端 DEBUG=True；生产环境请用真实验证码）
    r = call("POST", "/admin/login", {"username": "admin", "password": "admin123", "captcha": "8888", "captcha_id": "DEMO"})
    token = r["data"]["access_token"]
    print("登录 OK")

    # ---------- 蛋糕（8 个，覆盖不同分类/价格/推荐） ----------
    cakes = [
        # 红丝绒系列
        {"name": "醇香红丝绒", "category_id": 1, "is_featured": True, "sort_order": 1,
         "specs": [{"name": "6 寸", "price": 168}, {"name": "8 寸", "price": 228}, {"name": "10 寸", "price": 288}],
         "description": "比利时可可与马达加斯加香草的曼妙碰撞，绵密红丝绒蛋糕体，入口丝滑，回味悠长。"},
        {"name": "经典芝士蛋糕", "category_id": 3, "is_featured": True, "sort_order": 1,
         "specs": [{"name": "6 寸", "price": 178}, {"name": "8 寸", "price": 238}],
         "description": "法式重芝士，细腻绵密，搭配酥脆饼底，经典永不过时。"},
        {"name": "抹茶千层", "category_id": 4, "is_featured": True, "sort_order": 2,
         "specs": [{"name": "6 寸", "price": 198}, {"name": "8 寸", "price": 268}],
         "description": "宇治抹茶与动物奶油的层层交叠，微苦回甘，清新不腻。"},
        {"name": "黑森林巧克力", "category_id": 5, "is_featured": True, "sort_order": 3,
         "specs": [{"name": "6 寸", "price": 188}, {"name": "8 寸", "price": 258}],
         "description": "70% 黑巧与车厘子的经典组合，浓郁醇厚。"},
        {"name": "草莓奶油蛋糕", "category_id": 6, "is_featured": False, "sort_order": 4,
         "specs": [{"name": "6 寸", "price": 158}, {"name": "8 寸", "price": 218}],
         "description": "当季草莓与轻盈奶油，清爽的少女心之选。"},
        {"name": "芒果慕斯", "category_id": 2, "is_featured": False, "sort_order": 5,
         "specs": [{"name": "6 寸", "price": 168}, {"name": "8 寸", "price": 228}],
         "description": "新鲜芒果果肉与慕斯的绵密结合，热带风情。"},
        {"name": "节日翻糖礼盒", "category_id": 7, "is_featured": False, "sort_order": 6,
         "specs": [{"name": "小盒", "price": 258}, {"name": "大盒", "price": 388}],
         "description": "可定制图案的翻糖蛋糕，节日送礼首选。"},
        {"name": "圣诞限定款", "category_id": 8, "is_featured": False, "sort_order": 1,
         "specs": [{"name": "6 寸", "price": 268}, {"name": "8 寸", "price": 348}],
         "description": "每年圣诞限时供应，雪顶造型与热红酒风味。"},
    ]
    for c in cakes:
        r = call("POST", "/admin/cakes", {**c, "image_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=800&q=60", "is_active": True}, token)
        print("蛋糕:", c["name"], r["code"])
        # 每款蛋糕用不同图片更真实
        r = call("GET", "/admin/cakes", None, token)

    # ---------- 门店（3 家） ----------
    stores = [
        {"name": "联洋店", "address": "上海市浦东新区迎春路 767 号", "phone": "021-58388761",
         "hours": "08:00-21:00", "image_url": "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=800&q=60", "sort_order": 1, "is_active": True},
        {"name": "静安嘉里店", "address": "上海市静安区南京西路 1515 号", "phone": "021-62896666",
         "hours": "09:00-22:00", "image_url": "https://images.unsplash.com/photo-1567958451986-2de089a757fd?w=800&q=60", "sort_order": 2, "is_active": True},
        {"name": "徐汇滨江店", "address": "上海市徐汇区龙腾大道 3399 号", "phone": "021-64876677",
         "hours": "09:00-21:30", "image_url": "https://images.unsplash.com/photo-1445116572660-236099ec97a0?w=800&q=60", "sort_order": 3, "is_active": True},
    ]
    for s in stores:
        r = call("POST", "/admin/stores", s, token)
        print("门店:", s["name"], r["code"])

    # ---------- Banner（2 张） ----------
    banners = [
        {"image_url": "https://images.unsplash.com/photo-1578985545062-69928b1d9587?w=1600&q=80",
         "slogan": "麦屿手作，手作每一份甜蜜", "subtitle": "EST. 2020 SHANGHAI", "sort_order": 1, "is_active": True},
        {"image_url": "https://images.unsplash.com/photo-1565958011703-44f9829ba187?w=1600&q=80",
         "slogan": "甄选食材，让味道回归本真", "subtitle": "SELECTED INGREDIENTS", "sort_order": 2, "is_active": True},
    ]
    for b in banners:
        r = call("POST", "/admin/content/banners", b, token)
        print("Banner:", r["code"])

    print("== 演示数据灌入完成 ==")


if __name__ == "__main__":
    main()
