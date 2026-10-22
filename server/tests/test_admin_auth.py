# ============================================================
# 测试文件：后台认证（技术开发文档 §8.1 test_admin_auth.py）
#   登录成功/密码错误/停用/锁定（5 次锁定 15 分钟、到期解锁）、
#   me、无 token 访问后台 40100
# ============================================================

from datetime import timedelta

from app.models import AdminUser, utcnow
from app.security import hash_password
from app.utils.captcha_gen import save_captcha


class TestLogin:
    def test_login_success(self, client):
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["access_token"]
        assert data["token_type"] == "bearer"
        assert data["user"]["role"] == "super"

    def test_login_wrong_password(self, client):
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "wrong", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 401 and resp.json()["code"] == 40101
        assert resp.json()["message"] == "账号或密码错误"

    def test_login_unknown_user(self, client):
        """用户不存在与密码错误返回相同提示（防枚举）"""
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "nobody", "password": "x", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 401 and resp.json()["code"] == 40101

    def test_login_disabled_user(self, client, db_session):
        """停用账号 → 40102"""
        user = db_session.query(AdminUser).filter_by(username="admin").first()
        user.is_active = False
        db_session.commit()
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 401 and resp.json()["code"] == 40102

    def test_login_lock_after_5_failures(self, client, db_session):
        """连续 5 次错误 → 锁定 15 分钟（40103）"""
        for _ in range(4):
            cid = save_captcha("M8A2")
            resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "bad", "captcha": "M8A2", "captcha_id": cid})
            assert resp.json()["code"] == 40101
        # 第 5 次 → 锁定
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "bad", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 401 and resp.json()["code"] == 40103
        assert "15 分钟" in resp.json()["message"]
        # 锁定期间正确密码也被拒
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "M8A2", "captcha_id": cid})
        assert resp.json()["code"] == 40103

    def test_lock_expires(self, client, db_session):
        """锁定到期自动解锁"""
        user = db_session.query(AdminUser).filter_by(username="admin").first()
        user.failed_attempts = 5
        user.locked_until = utcnow() - timedelta(minutes=1)  # 已过期
        db_session.commit()
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 200
        assert resp.json()["code"] == 0
        # 解锁后失败计数已重置
        assert user.failed_attempts == 0

    def test_success_resets_failures(self, client, db_session):
        user = db_session.query(AdminUser).filter_by(username="admin").first()
        user.failed_attempts = 3
        db_session.commit()
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 200
        assert user.failed_attempts == 0

    def test_login_captcha_wrong(self, client):
        """验证码错误 → 40002"""
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "WXYZ", "captcha_id": cid})
        assert resp.status_code == 400 and resp.json()["code"] == 40002
        assert "验证码错误" in resp.json()["message"]

    def test_login_captcha_expired(self, client):
        """验证码不存在 → 40002"""
        resp = client.post("/api/v1/admin/login", json={"username": "admin", "password": "admin123", "captcha": "M8A2", "captcha_id": "no-such-id"})
        assert resp.status_code == 400 and resp.json()["code"] == 40002
        assert "过期" in resp.json()["message"]


class TestMe:
    def test_me(self, client, auth_headers):
        resp = client.get("/api/v1/admin/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["username"] == "admin" and data["role"] == "super"

    def test_me_no_token(self, client):
        resp = client.get("/api/v1/admin/me")
        assert resp.status_code == 401 and resp.json()["code"] == 40100

    def test_me_invalid_token(self, client):
        resp = client.get("/api/v1/admin/me", headers={"Authorization": "Bearer bad.token.here"})
        assert resp.status_code == 401 and resp.json()["code"] == 40100


class TestAuthGuard:
    def test_admin_api_requires_token(self, client):
        """无 token 访问后台接口 → 401/40100"""
        for path in ["/api/v1/admin/cakes", "/api/v1/admin/orders", "/api/v1/admin/stores"]:
            resp = client.get(path)
            assert resp.status_code == 401
            assert resp.json()["code"] == 40100

    def test_logout(self, client):
        resp = client.post("/api/v1/admin/logout")
        assert resp.status_code == 200 and resp.json()["code"] == 0
