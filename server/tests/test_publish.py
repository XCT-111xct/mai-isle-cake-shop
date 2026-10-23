# ============================================================
# 文件功能：内容版本化发布保护测试
#
# 覆盖重点：
#   ① 草稿绝不影响线上（这是「先预览」的全部意义）
#   ② 发布必填变更说明、回滚必填原因（版本留痕的底线）
#   ③ 乐观锁：两人同时编辑，后发布者必须被拒（409），不能静默覆盖
#   ④ 回滚 = 生成新版本，不是指针回拨 → 版本号只增不减，且回滚可再回滚
#   ⑤ 预览令牌：能看草稿、与 key 强绑定、发布后立即失效、失效时明确降级
#   ⑥ 下线后前台区块消失但内容仍在历史里
#   ⑦ 失败操作也留痕（并发冲突被拒要能在日志里查到）
#   ⑧ 草稿与「直接保存」共用同一套校验（不许口径分叉）
# ============================================================

import pytest

from app.models import Content
from app.models_publish import ContentPreviewToken, ContentPublishLog, ContentVersion
from app.utils.publish import get_current_version


# ============================================================
# 一、基线
# ============================================================

def test_baseline_created_from_existing_content(client, auth_headers, db_session):
    """版本系统启用前就存在的内容，第一次操作时必须自动固化为 v1 基线。

    否则版本链是空的：乐观锁没有比对基准，回滚也没有目标版本，
    已有内容会变成孤儿 —— 这是「后加版本系统」最容易丢数据的地方。
    """
    r = client.get("/api/v1/admin/content/brand_story/versions", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["current_version"] == 1
    items = data["items"]
    assert len(items) == 1
    assert items[0]["status"] == "published"
    assert items[0]["is_current"] is True
    assert items[0]["created_by_name"] == "system"
    assert "基线" in items[0]["change_summary"]


# ============================================================
# 二、草稿不影响线上
# ============================================================

def test_save_draft_does_not_touch_online(client, auth_headers, db_session):
    """存草稿后，前台读到的必须还是旧内容"""
    before = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert "测试故事" in before

    r = client.post("/api/v1/admin/content/brand_story/draft", headers=auth_headers,
                    json={"value": "# 新故事\n\n草稿内容", "change_summary": "改故事"})
    assert r.status_code == 200
    draft = r.json()["data"]
    assert draft["version"] >= 2

    # 前台仍是旧内容
    after = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert after == before, "存草稿却让线上内容变了 —— 草稿机制形同虚设"

    # 后台草稿可读取
    r = client.get("/api/v1/admin/content/brand_story/draft", headers=auth_headers)
    assert r.json()["data"]["value"] == "# 新故事\n\n草稿内容"


def test_draft_rejects_same_as_online(client, auth_headers):
    """与线上完全一致的「草稿」不该产生 —— 否则版本历史里全是空变更"""
    r = client.post("/api/v1/admin/content/brand_story/draft", headers=auth_headers,
                    json={"value": "# 品牌故事\n\n测试故事", "change_summary": "无变化"})
    assert r.status_code == 400
    assert "一致" in r.json()["message"]


# ============================================================
# 三、发布
# ============================================================

def _save_draft(client, headers, key, value, summary="变更说明"):
    r = client.post(f"/api/v1/admin/content/{key}/draft", headers=headers,
                    json={"value": value, "change_summary": summary})
    assert r.status_code == 200, r.text
    return r.json()["data"]["version_id"]


def test_publish_makes_content_live(client, auth_headers):
    vid = _save_draft(client, auth_headers, "brand_story", "# 发布了\n\n新正文", "上线新故事")
    r = client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                    json={"version_id": vid, "change_summary": "上线新故事"})
    assert r.status_code == 200

    live = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert live == "# 发布了\n\n新正文"

    # 新版本成为 current，旧版本转 superseded 但仍存在
    r = client.get("/api/v1/admin/content/brand_story/versions", headers=auth_headers)
    items = {i["version"]: i for i in r.json()["data"]["items"]}
    assert r.json()["data"]["current_version"] == items[vid]["version"]
    assert any(i["status"] == "superseded" for i in items.values()), "旧版本不能被删除"


def test_publish_requires_change_summary(client, auth_headers):
    """变更说明必填：没有它，一年后没人知道这一版为什么改"""
    vid = _save_draft(client, auth_headers, "brand_story", "改了", "")
    r = client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                    json={"version_id": vid, "change_summary": "   "})
    assert r.status_code == 400
    assert "变更说明" in r.json()["message"]


