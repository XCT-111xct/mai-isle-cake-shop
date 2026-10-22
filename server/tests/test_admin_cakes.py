# ============================================================
# 测试文件：后台商品与分类（技术开发文档 §8.1 test_admin_cakes.py）
#   新增（校验/重名 40900）、编辑、上下架、列表筛选搜索、
#   分类 CRUD + 迁移删除
# ============================================================

CAKE_PAYLOAD = {
    "name": "经典栗子蛋糕",
    "category_id": 1,
    "specs": [{"name": "6 寸", "price": 158.00}, {"name": "8 寸", "price": 198.00}],
    "description": "秋日限定款",
    "image_url": "/uploads/cakes/chestnut.jpg",
    "is_featured": True,
    "is_active": True,
    "sort_order": 7,
}


class TestCreateCake:
    def test_create_success(self, client, auth_headers):
        resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] > 0

    def test_create_duplicate_name(self, client, auth_headers):
        client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)
        resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)
        assert resp.status_code == 409 and resp.json()["code"] == 40900
        assert "已存在" in resp.json()["message"]

    def test_create_missing_specs(self, client, auth_headers):
        payload = {**CAKE_PAYLOAD, "specs": []}
        resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=payload)
        assert resp.status_code == 400 and resp.json()["code"] == 40001

    def test_create_price_invalid(self, client, auth_headers):
        payload = {**CAKE_PAYLOAD, "specs": [{"name": "6 寸", "price": 0}]}
        resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=payload)
        assert resp.status_code == 400

    def test_create_category_not_exist(self, client, auth_headers):
        payload = {**CAKE_PAYLOAD, "category_id": 999}
        resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=payload)
        assert resp.status_code == 400 and resp.json()["message"] == "分类不存在"

    def test_create_requires_image(self, client, auth_headers):
        payload = {**CAKE_PAYLOAD, "image_url": ""}
        resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json=payload)
        assert resp.status_code == 400


class TestCakeCrud:
    def test_list_filters(self, client, auth_headers):
        client.post("/api/v1/admin/cakes", headers=auth_headers, json={**CAKE_PAYLOAD, "name": "红丝绒A"})
        client.post("/api/v1/admin/cakes", headers=auth_headers, json={**CAKE_PAYLOAD, "name": "红丝绒B", "category_id": 2, "is_active": False})
        client.post("/api/v1/admin/cakes", headers=auth_headers, json={**CAKE_PAYLOAD, "name": "慕斯C", "category_id": 2})

        # 关键字
        resp = client.get("/api/v1/admin/cakes", headers=auth_headers, params={"keyword": "红丝绒"})
        assert resp.json()["data"]["total"] == 2
        # 分类筛选
        resp = client.get("/api/v1/admin/cakes", headers=auth_headers, params={"category_id": 2})
        assert resp.json()["data"]["total"] == 2
        # 上下架筛选（后台可见全部状态）
        resp = client.get("/api/v1/admin/cakes", headers=auth_headers, params={"is_active": 0})
        assert resp.json()["data"]["total"] == 1

    def test_get_detail_for_edit(self, client, auth_headers):
        cid = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD).json()["data"]["id"]
        resp = client.get(f"/api/v1/admin/cakes/{cid}", headers=auth_headers)
        data = resp.json()["data"]
        assert data["name"] == "经典栗子蛋糕"
        assert len(data["specs"]) == 2
        assert data["is_featured"] is True

    def test_update_overwrites_specs(self, client, auth_headers):
        cid = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD).json()["data"]["id"]
        new_payload = {**CAKE_PAYLOAD, "name": "改名栗子蛋糕", "specs": [{"name": "10 寸", "price": 268.00}]}
        resp = client.put(f"/api/v1/admin/cakes/{cid}", headers=auth_headers, json=new_payload)
        assert resp.status_code == 200
        data = client.get(f"/api/v1/admin/cakes/{cid}", headers=auth_headers).json()["data"]
        assert data["name"] == "改名栗子蛋糕"
        assert [s["name"] for s in data["specs"]] == ["10 寸"]

    def test_update_duplicate_exclude_self(self, client, auth_headers):
        cid = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD).json()["data"]["id"]
        # 不改名（自身重名不算冲突）
        resp = client.put(f"/api/v1/admin/cakes/{cid}", headers=auth_headers, json=CAKE_PAYLOAD)
        assert resp.status_code == 200
        # 与他人重名 → 409
        client.post("/api/v1/admin/cakes", headers=auth_headers, json={**CAKE_PAYLOAD, "name": "他人蛋糕"})
        resp = client.put(f"/api/v1/admin/cakes/{cid}", headers=auth_headers, json={**CAKE_PAYLOAD, "name": "他人蛋糕"})
        assert resp.status_code == 409 and resp.json()["code"] == 40900

    def test_update_status(self, client, auth_headers):
        cid = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD).json()["data"]["id"]
        resp = client.patch(f"/api/v1/admin/cakes/{cid}/status", headers=auth_headers, json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is False
        # 前台不可见
        assert client.get("/api/v1/cakes").json()["data"]["total"] == 0

    def test_no_delete_endpoint(self, client, auth_headers):
        """产品不支持删除：DELETE 应 405"""
        cid = client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD).json()["data"]["id"]
        resp = client.delete(f"/api/v1/admin/cakes/{cid}", headers=auth_headers)
        assert resp.status_code == 405


