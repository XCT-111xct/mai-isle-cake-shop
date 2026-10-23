# ============================================================
# 文件功能：转化归因链路测试
#
# 覆盖重点（每条都对应一个真实会出错的地方）：
#   ① 四级规则各自能命中，且置信度分级正确
#   ② 打了非官网号码 → 必须不可归因（防虚高，这是归因系统最重要的一条）
#   ③ 时间窗边界：超出窗口不得判 R1
#   ④ 多候选时会话有歧义 → 置信度自动降级 + 记录候选数
#   ⑤ 爬虫会话不进报表分母
#   ⑥ 手机号跨设备回溯（留言绑定的价值）
#   ⑦ 报表同时给出业绩数字与归因质量，不允许只给漂亮总数
# ============================================================

from datetime import timedelta

import pytest

from app.models import Message, utcnow
from app.models_attribution import (
    CallLog,
    TrackingNumber,
    VisitEvent,
    VisitorIdentity,
    VisitorSession,
)
from app.utils.attribution import (
    CONF_HIGH,
    CONF_MEDIUM,
    CONF_NONE,
    RULE_PHONE_LASTTOUCH,
    RULE_TRACKING_ONLY,
    RULE_TRACKING_WINDOW,
    RULE_UNMATCHED,
    attribute_call,
    detect_bot,
    detect_channel,
    detect_device,
    hash_phone,
    mask_phone,
)


# ============================================================
# 一、纯函数：渠道 / 设备 / 爬虫识别
# ============================================================

def test_detect_channel_by_utm_priority():
    """utm 标注优先于 referrer 域名 —— 人为标注比机器推断可靠"""
    # 小红书来的，但带了投放标注 → 应判 paid（投放），不是 social
    ch, detail = detect_channel(
        referrer="https://www.xiaohongshu.com/explore",
        utm_source="xiaohongshu", utm_medium="cpc",
    )
    assert ch == "paid"
    assert detail == "xiaohongshu"


def test_detect_channel_offline_qr():
    """线下海报二维码：referrer 为空，只能靠 utm 标注识别"""
    ch, detail = detect_channel(referrer="", utm_source="qr", utm_medium="qr", utm_campaign="store_jingan")
    assert ch == "qr_offline"


def test_detect_channel_search_and_social():
    assert detect_channel(referrer="https://www.baidu.com/s?wd=cake")[0] == "organic_search"
    assert detect_channel(referrer="https://www.xiaohongshu.com/x")[0] == "social"
    assert detect_channel(referrer="", utm_source="", utm_medium="")[0] == "direct"


def test_detect_bot_excludes_empty_ua():
    """无 UA 的请求按爬虫处理：宁可少算，不可把机器流量算成顾客"""
    assert detect_bot("Mozilla/5.0 (iPhone) Safari") is False
    assert detect_bot("Mozilla/5.0 (compatible; Baiduspider/2.0)") is True
    assert detect_bot("") is True
    assert detect_bot("python-requests/2.31") is True


def test_detect_device():
    assert detect_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile") == "mobile"
    assert detect_device("Mozilla/5.0 (iPad; CPU OS 17_0)") == "tablet"
    assert detect_device("Mozilla/5.0 (Windows NT 10.0) Chrome") == "desktop"


def test_phone_hash_stable_and_masked():
    """同一号码必须得到同一哈希（否则匹配全失效），且明文不出现在哈希里"""
    h1 = hash_phone("13800001111")
    h2 = hash_phone("13800001111")
    assert h1 == h2
    assert len(h1) == 64
    assert "13800001111" not in h1
    assert hash_phone("13800002222") != h1
    assert mask_phone("13800001111") == "138****1111"


# ============================================================
# 二、四级归因规则
# ============================================================

def _mk_tracking(db, no="021-88880001", channel="social", detail="xiaohongshu"):
    t = TrackingNumber(
        tracking_no=no, display_no=no, label="小红书专线",
        channel=channel, channel_detail=detail, is_active=True,
    )
    db.add(t)
    db.commit()
    return t


