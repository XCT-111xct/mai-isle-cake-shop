# ============================================================
# 测试文件：门店/内容/留言/用户/上传（技术开发文档 §8.1 test_admin_others.py）
#   门店 CRUD 内容读写、留言状态切换/删除、
#   用户 CRUD（超管保护、末位超管保护）、上传（类型/大小校验）
# ============================================================

from app.utils.captcha_gen import save_captcha

import io

from app.utils.captcha_gen import save_captcha

STORE_PAYLOAD = {
    "name": "联洋店",
    "address": "上海市浦东新区迎春路 767 号",
    "phone": "021-58388761",
    "hours": "08:00-21:00",
    "image_url": "/uploads/stores/s1.jpg",
    "sort_order": 1,
    "is_active": True,
}


# ---------- 门店 ----------

class TestStoreAdmin:
    def test_crud(self, client, auth_headers):
        # 新增
        resp = client.post("/api/v1/admin/stores", headers=auth_headers, json=STORE_PAYLOAD)
        sid = resp.json()["data"]["id"]
        assert resp.status_code == 200
        # 列表搜索
        resp = client.get("/api/v1/admin/stores", headers=auth_headers, params={"keyword": "联洋"})
        assert resp.json()["data"]["total"] == 1
        # 编辑
        resp = client.put(f"/api/v1/admin/stores/{sid}", headers=auth_headers,
                          json={**STORE_PAYLOAD, "name": "联洋旗舰店"})
        assert resp.status_code == 200
        # 停用
        resp = client.patch(f"/api/v1/admin/stores/{sid}/status", headers=auth_headers, json={"is_active": False})
        assert resp.json()["data"]["is_active"] is False
        # 删除
        resp = client.delete(f"/api/v1/admin/stores/{sid}", headers=auth_headers)
        assert resp.status_code == 200
        assert client.get("/api/v1/admin/stores", headers=auth_headers).json()["data"]["total"] == 0

    def test_validation(self, client, auth_headers):
        resp = client.post("/api/v1/admin/stores", headers=auth_headers, json={**STORE_PAYLOAD, "name": "A"})
        assert resp.status_code == 400
        resp = client.post("/api/v1/admin/stores", headers=auth_headers, json={**STORE_PAYLOAD, "address": "x" * 200})
        assert resp.status_code == 400


# ---------- 内容 ----------

class TestContentAdmin:
    def test_list_content_keys(self, client, auth_headers):
        resp = client.get("/api/v1/admin/content", headers=auth_headers)
        keys = [i["key"] for i in resp.json()["data"]["items"]]
        assert "banners" in keys and "custom_tips" in keys and len(keys) == 10

    def test_update_and_read(self, client, auth_headers):
        resp = client.put("/api/v1/admin/content/brand_story", headers=auth_headers,
                          json={"value": "# 新故事\n\n测试"})
        assert resp.status_code == 200
        # 前台实时生效
        resp = client.get("/api/v1/content/brand_story")
        assert resp.json()["data"]["value"] == "# 新故事\n\n测试"

    def test_update_json_content(self, client, auth_headers):
        resp = client.put("/api/v1/admin/content/order_info", headers=auth_headers,
                          json={"value": {"hotline": "021-111", "hours": "09:00-19:00", "delivery_note": "x"}})
        assert resp.status_code == 200
        resp = client.get("/api/v1/admin/content/order_info", headers=auth_headers)
        assert resp.json()["data"]["value"]["hotline"] == "021-111"

    def test_unknown_key(self, client, auth_headers):
        resp = client.put("/api/v1/admin/content/nope", headers=auth_headers, json={"value": "x"})
        assert resp.status_code == 404

    def test_banner_crud(self, client, auth_headers):
        # 新增 banner
        resp = client.post("/api/v1/admin/content/banners", headers=auth_headers, json={
            "image_url": "/uploads/banners/b1.jpg", "slogan": "麦屿手作", "subtitle": "EST. 2020",
        })
        bid = resp.json()["data"]["id"]
        assert resp.status_code == 200
        # 前台可见
        resp = client.get("/api/v1/content/banners")
        banners = resp.json()["data"]["value"]["banners"]
        assert len(banners) == 1 and banners[0]["id"] == bid
        # 编辑
        resp = client.put(f"/api/v1/admin/content/banners/{bid}", headers=auth_headers,
                          json={"image_url": "/uploads/banners/b2.jpg", "slogan": "新 slogan"})
        assert resp.status_code == 200
        # 删除
        resp = client.delete(f"/api/v1/admin/content/banners/{bid}", headers=auth_headers)
        assert resp.status_code == 200
        banners = client.get("/api/v1/content/banners").json()["data"]["value"]["banners"]
        assert banners == []

    def test_banner_max_4(self, client, auth_headers):
        for i in range(4):
            resp = client.post("/api/v1/admin/content/banners", headers=auth_headers,
                               json={"image_url": f"/uploads/banners/b{i}.jpg"})
            assert resp.status_code == 200
        resp = client.post("/api/v1/admin/content/banners", headers=auth_headers,
                           json={"image_url": "/uploads/banners/b5.jpg"})
        assert resp.status_code == 400


