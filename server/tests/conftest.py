# ============================================================
# 文件功能：pytest 测试环境（技术开发文档 §8.1）
# 说明：
#   1. 独立 SQLite 内存库（sqlite:// + StaticPool，所有连接共享同一内存库）
#   2. 每个用例前清空所有表 + 重新写入种子数据（独立、可重复）
#   3. 通过 dependency_overrides 替换 get_db，不碰真实文件库
# ============================================================

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import AdminUser, Category, Content
from app.security import hash_password

# ---------- 测试种子数据 ----------
TEST_CATEGORIES = [
    "红丝绒系列", "慕斯系列", "芝士系列", "抹茶系列",
    "巧克力系列", "水果系列", "翻糖系列", "节日限定",
]

# 测试用内容（覆盖前台内容读取用例）
TEST_CONTENT = {
    "banners": '{"banners": []}',
    "brand_story": "# 品牌故事\n\n测试故事",
    "brand_value": "测试理念",
    "brand_chars": '[]',
    "brand_journey": '[]',
    "hardware": '[]',
    "software": '[]',
    "order_info": '{"hotline": "021-12345678", "hours": "08:00-18:00", "delivery_note": "测试配送说明"}',
    "contact_info": '{"address": "上海市浦东新区迎春路 767 号", "email": "hello@mai-isle.com"}',
    "custom_tips": "支持定制，建议提前 1 天预约",
}


def seed_test_data(session):
    """清空全部表 + 写入测试种子数据（幂等可重复）。

    ⚠️ 清空列表必须覆盖**所有**业务表，包括归因/发布新增的 10 张。
    漏一张的后果是：上一个用例留下的来电/版本记录被下一个用例读到，
    表现为「单独跑通过、全量跑失败」这种最难查的串味问题。
    顺序注意外键：先删子表（order_attribution → orders）。
    """
    tables = [
        # 归因链路（order_attribution 引用 orders，必须排在 orders 前面）
        "order_attribution", "call_log", "visit_event", "visitor_session",
        "visitor_identity", "tracking_number", "attribution_rule",
        # 发布保护
        "content_preview_token", "content_publish_log", "content_version",
        # 原有业务表（保持原顺序：先子表后父表）
        "cake_spec", "cake", "orders", "message", "content", "store", "category", "admin_user",
    ]
    for table in tables:
        session.execute(text(f"DELETE FROM {table}"))
    session.commit()

    # 8 分类
    for i, name in enumerate(TEST_CATEGORIES, start=1):
        session.add(Category(name=name, sort_order=i))
    # 默认超管
    session.add(AdminUser(
        username="admin",
        name="系统管理员",
        password_hash=hash_password("admin123"),
        role="super",
        is_active=True,
    ))
    # 内容
    for key, value in TEST_CONTENT.items():
        session.add(Content(key=key, value=value))
    session.commit()


@pytest.fixture(scope="session")
def test_engine():
    """内存 SQLite 引擎（StaticPool：所有连接指向同一内存库）"""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture()
def db_session(test_engine):
    """每个用例独立会话：清空 + 种子 + 用例结束回滚"""
    Session = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    session = Session()
    seed_test_data(session)
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def client(db_session):
    """TestClient：get_db 依赖覆盖为测试会话（不碰真实文件库）"""
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def auth_headers(client):
    """登录超管并返回请求头（多个测试文件复用）"""
    from app.utils.captcha_gen import save_captcha
    cid = save_captcha("M8A2")
    resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "m8a2", "captcha_id": cid})
    assert resp.status_code == 200
    token = resp.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def login_payload():
    """返回构造登录 payload 的 helper（含新 captcha）"""
    from app.utils.captcha_gen import save_captcha
    def _mk(username: str = "admin", password: str = "admin123", captcha: str = "M8A2"):
        cid = save_captcha(captcha)
        return {"username": username, "password": password, "captcha": captcha, "captcha_id": cid}
    return _mk