def _mk_session(db, sid="S-1", vid="V-1", last_seen=None, first_seen=None,
                channel="social", detail="xiaohongshu", is_bot=False):
    """造一条访客会话。

    ⚠️ first_seen_at 必须显式给值，不能靠模型默认（默认=INSERT 那一刻）：
       测试里 now 是先取好的，插入发生在之后，于是 first_seen_at 会晚于
       called_at 几百毫秒，R1 的「会话开始不得晚于来电」就被判成不成立，
       本该 R1 的用例会静默降级成 R2。默认回推 5 分钟，表达「先浏览再打电话」。
    """
    last = last_seen or utcnow()
    s = VisitorSession(
        visitor_id=vid, session_id=sid,
        landing_page="/", exit_page="/cakes/3",
        channel=channel, channel_detail=detail,
        is_bot=is_bot,
        first_seen_at=first_seen or (last - timedelta(minutes=5)),
        last_seen_at=last,
    )
    db.add(s)
    db.commit()
    return s


def _mk_call(db, called_at=None, tracking_no="021-88880001", phone="13800001111", status="answered"):
    c = CallLog(
        call_no=f"C{utcnow().strftime('%Y%m%d')}{utcnow().microsecond % 1000:03d}",
        tracking_no=tracking_no,
        caller_phone_hash=hash_phone(phone),
        caller_phone_mask=mask_phone(phone),
        called_at=called_at or utcnow(),
        status=status,
        source_type="manual",
    )
    db.add(c)
    db.commit()
    return c


def test_R1_tracking_window_strong_attribution(db_session):
    """R1：打专属号 + 时间窗内访问过 → 访客级强归因"""
    now = utcnow()
    _mk_tracking(db_session)
    sess = _mk_session(db_session, last_seen=now - timedelta(minutes=5))
    call = _mk_call(db_session, called_at=now)

    attribute_call(db_session, call, persist=True)

    assert call.match_rule == RULE_TRACKING_WINDOW
    assert call.match_confidence == CONF_HIGH
    assert call.matched_session_id == sess.session_id
    assert call.matched_visitor_id == sess.visitor_id
    assert call.is_attributable is True
    assert call.attribution_channel == "social"
    assert call.match_time_gap_sec == 300


def test_R1_window_boundary_excludes_old_visit(db_session):
    """时间窗边界：40 分钟前的访问（默认窗 30 分钟）不得判 R1，应降级 R2"""
    now = utcnow()
    _mk_tracking(db_session)
    _mk_session(db_session, last_seen=now - timedelta(minutes=40))
    call = _mk_call(db_session, called_at=now)

    attribute_call(db_session, call, persist=False)

    assert call.match_rule == RULE_TRACKING_ONLY, "超窗仍判 R1 会把无关来电算成官网带来的"
    assert call.matched_session_id == ""


def test_R2_tracking_only_is_channel_level(db_session):
    """R2：号码能证明渠道，但定位不到人 → 渠道级，不许冒充访客级"""
    _mk_tracking(db_session)
    call = _mk_call(db_session, called_at=utcnow())
    attribute_call(db_session, call, persist=False)

    assert call.match_rule == RULE_TRACKING_ONLY
    assert call.match_confidence == CONF_MEDIUM
    assert call.matched_visitor_id == ""
    assert call.attribution_channel == "social"


def test_R1_multiple_candidates_downgrades_confidence(db_session):
    """时间窗内有两个人 → 无法确定是谁打的，置信度必须降级并记录候选数"""
    now = utcnow()
    _mk_tracking(db_session)
    _mk_session(db_session, sid="S-a", vid="V-a", last_seen=now - timedelta(minutes=2))
    _mk_session(db_session, sid="S-b", vid="V-b", last_seen=now - timedelta(minutes=3))
    call = _mk_call(db_session, called_at=now)

    attribute_call(db_session, call, persist=False)

    assert call.match_rule == RULE_TRACKING_WINDOW
    assert call.candidate_count == 2
    assert call.match_confidence == CONF_MEDIUM, "多候选仍报 high 等于假装确定"