# ---------- 留言管理 ----------

class TestMessageAdmin:
    def _create_message(self, client, name="林小姐"):
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/messages", json={
            "name": name, "phone": "13863210086", "content": "测试留言内容",
            "captcha": "M8A2", "captcha_id": cid,
        })
        return resp.json()["data"]["id"]

    def test_list_and_detail(self, client, auth_headers):
        mid = self._create_message(client)
        resp = client.get("/api/v1/admin/messages", headers=auth_headers)
        assert resp.json()["data"]["total"] == 1
        # 列表手机号脱敏
        assert resp.json()["data"]["items"][0]["phone"] == "138****0086"
        # 详情完整
        detail = client.get(f"/api/v1/admin/messages/{mid}", headers=auth_headers).json()["data"]
        assert detail["phone"] == "13863210086"

    def test_status_toggle(self, client, auth_headers):
        mid = self._create_message(client)
        resp = client.patch(f"/api/v1/admin/messages/{mid}/status", headers=auth_headers, json={"status": "done"})
        assert resp.status_code == 200
        resp = client.get("/api/v1/admin/messages", headers=auth_headers, params={"status": "done"})
        assert resp.json()["data"]["total"] == 1

    def test_delete(self, client, auth_headers):
        mid = self._create_message(client)
        resp = client.delete(f"/api/v1/admin/messages/{mid}", headers=auth_headers)
        assert resp.status_code == 200
        assert client.get("/api/v1/admin/messages", headers=auth_headers).json()["data"]["total"] == 0

    def test_dashboard_recent_messages(self, client, auth_headers):
        """Q2 已确认：仪表盘 stats 返回 recent_messages"""
        self._create_message(client)
        resp = client.get("/api/v1/admin/dashboard/stats", headers=auth_headers)
        data = resp.json()["data"]
        assert data["pending_message_count"] == 1
        assert len(data["recent_messages"]) == 1
        assert data["recent_messages"][0]["phone"] == "138****0086"


# ---------- 用户管理（仅超管） ----------

