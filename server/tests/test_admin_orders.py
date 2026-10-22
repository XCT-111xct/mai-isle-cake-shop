# ============================================================
# 测试文件：后台订单（技术开发文档 §8.1 test_admin_orders.py）
#   新增（金额自动计算/快照/订单号自增/配送地址必填）、
#   状态机合法与非法流转、已完成不可编辑、列表筛选搜索
# ============================================================

import json

ORDER_PAYLOAD = {
    "customer_name": "林小姐",
    "customer_phone": "13863210086",
    "cake_id": None,  # 用例内创建商品后回填
    "spec_name": "8 寸",
    "quantity": 2,
    "pickup_type": "delivery",
    "delivery_address": "上海市浦东新区迎春路 767 号",
    "custom_note": "顶部用草莓装饰",
    "remark": "老客户",
}


def _mk_cake(client, auth_headers, price=198.00):
    """创建测试商品，返回 cake_id"""
    resp = client.post("/api/v1/admin/cakes", headers=auth_headers, json={
        "name": f"测试蛋糕{price}",
        "category_id": 1,
        "specs": [{"name": "6 寸", "price": 128.00}, {"name": "8 寸", "price": price}],
        "image_url": "/uploads/cakes/t.jpg",
    })
    return resp.json()["data"]["id"]


def _mk_order(client, auth_headers, **overrides):
    payload = {**ORDER_PAYLOAD, **overrides}
    return client.post("/api/v1/admin/orders", headers=auth_headers, json=payload)