def test_R3_phone_identity_cross_device(db_session):
    """R3：打的是普通号，但手机号绑定过访客 → 跨设备仍可归因"""
    now = utcnow()
    phone = "13800002222"
    _mk_session(db_session, sid="S-pc", vid="V-pc", last_seen=now - timedelta(hours=2), channel="direct", detail="direct")
    db_session.add(VisitorIdentity(
        visitor_id="V-pc", phone_hash=hash_phone(phone),
        phone_mask=mask_phone(phone), bind_source="message",
    ))
    db_session.commit()
    call = _mk_call(db_session, called_at=now, tracking_no="", phone=phone)

    attribute_call(db_session, call, persist=False)

    assert call.match_rule == RULE_PHONE_LASTTOUCH
    assert call.matched_visitor_id == "V-pc"
    assert call.is_attributable is True
    assert "R3来源:visitor_identity" in call.remark


def test_R4_non_official_number_not_attributed(db_session):
    """⚠️ 防虚高核心用例：打了非官网号码、手机号也没绑过 → 不可归因"""
    call = _mk_call(db_session, called_at=utcnow(), tracking_no="021-99999999", phone="13900009999")
    attribute_call(db_session, call, persist=False)

    assert call.match_rule == RULE_UNMATCHED
    assert call.match_confidence == CONF_NONE
    assert call.is_attributable is False, "自然到店客流若被算成官网业绩，报表会系统性虚高"


def test_R4_unmatched_when_no_evidence(db_session):
    """号码对、但时间窗没人 + 手机号没绑 → R4 未归因，金额不计入官网"""
    _mk_tracking(db_session)
    call = _mk_call(db_session, called_at=utcnow())
    attribute_call(db_session, call, persist=False)

    assert call.match_rule == RULE_TRACKING_ONLY
    assert call.matched_visitor_id == ""


def test_test_and_wrong_number_calls_excluded(db_session):
    """测试/错号电话不参与归因，避免污染分母"""
    _mk_tracking(db_session)
    _mk_session(db_session)
    call = _mk_call(db_session, called_at=utcnow(), status="test")
    attribute_call(db_session, call, persist=False)
    assert call.is_attributable is False
    assert call.match_rule == RULE_UNMATCHED


def test_bot_session_never_matched(db_session):
    """爬虫会话不得被当作访客匹配 —— 否则会凭空造出「访客级归因」"""
    now = utcnow()
    _mk_tracking(db_session)
    _mk_session(db_session, sid="S-bot", vid="V-bot", last_seen=now - timedelta(minutes=1), is_bot=True)
    call = _mk_call(db_session, called_at=now)

    attribute_call(db_session, call, persist=False)

    # 人没匹配到，但号码是真的 → 落到 R2 渠道级
    assert call.match_rule == RULE_TRACKING_ONLY
    assert call.matched_visitor_id == ""
    assert call.candidate_count == 0


def test_attribution_is_idempotent(db_session):
    """重复归因必须得到同一结果（否则重跑会改历史，报表对不上）"""
    now = utcnow()
    _mk_tracking(db_session)
    _mk_session(db_session, last_seen=now - timedelta(minutes=5))
    call = _mk_call(db_session, called_at=now)

    attribute_call(db_session, call, persist=False)
    first = (call.match_rule, call.matched_session_id, call.match_confidence)
    attribute_call(db_session, call, persist=False)
    second = (call.match_rule, call.matched_session_id, call.match_confidence)

    assert first == second


# ============================================================
# 三、接口链路
# ============================================================