class TestUserAdmin:
    def test_create_and_list(self, client, auth_headers):
        resp = client.post("/api/v1/admin/users", headers=auth_headers, json={
            "username": "ops01", "name": "运营小张", "password": "pass123", "role": "ops", "is_active": True,
        })
        assert resp.status_code == 200
        resp = client.get("/api/v1/admin/users", headers=auth_headers, params={"role": "ops"})
        assert resp.json()["data"]["total"] == 1

    def test_create_duplicate_username(self, client, auth_headers):
        client.post("/api/v1/admin/users", headers=auth_headers, json={
            "username": "admin", "name": "x", "password": "pass123", "role": "ops",
        })
        resp = client.post("/api/v1/admin/users", headers=auth_headers, json={
            "username": "admin", "name": "x", "password": "pass123", "role": "ops",
        })
        assert resp.status_code == 409

    def test_ops_cannot_access_users(self, client, auth_headers):
        """运营管理员访问用户管理 → 403/40300"""
        client.post("/api/v1/admin/users", headers=auth_headers, json={
            "username": "ops01", "name": "运营小张", "password": "pass123", "role": "ops",
        })
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "ops01", "password": "pass123", "captcha": "M8A2", "captcha_id": cid})
        ops_token = resp.json()["data"]["access_token"]
        resp = client.get("/api/v1/admin/users", headers={"Authorization": f"Bearer {ops_token}"})
        assert resp.status_code == 403 and resp.json()["code"] == 40300

    def test_super_cannot_delete(self, client, auth_headers):
        resp = client.delete("/api/v1/admin/users/1", headers=auth_headers)
        assert resp.status_code == 400
        assert "超级管理员" in resp.json()["message"]

    def test_last_super_protection(self, client, auth_headers):
        """停用/降级最后一名启用超管 → 40001"""
        # 停用
        resp = client.patch("/api/v1/admin/users/1/status", headers=auth_headers, json={"is_active": False})
        assert resp.status_code == 400
        assert "至少保留" in resp.json()["message"]
        # 降级
        resp = client.put("/api/v1/admin/users/1", headers=auth_headers,
                          json={"name": "系统管理员", "role": "ops", "is_active": True})
        assert resp.status_code == 400

    def test_reset_password(self, client, auth_headers):
        client.post("/api/v1/admin/users", headers=auth_headers, json={
            "username": "ops01", "name": "运营小张", "password": "pass123", "role": "ops",
        })
        # 找出 ops01 的 id
        users = client.get("/api/v1/admin/users", headers=auth_headers).json()["data"]["items"]
        uid = next(u["id"] for u in users if u["username"] == "ops01")
        resp = client.patch(f"/api/v1/admin/users/{uid}/password", headers=auth_headers,
                            json={"new_password": "newpass456"})
        assert resp.status_code == 200
        # 用新密码登录
        cid = save_captcha("M8A2")
        resp = client.post("/api/v1/admin/login", json={"username": "ops01", "password": "newpass456", "captcha": "M8A2", "captcha_id": cid})
        assert resp.status_code == 200

    def test_delete_ops_user(self, client, auth_headers):
        client.post("/api/v1/admin/users", headers=auth_headers, json={
            "username": "ops01", "name": "运营小张", "password": "pass123", "role": "ops",
        })
        users = client.get("/api/v1/admin/users", headers=auth_headers).json()["data"]["items"]
        uid = next(u["id"] for u in users if u["username"] == "ops01")
        resp = client.delete(f"/api/v1/admin/users/{uid}", headers=auth_headers)
        assert resp.status_code == 200


# ---------- 上传 ----------

class TestUpload:
    def test_upload_jpg(self, client, auth_headers):
        resp = client.post("/api/v1/admin/upload", headers=auth_headers,
                           files={"file": ("cake.jpg", io.BytesIO(b"\xff\xd8\xff" + b"0" * 100), "image/jpeg")},
                           data={"dir": "cakes"})
        assert resp.status_code == 200
        url = resp.json()["data"]["url"]
        assert url.startswith("/uploads/cakes/") and url.endswith(".jpg")

    def test_upload_wrong_type(self, client, auth_headers):
        resp = client.post("/api/v1/admin/upload", headers=auth_headers,
                           files={"file": ("evil.exe", io.BytesIO(b"MZ" * 100), "application/octet-stream")})
        assert resp.status_code == 400
        assert "jpg/png/webp" in resp.json()["message"]

    def test_upload_dir_whitelist(self, client, auth_headers):
        """非白名单 dir 回退 cakes"""
        resp = client.post("/api/v1/admin/upload", headers=auth_headers,
                           files={"file": ("x.png", io.BytesIO(b"pngdata"), "image/png")},
                           data={"dir": "../../etc"})
        assert resp.status_code == 200
        assert resp.json()["data"]["url"].startswith("/uploads/cakes/")

    def test_upload_too_large(self, client, auth_headers):
        big = io.BytesIO(b"0" * (5 * 1024 * 1024 + 1))
        resp = client.post("/api/v1/admin/upload", headers=auth_headers,
                           files={"file": ("big.jpg", big, "image/jpeg")})
        assert resp.status_code == 400
        assert "5MB" in resp.json()["message"]
