# -*- coding: utf-8 -*-
"""端到端验证：转化归因链路 + 发布保护机制

不是在测单个函数，而是模拟真实业务流，验证「链路真的接上了」：
  访客带渠道 → 页面看到专属号 → 点击热线 → 接线员录来电 → 归因命中 → 报表可见

运行：python tools/verify_attribution_publish.py
"""
import os
import sys
import tempfile
from datetime import timedelta

DB = os.path.join(tempfile.gettempdir(), "e2e_verify.db")
os.environ["MAI_ISLE_DB_PATH"] = DB
if os.path.exists(DB):
    os.remove(DB)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

from fastapi.testclient import TestClient  # noqa: E402

from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import AdminUser, utcnow  # noqa: E402
from app.security import create_token, hash_password  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  ← {detail}" if detail and not cond else ""))


def main():
    init_db()

    # 建超管（绕过验证码登录，直连 DB）
    from app.database import SessionLocal
    db = SessionLocal()
    if not db.query(AdminUser).filter(AdminUser.username == "admin").first():
        db.add(AdminUser(username="admin", name="系统管理员",
                         password_hash=hash_password("admin123"), role="super", is_active=True))
        db.commit()
    admin = db.query(AdminUser).filter(AdminUser.username == "admin").first()
    token = create_token(admin.id, admin.role)
    db.close()
    H = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as c:
        print("\n" + "=" * 66)
        print("一、转化归因链路")
        print("=" * 66)

        # ---------- 1. 配两个渠道专属号 ----------
        print("\n[1] 配置渠道专属号码")
        for no, label, ch, detail in [
            ("021-6666-1001", "小红书渠道专线", "social", "xiaohongshu"),
            ("021-6666-1002", "门店海报二维码专线", "qr_offline", "qr"),
        ]:
            r = c.post("/api/v1/admin/attribution/tracking-numbers", headers=H, json={
                "tracking_no": no, "display_no": no, "label": label,
                "channel": ch, "channel_detail": detail, "is_active": True,
            })
            check(f"新建专属号 {no}", r.status_code == 200, r.text[:80])

        # ---------- 2. 不同渠道的访客看到不同号码 ----------
        print("\n[2] 页面号码随渠道变化（归因能成立的前提）")
        r1 = c.get("/api/v1/track/hotline", params={"referrer": "https://www.xiaohongshu.com/explore/abc"})
        p1 = r1.json()["data"]["phone"]
        check("小红书访客看到小红书专线", p1 == "021-6666-1001", str(r1.json()["data"]))

        r2 = c.get("/api/v1/track/hotline", params={"utm_source": "qr", "utm_medium": "qr", "utm_campaign": "store_jingan"})
        p2 = r2.json()["data"]["phone"]
        check("扫码访客看到二维码专线", p2 == "021-6666-1002", str(r2.json()["data"]))

        r3 = c.get("/api/v1/track/hotline", params={"referrer": ""})
        p3 = r3.json()["data"]["phone"]
        check("无渠道访客拿到兜底号码（不为空）", bool(p3), str(r3.json()["data"]))

        # ---------- 3. 访客访问行为 ----------
        print("\n[3] 埋点：访客浏览与热线点击")
        VID = "visitor-aaaa-0001"
        SID = "session-aaaa-0001"
        r = c.post("/api/v1/track/session", json={
            "visitor_id": VID, "session_id": SID, "page_path": "/",
            "referrer": "https://www.xiaohongshu.com/explore/abc",
        })
        check("会话建立且渠道识别为 social", r.json()["data"]["channel"] == "social", str(r.json()["data"]))

        for ev, page, obj in [
            ("page_view", "/", None),
            ("page_view", "/cakes", None),
            ("cake_view", "/cakes/3", 3),
            ("hotline_click", "/cakes/3", 3),
        ]:
            body = {"visitor_id": VID, "session_id": SID, "event_type": ev, "page_path": page}
            if obj:
                body["ref_object_type"] = "cake"
                body["ref_object_id"] = obj
            c.post("/api/v1/track/event", json=body)

        db = SessionLocal()
        from app.models_attribution import VisitEvent, VisitorSession
        sess = db.query(VisitorSession).filter(VisitorSession.session_id == SID).first()
        n_ev = db.query(VisitEvent).filter(VisitEvent.session_id == SID).count()
        db.close()
        check("会话记录页面数与热线点击", sess.page_view_count == 2 and sess.hotline_click_count == 1,
              f"page_view={sess.page_view_count}, hotline={sess.hotline_click_count}")
        check("行为事件已落库（4 条）", n_ev == 4, f"实际 {n_ev}")

        # ---------- 4. 接线员录来电 → 自动归因 ----------
        print("\n[4] 录来电 → 保存即归因（R1 强归因）")

        # ⚠️ 时间先后必须自洽：真实顺序是「顾客先浏览 → 打电话 → 挂断后接线员录单」。
        #    上面几步的会话是"此刻"建的，而下面要把 called_at 倒填 2 分钟来模拟
        #    录单延迟 —— 若不一起倒填会话时间，就变成了"先打电话、后访问官网"，
        #    R1（要求会话开始早于来电）当然判不中。测试里只能倒填，真实环境天然成立。
        db = SessionLocal()
        sess_row = db.query(VisitorSession).filter(VisitorSession.session_id == SID).first()
        sess_row.first_seen_at = utcnow() - timedelta(minutes=10)   # 已浏览 10 分钟
        sess_row.last_seen_at = utcnow() - timedelta(minutes=3)     # 最后动作在 3 分钟前
        db.query(VisitEvent).filter(VisitEvent.session_id == SID).update(
            {"occurred_at": utcnow() - timedelta(minutes=10)}
        )
        db.commit()
        db.close()

        called_at = utcnow()
        r = c.post("/api/v1/admin/attribution/calls", headers=H, json={
            "caller_phone": "13800001234",
            # 模拟「挂断后 2 分钟才录单」的平均操作延迟
            "called_at": (called_at - timedelta(minutes=2)).isoformat(),
            "tracking_no": "021-6666-1001",
            "duration_sec": 195,
            "status": "answered",
        })
        d = r.json()["data"]
        check("归因规则 = R1（追踪号+时间窗）", d["match_rule"] == "R1_TRACKING_WINDOW", str(d))
        check("置信度 = high", d["match_confidence"] == "high", str(d))
        check("匹配到具体访客", d["matched_visitor_id"] == VID, str(d))
        check("归因渠道 = social", d["attribution_channel"] == "social", str(d))
        check("标记为可归因", d["is_attributable"] is True, str(d))
        # 访客在录单时仍在站内活动 → 时间差为负是正常的，不应被当成异常
        gap = d["match_time_gap_sec"]
        check("时间差记录了真实间隔（允许为负=仍在站内）", isinstance(gap, int) and gap <= 300, f"gap={gap}")

        # ---------- 5. 防虚高：打门店普通号的来电 ----------
        print("\n[5] 防虚高：非官网号码不得算作官网业绩")
        r = c.post("/api/v1/admin/attribution/calls", headers=H, json={
            "caller_phone": "13900005678",
            "called_at": utcnow().isoformat(),
            "tracking_no": "021-0000-0000",   # 门店普通号，不是任何专属号
            "status": "answered",
        })
        d2 = r.json()["data"]
        check("非官网号 → R4 未归因", d2["match_rule"] == "R4_UNMATCHED", str(d2))
        check("非官网号 → is_attributable=False", d2["is_attributable"] is False, str(d2))

        # ---------- 6. 跨设备：手机号回溯 ----------
        print("\n[6] 跨设备归因：留言留过手机号 → 换设备也能认出来")
        from app.utils.captcha_gen import save_captcha
        cid = save_captcha("M8A2")
        VID2, SID2 = "visitor-bbbb-0002", "session-bbbb-0002"
        c.post("/api/v1/track/session", json={
            "visitor_id": VID2, "session_id": SID2, "page_path": "/contact", "referrer": "",
        })
        r = c.post("/api/v1/messages", json={
            "name": "李四", "phone": "13700007777", "content": "想订十寸蛋糕",
            "captcha": "m8a2", "captcha_id": cid, "visitor_id": VID2, "session_id": SID2,
        })
        check("留言提交并绑定访客身份", r.status_code == 200, r.text[:80])

        # 两小时后用座机打门店号 → 靠手机号回溯归因
        r = c.post("/api/v1/admin/attribution/calls", headers=H, json={
            "caller_phone": "13700007777",
            "called_at": utcnow().isoformat(),
            "tracking_no": "",
            "status": "answered",
        })
        d3 = r.json()["data"]
        check("手机号回溯命中 R3", d3["match_rule"] == "R3_PHONE_LASTTOUCH", str(d3))
        check("归因到留言的那个访客", d3["matched_visitor_id"] == VID2, str(d3))

        # ---------- 7. 报表 ----------
        print("\n[7] 归因报表（业绩 + 归因质量并排）")
        r = c.get("/api/v1/admin/attribution/report", headers=H, params={"days": 30})
        rep = r.json()["data"]
        funnel = rep["funnel"]
        quality = rep["attribution_quality"]
        print(f"      漏斗：有效会话 {funnel['sessions']} → 热线点击 {funnel['hotline_clicks']} "
              f"→ 来电 {funnel['calls']}（可归因 {funnel['calls_attributed']}）")
        print(f"      归因质量：访客级归因率 {quality['visitor_level_rate']:.0%}")
        for it in quality["items"]:
            print(f"        {it['rule']:<22} {it['count']:>3} 通  {it['ratio']:.0%}")
        check("报表含漏斗", funnel["sessions"] >= 2 and funnel["hotline_clicks"] >= 1, str(funnel))
        check("报表含归因质量四级", len(quality["items"]) == 4, str(len(quality["items"])))
        check("访客级归因率已计算", isinstance(quality["visitor_level_rate"], float), str(quality))
        check("报表附带规则口径", "session_window_minutes" in rep["rules"], str(rep.get("rules")))
        check("分渠道明细非空", len(rep["channels"]) >= 1, str(rep["channels"]))

        # ---------- 8. 时间窗边界 ----------
        print("\n[8] 时间窗边界：超窗不得判 R1")
        r = c.post("/api/v1/admin/attribution/calls", headers=H, json={
            "caller_phone": "13600001111",
            "called_at": (utcnow() + timedelta(hours=3)).isoformat(),  # 会话早已超时
            "tracking_no": "021-6666-1001",
            "status": "answered",
        })
        d4 = r.json()["data"]
        check("超窗降级为 R2 渠道级", d4["match_rule"] == "R2_TRACKING_ONLY", str(d4))
        check("R2 不冒充访客级（matched_visitor 为空）", d4["matched_visitor_id"] == "", str(d4))

        print("\n" + "=" * 66)
        print("二、发布保护机制")
        print("=" * 66)

        # ---------- 1. 基线 ----------
        print("\n[1] 版本基线与草稿隔离")
        r = c.get("/api/v1/admin/content/brand_story/versions", headers=H)
        check("首次访问自动建立 v1 基线", r.json()["data"]["current_version"] == 1, str(r.json()["data"]))

        before = c.get("/api/v1/content/brand_story").json()["data"]["value"]
        r = c.post("/api/v1/admin/content/brand_story/draft", headers=H,
                   json={"value": "# 新品牌故事\n\n这是草稿版内容。", "change_summary": "重写品牌故事"})
        check("保存草稿成功", r.status_code == 200, r.text[:80])
        draft_vid = r.json()["data"]["version_id"]
        after = c.get("/api/v1/content/brand_story").json()["data"]["value"]
        check("草稿不影响线上（顾客看到的仍是旧版）", before == after, f"before={before[:20]!r} after={after[:20]!r}")

        # ---------- 2. 预览 ----------
        print("\n[2] 预览：能看到草稿，但线上未变")
        r = c.post("/api/v1/admin/content/brand_story/preview-token", headers=H, json={"version_id": draft_vid})
        pv = r.json()["data"]
        check("生成预览令牌", bool(pv.get("token")), str(pv)[:80])
        check("预览链接用 URL search 传参（HashRouter 不会 404）",
              pv["preview_url"].startswith("/?"), pv["preview_url"])

        r = c.get("/api/v1/content/brand_story", params={"preview_token": pv["token"]})
        d = r.json()["data"]
        check("带令牌读到草稿内容", d["preview"] is True and "草稿版" in str(d["value"]), str(d)[:100])
        check("线上内容仍未改变",
              c.get("/api/v1/content/brand_story").json()["data"]["value"] == before)

        r = c.get("/api/v1/content/brand_value", params={"preview_token": pv["token"]})
        check("令牌与 key 强绑定（拿 A 的令牌看不了 B）",
              r.json()["data"]["preview"] is False, str(r.json()["data"])[:80])

        # ---------- 3. 发布 ----------
        print("\n[3] 发布：生效 + 留痕 + 必填变更说明")
        r = c.post("/api/v1/admin/content/brand_story/publish", headers=H,
                   json={"version_id": draft_vid, "change_summary": ""})
        check("变更为空时拒绝发布", r.status_code == 400, r.text[:80])

        r = c.post("/api/v1/admin/content/brand_story/publish", headers=H,
                   json={"version_id": draft_vid, "change_summary": "重写品牌故事，突出十年手作"})
        check("填写说明后发布成功", r.status_code == 200, r.text[:80])
        live = c.get("/api/v1/content/brand_story").json()["data"]["value"]
        check("发布后线上立即生效", "草稿版" in live, live[:40])

        r = c.get("/api/v1/content/brand_story", params={"preview_token": pv["token"]})
        check("发布后旧预览链接立即失效", r.json()["data"]["preview"] is False, str(r.json()["data"])[:80])

        # ---------- 4. 回滚 ----------
        print("\n[4] 回滚：用旧内容造新版本（版本链只增不减）")
        r = c.post("/api/v1/admin/content/brand_story/rollback", headers=H,
                   json={"target_version": 1, "reason": ""})
        check("回滚原因必填", r.status_code == 400, r.text[:80])

        r = c.post("/api/v1/admin/content/brand_story/rollback", headers=H,
                   json={"target_version": 1, "reason": "客户反馈新文案口径不对"})
        check("回滚成功", r.status_code == 200, r.text[:80])
        rb = r.json()["data"]
        check("回滚产生新版本号（不是拨指针回 v1）", rb["version"] > 1, str(rb))
        check("内容确实回到 v1", c.get("/api/v1/content/brand_story").json()["data"]["value"] == before)
        check("记录内容来源版本 = v1", rb["rollback_from_version"] == 1, str(rb))

        items = c.get("/api/v1/admin/content/brand_story/versions", headers=H).json()["data"]["items"]
        vers = sorted(i["version"] for i in items)
        check("版本链完整、无删除、无重号", len(vers) == len(set(vers)) and 1 in vers and rb["version"] in vers, str(vers))

        # 回滚可再回滚
        r = c.post("/api/v1/admin/content/brand_story/rollback", headers=H,
                   json={"target_version": draft_vid and 2, "reason": "撤销上次回滚，恢复新文案"})
        check("回滚本身也能被回滚", r.status_code == 200, r.text[:80])

        # ---------- 5. 并发冲突 ----------
        print("\n[5] 并发冲突：不允许静默覆盖别人的修改")
        r = c.post("/api/v1/admin/content/brand_story/draft", headers=H,
                   json={"value": "A 写的文案", "change_summary": "A 的草稿"})
        a_vid = r.json()["data"]["version_id"]
        # 期间他人通过「保存即生效」改了线上
        c.put("/api/v1/admin/content/brand_story", headers=H, json={"value": "B 直接改的文案"})
        r = c.post("/api/v1/admin/content/brand_story/publish", headers=H,
                   json={"version_id": a_vid, "change_summary": "A 发布"})
        check("版本冲突被拒（409）", r.status_code == 409, f"{r.status_code} {r.text[:80]}")
        check("冲突时线上内容未被覆盖",
              c.get("/api/v1/content/brand_story").json()["data"]["value"] == "B 直接改的文案")

        # ---------- 6. 快速通道也留痕 ----------
        print("\n[6] 快速通道（保存即生效）也必须进版本表")
        items = c.get("/api/v1/admin/content/brand_story/versions", headers=H).json()["data"]["items"]
        check("直接保存产生了版本记录", len(items) >= 4, f"版本数 {len(items)}")
        cur = next((i for i in items if i["is_current"]), None)
        check("当前版本标记为快速通道", cur and "快速通道" in cur["change_summary"], str(cur))

        # ---------- 7. 下线 ----------
        print("\n[7] 紧急下线：区块消失但内容仍在历史里")
        r = c.post("/api/v1/admin/content/brand_story/offline", headers=H,
                   json={"reason": "文案有错别字，先撤下"})
        check("下线成功", r.status_code == 200, r.text[:80])
        check("前台区块内容已置空", c.get("/api/v1/content/brand_story").json()["data"]["value"] == "")
        items2 = c.get("/api/v1/admin/content/brand_story/versions", headers=H).json()["data"]["items"]
        check("下线后版本历史仍完整可查", len(items2) == len(items), f"{len(items2)} vs {len(items)}")

        # ---------- 8. 审计日志 ----------
        print("\n[8] 审计日志：五类动作 + 失败记录")
        logs = c.get("/api/v1/admin/content/publish-logs", headers=H,
                     params={"key": "brand_story"}).json()["data"]["items"]
        actions = {g["action"] for g in logs}
        check("覆盖 存草稿/预览/发布/回滚/下线", {"save_draft", "preview", "publish", "rollback", "offline"} <= actions, str(actions))
        check("失败记录也留痕", any(g["result"] == "failed" for g in logs), str([g["action"] for g in logs if g["result"] == "failed"]))
        check("每步都有操作人", all(g["operator_name"] for g in logs))

        # ---------- 9. 计数口径交叉核对 ----------
        print("\n[9] 交叉核对：归因总数 = 各级之和")
        # ⚠️ 必须重新取一次报表：[7] 之后又录了两通电话，
        #    拿旧快照去核对只会得出「对不上」的假结论。
        rep2 = c.get("/api/v1/admin/attribution/report", headers=H, params={"days": 30}).json()["data"]
        db = SessionLocal()
        from app.models_attribution import CallLog
        total_call = db.query(CallLog).count()
        db.close()
        sum_rules = sum(i["count"] for i in rep2["attribution_quality"]["items"])
        check("R1~R4 之和 = 来电总数", sum_rules == total_call, f"{sum_rules} vs {total_call}")
        check("可归因数 ≤ 来电总数",
              rep2["funnel"]["calls_attributed"] <= rep2["funnel"]["calls"],
              f"{rep2['funnel']['calls_attributed']} vs {rep2['funnel']['calls']}")

    print("\n" + "=" * 66)
    print(f"结果：{len(PASS)} 项通过，{len(FAIL)} 项失败")
    if FAIL:
        print("失败项：")
        for f in FAIL:
            print("  -", f)
    print("=" * 66)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