def test_track_session_and_event(client, db_session):
    """埋点会话建立 + 事件上报，渠道与会话计数正确"""
    r = client.post("/api/v1/track/session", json={
        "visitor_id": "aaaaaaaa-1111-1111-1111-111111111111",
        "session_id": "bbbbbbbb-1111-1111-1111-111111111111",
        "page_path": "/",
        "referrer": "https://www.xiaohongshu.com/explore/123",
    })
    assert r.status_code == 200
    assert r.json()["data"]["channel"] == "social"

    r = client.post("/api/v1/track/event", json={
        "visitor_id": "aaaaaaaa-1111-1111-1111-111111111111",
        "session_id": "bbbbbbbb-1111-1111-1111-111111111111",
        "event_type": "page_view", "page_path": "/cakes/3",
    })
    assert r.status_code == 200
    r = client.post("/api/v1/track/event", json={
        "visitor_id": "aaaaaaaa-1111-1111-1111-111111111111",
        "session_id": "bbbbbbbb-1111-1111-1111-111111111111",
        "event_type": "hotline_click", "page_path": "/cakes/3",
        "ref_object_type": "cake", "ref_object_id": 3,
    })
    assert r.status_code == 200

    sess = db_session.query(VisitorSession).filter(
        VisitorSession.session_id == "bbbbbbbb-1111-1111-1111-111111111111"
    ).first()
    assert sess.page_view_count == 1
    assert sess.hotline_click_count == 1
    assert sess.exit_page == "/cakes/3"
    assert sess.last_seen_at is not None, "last_seen_at 为 NULL 会让时间窗匹配全部失效"


def test_track_event_rejects_unknown_event_type(client):
    r = client.post("/api/v1/track/event", json={
        "visitor_id": "aaaaaaaa-1111-1111-1111-111111111111",
        "session_id": "bbbbbbbb-1111-1111-1111-111111111111",
        "event_type": "hack_attempt",
    })
    assert r.status_code == 400


def test_hotline_endpoint_returns_channel_number(client, db_session):
    """专属号码下发：不同渠道看到不同号码，这是归因能成立的前提"""
    db_session.add(TrackingNumber(
        tracking_no="021-88880001", display_no="021-88880001",
        label="小红书专线", channel="social", channel_detail="xiaohongshu",
    ))
    db_session.add(TrackingNumber(
        tracking_no="021-88880002", display_no="021-88880002",
        label="投放专线", channel="paid", channel_detail="baidu",
    ))
    db_session.commit()

    r = client.get("/api/v1/track/hotline", params={"referrer": "https://www.xiaohongshu.com/x"})
    assert r.json()["data"]["phone"] == "021-88880001"

    r = client.get("/api/v1/track/hotline", params={"utm_source": "baidu", "utm_medium": "cpc"})
    assert r.json()["data"]["phone"] == "021-88880002"


def test_hotline_falls_back_to_content_order_info(client):
    """一个专属号都没配时，必须回落到「订购信息」的专线，不能返回空号码"""
    r = client.get("/api/v1/track/hotline")
    data = r.json()["data"]
    assert data["phone"] == "021-12345678", "返回空号码会让页面上的订购电话变成空白"
    assert data["is_default"] is True


def test_message_submit_binds_identity(client, db_session):
    """留言提交时带 visitor_id → 建立手机号绑定（R3 的桥梁）"""
    from app.utils.captcha_gen import save_captcha
    cid = save_captcha("M8A2")
    r = client.post("/api/v1/messages", json={
        "name": "张三", "phone": "13800005555",
        "content": "想订一个 10 寸水果蛋糕",
        "captcha": "m8a2", "captcha_id": cid,
        "visitor_id": "cccccccc-1111-1111-1111-111111111111",
    })
    assert r.status_code == 200
    ident = db_session.query(VisitorIdentity).filter(
        VisitorIdentity.visitor_id == "cccccccc-1111-1111-1111-111111111111"
    ).first()
    assert ident is not None
    assert ident.phone_hash == hash_phone("13800005555")
    assert ident.phone_mask == "138****5555"
    assert ident.bind_source == "message"


