# ============================================================
# 文件功能：转化归因引擎（纯函数为主，便于单测）
#
# 归因的本质：来电记录本身不带任何来源信息 —— 它只有「谁打来的」和「什么
# 时候打的」。要把它接到某次官网访问上，只有两条路：
#   ① 号码来源证明（打的是哪个号）→ 追踪号码
#   ② 时间接近证明（刚才还在看官网）→ 时间窗
# 两条都有 = 强归因；只有① = 渠道级归因；只有② = 弱归因。
#
# 四级规则（按优先级依次尝试，命中即停）：
#   R1_TRACKING_WINDOW  追踪号 + 时间窗内会话       → high   访客级
#   R2_TRACKING_ONLY    追踪号，时间窗内无会话      → medium 渠道级
#   R3_PHONE_LASTTOUCH  手机号回溯命中历史访客      → medium 访客级（跨设备）
#   R4_UNMATCHED        全都不命中                  → none   不归因
#
# 为什么一定要分四级而不是「能匹配就算」：
#   如果把 R2/R3 也算成「官网带来的访客」，报表会系统性虚高，老板拿这个
#   数字做投放决策就会亏钱。**归因系统最大的风险不是漏归因，是虚高。**
#   所以每级都单独打标、单独统计，报表里分别给出，让人自己决定信到哪一级。
# ============================================================

import hashlib
import json
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models import Message, Order, utcnow
from app.models_attribution import (
    AttributionRule,
    CallLog,
    TrackingNumber,
    VisitorIdentity,
    VisitorSession,
    DEFAULT_ATTRIBUTION_RULES,
)

# ---------- 规则标识常量（写库与报表统计都要用，避免散落的魔法字符串） ----------
RULE_TRACKING_WINDOW = "R1_TRACKING_WINDOW"
RULE_TRACKING_ONLY = "R2_TRACKING_ONLY"
RULE_PHONE_LASTTOUCH = "R3_PHONE_LASTTOUCH"
RULE_UNMATCHED = "R4_UNMATCHED"

CONF_HIGH = "high"
CONF_MEDIUM = "medium"
CONF_LOW = "low"
CONF_NONE = "none"

# 归因规则说明（后台报表直接展示，保证「规则」与「呈现」同源，不会两处写不一致）
RULE_LABELS = {
    RULE_TRACKING_WINDOW: "R1 追踪号 + 时间窗（强归因·访客级）",
    RULE_TRACKING_ONLY: "R2 仅追踪号（渠道级，不含访客）",
    RULE_PHONE_LASTTOUCH: "R3 手机号回溯（跨设备·访客级）",
    RULE_UNMATCHED: "R4 未归因（不计入官网业绩）",
}


# ============================================================
# 一、基础工具：手机号脱敏、渠道识别、设备识别
# ============================================================

def hash_phone(phone: str) -> str:
    """手机号 → 不可逆哈希（带固定盐）。

    为什么用哈希而不是明文：归因系统会同时接触「访客行为」和「来电号码」，
    如果落明文，它就成了一个比官网本身更危险的个人信息库。
    哈希足以完成匹配（同一号码必然同哈希），又不泄露号码本身。
    """
    raw = (phone or "").strip()
    if not raw:
        return ""
    return hashlib.sha256((raw + settings.PHONE_HASH_SALT).encode("utf-8")).hexdigest()


def mask_phone(phone: str) -> str:
    """手机号掩码：13812345678 → 138****5678（供人工核对用）"""
    raw = (phone or "").strip()
    if len(raw) < 7:
        return raw[:2] + "****" if raw else ""
    return f"{raw[:3]}****{raw[-4:]}"


def detect_device(user_agent: str) -> str:
    """从 UA 判断设备类型（只分三档，报表够用）"""
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return "tablet"
    if "mobile" in ua or "android" in ua or "iphone" in ua or "ipod" in ua:
        return "mobile"
    if not ua:
        return "unknown"
    return "desktop"


# 爬虫/监控特征：这些流量必须从归因分母里剔除，否则「官网访问量」和
# 「归因率」都会被机器流量污染。
_BOT_PATTERNS = (
    "bot", "spider", "crawler", "crawler", "slurp", "curl", "wget",
    "python-requests", "headlesschrome", "phantomjs", "scrapy", "httpclient",
    "uptime", "monitor", "pingdom", "ahrefs", "semrush", "bingpreview",
)


def detect_bot(user_agent: str) -> bool:
    """判断是否爬虫/监控流量"""
    ua = (user_agent or "").lower()
    if not ua:
        # 完全没有 UA 的请求极可能是脚本，按 bot 处理（宁可少算，不可虚高）
        return True
    return any(p in ua for p in _BOT_PATTERNS)