class TestCreateOrder:
    def test_amount_auto_calculated(self, client, auth_headers):
        """金额 = 规格价 × 数量（Decimal），忽略前端 amount"""
        cid = _mk_cake(client, auth_headers, price=198.00)
        resp = _mk_order(client, auth_headers, cake_id=cid, quantity=2)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["amount"] == 396.0  # 198 × 2
        assert data["status"] == "pending"
        assert data["order_no"].startswith("2026")

    def test_snapshot_saved(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers, price=198.00)
        oid = _mk_order(client, auth_headers, cake_id=cid).json()["data"]["id"]
        detail = client.get(f"/api/v1/admin/orders/{oid}", headers=auth_headers).json()["data"]
        snap = detail["cake_snapshot"]
        assert snap["cake_id"] == cid
        assert snap["cake_name"] == "测试蛋糕198.0"
        assert snap["spec_name"] == "8 寸"
        assert snap["price"] == 198.0

    def test_order_no_increment(self, client, auth_headers):
        """同一天订单号自增：...001 → ...002"""
        cid = _mk_cake(client, auth_headers)
        o1 = _mk_order(client, auth_headers, cake_id=cid).json()["data"]
        o2 = _mk_order(client, auth_headers, cake_id=cid).json()["data"]
        assert o1["order_no"][-3:] == "001"
        assert o2["order_no"][-3:] == "002"

    def test_delivery_requires_address(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        resp = _mk_order(client, auth_headers, cake_id=cid, pickup_type="delivery", delivery_address="")
        assert resp.status_code == 400
        assert "配送地址" in resp.json()["message"]

    def test_self_pickup_no_address(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        resp = _mk_order(client, auth_headers, cake_id=cid, pickup_type="self", delivery_address=None)
        assert resp.status_code == 200

    def test_inactive_cake_rejected(self, client, auth_headers):
        """产品已下架不可下单（40001）"""
        cid = _mk_cake(client, auth_headers)
        client.patch(f"/api/v1/admin/cakes/{cid}/status", headers=auth_headers, json={"is_active": False})
        resp = _mk_order(client, auth_headers, cake_id=cid)
        assert resp.status_code == 400
        assert "已下架" in resp.json()["message"]

    def test_spec_not_exist(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        resp = _mk_order(client, auth_headers, cake_id=cid, spec_name="99 寸")
        assert resp.status_code == 400

    def test_phone_required(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        resp = _mk_order(client, auth_headers, cake_id=cid, customer_phone="123")
        assert resp.status_code == 400 and resp.json()["code"] == 40001


class TestOrderStatusMachine:
    """必测状态机用例（技术文档 §8.1）：
    pending→confirmed ✓、pending→completed ✗、confirmed→completed ✓、
    completed→任何 ✗、cancelled→任何 ✗"""

    def _new_order(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        return _mk_order(client, auth_headers, cake_id=cid).json()["data"]["id"]

    def _patch(self, client, auth_headers, oid, status):
        return client.patch(f"/api/v1/admin/orders/{oid}/status", headers=auth_headers, json={"status": status})

    def test_pending_to_confirmed_ok(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        resp = self._patch(client, auth_headers, oid, "confirmed")
        assert resp.status_code == 200 and resp.json()["data"]["status"] == "confirmed"

    def test_pending_to_completed_rejected(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        resp = self._patch(client, auth_headers, oid, "completed")
        assert resp.status_code == 400
        assert "非法状态流转" in resp.json()["message"]

    def test_confirmed_to_completed_ok(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        self._patch(client, auth_headers, oid, "confirmed")
        resp = self._patch(client, auth_headers, oid, "completed")
        assert resp.status_code == 200

    def test_completed_no_transition(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        self._patch(client, auth_headers, oid, "confirmed")
        self._patch(client, auth_headers, oid, "completed")
        for status in ["pending", "confirmed", "cancelled", "completed"]:
            resp = self._patch(client, auth_headers, oid, status)
            assert resp.status_code == 400

    def test_cancelled_no_transition(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        self._patch(client, auth_headers, oid, "cancelled")
        resp = self._patch(client, auth_headers, oid, "confirmed")
        assert resp.status_code == 400

    def test_pending_to_cancelled_ok(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        resp = self._patch(client, auth_headers, oid, "cancelled")
        assert resp.status_code == 200

    def test_confirmed_to_cancelled_ok(self, client, auth_headers):
        oid = self._new_order(client, auth_headers)
        self._patch(client, auth_headers, oid, "confirmed")
        resp = self._patch(client, auth_headers, oid, "cancelled")
        assert resp.status_code == 200


class TestOrderUpdate:
    def test_edit_pending_order(self, client, auth_headers):
        """pending 可编辑；改数量重算金额"""
        cid = _mk_cake(client, auth_headers, price=100.00)
        oid = _mk_order(client, auth_headers, cake_id=cid, quantity=1).json()["data"]["id"]
        resp = client.put(f"/api/v1/admin/orders/{oid}", headers=auth_headers, json={
            **ORDER_PAYLOAD, "cake_id": cid, "quantity": 3,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["amount"] == 300.0  # 100 × 3

    def test_completed_not_editable(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        oid = _mk_order(client, auth_headers, cake_id=cid).json()["data"]["id"]
        # 先合法流转到 completed（pending → confirmed → completed）
        client.patch(f"/api/v1/admin/orders/{oid}/status", headers=auth_headers, json={"status": "confirmed"})
        client.patch(f"/api/v1/admin/orders/{oid}/status", headers=auth_headers, json={"status": "completed"})
        resp = client.put(f"/api/v1/admin/orders/{oid}", headers=auth_headers, json={**ORDER_PAYLOAD, "cake_id": cid})
        assert resp.status_code == 400
        assert "不可编辑" in resp.json()["message"]

    def test_cancelled_not_editable(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        oid = _mk_order(client, auth_headers, cake_id=cid).json()["data"]["id"]
        client.patch(f"/api/v1/admin/orders/{oid}/status", headers=auth_headers, json={"status": "cancelled"})
        resp = client.put(f"/api/v1/admin/orders/{oid}", headers=auth_headers, json={**ORDER_PAYLOAD, "cake_id": cid})
        assert resp.status_code == 400


class TestOrderList:
    def test_phone_masked_in_list(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        _mk_order(client, auth_headers, cake_id=cid, customer_phone="13863210086")
        resp = client.get("/api/v1/admin/orders", headers=auth_headers)
        item = resp.json()["data"]["items"][0]
        assert item["customer_phone"] == "138****0086"

    def test_detail_full_phone(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        oid = _mk_order(client, auth_headers, cake_id=cid, customer_phone="13863210086").json()["data"]["id"]
        detail = client.get(f"/api/v1/admin/orders/{oid}", headers=auth_headers).json()["data"]
        assert detail["customer_phone"] == "13863210086"

    def test_keyword_search(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        _mk_order(client, auth_headers, cake_id=cid, customer_name="张三")
        _mk_order(client, auth_headers, cake_id=cid, customer_name="李四")
        resp = client.get("/api/v1/admin/orders", headers=auth_headers, params={"keyword": "张三"})
        assert resp.json()["data"]["total"] == 1

    def test_status_filter(self, client, auth_headers):
        cid = _mk_cake(client, auth_headers)
        oid = _mk_order(client, auth_headers, cake_id=cid).json()["data"]["id"]
        client.patch(f"/api/v1/admin/orders/{oid}/status", headers=auth_headers, json={"status": "confirmed"})
        resp = client.get("/api/v1/admin/orders", headers=auth_headers, params={"status": "confirmed"})
        assert resp.json()["data"]["total"] == 1
        resp = client.get("/api/v1/admin/orders", headers=auth_headers, params={"status": "pending"})
        assert resp.json()["data"]["total"] == 0