def test_publish_conflict_rejected_409(client, auth_headers, db_session):
    """乐观锁：A 基于 v1 存了草稿，期间他人通过「保存即生效」改了线上，
    A 再发布必须被拒（否则会静默覆盖别人的修改）。

    这个场景是真实会发生的：老后台习惯点「保存并生效」，新流程的人用草稿，
    两条路径撞在一起时，绝不能谁后点谁覆盖。
    """
    # A 存草稿（基于当前线上版本 v1）
    a_vid = _save_draft(client, auth_headers, "brand_story", "A 改的内容", "A 的修改")

    # 他人通过快速通道直接保存生效 → 线上推进到新版本
    r = client.put("/api/v1/admin/content/brand_story", headers=auth_headers,
                   json={"value": "B 直接改的内容"})
    assert r.status_code == 200

    # A 再发布 → 必须被拒
    r = client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                    json={"version_id": a_vid, "change_summary": "A 发布"})
    assert r.status_code == 409
    assert "版本冲突" in r.json()["message"]

    # 冲突不得改变线上内容
    live = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert live == "B 直接改的内容"

    # 失败的发布尝试必须留痕
    logs = client.get("/api/v1/admin/content/publish-logs", headers=auth_headers,
                      params={"key": "brand_story"}).json()["data"]["items"]
    failed = [g for g in logs if g["action"] == "publish" and g["result"] == "failed"]
    assert failed, "被拒的发布若不入日志，事后完全查不到为什么没更新"
    assert "版本冲突" in failed[0]["error_msg"]


def test_direct_save_also_creates_version(client, auth_headers, db_session):
    """快速通道也必须写版本记录，否则版本链与线上内容脱节、回滚会抹掉改动"""
    client.get("/api/v1/admin/content/brand_story/versions", headers=auth_headers)  # 建基线 v1
    client.put("/api/v1/admin/content/brand_story", headers=auth_headers,
               json={"value": "快速通道改的内容"})

    items = client.get("/api/v1/admin/content/brand_story/versions",
                       headers=auth_headers).json()["data"]["items"]
    assert len(items) >= 2, "直接保存没进版本表 —— 回滚时这次改动会凭空消失"
    latest = max(items, key=lambda i: i["version"])
    assert latest["is_current"] is True
    assert "快速通道" in latest["change_summary"]


# ============================================================
# 四、回滚
# ============================================================

def test_rollback_creates_new_version_not_rewind(client, auth_headers):
    """回滚必须「用旧内容造新版本」，版本号只增不减"""
    # 先发布一版新内容
    vid = _save_draft(client, auth_headers, "brand_story", "# v2 内容", "第二版")
    client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                json={"version_id": vid, "change_summary": "发布第二版"})

    # 回滚到 v1
    r = client.post("/api/v1/admin/content/brand_story/rollback", headers=auth_headers,
                    json={"target_version": 1, "reason": "客户反馈新文案有错别字"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["rollback_from_version"] == 1
    assert data["version"] > 1, "回滚必须产生新版本号，不能复用 v1"

    # 内容确实回到 v1
    live = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert "测试故事" in live

    # 版本链完整：v1、v2、回滚版三条都在
    items = client.get("/api/v1/admin/content/brand_story/versions",
                       headers=auth_headers).json()["data"]["items"]
    versions = [i["version"] for i in items]
    assert len(versions) == len(set(versions)), "版本号不得重复"
    assert min(versions) == 1
    assert data["version"] in versions


def test_rollback_requires_reason(client, auth_headers):
    vid = _save_draft(client, auth_headers, "brand_story", "改了", "改")
    client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                json={"version_id": vid, "change_summary": "发布"})
    r = client.post("/api/v1/admin/content/brand_story/rollback", headers=auth_headers,
                    json={"target_version": 1, "reason": ""})
    assert r.status_code == 400
    assert "原因" in r.json()["message"]


def test_rollback_is_reversible(client, auth_headers):
    """回滚本身也能被回滚 —— 这是「版本只追加」设计的直接好处"""
    vid = _save_draft(client, auth_headers, "brand_story", "# v2 好内容", "第二版")
    client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                json={"version_id": vid, "change_summary": "发布第二版"})

    # 误回滚到 v1
    client.post("/api/v1/admin/content/brand_story/rollback", headers=auth_headers,
                json={"target_version": 1, "reason": "误操作"})
    # 发现错了，回滚回 v2
    r = client.post("/api/v1/admin/content/brand_story/rollback", headers=auth_headers,
                    json={"target_version": 2, "reason": "撤销上一次误回滚"})
    assert r.status_code == 200
    live = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert live == "# v2 好内容", "回滚不可逆的话，误操作就是永久事故"


