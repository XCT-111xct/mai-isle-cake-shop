# ============================================================
# 测试文件：前台接口（技术开发文档 §8.1 test_front_api.py）
#   蛋糕列表（分类筛选/分页/四种排序）、详情（含 404）、
#   分类 count、门店（仅启用）、内容读取、留言（4 字段校验 + 验证码）
# ============================================================

import pytest

from app.utils.captcha_gen import save_captcha


def _mk_cake(client, auth_headers, name, category_id=1, specs=None, **kw):
    """辅助：新增一个商品"""
    payload = {
        "name": name,
        "category_id": category_id,
        "specs": specs or [{"name": "6 寸", "price": 168.00}, {"name": "8 寸", "price": 228.00}],
        "image_url": "/uploads/cakes/test.jpg",
        "is_active": kw.get("is_active", True),
        "is_featured": kw.get("is_featured", False),
        "sort_order": kw.get("sort_order", 1),
    }
    resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]["id"]


# ---------- 蛋糕列表 ----------

class TestCakeList:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/cakes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["items"] == [] and data["total"] == 0

    def test_list_pagination(self, client, auth_headers):
        for i in range(5):
            _mk_cake(client, auth_headers, f"蛋糕{i}", sort_order=i)
        resp = client.get("/api/v1/cakes", params={"page": 1, "page_size": 2})
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["items"]) == 2
        assert data["total_pages"] == 3

    def test_category_filter(self, client, auth_headers):
        _mk_cake(client, auth_headers, "红丝绒款", category_id=1)
        _mk_cake(client, auth_headers, "慕斯款", category_id=2)
        resp = client.get("/api/v1/cakes", params={"category_id": 1})
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["name"] == "红丝绒款"

    def test_featured_filter(self, client, auth_headers):
        _mk_cake(client, auth_headers, "推荐款", is_featured=True)
        _mk_cake(client, auth_headers, "普通款", is_featured=False)
        resp = client.get("/api/v1/cakes", params={"featured": 1})
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["name"] == "推荐款"

    def test_inactive_not_visible(self, client, auth_headers):
        _mk_cake(client, auth_headers, "已下架款", is_active=False)
        resp = client.get("/api/v1/cakes")
        assert resp.json()["data"]["total"] == 0

    def test_sort_price_asc(self, client, auth_headers):
        _mk_cake(client, auth_headers, "贵蛋糕", specs=[{"name": "6 寸", "price": 500.00}])
        _mk_cake(client, auth_headers, "便宜蛋糕", specs=[{"name": "6 寸", "price": 100.00}])
        _mk_cake(client, auth_headers, "中等蛋糕", specs=[{"name": "6 寸", "price": 300.00}])
        resp = client.get("/api/v1/cakes", params={"sort": "price_asc"})
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert names == ["便宜蛋糕", "中等蛋糕", "贵蛋糕"]
        # price_from 是最低规格价
        cheap = next(i for i in resp.json()["data"]["items"] if i["name"] == "便宜蛋糕")
        assert cheap["price_from"] == 100.0

    def test_sort_price_desc(self, client, auth_headers):
        _mk_cake(client, auth_headers, "贵蛋糕", specs=[{"name": "6 寸", "price": 500.00}])
        _mk_cake(client, auth_headers, "便宜蛋糕", specs=[{"name": "6 寸", "price": 100.00}])
        resp = client.get("/api/v1/cakes", params={"sort": "price_desc"})
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert names == ["贵蛋糕", "便宜蛋糕"]

    def test_sort_newest(self, client, auth_headers):
        _mk_cake(client, auth_headers, "先创建")
        _mk_cake(client, auth_headers, "后创建")
        resp = client.get("/api/v1/cakes", params={"sort": "newest"})
        assert resp.json()["data"]["items"][0]["name"] == "后创建"

    def test_invalid_sort(self, client):
        resp = client.get("/api/v1/cakes", params={"sort": "bad"})
        assert resp.status_code == 400 and resp.json()["code"] == 40001


# ---------- 蛋糕详情 ----------

class TestCakeDetail:
    def test_detail_with_specs_related_tips(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers, "醇香红丝绒", category_id=1,
                       specs=[{"name": "6 寸", "price": 168.00}, {"name": "8 寸", "price": 228.00}])
        _mk_cake(client, auth_headers, "同分类其他", category_id=1)
        _mk_cake(client, auth_headers, "不同分类", category_id=2)

        resp = client.get(f"/api/v1/cakes/{cid}")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["category"] == "红丝绒系列"
        assert [s["name"] for s in data["specs"]] == ["6 寸", "8 寸"]
        assert data["specs"][0]["price"] == 168.0
        # 相关推荐：同分类、排除自己、最多 4 个
        related_names = [r["name"] for r in data["related"]]
        assert "同分类其他" in related_names and "不同分类" not in related_names
        assert "醇香红丝绒" not in related_names
        # custom_tips 来自 content
        assert "定制" in data["custom_tips"]

    def test_detail_not_found(self, client):
        resp = client.get("/api/v1/cakes/99999")
        assert resp.status_code == 404 and resp.json()["code"] == 40400

    def test_detail_inactive_404(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers, "下架款", is_active=False)
        resp = client.get(f"/api/v1/cakes/{cid}")
        assert resp.status_code == 404 and resp.json()["code"] == 40400


# ---------- 分类 count ----------

