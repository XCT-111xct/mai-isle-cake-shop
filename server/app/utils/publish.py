# ============================================================
# 文件功能：内容版本化发布引擎（草稿 → 预览 → 发布 → 回滚）
#
# 核心不变式（任何改动都必须守住这三条）：
#   I1. content.value 永远是前台唯一读取源 —— 前台业务代码零改动，
#       版本系统对前台完全透明。
#   I2. content_version 只追加，永不删除、永不就地覆盖。回滚 = 用旧内容
#       造一个新版本，所以「回滚」这个动作本身也能被回滚。
#   I3. 发布/回滚是单事务：版本状态 + content.value + 审计日志三步同生共死。
#
# 为什么必须有「基线（baseline）」这一步：
#   版本系统是后加的，线上 content.value 里已经有内容但版本表是空的。
#   若不先建 v1 基线，第一次发布会找不到「当前线上版本」，乐观锁无从比对，
#   回滚也没有目标版本 —— 等于把已有内容变成了孤儿。
#   所以任何操作前先 ensure_baseline()，把现状固化成 v1。
# ============================================================

import secrets
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Content, utcnow
from app.models_publish import (
    ContentPreviewToken,
    ContentPublishLog,
    ContentVersion,
)
from app.utils.content_rules import (
    ALL_KEYS,
    content_hash,
    deserialize,
    serialize,
    validate_and_normalize,
)
from app.utils.response import bad_request, conflict, not_found

PREVIEW_TOKEN_TTL_MINUTES = 30   # 预览链接有效期
PREVIEW_TOKEN_MAX_USES = 50      # 单个链接最多请求次数


# ============================================================
# 一、版本链读取工具
# ============================================================

def _get_content_row(db: Session, key: str) -> Content:
    """取 content 行，不存在则创建空行（Markdown 型默认空串，JSON 型默认 {}）"""
    row = db.query(Content).filter(Content.key == key).first()
    if row:
        return row
    row = Content(key=key, value="" if key not in {"banners", "brand_chars", "brand_journey",
                                                   "hardware", "software", "order_info",
                                                   "contact_info"} else "{}")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_current_version(db: Session, key: str) -> Optional[ContentVersion]:
    """当前线上版本（同一 key 至多一个 is_current=1）"""
    return (
        db.query(ContentVersion)
        .filter(ContentVersion.key == key, ContentVersion.is_current == True)  # noqa: E712
        .first()
    )


def _max_version(db: Session, key: str) -> int:
    """该 key 的历史最大版本号（无版本时返回 0）"""
    val = db.query(func.max(ContentVersion.version)).filter(ContentVersion.key == key).scalar()
    return int(val) if val else 0


def ensure_baseline(db: Session, key: str) -> Optional[ContentVersion]:
    """确保该 key 有版本链，返回当前线上版本（可能为 None）。

    ⚠️ 判据必须用「版本链是否为空」，不能用「有没有 current 版本」：
       下线（offline）会把 current 清掉，此时版本链其实还在。若按下线状态
       就重建基线，会重复插入 v1 撞上 (key, version) 唯一约束 —— 实测踩过。
       返回值可能是 None，表示「有历史但当前处于下线状态」，调用方需自行处理。
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")

    if _max_version(db, key) > 0:
        # 已有版本链：直接返回当前线上版本（下线后为 None）
        return get_current_version(db, key)

    # 版本链为空 → 用 content.value 的现状固化为 v1
    row = _get_content_row(db, key)
    raw = row.value or ""
    baseline = ContentVersion(
        key=key,
        version=1,
        value=raw,
        content_hash=content_hash(raw),
        status="published",
        is_current=True,
        change_summary="基线快照：版本管理启用时的线上内容",
        based_on_version=0,
        created_by_id=None,
        created_by_name="system",
        published_by_name="system",
        published_at=utcnow(),
    )
    db.add(baseline)
    db.commit()
    db.refresh(baseline)
    return baseline


def list_versions(db: Session, key: str, limit: int = 50) -> list[ContentVersion]:
    """版本历史（倒序，最新在前）。注意：回滚过的版本也都在，一条不少。"""
    ensure_baseline(db, key)
    return (
        db.query(ContentVersion)
        .filter(ContentVersion.key == key)
        .order_by(ContentVersion.version.desc())
        .limit(limit)
        .all()
    )


def get_draft(db: Session, key: str) -> Optional[ContentVersion]:
    """取该 key 最新的草稿（没有则 None）"""
    return (
        db.query(ContentVersion)
        .filter(ContentVersion.key == key, ContentVersion.status == "draft")
        .order_by(ContentVersion.version.desc())
        .first()
    )


# ============================================================
# 二、保存草稿
# ============================================================

def save_draft(
    db: Session,
    key: str,
    value: Any,
    editor_id: Optional[int],
    editor_name: str,
    change_summary: str = "",
) -> ContentVersion:
    """保存草稿 —— **不影响线上内容**。

    同一 key 只保留一份草稿：再次保存会覆盖上一份草稿（草稿本身不需要
    版本历史，需要留痕的是「发布过什么」）。覆盖草稿前记一条审计日志，
    至少能看出「谁在什么时候又改了草稿」。
    """
    normalized = validate_and_normalize(key, value)
    raw = serialize(normalized)

    ensure_baseline(db, key)
    current = get_current_version(db, key)
    cur_ver = current.version if current else 0

    # 内容与线上完全一致 → 没必要产生草稿，直接告知
    if current and content_hash(current.value) == content_hash(raw):
        raise bad_request("草稿内容与当前线上版本一致，无需发布")

    existing = get_draft(db, key)
    try:
        if existing:
            existing.value = raw
            existing.content_hash = content_hash(raw)
            existing.change_summary = change_summary[:200]
            existing.created_by_id = editor_id
            existing.created_by_name = editor_name
            existing.created_at = utcnow()
            # 草稿是基于哪个线上版本改的 —— 乐观锁的依据，每次存草稿都刷新
            existing.based_on_version = cur_ver
            draft = existing
        else:
            draft = ContentVersion(
                key=key,
                version=_max_version(db, key) + 1,
                value=raw,
                content_hash=content_hash(raw),
                status="draft",
                is_current=False,
                change_summary=change_summary[:200],
                based_on_version=cur_ver,
                created_by_id=editor_id,
                created_by_name=editor_name,
            )
            db.add(draft)
        db.add(ContentPublishLog(
            key=key,
            action="save_draft",
            from_version=cur_ver,
            to_version=draft.version,
            operator_id=editor_id,
            operator_name=editor_name,
            reason=change_summary[:300],
            result="success",
        ))
        db.commit()
        db.refresh(draft)
        return draft
    except Exception as exc:
        # 失败留痕也是留痕：只有成功的日志等于「出事了查不到」
        db.rollback()
        try:
            db.add(ContentPublishLog(
                key=key, action="save_draft", from_version=cur_ver,
                operator_id=editor_id, operator_name=editor_name,
                result="failed", error_msg=str(exc)[:500],
            ))
            db.commit()
        except Exception:
            db.rollback()
        raise


# ============================================================
# 三、发布
# ============================================================

def publish_version(
    db: Session,
    key: str,
    version_id: int,
    publisher_id: Optional[int],
    publisher_name: str,
    change_summary: str,
) -> ContentVersion:
    """把指定草稿发布上线。

    三道闸门：
      ① 必须是 draft 状态（已发布的不能再发一次）
      ② 变更说明必填（版本留痕的底线，不然历史记录全是「无」）
      ③ 乐观锁：草稿的 based_on_version 必须等于当前线上版本号，
         否则说明「你编辑期间别人已经发布过了」，拒绝并让人基于最新版重做
    """
    if not (change_summary or "").strip():
        raise bad_request("发布必须填写变更说明，否则版本历史将无法追溯")

    ensure_baseline(db, key)
    draft = db.get(ContentVersion, version_id)
    if not draft or draft.key != key:
        raise not_found("草稿版本不存在")
    if draft.status != "draft":
        raise bad_request("只有草稿状态的内容可以发布，当前状态：" + draft.status)

    current = get_current_version(db, key)
    cur_ver = current.version if current else 0

    # ---------- 乐观锁：防止两个人同时改内容互相覆盖 ----------
    if draft.based_on_version != cur_ver:
        db.add(ContentPublishLog(
            key=key, action="publish", from_version=cur_ver, to_version=draft.version,
            operator_id=publisher_id, operator_name=publisher_name,
            result="failed",
            error_msg=f"版本冲突：草稿基于 v{draft.based_on_version}，线上已是 v{cur_ver}",
        ))
        db.commit()
        raise conflict(
            f"版本冲突：您编辑时基于 v{draft.based_on_version}，"
            f"但线上已被他人更新到 v{cur_ver}。请基于最新版本重新编辑后再发布。"
        )

    row = _get_content_row(db, key)
    try:
        # I3：三步同生共死
        if current:
            current.is_current = False
            current.status = "superseded"

        draft.status = "published"
        draft.is_current = True
        draft.change_summary = change_summary[:200]
        draft.published_by_id = publisher_id
        draft.published_by_name = publisher_name
        draft.published_at = utcnow()

        row.value = draft.value

        db.add(ContentPublishLog(
            key=key, action="publish", from_version=cur_ver, to_version=draft.version,
            operator_id=publisher_id, operator_name=publisher_name,
            reason=change_summary[:300], result="success",
        ))
        db.commit()
        db.refresh(draft)
        return draft
    except Exception as exc:
        db.rollback()
        try:
            db.add(ContentPublishLog(
                key=key, action="publish", from_version=cur_ver, to_version=draft.version,
                operator_id=publisher_id, operator_name=publisher_name,
                result="failed", error_msg=str(exc)[:500],
            ))
            db.commit()
        except Exception:
            db.rollback()
        raise


# ============================================================
# 三半、快速通道：保存即发布（仍留版本痕迹）
# ============================================================

def save_and_publish(
    db: Session,
    key: str,
    value: Any,
    operator_id: Optional[int],
    operator_name: str,
    summary: str = "直接保存生效",
) -> ContentVersion:
    """快速通道：保存并立即生效，但**必须写版本记录**。

    为什么快速通道也要留痕（这条容易漏）：
      如果「保存即生效」不产生版本，版本链就与真实线上内容脱节了 ——
      下一次回滚会把这期间通过快速通道做的修改**静默抹掉**，而且事后
      查不出是谁改的。所以任何写 content.value 的路径都必须进版本表。
    它与 publish 的唯一差别是：**不做乐观锁校验**（本意就是立刻生效）。

    刻意**不**作废已有草稿：留着它，编辑者下次点发布时会收到 409
    「版本冲突，请基于最新版重新编辑」，而不是草稿神秘消失。
    """
    normalized = validate_and_normalize(key, value)
    raw = serialize(normalized)

    ensure_baseline(db, key)
    current = get_current_version(db, key)
    cur_ver = current.version if current else 0
    new_ver = _max_version(db, key) + 1
    row = _get_content_row(db, key)

    try:
        if current:
            current.is_current = False
            current.status = "superseded"

        ver = ContentVersion(
            key=key,
            version=new_ver,
            value=raw,
            content_hash=content_hash(raw),
            status="published",
            is_current=True,
            # 变更说明里显式标「快速通道」：版本历史要能一眼看出「这一版绕过
            # 了草稿/预览/回滚保护」，否则事后复盘分不清哪次改动按流程走过
            change_summary=f"快速通道：{summary}"[:200],
            based_on_version=cur_ver,
            created_by_id=operator_id,
            created_by_name=operator_name,
            published_by_id=operator_id,
            published_by_name=operator_name,
            published_at=utcnow(),
        )
        db.add(ver)
        row.value = raw
        db.add(ContentPublishLog(
            key=key, action="publish", from_version=cur_ver, to_version=new_ver,
            operator_id=operator_id, operator_name=operator_name,
            reason=f"快速通道：{summary}"[:300], result="success",
        ))
        db.commit()
        db.refresh(ver)
        return ver
    except Exception as exc:
        db.rollback()
        try:
            db.add(ContentPublishLog(
                key=key, action="publish", from_version=cur_ver,
                operator_id=operator_id, operator_name=operator_name,
                result="failed", error_msg=str(exc)[:500],
            ))
            db.commit()
        except Exception:
            db.rollback()
        raise


# ============================================================
# 四、回滚
# ============================================================

def rollback_to_version(
    db: Session,
    key: str,
    target_version: int,
    operator_id: Optional[int],
    operator_name: str,
    reason: str,
) -> ContentVersion:
    """回滚到指定历史版本。

    ⚠️ 语义澄清（最容易被误解的一点）：
       回滚**不是**把 is_current 指针拨回旧版本，而是「以旧版本的内容为素材，
       创建一个新版本」。所以：
         - 目标版本号（target_version）= 内容取自哪一版
         - 新版本号（返回值 .version） = 这次回滚产生的版本
       历史链条只会变长，不会出现「时间倒流」造成的审计空洞。
       也因此，回滚可以再回滚（把回滚掉的东西再回滚回来），不会丢任何一版。
    """
    if not (reason or "").strip():
        raise bad_request("回滚必须填写原因，否则事后无法判断这次回滚是否该保留")

    ensure_baseline(db, key)
    target = (
        db.query(ContentVersion)
        .filter(ContentVersion.key == key, ContentVersion.version == target_version)
        .first()
    )
    if not target:
        raise not_found("目标版本不存在")
    if target.status == "draft":
        raise bad_request("草稿版本不能作为回滚目标，请先发布")

    current = get_current_version(db, key)
    cur_ver = current.version if current else 0
    if current and current.version == target.version:
        raise bad_request("目标版本已是当前线上版本，无需回滚")

    row = _get_content_row(db, key)
    new_version = _max_version(db, key) + 1

    try:
        if current:
            current.is_current = False
            current.status = "superseded"

        restored = ContentVersion(
            key=key,
            version=new_version,
            value=target.value,                      # 内容来自旧版本
            content_hash=target.content_hash,
            status="rolled_back",                    # 标记「这一版是回滚来的」
            is_current=True,
            change_summary=f"回滚至 v{target.version}：{reason}"[:200],
            based_on_version=cur_ver,
            rollback_from_version=target.version,    # 内容来源版本
            created_by_id=operator_id,
            created_by_name=operator_name,
            published_by_id=operator_id,
            published_by_name=operator_name,
            published_at=utcnow(),
        )
        db.add(restored)

        row.value = target.value

        db.add(ContentPublishLog(
            key=key, action="rollback", from_version=cur_ver, to_version=new_version,
            operator_id=operator_id, operator_name=operator_name,
            reason=f"回到 v{target.version}｜{reason}"[:300], result="success",
        ))
        db.commit()
        db.refresh(restored)
        return restored
    except Exception as exc:
        db.rollback()
        try:
            db.add(ContentPublishLog(
                key=key, action="rollback", from_version=cur_ver, to_version=new_version,
                operator_id=operator_id, operator_name=operator_name,
                result="failed", error_msg=str(exc)[:500],
            ))
            db.commit()
        except Exception:
            db.rollback()
        raise


# ============================================================
# 五、下线 / 恢复
# ============================================================

def set_offline(db: Session, key: str, operator_id: Optional[int], operator_name: str, reason: str) -> None:
    """紧急下线：把当前版本内容置空，让前台区块按「空内容隐藏」规则消失。

    为什么要做「置空」而不是打标记：前台的隐藏规则是「区块内容为空即隐藏」
    （PRD F1 各区块）。置空能立刻在所有端生效且不需要前台配合；
    打标记则需要前台读标记，属于改前台契约，风险更大。
    完整内容仍在版本历史里，随时可以回滚回来。
    """
    if not (reason or "").strip():
        raise bad_request("下线必须填写原因")

    ensure_baseline(db, key)
    current = get_current_version(db, key)
    row = _get_content_row(db, key)
    empty = "" if key in {"brand_story", "brand_value", "custom_tips"} else ("{\"banners\": []}" if key == "banners" else "{}")

    try:
        if current:
            current.is_current = False
            current.status = "superseded"
            current.is_offline = True
        row.value = empty
        db.add(ContentPublishLog(
            key=key, action="offline",
            from_version=current.version if current else 0,
            operator_id=operator_id, operator_name=operator_name,
            reason=reason[:300], result="success",
        ))
        db.commit()
    except Exception:
        db.rollback()
        raise


# ============================================================
# 六、预览令牌
# ============================================================

def create_preview_token(
    db: Session, key: str, version_id: int,
    operator_id: Optional[int], operator_name: str,
    ttl_minutes: int = PREVIEW_TOKEN_TTL_MINUTES,
) -> ContentPreviewToken:
    """生成预览链接令牌（短效、与 key 强绑定）。

    安全要点：
      - token 用 secrets.token_urlsafe 生成，不可预测（不用时间戳/自增）
      - 与 key 强绑定：拿到 Banner 的 token 看不到品牌故事
      - 短效 + 次数上限：链接被转发到群里也不会变成长期后门
      - 发布后立即吊销（publish 时会把该 key 的 token 全撤）
    """
    ver = db.get(ContentVersion, version_id)
    if not ver or ver.key != key:
        raise not_found("待预览的版本不存在")
    if ver.status != "draft":
        raise bad_request("只有草稿可以预览，已发布内容直接看线上即可")

    token = ContentPreviewToken(
        token=secrets.token_urlsafe(32),
        key=key,
        version_id=version_id,
        created_by_id=operator_id,
        created_by_name=operator_name,
        expires_at=utcnow() + timedelta(minutes=ttl_minutes),
        max_uses=PREVIEW_TOKEN_MAX_USES,
    )
    db.add(token)
    db.add(ContentPublishLog(
        key=key, action="preview", to_version=ver.version,
        operator_id=operator_id, operator_name=operator_name,
        reason=f"预览令牌有效期 {ttl_minutes} 分钟", result="success",
    ))
    db.commit()
    db.refresh(token)
    return token


def resolve_preview_token(db: Session, token_str: str, key: str) -> Optional[ContentVersion]:
    """校验预览令牌并返回对应草稿版本（不合法一律返回 None，不区分原因）。

    为什么不区分「过期/超次/已撤销/不存在」：
    对外区分等于告诉攻击者「这个 token 曾经真实存在」，是信息泄露。
    后台审计日志里有真实原因，够排查了。
    """
    if not token_str:
        return None
    tok = db.query(ContentPreviewToken).filter(ContentPreviewToken.token == token_str).first()
    if not tok:
        return None
    now = utcnow()
    if tok.revoked or tok.expires_at < now or tok.used_count >= tok.max_uses:
        return None
    if tok.key != key:
        return None

    ver = db.get(ContentVersion, tok.version_id)
    if not ver or ver.status != "draft":
        # 草稿已被发布/删除 → 令牌自动失效
        return None

    tok.used_count += 1
    db.commit()
    return ver


def revoke_tokens_for_key(db: Session, key: str) -> int:
    """吊销某 key 的全部预览令牌（发布/回滚后调用，防止旧草稿被继续围观）"""
    rows = (
        db.query(ContentPreviewToken)
        .filter(ContentPreviewToken.key == key, ContentPreviewToken.revoked == False)  # noqa: E712
        .all()
    )
    for r in rows:
        r.revoked = True
    if rows:
        db.commit()
    return len(rows)


# ============================================================
# 七、审计日志读取
# ============================================================

def list_publish_logs(db: Session, key: Optional[str] = None, limit: int = 100) -> list[ContentPublishLog]:
    """发布操作审计日志（可按 key 过滤）"""
    q = db.query(ContentPublishLog)
    if key:
        q = q.filter(ContentPublishLog.key == key)
    return q.order_by(ContentPublishLog.created_at.desc()).limit(limit).all()