# 渠道识别：referrer 域名 + utm 参数 → 一级渠道 + 细分
# 顺序敏感：先判 utm（投放/线下二维码是人为标注的，优先级最高），
# 再判 referrer 域名，最后才落到 direct/referral。
_SEARCH_ENGINES = {
    "baidu.com": "baidu", "sogou.com": "sogou", "so.com": "360",
    "google.": "google", "bing.com": "bing", "sm.cn": "shenma",
    "toutiao.com": "toutiao_search",
}
_SOCIAL_SITES = {
    "weixin.qq.com": "wechat", "wechat.com": "wechat", "mp.weixin.qq.com": "wechat_mp",
    "xiaohongshu.com": "xiaohongshu", "xhslink.com": "xiaohongshu",
    "weibo.com": "weibo", "weibo.cn": "weibo",
    "douyin.com": "douyin", "iesdouyin.com": "douyin",
    "zhihu.com": "zhihu", "bilibili.com": "bilibili",
}

_PAID_MEDIUMS = {"cpc", "ppc", "paid", "sem", "display", "cpm", "feed"}
_QR_SOURCES = {"qr", "qrcode", "offline_qr"}
_SMS_SOURCES = {"sms", "message", "duanxin"}


def detect_channel(
    referrer: str = "",
    utm_source: str = "",
    utm_medium: str = "",
    utm_campaign: str = "",
    page_path: str = "",
) -> tuple[str, str]:
    """识别渠道，返回 (一级渠道, 细分来源)。

    一级渠道枚举与 tracking_number.channel 的 CHECK 约束完全一致：
    direct / organic_search / social / paid / qr_offline / sms / referral / unknown
    """
    src = (utm_source or "").strip().lower()
    med = (utm_medium or "").strip().lower()
    ref = (referrer or "").strip().lower()

    # ① 线下二维码 / 短信：靠 utm 标注，机器无法自动推断
    if src in _QR_SOURCES or med == "qr":
        return "qr_offline", src or med
    if src in _SMS_SOURCES or med == "sms":
        return "sms", src or med

    # ② 付费投放
    if med in _PAID_MEDIUMS:
        detail = src or "paid"
        return "paid", detail

    # ③ 社交媒体（utm 标注优先，其次 referrer 域名）
    for host, name in _SOCIAL_SITES.items():
        if host in ref:
            return "social", name
    if src in {v for v in _SOCIAL_SITES.values()}:
        return "social", src

    # ④ 搜索引擎
    for host, name in _SEARCH_ENGINES.items():
        if host in ref:
            return "organic_search", name
    if med == "organic" and src:
        return "organic_search", src

    # ⑤ 无 referrer + 无 utm = 直接访问（收藏夹、直接输网址、App 内打开）
    if not ref and not src:
        return "direct", "direct"

    # ⑥ 站内跳转（referrer 是自己站点）也归为 direct —— 避免把站内跳转算成外链
    if "mai-isle" in ref or "localhost" in ref or "127.0.0.1" in ref:
        return "direct", "internal"

    # ⑦ 其他外链
    return "referral", _extract_host(ref)


def _extract_host(referrer: str) -> str:
    """从 referrer 里抠出域名主体，作为 referral 的细分标识"""
    m = re.match(r"https?://([^/:]+)", referrer or "")
    if not m:
        return "unknown"
    host = m.group(1).lower()
    return host[4:] if host.startswith("www.") else host


# ============================================================
# 二、规则配置读取
# ============================================================

def get_rules(db: Session) -> dict:
    """读取归因规则配置（缺失则用默认值并落库，保证首次运行可用）"""
    rows = db.query(AttributionRule).all()
    existing = {r.key: r.value for r in rows}

    # 首次运行：写入默认规则
    if not rows:
        for key, value, desc in DEFAULT_ATTRIBUTION_RULES:
            db.add(AttributionRule(key=key, value=value, description=desc))
        db.commit()
        existing = {k: v for k, v, _ in DEFAULT_ATTRIBUTION_RULES}

    def _int(key: str, fallback: int) -> int:
        try:
            return int(existing.get(key, fallback))
        except (TypeError, ValueError):
            return fallback

    return {
        "session_window_minutes": _int("session_window_minutes", 30),
        "phone_lookback_days": _int("phone_lookback_days", 7),
        "bot_filter_enabled": _int("bot_filter_enabled", 1),
        "min_visit_seconds": _int("min_visit_seconds", 3),
        "max_time_gap_seconds": _int("max_time_gap_seconds", 86400),
    }