class TestCategories:
    def test_category_counts(self, client, auth_headers):
        _mk_cake(client, auth_headers, "红1", category_id=1)
        _mk_cake(client, auth_headers, "红2", category_id=1)
        _mk_cake(client, auth_headers, "红3下架", category_id=1, is_active=False)
        _mk_cake(client, auth_headers, "慕斯1", category_id=2)
        resp = client.get("/api/v1/categories")
        items = resp.json()["data"]["items"]
        red = next(i for i in items if i["name"] == "红丝绒系列")
        mousse = next(i for i in items if i["name"] == "慕斯系列")
        # count 只算上架产品；无产品分类也返回
        assert red["count"] == 2
        assert mousse["count"] == 1
        assert len(items) == 8


# ---------- 门店列表 ----------

class TestStores:
    def test_only_active(self, client, auth_headers):
        client.post("/api/v1/admin/stores", headers=auth_headers, json={
            "name": "联洋店", "address": "浦东迎春路 767 号", "phone": "021-58388761",
            "hours": "08:00-21:00", "image_url": "/uploads/stores/s1.jpg",
            "sort_order": 1, "is_active": True,
        })
        client.post("/api/v1/admin/stores", headers=auth_headers, json={
            "name": "停用店", "address": "测试地址", "phone": "021-00000000",
            "sort_order": 2, "is_active": False,
        })
        resp = client.get("/api/v1/stores")
        items = resp.json()["data"]["items"]
        assert len(items) == 1 and items[0]["name"] == "联洋店"
        assert items[0]["image_url"] == "/uploads/stores/s1.jpg"


# ---------- 内容读取 ----------

class TestContent:
    def test_read_json_content(self, client):
        resp = client.get("/api/v1/content/order_info")
        assert resp.status_code == 200
        value = resp.json()["data"]["value"]
        assert value["hotline"] == "021-12345678"

    def test_read_markdown_content(self, client):
        resp = client.get("/api/v1/content/brand_story")
        assert resp.json()["data"]["value"] == "# 品牌故事\n\n测试故事"

    def test_banners_structure(self, client):
        resp = client.get("/api/v1/content/banners")
        assert resp.json()["data"]["value"] == {"banners": []}

    def test_unknown_key_404(self, client):
        resp = client.get("/api/v1/content/nope")
        assert resp.status_code == 404 and resp.json()["code"] == 40400


# ---------- 留言提交 ----------

class TestMessages:
    def _get_valid_captcha_id(self, text="M8A2"):
        """直接写入内存验证码存储（同进程共享）"""
        return save_captcha(text)

    def test_submit_success(self, client):
        cid = self._get_valid_captcha_id("M8A2")
        resp = client.post("/api/v1/messages", json={
            "name": "林小姐", "phone": "13863210086",
            "content": "想预订一款 8 寸生日蛋糕",
            "captcha": "m8a2",  # 不区分大小写
            "captcha_id": cid,
        })
        assert resp.status_code == 200 and resp.json()["code"] == 0
        assert resp.json()["data"]["id"] > 0

    def test_name_too_short(self, client):
        cid = self._get_valid_captcha_id()
        resp = client.post("/api/v1/messages", json={
            "name": "林", "phone": "13863210086", "content": "留言内容",
            "captcha": "M8A2", "captcha_id": cid,
        })
        assert resp.status_code == 400 and resp.json()["code"] == 40001
        assert "2-20" in resp.json()["message"]

    def test_phone_invalid(self, client):
        cid = self._get_valid_captcha_id()
        resp = client.post("/api/v1/messages", json={
            "name": "林小姐", "phone": "12345", "content": "留言内容",
            "captcha": "M8A2", "captcha_id": cid,
        })
        assert resp.status_code == 400 and resp.json()["code"] == 40001
        assert "11 位" in resp.json()["message"]

    def test_content_empty(self, client):
        cid = self._get_valid_captcha_id()
        resp = client.post("/api/v1/messages", json={
            "name": "林小姐", "phone": "13863210086", "content": "",
            "captcha": "M8A2", "captcha_id": cid,
        })
        assert resp.status_code == 400 and resp.json()["code"] == 40001

    def test_captcha_wrong(self, client):
        cid = self._get_valid_captcha_id("M8A2")
        resp = client.post("/api/v1/messages", json={
            "name": "林小姐", "phone": "13863210086", "content": "留言内容",
            "captcha": "WXYZ", "captcha_id": cid,  # 4 位但与图形不符
        })
        assert resp.status_code == 400 and resp.json()["code"] == 40002
        assert "验证码错误" in resp.json()["message"]

    def test_captcha_expired(self, client):
        resp = client.post("/api/v1/messages", json={
            "name": "林小姐", "phone": "13863210086", "content": "留言内容",
            "captcha": "M8A2", "captcha_id": "no-such-id",
        })
        assert resp.status_code == 400 and resp.json()["code"] == 40002
        assert "过期" in resp.json()["message"]

    def test_captcha_one_time(self, client):
        """验证码一次性：同一 id 第二次提交失败"""
        cid = self._get_valid_captcha_id("M8A2")
        payload = {
            "name": "林小姐", "phone": "13863210086", "content": "留言内容",
            "captcha": "M8A2", "captcha_id": cid,
        }
        assert client.post("/api/v1/messages", json=payload).json()["code"] == 0
        resp = client.post("/api/v1/messages", json=payload)
        assert resp.status_code == 400 and resp.json()["code"] == 40002

    def test_fields_errors_in_data(self, client):
        """校验失败 data 携带字段级错误（技术文档 §5.2.7 可选增强）"""
        cid = self._get_valid_captcha_id()
        resp = client.post("/api/v1/messages", json={
            "name": "林", "phone": "123", "content": "", "captcha": "M8A2", "captcha_id": cid,
        })
        assert resp.status_code == 400
        assert "errors" in resp.json()["data"]
