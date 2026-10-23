# ============================================================
# 文件功能：后台归因管理（需登录）
#   ① 官网专属号码维护 —— 归因链路的锚点
#   ② 来电录入 —— 写入即触发归因，保存四级规则结果
#   ③ 归因报表 —— 漏斗 + 归因质量 + 分渠道明细
#   ④ 规则配置 —— 时间窗等参数运营可调
#
# 报表设计的一条铁律：
#   **归因质量必须和业绩数字并排展示，不能只给一个漂亮的总数。**
#   如果只报「官网带来 95 单」，没人知道里面有 30 单只是「打了个普通号、
#   恰好手机号匹配上」，决策会被高估的转化率带偏。所以报表里 R1/R2/R3/R4
#   四级占比与「访客级归因率」必须同时出现。
# ============================================================

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Category, Order
from app.models_attribution import (
    AttributionRule,
    CallLog,
    OrderAttribution,
    TrackingNumber,
    VisitEvent,
    VisitorSession,
)
from app.utils.attribution import (
    CONF_HIGH,
    RULE_LABELS,
    RULE_PHONE_LASTTOUCH,
    RULE_TRACKING_ONLY,
    RULE_TRACKING_WINDOW,
    RULE_UNMATCHED,
    attribute_call,
    attribute_order,
    get_rules,
    hash_phone,
    mask_phone,
)
from app.utils.response import bad_request, conflict, not_found, ok

router = APIRouter()


def _next_call_no(db: Session) -> str:
    """生成来电编号：C + YYYYMMDD + 3 位当日序号（与订单号同思路，便于人工对账）"""
    from app.models import utcnow
    stamp = utcnow().strftime("%Y%m%d")
    prefix = f"C{stamp}"
    last = (
        db.query(CallLog.call_no)
        .filter(CallLog.call_no.like(f"{prefix}%"))
        .order_by(CallLog.call_no.desc())
        .first()
    )
    seq = int(last[0][-3:]) + 1 if last else 1
    return f"{prefix}{seq:03d}"


# ============================================================
# 一、官网专属号码
# ============================================================

CHANNELS = ["direct", "organic_search", "social", "paid", "qr_offline", "sms", "referral", "unknown"]


class TrackingIn(BaseModel):
    tracking_no: str = Field(description="追踪号码（唯一，来电时靠它反查渠道）", max_length=20)
    display_no: str = Field(default="", max_length=20, description="页面展示号码，留空则同追踪号")
    label: str = Field(max_length=50)
    channel: str = Field(description="渠道：" + "/".join(CHANNELS))
    channel_detail: str = Field(default="", max_length=30, description="细分，如 xiaohongshu / baidu")
    campaign: str = Field(default="", max_length=50)
    is_active: bool = True
    remark: str = Field(default="", max_length=200)

    @field_validator("tracking_no")
    @classmethod
    def _v_no(cls, v: str) -> str:
        v = (v or "").strip()
        if not (3 <= len(v) <= 20):
            raise ValueError("追踪号码长度需为 3-20 位")
        return v

    @field_validator("channel")
    @classmethod
    def _v_channel(cls, v: str) -> str:
        if v not in CHANNELS:
            raise ValueError("渠道不在允许范围内")
        return v