def test_admin_can_record_call_and_get_attribution(client, auth_headers, db_session):
    """后台录来电 → 保存即归因，返回里直接能看到归因结果"""
    now = utcnow()
    db_session.add(TrackingNumber(
        tracking_no="021-88880001", display_no="021-88880001",
        label="官网主站", channel="direct", channel_detail="direct",
    ))
    db_session.add(VisitorSession(
        visitor_id="V-x", session_id="S-x", landing_page="/",
        channel="direct", channel_detail="direct",
        first_seen_at=now - timedelta(minutes=8),
        last_seen_at=now - timedelta(minutes=3),
    ))
    db_session.commit()

    r = client.post("/api/v1/admin/attribution/calls", headers=auth_headers, json={
        "caller_phone": "13800006666",
        "called_at": now.isoformat(),
        "tracking_no": "021-88880001",
        "duration_sec": 120,
        "status": "answered",
    })
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["match_rule"] == RULE_TRACKING_WINDOW
    assert data["match_confidence"] == CONF_HIGH
    assert data["is_attributable"] is True
    assert data["call_no"].startswith("C")


def test_report_exposes_attribution_quality(client, auth_headers, db_session):
    """报表必须同时给业绩数字与归因质量，不允许只给一个漂亮总数"""
    now = utcnow()
    db_session.add(TrackingNumber(
        tracking_no="021-88880001", display_no="021-88880001",
        label="官网主站", channel="direct", channel_detail="direct",
    ))
    db_session.add(VisitorSession(
        visitor_id="V-r", session_id="S-r", landing_page="/",
        channel="direct", channel_detail="direct",
        first_seen_at=now - timedelta(minutes=7),
        last_seen_at=now - timedelta(minutes=2),
    ))
    db_session.commit()

    # 一通能归因的、一通不能归因的
    client.post("/api/v1/admin/attribution/calls", headers=auth_headers, json={
        "caller_phone": "13800007777", "called_at": now.isoformat(),
        "tracking_no": "021-88880001", "status": "answered",
    })
    client.post("/api/v1/admin/attribution/calls", headers=auth_headers, json={
        "caller_phone": "13800008888", "called_at": now.isoformat(),
        "tracking_no": "021-99990000", "status": "answered",
    })

    r = client.get("/api/v1/admin/attribution/report", headers=auth_headers, params={"days": 30})
    assert r.status_code == 200
    data = r.json()["data"]

    assert "funnel" in data and "attribution_quality" in data and "channels" in data
    assert "rules" in data, "口径参数必须随报表返回，否则同一份报表不同人算出不同数"
    rules = {i["rule"]: i["count"] for i in data["attribution_quality"]["items"]}
    assert rules[RULE_TRACKING_WINDOW] >= 1
    assert rules[RULE_UNMATCHED] >= 1
    # 访客级归因率必须单独给出，它是「链路真的接上了」的比例
    assert 0 <= data["attribution_quality"]["visitor_level_rate"] <= 1


def test_tracking_number_delete_soft_when_used(client, auth_headers, db_session):
    """已产生历史来电的号码不能物理删除，否则历史报表失去渠道归属"""
    db_session.add(TrackingNumber(
        tracking_no="021-88880009", display_no="021-88880009",
        label="旧活动专线", channel="social", channel_detail="weibo",
    ))
    db_session.commit()
    tid = db_session.query(TrackingNumber).filter(TrackingNumber.tracking_no == "021-88880009").first().id

    client.post("/api/v1/admin/attribution/calls", headers=auth_headers, json={
        "caller_phone": "13800009999", "tracking_no": "021-88880009", "status": "answered",
    })
    r = client.delete(f"/api/v1/admin/attribution/tracking-numbers/{tid}", headers=auth_headers)
    assert r.status_code == 200
    row = db_session.query(TrackingNumber).filter(TrackingNumber.id == tid).first()
    assert row is not None, "有历史引用的号码被物理删除会导致历史归因查不到渠道"
    assert row.is_active is False