class TestCategoriesAdmin:
    def test_list_with_counts(self, client, auth_headers):
        resp = client.get("/api/v1/admin/categories", headers=auth_headers)
        items = resp.json()["data"]["items"]
        assert len(items) == 8
        assert items[0]["name"] == "红丝绒系列"

    def test_create_duplicate(self, client, auth_headers):
        resp = client.post("/api/v1/admin/categories", headers=auth_headers, json={"name": "红丝绒系列", "sort_order": 1})
        assert resp.status_code == 409 and resp.json()["code"] == 40900

    def test_update_category(self, client, auth_headers):
        resp = client.put("/api/v1/admin/categories/1", headers=auth_headers, json={"name": "红丝绒新名", "sort_order": 5})
        assert resp.status_code == 200

    def test_delete_empty_category(self, client, auth_headers):
        """无产品分类可直接删除（不带 move_to_id）"""
        new_id = client.post("/api/v1/admin/categories", headers=auth_headers,
                             json={"name": "空分类", "sort_order": 99}).json()["data"]["id"]
        resp = client.delete(f"/api/v1/admin/categories/{new_id}", headers=auth_headers)
        assert resp.status_code == 200

    def test_delete_with_products_requires_move(self, client, auth_headers):
        """有产品分类必须带 move_to_id"""
        client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)  # 挂在分类 1
        resp = client.delete("/api/v1/admin/categories/1", headers=auth_headers)
        assert resp.status_code == 400
        assert "迁移" in resp.json()["message"]

    def test_delete_with_move(self, client, auth_headers):
        """迁移删除：产品移到目标分类后删除"""
        client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)  # 分类 1
        resp = client.delete("/api/v1/admin/categories/1", headers=auth_headers, params={"move_to_id": 2})
        assert resp.status_code == 200
        # 产品已迁移到分类 2
        cakes = client.get("/api/v1/admin/cakes", headers=auth_headers, params={"category_id": 2}).json()["data"]["items"]
        assert len(cakes) == 1

    def test_delete_move_to_self_rejected(self, client, auth_headers):
        client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)
        resp = client.delete("/api/v1/admin/categories/1", headers=auth_headers, params={"move_to_id": 1})
        assert resp.status_code == 400

    def test_delete_move_to_missing(self, client, auth_headers):
        client.post("/api/v1/admin/cakes", headers=auth_headers, json=CAKE_PAYLOAD)
        resp = client.delete("/api/v1/admin/categories/1", headers=auth_headers, params={"move_to_id": 999})
        assert resp.status_code == 400