@router.get("/attribution/tracking-numbers", summary="专属号码列表")
def list_tracking(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(TrackingNumber).order_by(TrackingNumber.id.asc()).all()
    return ok({"items": [
        {
            "id": r.id, "tracking_no": r.tracking_no, "display_no": r.display_no,
            "label": r.label, "channel": r.channel, "channel_detail": r.channel_detail,
            "campaign": r.campaign, "is_active": bool(r.is_active), "remark": r.remark,
        }
        for r in rows
    ]})


@router.post("/attribution/tracking-numbers", summary="新增专属号码")
def create_tracking(payload: TrackingIn, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """新增渠道专属号码。号码唯一 —— 同一个号绑两个渠道，归因就永远说不清。"""
    exists = db.query(TrackingNumber).filter(TrackingNumber.tracking_no == payload.tracking_no).first()
    if exists:
        raise conflict("该追踪号码已存在")
    row = TrackingNumber(
        tracking_no=payload.tracking_no,
        display_no=(payload.display_no or payload.tracking_no).strip(),
        label=payload.label, channel=payload.channel,
        channel_detail=payload.channel_detail, campaign=payload.campaign,
        is_active=payload.is_active, remark=payload.remark,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return ok({"id": row.id})


@router.put("/attribution/tracking-numbers/{tid}", summary="编辑专属号码")
def update_tracking(tid: int, payload: TrackingIn, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(TrackingNumber, tid)
    if not row:
        raise not_found("号码不存在")
    dup = (
        db.query(TrackingNumber)
        .filter(TrackingNumber.tracking_no == payload.tracking_no, TrackingNumber.id != tid)
        .first()
    )
    if dup:
        raise conflict("该追踪号码已被其他记录使用")
    row.tracking_no = payload.tracking_no
    row.display_no = (payload.display_no or payload.tracking_no).strip()
    row.label = payload.label
    row.channel = payload.channel
    row.channel_detail = payload.channel_detail
    row.campaign = payload.campaign
    row.is_active = payload.is_active
    row.remark = payload.remark
    db.commit()
    return ok({"id": row.id})


@router.delete("/attribution/tracking-numbers/{tid}", summary="删除专属号码")
def delete_tracking(tid: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(TrackingNumber, tid)
    if not row:
        raise not_found("号码不存在")
    # 有历史来电引用的号码不物理删除，改为停用 —— 否则历史报表会失去渠道归属
    used = db.query(CallLog).filter(CallLog.tracking_no == row.tracking_no).first()
    if used:
        row.is_active = False
        db.commit()
        return ok(None, "该号码已有历史来电记录，已改为停用（保留历史归因可查）")
    db.delete(row)
    db.commit()
    return ok(None, "success")


# ============================================================
# 二、来电录入（写入即归因）
# ============================================================

class CallIn(BaseModel):
    caller_phone: str = Field(description="主叫号码（存哈希+掩码，不落明文）")
    called_at: Optional[datetime] = Field(default=None, description="来电时间，不传=当前时间")
    tracking_no: str = Field(default="", max_length=20, description="被拨打的官网专属号，空=打的非官网号")
    duration_sec: int = Field(default=0, ge=0)
    status: str = Field(default="answered", description="answered/missed/wrong_number/test")
    remark: str = Field(default="", max_length=500)

    @field_validator("caller_phone")
    @classmethod
    def _v_phone(cls, v: str) -> str:
        import re
        v = (v or "").strip()
        # 允许手机号与固定电话（带区号横线），统一去掉非数字字符后校验
        digits = re.sub(r"\D", "", v)
        if not (7 <= len(digits) <= 15):
            raise ValueError("请输入有效的来电号码")
        return v

    @field_validator("status")
    @classmethod
    def _v_status(cls, v: str) -> str:
        if v not in ("answered", "missed", "wrong_number", "test"):
            raise ValueError("通话状态不合法")
        return v


@router.post("/attribution/calls", summary="录入手电（保存即自动归因）")
def create_call(payload: CallIn, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """录入一通来电，**保存时立即执行四级归因**，结果一并返回。

    返回里带 match_rule 与 match_confidence，录入的人当场就能看到这通电话
    「被算到谁头上、凭什么这么算」，不用等报表出来才发现归错了。
    """
    import re
    from app.models import utcnow

    digits = re.sub(r"\D", "", payload.caller_phone)
    call = CallLog(
        call_no=_next_call_no(db),
        tracking_no=(payload.tracking_no or "").strip(),
        caller_phone_hash=hash_phone(digits),
        caller_phone_mask=mask_phone(digits),
        called_at=payload.called_at or utcnow(),
        duration_sec=payload.duration_sec,
        status=payload.status,
        source_type="manual",
        remark=payload.remark,
        operator=current_user.name,
    )
    db.add(call)
    db.commit()
    db.refresh(call)

    attribute_call(db, call, persist=True)

    return ok({
        "id": call.id,
        "call_no": call.call_no,
        "match_rule": call.match_rule,
        "match_rule_label": RULE_LABELS.get(call.match_rule, call.match_rule),
        "match_confidence": call.match_confidence,
        "is_attributable": bool(call.is_attributable),
        "attribution_channel": call.attribution_channel,
        "attribution_channel_detail": call.attribution_channel_detail,
        "matched_visitor_id": call.matched_visitor_id,
        "match_time_gap_sec": call.match_time_gap_sec,
        "candidate_count": call.candidate_count,
    }, "来电已录入并完成归因")


@router.get("/attribution/calls", summary="来电列表")
def list_calls(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    rule: Optional[str] = Query(None, description="按归因规则过滤"),
    channel: Optional[str] = Query(None, description="按渠道过滤"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(CallLog)
    if rule:
        q = q.filter(CallLog.match_rule == rule)
    if channel:
        q = q.filter(CallLog.attribution_channel == channel)
    total = q.count()
    rows = q.order_by(CallLog.called_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ok({
        "items": [
            {
                "id": r.id, "call_no": r.call_no,
                "caller_phone_mask": r.caller_phone_mask,
                "tracking_no": r.tracking_no,
                "called_at": r.called_at.isoformat() if r.called_at else None,
                "duration_sec": r.duration_sec, "status": r.status,
                "match_rule": r.match_rule,
                "match_rule_label": RULE_LABELS.get(r.match_rule, r.match_rule),
                "match_confidence": r.match_confidence,
                "is_attributable": bool(r.is_attributable),
                "attribution_channel": r.attribution_channel,
                "attribution_channel_detail": r.attribution_channel_detail,
                "match_time_gap_sec": r.match_time_gap_sec,
                "candidate_count": r.candidate_count,
                "operator": r.operator, "remark": r.remark,
            }
            for r in rows
        ],
        "total": total, "page": page, "page_size": page_size,
    })


@router.post("/attribution/calls/{call_id}/reattribute", summary="重新归因单条来电")
def reattribute(call_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """重跑归因（例：先录了来电、后补了专属号码配置）。

    就地更新该条记录并返回新结果。注意这会让**历史报表数字变化**，
    所以返回里明确告知：如需保留旧结论，应先导出报表。
    """
    call = db.get(CallLog, call_id)
    if not call:
        raise not_found("来电记录不存在")
    old = {"rule": call.match_rule, "channel": call.attribution_channel}
    attribute_call(db, call, persist=True)
    return ok({
        "old": old,
        "new": {"rule": call.match_rule, "channel": call.attribution_channel,
                "confidence": call.match_confidence, "visitor_id": call.matched_visitor_id},
    }, "已重新归因（历史报表口径会随之变化，请知悉）")


# ============================================================
# 三、归因报表
# ============================================================

@router.get("/attribution/report", summary="转化归因报表")
def attribution_report(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """「官网带来多少单」的唯一权威口径。

    返回四块：
      ① funnel          漏斗：有效会话 → 热线点击 → 来电 → 成单
      ② attribution_quality  归因质量：R1-R4 及各占比、访客级归因率
      ③ channels        分渠道明细（含转化率）
      ④ rules           当前生效的归因参数（口径透明，谁看都一样）
    """
    from app.models import utcnow

    end = utcnow()
    start = end - timedelta(days=days)

    # ---------- ① 漏斗 ----------
    # 分母明确排除 bot：机器流量进分母会把转化率系统性压低，指标失真
    sessions = (
        db.query(func.count(VisitorSession.id))
        .filter(VisitorSession.created_at >= start, VisitorSession.is_bot == False)  # noqa: E712
        .scalar() or 0
    )
    hotline_clicks = (
        db.query(func.count(VisitEvent.id))
        .filter(VisitEvent.occurred_at >= start, VisitEvent.event_type == "hotline_click")
        .scalar() or 0
    )
    calls_q = db.query(CallLog).filter(
        CallLog.called_at >= start,
        CallLog.status.notin_(["test", "wrong_number"]),
    )
    calls_total = calls_q.count()
    calls_attributed = calls_q.filter(CallLog.is_attributable == True).count()  # noqa: E712

    # ---------- ② 归因质量 ----------
    rule_counts = {
        row[0]: row[1]
        for row in db.query(CallLog.match_rule, func.count(CallLog.id))
        .filter(CallLog.called_at >= start, CallLog.status.notin_(["test", "wrong_number"]))
        .group_by(CallLog.match_rule)
        .all()
    }
    denom = max(calls_total, 1)
    quality = []
    for rule in (RULE_TRACKING_WINDOW, RULE_TRACKING_ONLY, RULE_PHONE_LASTTOUCH, RULE_UNMATCHED):
        cnt = int(rule_counts.get(rule, 0))
        quality.append({
            "rule": rule,
            "label": RULE_LABELS[rule],
            "count": cnt,
            "ratio": round(cnt / denom, 4),
        })
    # 访客级归因率 = 能定位到具体访客的来电占比（R1 + R3）。
    # 这是归因链路真正「接上了」的比例，比单看总数有意义得多。
    visitor_level = int(rule_counts.get(RULE_TRACKING_WINDOW, 0)) + int(rule_counts.get(RULE_PHONE_LASTTOUCH, 0))
    visitor_level_rate = round(visitor_level / denom, 4)

    # ---------- ③ 分渠道明细 ----------
    # 以「归因到渠道」的来电为口径，逐渠道带出成单与金额
    call_rows = {
        (r[0], r[1]): int(r[2])
        for r in db.query(
            CallLog.attribution_channel,
            CallLog.attribution_channel_detail,
            func.count(CallLog.id),
        )
        .filter(CallLog.called_at >= start, CallLog.is_attributable == True)  # noqa: E712
        .group_by(CallLog.attribution_channel, CallLog.attribution_channel_detail)
        .all()
    }
    sess_rows = {
        (r[0], r[1]): int(r[2])
        for r in db.query(
            VisitorSession.channel, VisitorSession.channel_detail, func.count(VisitorSession.id)
        )
        .filter(VisitorSession.created_at >= start, VisitorSession.is_bot == False)  # noqa: E712
        .group_by(VisitorSession.channel, VisitorSession.channel_detail)
        .all()
    }
    order_rows = {
        (r[0], r[1]): (int(r[2]), r[3])
        for r in db.query(
            OrderAttribution.attribution_channel,
            OrderAttribution.attribution_channel_detail,
            func.count(OrderAttribution.id),
            func.coalesce(func.sum(OrderAttribution.amount), 0),
        )
        .filter(OrderAttribution.created_at >= start)
        .group_by(OrderAttribution.attribution_channel, OrderAttribution.attribution_channel_detail)
        .all()
    }
    click_rows = {
        (r[0], r[1]): int(r[2] or 0)
        for r in db.query(
            VisitorSession.channel, VisitorSession.channel_detail, func.sum(VisitorSession.hotline_click_count)
        )
        .filter(VisitorSession.created_at >= start, VisitorSession.is_bot == False)  # noqa: E712
        .group_by(VisitorSession.channel, VisitorSession.channel_detail)
        .all()
    }

    channels = []
    for ch, detail in sorted(set(sess_rows) | set(call_rows) | set(order_rows),
                             key=lambda k: (-float(order_rows.get(k, (0, 0))[1] or 0), k[0])):
        s_cnt = sess_rows.get((ch, detail), 0)
        c_cnt = call_rows.get((ch, detail), 0)
        o_cnt, o_amt = order_rows.get((ch, detail), (0, 0))
        clicks = click_rows.get((ch, detail), 0)
        channels.append({
            "channel": ch,
            "channel_detail": detail,
            "sessions": s_cnt,
            "hotline_clicks": clicks,
            "calls": c_cnt,
            "orders": o_cnt,
            "amount": float(o_amt or 0),
            # 转化率 = 来电 / 有效会话，分母为 0 时给 None 而不是 0，
            # 避免「0/0 显示 0%」被误读成「渠道完全无效」
            "call_rate": round(c_cnt / s_cnt, 4) if s_cnt else None,
        })

    # ---------- ④ 当前规则口径 ----------
    return ok({
        "period": {"days": days, "start": start.isoformat(), "end": end.isoformat()},
        "funnel": {
            "sessions": int(sessions),
            "hotline_clicks": int(hotline_clicks),
            "calls": int(calls_total),
            "calls_attributed": int(calls_attributed),
            "orders": int(sum(int(v[0]) for v in order_rows.values())),
            "amount": float(sum(float(v[1] or 0) for v in order_rows.values())),
            "click_rate": round(int(hotline_clicks) / int(sessions), 4) if sessions else None,
            "call_rate": round(int(calls_attributed) / int(sessions), 4) if sessions else None,
        },
        "attribution_quality": {
            "items": quality,
            "visitor_level_count": int(visitor_level),
            "visitor_level_rate": visitor_level_rate,
            "note": "R2 为渠道级归因（定位不到具体访客），R4 不计入官网业绩；"
                    "对外报数请注明口径，勿把四级合计当作「官网带来」",
        },
        "channels": channels,
        "rules": get_rules(db),
    })


# ============================================================
# 四、规则配置
# ============================================================

class RuleUpdateIn(BaseModel):
    value: str = Field(max_length=100)


@router.get("/attribution/rules", summary="归因规则列表")
def list_rules(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    get_rules(db)  # 确保默认值已落库
    rows = db.query(AttributionRule).order_by(AttributionRule.id.asc()).all()
    return ok({"items": [
        {"key": r.key, "value": r.value, "description": r.description,
         "updated_at": r.updated_at.isoformat() if r.updated_at else None}
        for r in rows
    ]})


@router.put("/attribution/rules/{key}", summary="修改归因规则")
def update_rule(key: str, payload: RuleUpdateIn, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(AttributionRule).filter(AttributionRule.key == key).first()
    if not row:
        raise not_found("规则不存在")
    # 数值型规则必须能解析成非负整数，否则归因会在运行时报错
    if key != "bot_filter_enabled":
        try:
            if int(payload.value) < 0:
                raise ValueError
        except ValueError:
            raise bad_request("该规则需要一个非负整数")
    else:
        if payload.value not in ("0", "1"):
            raise bad_request("该开关只能为 0 或 1")
    row.value = payload.value
    db.commit()
    return ok({"key": key, "value": row.value},
              "规则已更新，仅对**之后**的来电生效（历史归因结果不变）")


# ============================================================
# 五、订单归因补挂
# ============================================================

@router.post("/attribution/orders/{order_id}/attribute", summary="为订单补挂归因")
def attribute_single_order(order_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """给历史订单补建归因关联（用于订单先录、归因配置后补的场景）"""
    order = db.get(Order, order_id)
    if not order:
        raise not_found("订单不存在")
    attr = attribute_order(db, order, persist=True)
    return ok({
        "order_no": attr.order_no,
        "attribution_channel": attr.attribution_channel,
        "match_rule": attr.match_rule,
        "match_confidence": attr.match_confidence,
        "amount": float(attr.amount or 0),
    })