# ============================================================
# 三、归因主流程
# ============================================================

def attribute_call(db: Session, call: CallLog, persist: bool = False) -> CallLog:
    """对一条来电记录执行归因，把结果写回 call 对象。

    参数 persist=True 时直接提交（后台录入用）；False 时只改内存对象，
    便于单测和对历史数据做「重新归因」试算。

    注意：归因结果一经写入即不再自动变更。业务上真要重算，应生成新记录
    并把旧的标记为已重算，而不是就地覆盖 —— 否则昨天给老板的报表数字
    今天会莫名其妙变化，且查不出为什么变。
    """
    rules = get_rules(db)
    window_min = rules["session_window_minutes"]
    lookback_days = rules["phone_lookback_days"]

    # 先清零，保证重复调用得到一致结果（幂等）
    call.matched_session_id = ""
    call.matched_visitor_id = ""
    call.match_rule = RULE_UNMATCHED
    call.match_confidence = CONF_NONE
    call.match_time_gap_sec = None
    call.candidate_count = 0
    call.attribution_channel = "unknown"
    call.attribution_channel_detail = ""

    # ---------- 前置闸门：测试/错号电话不参与归因 ----------
    if call.status in ("test", "wrong_number"):
        call.is_attributable = False
        return call

    # ---------- 闸门 1：数字来源证明（追踪号码） ----------
    tracking: Optional[TrackingNumber] = None
    if call.tracking_no:
        tracking = (
            db.query(TrackingNumber)
            .filter(TrackingNumber.tracking_no == call.tracking_no)
            .first()
        )

    # 打的不是任何官网专属号 → 根本不该算官网业绩。
    # 先把渠道记成 unknown，后面若靠 R3 命中再修正（那种情况属于「官网有影响」，
    # 而不是「官网直接带来」，报表里单独一列，不允许混算）。
    if tracking is None:
        call.is_attributable = False

    # ---------- 规则 R1：追踪号 + 时间窗 → 访客级强归因 ----------
    if tracking is not None and tracking.is_active:
        since = call.called_at - timedelta(minutes=window_min)
        # 命中判据：会话活动区间与「来电前 N 分钟」有交集。
        #
        # ⚠️ 为什么不写成 last_seen_at <= called_at（更直觉但会漏）：
        #    真实业务里接线员常在挂断后几分钟才录单，这期间顾客可能还在官网
        #    继续浏览，last_seen_at 就落到 called_at 之后了。用「必须早于来电」
        #    当条件，会把这类本该判强归因的电话错判成渠道级（实测踩过）。
        #    换成「last_seen 在窗口内 + 会话不是来电之后才开始的」更贴合实际：
        #    既不会漏掉仍在线的人，也不会把来电之后才进站的新访客算进来。
        base_q = db.query(VisitorSession).filter(
            VisitorSession.last_seen_at >= since,
            VisitorSession.first_seen_at <= call.called_at,
            VisitorSession.is_bot == False,  # noqa: E712
        )
        # 优先同渠道会话：多个专属号并存时，避免把 A 渠道的访客算给 B
        candidates = (
            base_q.filter(VisitorSession.channel == tracking.channel)
            .order_by(VisitorSession.last_seen_at.desc())
            .all()
        )
        if not candidates:
            # 渠道对不上（例如访客直接访问后打了投放专线）——放宽到全部渠道，
            # 但置信度要降级，因为「渠道归属」这一步没有证据支撑
            candidates = base_q.order_by(VisitorSession.last_seen_at.desc()).all()

        if candidates:
            best = candidates[0]
            # 时间差允许为负：负数表示「来电时该访客仍在站内活动」，
            # 这是正常现象（通话中/挂断后继续浏览），不是异常数据。
            gap = int((call.called_at - best.last_seen_at).total_seconds())
            call.matched_session_id = best.session_id
            call.matched_visitor_id = best.visitor_id
            call.match_rule = RULE_TRACKING_WINDOW
            # 多个候选 = 时间窗内有多个人在访问，无法唯一确定是谁打的 →
            # 访客级置信度降为 medium，但仍记为 R1（渠道归属是确定的）
            call.match_confidence = CONF_HIGH if len(candidates) == 1 else CONF_MEDIUM
            call.match_time_gap_sec = gap
            call.candidate_count = len(candidates)
            call.attribution_channel = tracking.channel
            call.attribution_channel_detail = tracking.channel_detail
            call.is_attributable = True
            if persist:
                db.commit()
            return call

        # ---------- 规则 R2：只有追踪号，时间窗内没人 → 渠道级 ----------
        call.match_rule = RULE_TRACKING_ONLY
        call.match_confidence = CONF_MEDIUM
        call.attribution_channel = tracking.channel
        call.attribution_channel_detail = tracking.channel_detail
        call.is_attributable = True
        if persist:
            db.commit()
        return call

    # ---------- 规则 R3：手机号回溯（跨设备兜底） ----------
    if call.caller_phone_hash:
        matched = _match_by_phone(db, call, lookback_days)
        if matched is not None:
            session, gap_sec, via = matched
            call.matched_session_id = session.session_id
            call.matched_visitor_id = session.visitor_id
            call.match_rule = RULE_PHONE_LASTTOUCH
            call.match_confidence = CONF_MEDIUM
            call.match_time_gap_sec = gap_sec
            call.attribution_channel = session.channel
            call.attribution_channel_detail = session.channel_detail
            # 打的是非官网号，但历史上确实访问过官网 → 算「官网有影响」，
            # 可归因但要能区分来源（via 记录是靠身份绑定还是留言/订单反查）
            call.is_attributable = True
            call.remark = (call.remark + f"｜R3来源:{via}").strip("｜") if call.remark else f"R3来源:{via}"
            if persist:
                db.commit()
            return call

    # ---------- 规则 R4：未归因 ----------
    if persist:
        db.commit()
    return call


