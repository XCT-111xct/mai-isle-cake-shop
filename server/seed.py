# ============================================================
# 文件功能：种子数据初始化（技术开发文档 §4.4）
# 用法：python seed.py（幂等——已存在的数据自动跳过，可重复执行）
# 内容：
#   ① 8 个初始分类（PRD §6.2.3 F2-1）
#   ② 默认超级管理员 admin / admin123
#   ③ 品牌初始化文案（10 个 content key）
# ============================================================

import json

from app.database import SessionLocal, init_db
from app.models import AdminUser, Category, Content
from app.security import hash_password

# ---------- ① 8 个初始分类 ----------
INITIAL_CATEGORIES = [
    "红丝绒系列",
    "慕斯系列",
    "芝士系列",
    "抹茶系列",
    "巧克力系列",
    "水果系列",
    "翻糖系列",
    "节日限定",
]

# ---------- ③ 品牌初始化文案（10 个 key） ----------
# 富文本（brand_story/brand_value/custom_tips）存 Markdown；其余存 JSON
INITIAL_CONTENT = {
    # banners：空数组 → 前台 Hero 区块隐藏（PRD §6.2.2 空内容隐藏规则）
    "banners": {"banners": []},
    "brand_story": (
        "城市的节奏总是匆匆，流水线的甜品层出不穷，大多追逐网红爆款与花哨外表，却慢慢丢失了烘焙本身最质朴的味道。\n\n"
        "麦屿手作的主理人深耕甜品行业多年，走访多地学习烘焙技艺，尝过无数甜点之后，"
        "内心萌生一个想法：想要在喧嚣的城市之中，打造一座专属于甜蜜的小小岛屿。\n\n"
        "2020 年，麦屿手作正式诞生。取名“麦屿”，“麦”代表面粉、谷物，是一切烘焙的起点；"
        "“屿”寓意一处远离浮躁、安下心打磨甜品的静谧小岛。"
    ),
    "brand_value": (
        "· 甄选食材：全球直采，让味道回归本真\n"
        "· 手作工艺：每一只蛋糕都由烘焙师亲手完成\n"
        "· 服务初心：为每一个重要时刻，认真做蛋糕"
    ),
    "brand_chars": [
        {"title": "甄选食材", "desc": "全球直采优质原料，从源头保证口感与健康"},
        {"title": "手作工艺", "desc": "拒绝流水线，每一只蛋糕都倾注烘焙师的心意"},
        {"title": "服务初心", "desc": "从订制到配送，让每个重要时刻更甜蜜"},
    ],
    "brand_journey": [
        {"year": "2020", "title": "麦屿手作·诞生", "desc": "主理人走访多地学习烘焙技艺后，于上海正式创立麦屿手作，首店落地浦东联洋。“麦”是起点，“屿”是归处。"},
        {"year": "2021", "title": "中央手作工坊建立", "desc": "自建 1200㎡ 中央手作工坊，所有产品由工坊每日新鲜手作，统一冷链配送至全部门店。"},
        {"year": "2022", "title": "甄选食材体系", "desc": "与法国 AOP 奶源、日本日清面粉、京都宇治抹茶建立长期合作，搭建可追溯的食材供应体系。"},
        {"year": "2024", "title": "门店拓展至 8 家", "desc": "线下门店覆盖上海、苏州，逐步构建长三角品牌矩阵。"},
        {"year": "2026", "title": "官网 & 数字化运营", "desc": "品牌官网与后台管理系统正式上线，开启可持续的品牌数字化运营。"},
    ],
    "hardware": [
        {"name": "中央冷链配送", "desc": "全程冷链 2 小时达，新鲜如初"},
        {"name": "独立烘焙车间", "desc": "恒温恒湿，保证出品稳定"},
    ],
    "software": [
        {"name": "专业烘焙团队", "desc": "法国蓝带背景主厨领衔"},
        {"name": "严格品控体系", "desc": "每批次出品三检三验"},
    ],
    "order_info": {
        "hotline": "021-XXXXXXX",
        "hours": "08:00-18:00",
        "delivery_note": "11 点前订购当日送达 · 市内免费配送",
    },
    "contact_info": {
        "address": "上海市浦东新区迎春路 767 号",
        "email": "hello@mai-isle.com",
    },
    "custom_tips": "支持尺寸/口味/图案/祝福语定制，建议提前 1 天电话预约",
}


def seed_categories(db) -> None:
    """8 个初始分类（幂等：同名跳过）"""
    for i, name in enumerate(INITIAL_CATEGORIES, start=1):
        exists = db.query(Category).filter(Category.name == name).first()
        if not exists:
            db.add(Category(name=name, sort_order=i))
            print(f"  [分类] 新增：{name}")


def seed_admin(db) -> None:
    """默认超级管理员 admin / admin123（幂等）"""
    exists = db.query(AdminUser).filter(AdminUser.username == "admin").first()
    if not exists:
        db.add(AdminUser(
            username="admin",
            name="系统管理员",
            password_hash=hash_password("admin123"),
            role="super",
            is_active=True,
        ))
        print("  [管理员] 新增：admin / admin123（super）")
    else:
        print("  [管理员] admin 已存在，跳过")


def seed_content(db) -> None:
    """品牌初始化文案（幂等：key 已存在跳过）"""
    for key, value in INITIAL_CONTENT.items():
        exists = db.query(Content).filter(Content.key == key).first()
        if exists:
            continue
        if isinstance(value, str):
            text = value  # Markdown 原样存
        else:
            text = json.dumps(value, ensure_ascii=False)
        db.add(Content(key=key, value=text))
        print(f"  [内容] 新增：{key}")


def seed() -> None:
    """主入口：建表 + 写入种子数据（幂等可重复执行）"""
    print("== 麦屿手作数据库初始化 ==")
    init_db()
    db = SessionLocal()
    try:
        seed_categories(db)
        seed_admin(db)
        seed_content(db)
        db.commit()
        print("== 种子数据初始化完成 ==")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