def test_rollback_to_current_version_rejected(client, auth_headers):
    client.get("/api/v1/admin/content/brand_story/versions", headers=auth_headers)
    r = client.post("/api/v1/admin/content/brand_story/rollback", headers=auth_headers,
                    json={"target_version": 1, "reason": "试试"})
    assert r.status_code == 400
    assert "已是当前" in r.json()["message"]


# ============================================================
# 五、预览
# ============================================================

def test_preview_token_returns_draft(client, auth_headers):
    """带合法 token 时，前台读到的是草稿内容"""
    vid = _save_draft(client, auth_headers, "brand_story", "# 草稿预览内容", "预览用")
    r = client.post("/api/v1/admin/content/brand_story/preview-token", headers=auth_headers,
                    json={"version_id": vid})
    assert r.status_code == 200
    token = r.json()["data"]["token"]
    # ⚠️ 参数必须放在 # 之前（search 部分）：放在 hash 后面浏览器不发给服务端，
    #    而前端 readPreviewState() 读的就是 location.search。改这一行前先改前端。
    assert r.json()["data"]["preview_url"].startswith("/?preview_token=")

    r = client.get("/api/v1/content/brand_story", params={"preview_token": token})
    data = r.json()["data"]
    assert data["preview"] is True
    assert data["preview_version"] == vid
    assert data["value"] == "# 草稿预览内容"

    # 线上仍未改变
    live = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert "草稿预览内容" not in live


def test_preview_token_bound_to_key(client, auth_headers):
    """拿 A 的 token 看不了 B —— 防止一个预览链接越权看全部草稿"""
    vid = _save_draft(client, auth_headers, "brand_story", "A 的草稿", "A")
    token = client.post("/api/v1/admin/content/brand_story/preview-token",
                        headers=auth_headers, json={"version_id": vid}).json()["data"]["token"]

    r = client.get("/api/v1/content/brand_value", params={"preview_token": token})
    data = r.json()["data"]
    assert data["preview"] is False
    assert data["preview_invalid"] is True


def test_preview_token_invalid_degrades_and_flags(client, auth_headers):
    """无效 token 不报错，降级返回线上内容并明确标记「预览失效」"""
    r = client.get("/api/v1/content/brand_story", params={"preview_token": "totally-invalid-token"})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["preview"] is False
    assert data["preview_invalid"] is True, "失效却不标记，预览者会以为看到的就是草稿"
    assert "测试故事" in data["value"]


def test_preview_token_revoked_after_publish(client, auth_headers):
    """发布后旧预览链接立即失效（否则链接被转发到群里就成了长期后门）"""
    vid = _save_draft(client, auth_headers, "brand_story", "# 待发布", "待发布")
    token = client.post("/api/v1/admin/content/brand_story/preview-token",
                        headers=auth_headers, json={"version_id": vid}).json()["data"]["token"]
    client.post("/api/v1/admin/content/brand_story/publish", headers=auth_headers,
                json={"version_id": vid, "change_summary": "发布"})

    r = client.get("/api/v1/content/brand_story", params={"preview_token": token})
    assert r.json()["data"]["preview"] is False


def test_preview_token_expired(client, auth_headers, db_session):
    """过期令牌必须失效"""
    from datetime import timedelta
    from app.models import utcnow

    vid = _save_draft(client, auth_headers, "brand_story", "# 过期测试", "过期")
    token = client.post("/api/v1/admin/content/brand_story/preview-token",
                        headers=auth_headers, json={"version_id": vid}).json()["data"]["token"]

    row = db_session.query(ContentPreviewToken).filter(ContentPreviewToken.token == token).first()
    row.expires_at = utcnow() - timedelta(minutes=1)
    db_session.commit()

    r = client.get("/api/v1/content/brand_story", params={"preview_token": token})
    assert r.json()["data"]["preview"] is False


def test_preview_only_for_draft(client, auth_headers):
    """已发布版本不给预览令牌（直接看线上即可）"""
    # 用接口拿当前（已发布）版本 id
    versions = client.get("/api/v1/admin/content/brand_story/versions",
                          headers=auth_headers).json()["data"]["items"]
    published = next(v for v in versions if v["is_current"])
    r = client.post("/api/v1/admin/content/brand_story/preview-token", headers=auth_headers,
                    json={"version_id": published["id"]})
    assert r.status_code == 400
    assert "草稿" in r.json()["message"]


# ============================================================
# 六、下线
# ============================================================

def test_offline_hides_block_but_keeps_history(client, auth_headers):
    """紧急下线：前台区块消失，但内容仍在历史里可恢复"""
    before = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert before

    r = client.post("/api/v1/admin/content/brand_story/offline", headers=auth_headers,
                    json={"reason": "发布后发现有严重错别字，先撤"})
    assert r.status_code == 200

    after = client.get("/api/v1/content/brand_story").json()["data"]["value"]
    assert after == "", "置空才能让前台按「空即隐藏」规则立刻生效"

    # 历史仍在
    items = client.get("/api/v1/admin/content/brand_story/versions",
                       headers=auth_headers).json()["data"]["items"]
    assert any(i["version"] == 1 for i in items)

    # 可以回滚恢复
    r = client.post("/api/v1/admin/content/brand_story/rollback", headers=auth_headers,
                    json={"target_version": 1, "reason": "错别字已修好，恢复上线"})
    assert r.status_code == 200
    assert client.get("/api/v1/content/brand_story").json()["data"]["value"] == before


def test_offline_requires_reason(client, auth_headers):
    r = client.post("/api/v1/admin/content/brand_story/offline", headers=auth_headers,
                    json={"reason": "  "})
    assert r.status_code == 400


# ============================================================
# 七、校验同源
# ============================================================

def test_draft_and_direct_save_share_validation(client, auth_headers):
    """两条写路径必须同一套校验，否则「同一个值换个按钮就报错」"""
    # banners 超过 4 张：直接保存路径
    bad = {"banners": [{"id": i, "image_url": "/uploads/banners/b.webp", "slogan": "s",
                        "subtitle": "", "sort_order": i, "is_active": True} for i in range(1, 6)]}
    r1 = client.put("/api/v1/admin/content/banners", headers=auth_headers, json={"value": bad})
    # 草稿路径
    r2 = client.post("/api/v1/admin/content/banners/draft", headers=auth_headers,
                     json={"value": bad, "change_summary": "测试"})
    assert r1.status_code == 400
    assert r2.status_code == 400
    assert r1.json()["message"] == r2.json()["message"], "两条路径的报错文案都不一致，运营会以为是两个 bug"


def test_markdown_length_limit_shared(client, auth_headers):
    too_long = "字" * 20001
    r1 = client.put("/api/v1/admin/content/brand_story", headers=auth_headers, json={"value": too_long})
    r2 = client.post("/api/v1/admin/content/brand_story/draft", headers=auth_headers,
                     json={"value": too_long, "change_summary": "x"})
    assert r1.status_code == 400 and r2.status_code == 400


# ============================================================
# 八、审计日志
# ============================================================

def test_publish_log_covers_all_actions(client, auth_headers):
    """存草稿/预览/发布/回滚/下线，五类动作都要入日志"""
    vid = _save_draft(client, auth_headers, "custom_tips", "新提示", "改提示")
    client.post("/api/v1/admin/content/custom_tips/preview-token", headers=auth_headers,
                json={"version_id": vid})
    client.post("/api/v1/admin/content/custom_tips/publish", headers=auth_headers,
                json={"version_id": vid, "change_summary": "发布提示"})
    client.post("/api/v1/admin/content/custom_tips/rollback", headers=auth_headers,
                json={"target_version": 1, "reason": "恢复"})
    client.post("/api/v1/admin/content/custom_tips/offline", headers=auth_headers,
                json={"reason": "下线测试"})

    logs = client.get("/api/v1/admin/content/publish-logs", headers=auth_headers,
                      params={"key": "custom_tips"}).json()["data"]["items"]
    actions = {g["action"] for g in logs}
    assert {"save_draft", "preview", "publish", "rollback", "offline"} <= actions
    for g in logs:
        assert g["operator_name"], "操作人不能为空，否则日志无法追责"
        assert g["created_at"]