def _match_by_phone(
    db: Session, call: CallLog, lookback_days: int
) -> Optional[tuple[VisitorSession, int, str]]:
    """手机号回溯：返回 (命中的会话, 时间差秒数, 命中途径)。

    三条路径，按可靠性从高到低：
      ① visitor_identity：用户在留言表单留过手机号，已绑定 visitor_id —— 最可靠
      ② message：留言表里的明文手机号反算哈希 —— 等价于①，但没绑 visitor，只能靠时间对齐
      ③ orders：历史订单手机号 → 说明是老客户，但「这次来电是不是官网带来的」证据最弱
    """
    since = call.called_at - timedelta(days=lookback_days)

    # ① 身份绑定表（精确、跨设备有效）
    ident = (
        db.query(VisitorIdentity)
        .filter(VisitorIdentity.phone_hash == call.caller_phone_hash)
        .order_by(VisitorIdentity.bind_at.desc())
        .first()
    )
    if ident:
        sess = (
            db.query(VisitorSession)
            .filter(
                VisitorSession.visitor_id == ident.visitor_id,
                VisitorSession.last_seen_at >= since,
                VisitorSession.last_seen_at <= call.called_at,
                VisitorSession.is_bot == False,  # noqa: E712
            )
            .order_by(VisitorSession.last_seen_at.desc())
            .first()
        )
        if sess:
            gap = int((call.called_at - sess.last_seen_at).total_seconds())
            return sess, gap, "visitor_identity"

    # ② 留言表反查（留言时同一手机号 → 那条留言的时间点附近应有会话）
    #    SQLite 无内置 sha256，无法在 SQL 层比对，故在 Python 侧算。
    #    单店量级（留言百级）完全可接受；若将来上万级应改为落 phone_hash 列。
    msgs = (
        db.query(Message)
        .filter(Message.created_at >= since, Message.created_at <= call.called_at)
        .all()
    )
    for msg in msgs:
        if hash_phone(msg.phone) == call.caller_phone_hash:
            sess = (
                db.query(VisitorSession)
                .filter(
                    VisitorSession.last_seen_at >= since,
                    VisitorSession.last_seen_at <= msg.created_at + timedelta(minutes=30),
                    VisitorSession.is_bot == False,  # noqa: E712
                )
                .order_by(VisitorSession.last_seen_at.desc())
                .first()
            )
            if sess:
                gap = int((call.called_at - sess.last_seen_at).total_seconds())
                return sess, gap, "message"

    # ③ 历史订单反查（最弱：只能说明是回头客）
    orders = (
        db.query(Order)
        .filter(Order.created_at >= since, Order.created_at <= call.called_at)
        .all()
    )
    for od in orders:
        if hash_phone(od.customer_phone) == call.caller_phone_hash:
            sess = (
                db.query(VisitorSession)
                .filter(
                    VisitorSession.last_seen_at >= since,
                    VisitorSession.last_seen_at <= call.called_at,
                    VisitorSession.is_bot == False,  # noqa: E712
                )
                .order_by(VisitorSession.last_seen_at.desc())
                .first()
            )
            if sess:
                gap = int((call.called_at - sess.last_seen_at).total_seconds())
                return sess, gap, "order"
    return None


# ============================================================
# 四、订单归因：把成单金额接到归因链上
# ============================================================

def attribute_order(db: Session, order: Order, persist: bool = True) -> Optional["OrderAttribution"]:
    """给新订单建立归因关联。

    匹配顺序：
      ① 订单手机号 → 最近一条已归因来电（同号）→ 继承该来电的归因结果
      ② 找不到来电 → 订单手机号 → visitor_identity → 最近会话（弱归因）
      ③ 都没有 → 记 R4，金额不进「官网带来 GMV」
    """
    from app.models_attribution import OrderAttribution

    exists = (
        db.query(OrderAttribution)
        .filter(OrderAttribution.order_id == order.id)
        .first()
    )
    if exists:
        return exists

    attr = OrderAttribution(
        order_id=order.id,
        order_no=order.order_no,
        amount=order.amount,
        attribution_channel="unknown",
    )
    phone_hash = hash_phone(order.customer_phone)

    # ① 同号来电（时间上先于订单，且已归因）
    call = None
    if phone_hash:
        call = (
            db.query(CallLog)
            .filter(
                CallLog.caller_phone_hash == phone_hash,
                CallLog.called_at <= order.created_at,
                CallLog.is_attributable == True,  # noqa: E712
            )
            .order_by(CallLog.called_at.desc())
            .first()
        )
    if call:
        attr.call_id = call.id
        attr.session_id = call.matched_session_id
        attr.visitor_id = call.matched_visitor_id
        attr.attribution_channel = call.attribution_channel
        attr.attribution_channel_detail = call.attribution_channel_detail
        attr.match_rule = call.match_rule
        attr.match_confidence = call.match_confidence
    else:
        # ② 身份绑定兜底
        ident = None
        if phone_hash:
            ident = (
                db.query(VisitorIdentity)
                .filter(VisitorIdentity.phone_hash == phone_hash)
                .order_by(VisitorIdentity.bind_at.desc())
                .first()
            )
        if ident:
            sess = (
                db.query(VisitorSession)
                .filter(
                    VisitorSession.visitor_id == ident.visitor_id,
                    VisitorSession.last_seen_at <= order.created_at,
                    VisitorSession.is_bot == False,  # noqa: E712
                )
                .order_by(VisitorSession.last_seen_at.desc())
                .first()
            )
            if sess:
                attr.session_id = sess.session_id
                attr.visitor_id = sess.visitor_id
                attr.attribution_channel = sess.channel
                attr.attribution_channel_detail = sess.channel_detail
                attr.match_rule = RULE_PHONE_LASTTOUCH
                attr.match_confidence = CONF_LOW   # 无来电证据，最低置信

    db.add(attr)
    if persist:
        db.commit()
        db.refresh(attr)
    return attr


# ============================================================
# 五、会话维护（埋点写入时调用）
# ============================================================

SESSION_IDLE_MINUTES = 30   # 会话空闲超时（与归因时间窗默认值一致）


def touch_session(
    db: Session,
    visitor_id: str,
    session_id: str,
    page_path: str,
    referrer: str = "",
    utm: Optional[dict] = None,
    user_agent: str = "",
    ip_hash: str = "",
) -> VisitorSession:
    """创建或更新会话。

    会话边界规则：同一 visitor_id 且距上次活动 ≤30 分钟 → 续用；
    否则前端会生成新 session_id，这里自然插入新行。
    """
    utm = utm or {}
    sess = (
        db.query(VisitorSession)
        .filter(VisitorSession.session_id == session_id)
        .first()
    )
    if sess:
        sess.last_seen_at = utcnow()
        sess.exit_page = page_path
        db.commit()
        return sess

    channel, detail = detect_channel(
        referrer=referrer,
        utm_source=utm.get("utm_source", ""),
        utm_medium=utm.get("utm_medium", ""),
        utm_campaign=utm.get("utm_campaign", ""),
        page_path=page_path,
    )
    sess = VisitorSession(
        visitor_id=visitor_id,
        session_id=session_id,
        landing_page=page_path,
        exit_page=page_path,
        referrer=(referrer or "")[:500],
        utm_source=(utm.get("utm_source") or "")[:50],
        utm_medium=(utm.get("utm_medium") or "")[:50],
        utm_campaign=(utm.get("utm_campaign") or "")[:50],
        utm_content=(utm.get("utm_content") or "")[:50],
        utm_term=(utm.get("utm_term") or "")[:50],
        channel=channel,
        channel_detail=detail,
        device_type=detect_device(user_agent),
        is_bot=detect_bot(user_agent),
        user_agent=(user_agent or "")[:300],
        ip_hash=ip_hash,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess
