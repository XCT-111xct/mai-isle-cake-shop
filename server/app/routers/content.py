# ============================================================
# 文件功能：后台内容管理（技术开发文档 §5.3.7）
#   ① 原有接口：内容 key 列表/读取/直接保存 + banner 子接口（行为不变）
#   ② 新增接口：版本化发布（草稿 → 预览 → 发布 → 回滚 → 下线 → 审计日志）
#
# 两套接口并存的原因：
#   PUT /content/{key} 保持「保存即生效」的老语义，既有调用方与 105 个用例
#   不受影响；新的发布保护走 /content/{key}/draft 等独立端点。
#   两条写路径共用 content_rules 里的同一套校验，不会出现口径分叉。
# ============================================================

import json
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Content
from app.schemas import BannerItem, ContentUpdate
from app.utils import publish as publish_svc
from app.utils.content_rules import (
    ALL_KEYS,
    JSON_KEYS,
    MARKDOWN_KEYS,
    MAX_BANNERS,
    MAX_MARKDOWN_LEN,
    deserialize,
    load_json_value,
    serialize,
    validate_and_normalize,
)
from app.utils.response import BizError, bad_request, not_found, ok

router = APIRouter()


def _get_or_create(db: Session, key: str) -> Content:
    """取内容记录，不存在则创建（默认值按类型）"""
    row = db.query(Content).filter(Content.key == key).first()
    if row:
        return row
    default = "{}" if key in JSON_KEYS else ""
    row = Content(key=key, value=default)
    db.add(row)
    return row


def _load_json(value: str) -> object:
    """解析 JSON 字符串，保留原类型（dict / list）。
    实现统一收敛到 content_rules.load_json_value，避免两处解析口径不一致。"""
    return load_json_value(value)


def _save(db: Session, key: str, value, user=None) -> dict:
    """通用保存：走版本化快速通道 —— 既更新 content.value，也留下版本记录。

    这条不变式很重要：**任何改写 content.value 的路径都必须进版本表**。
    否则回滚时会把「没进版本表的那部分改动」静默抹掉。
    """
    if user is not None:
        publish_svc.save_and_publish(db, key, value, user.id, user.name)
    else:
        row = _get_or_create(db, key)
        row.value = serialize(value)
        db.commit()
    row = db.query(Content).filter(Content.key == key).first()
    return {"key": key, "updated_at": row.updated_at.isoformat() if row and row.updated_at else None}


# ============================================================
# banner 子接口（独立增删改，避免整数组覆盖误删）
# ============================================================

def _read_banners(db: Session) -> list:
    """读取 banners 数组（兼容 {"banners":[...]} 与裸数组）"""
    row = db.query(Content).filter(Content.key == "banners").first()
    if not row:
        return []
    data = _load_json(row.value)
    banners = data.get("banners", [])
    return banners if isinstance(banners, list) else []


def _write_banners(db: Session, banners: list, user=None):
    if len(banners) > MAX_BANNERS:
        raise bad_request("banner 最多 4 张")
    _save(db, "banners", {"banners": banners}, user)


@router.post("/content/banners", summary="新增 banner")
def create_banner(payload: BannerItem, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """新增单张 banner（校验后总数 ≤4）"""
    banners = _read_banners(db)
    if len(banners) >= MAX_BANNERS:
        raise bad_request("banner 最多 4 张")
    new_id = max([b.get("id", 0) for b in banners], default=0) + 1
    banners.append({
        "id": new_id,
        "image_url": payload.image_url.strip(),
        "slogan": payload.slogan,
        "subtitle": payload.subtitle,
        "sort_order": payload.sort_order,
        "is_active": payload.is_active,
    })
    _write_banners(db, banners, current_user)
    return ok({"id": new_id})


@router.put("/content/banners/{banner_id}", summary="编辑 banner")
def update_banner(
    banner_id: int,
    payload: BannerItem,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """编辑单张 banner"""
    banners = _read_banners(db)
    target = next((b for b in banners if b.get("id") == banner_id), None)
    if not target:
        raise not_found("banner 不存在")
    target.update({
        "image_url": payload.image_url.strip(),
        "slogan": payload.slogan,
        "subtitle": payload.subtitle,
        "sort_order": payload.sort_order,
        "is_active": payload.is_active,
    })
    _write_banners(db, banners, current_user)
    return ok({"id": banner_id})


@router.delete("/content/banners/{banner_id}", summary="删除 banner")
def delete_banner(banner_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """删除单张 banner"""
    banners = _read_banners(db)
    new_list = [b for b in banners if b.get("id") != banner_id]
    if len(new_list) == len(banners):
        raise not_found("banner 不存在")
    _write_banners(db, new_list, current_user)
    return ok(None, "success")


# ============================================================
# 内容 key 管理
# ============================================================

# ⚠️ 注册顺序敏感：本接口路径只有一段（/content/publish-logs），
# 必须排在 /content/{key} 之前，否则会被当成 key="publish-logs" 而返回 404。
@router.get("/content/publish-logs", summary="发布操作审计日志")
def publish_logs(
    key: Optional[str] = Query(None, description="按内容 key 过滤，不传=全部"),
    limit: int = Query(100, ge=1, le=500),
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发布/回滚/下线/存草稿/预览的全部操作流水，含失败记录。

    失败记录尤其重要：并发冲突被拒、发布时数据库报错，这些「没成功」的动作
    若不入日志，事后完全查不到为什么内容没更新。
    """
    logs = publish_svc.list_publish_logs(db, key=key, limit=limit)
    return ok({
        "items": [
            {
                "id": g.id,
                "key": g.key,
                "action": g.action,
                "from_version": g.from_version,
                "to_version": g.to_version,
                "operator_name": g.operator_name,
                "reason": g.reason,
                "result": g.result,
                "error_msg": g.error_msg,
                "created_at": g.created_at.isoformat() if g.created_at else None,
            }
            for g in logs
        ]
    })


@router.get("/content", summary="内容 key 列表")
def list_content(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """全部内容 key 列表（key/更新时间）"""
    rows = db.query(Content).order_by(Content.key.asc()).all()
    items = [
        {
            "key": c.key,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        }
        for c in rows
    ]
    # 未初始化的 key 也返回（updated_at=None），保证后台 9 张卡齐全
    existing = {c.key for c in rows}
    for k in sorted(ALL_KEYS - existing):
        items.append({"key": k, "updated_at": None})
    return ok({"items": items})


@router.get("/content/{key}", summary="读取内容")
def get_content(key: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """读取某 key 的 value（编辑回填用），与前台解析规则一致"""
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    row = db.query(Content).filter(Content.key == key).first()
    if not row:
        value: object = {} if key in JSON_KEYS else ""
    else:
        value = row.value
        if key in JSON_KEYS:
            value = _load_json(row.value)
            if key == "banners" and "banners" not in value:
                value = {"banners": []}
    return ok({"key": key, "value": value})


@router.put("/content/{key}", summary="保存内容（立即生效，跳过发布保护）")
def update_content(key: str, payload: ContentUpdate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """保存某 key 的 value：保存后前台实时生效（前端每次进页面重新拉取）

    ⚠️ 这是「快速通道」：会跳过草稿、预览、版本留痕与回滚保护。
    它被保留是为了兼容既有调用方；**生产环境的内容修改应走
    /content/{key}/draft → /preview-token → /publish 三步**。
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    value = validate_and_normalize(key, payload.value)
    return ok(_save(db, key, value, current_user))


# ============================================================
# 以下：版本化发布保护（草稿 → 预览 → 发布 → 回滚）
# ============================================================

class DraftSaveIn(BaseModel):
    value: Any
    change_summary: str = Field(default="", max_length=200, description="变更说明（发布时必填）")


class PublishIn(BaseModel):
    version_id: int = Field(description="要发布的草稿版本 ID")
    change_summary: str = Field(description="变更说明（必填，写入版本历史）", max_length=200)


class RollbackIn(BaseModel):
    target_version: int = Field(description="内容取自哪个历史版本号")
    reason: str = Field(description="回滚原因（必填，写入审计日志）", max_length=300)


class PreviewTokenIn(BaseModel):
    version_id: int = Field(description="要预览的草稿版本 ID")


class OfflineIn(BaseModel):
    reason: str = Field(description="下线原因（必填）", max_length=300)


def _version_brief(v) -> dict:
    """版本对象 → 前端展示结构（不返回 value 全文，避免列表接口体积爆炸）"""
    return {
        "id": v.id,
        "version": v.version,
        "status": v.status,
        "is_current": bool(v.is_current),
        "change_summary": v.change_summary,
        "based_on_version": v.based_on_version,
        "rollback_from_version": v.rollback_from_version,
        "created_by_name": v.created_by_name,
        "created_at": v.created_at.isoformat() if v.created_at else None,
        "published_by_name": v.published_by_name,
        "published_at": v.published_at.isoformat() if v.published_at else None,
        "content_hash": v.content_hash,
        "value_size": len(v.value or ""),
    }


@router.get("/content/{key}/versions", summary="版本历史（含当前线上版本与草稿）")
def list_versions(key: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """该内容 key 的全部历史版本，倒序。回滚产生的版本也在其中，一条不少。"""
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    versions = publish_svc.list_versions(db, key)
    current = publish_svc.get_current_version(db, key)
    return ok({
        "items": [_version_brief(v) for v in versions],
        "current_version": current.version if current else None,
        "draft_version": next((v.version for v in versions if v.status == "draft"), None),
    })


@router.get("/content/{key}/draft", summary="读取当前草稿")
def get_draft(key: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """取当前未发布的草稿（编辑器回填用）。没有草稿则返回 null，前端应回填线上值。"""
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    publish_svc.ensure_baseline(db, key)
    draft = publish_svc.get_draft(db, key)
    if not draft:
        return ok(None)
    return ok({
        "version_id": draft.id,
        "version": draft.version,
        "value": deserialize(key, draft.value),
        "change_summary": draft.change_summary,
        "based_on_version": draft.based_on_version,
        "updated_at": draft.created_at.isoformat() if draft.created_at else None,
    })


@router.post("/content/{key}/draft", summary="保存草稿（不影响线上）")
def save_draft(
    key: str,
    payload: DraftSaveIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """保存为草稿：**线上内容完全不变**，顾客看到的仍是已发布版本。"""
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    draft = publish_svc.save_draft(
        db, key, payload.value,
        editor_id=current_user.id,
        editor_name=current_user.name,
        change_summary=payload.change_summary,
    )
    return ok({
        "version_id": draft.id,
        "version": draft.version,
        "based_on_version": draft.based_on_version,
    }, "草稿已保存，线上内容未变更")


@router.post("/content/{key}/preview-token", summary="生成预览链接")
def create_preview(
    key: str,
    payload: PreviewTokenIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """生成短效预览令牌，拼成前台预览地址。

    地址形如：`/?preview_token=xxx&preview_key=banners`
    参数放在 URL search（`?` 后）而不是 hash 内，因为前台用 HashRouter，
    它只解析 `#` 之后的部分，search 不会被当成路由而 404。
    前台打开后会立刻把 token 从地址栏抹掉并转存到 sessionStorage，
    避免截图/复制链接把预览权限一起传播出去。
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    tok = publish_svc.create_preview_token(db, key, payload.version_id, current_user.id, current_user.name)
    return ok({
        "token": tok.token,
        "key": key,
        "expires_at": tok.expires_at.isoformat(),
        "ttl_minutes": publish_svc.PREVIEW_TOKEN_TTL_MINUTES,
        "max_uses": tok.max_uses,
        "preview_url": f"/?preview_token={tok.token}&preview_key={key}",
    })


@router.post("/content/{key}/publish", summary="发布草稿")
def publish(
    key: str,
    payload: PublishIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发布草稿 → 线上立即生效。

    - 变更说明必填（否则版本历史无法追溯）
    - 带乐观锁：编辑期间若他人已发布，返回 409 并提示基于最新版重做
    - 发布成功后该 key 的所有预览链接立即失效
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    ver = publish_svc.publish_version(
        db, key, payload.version_id, current_user.id, current_user.name, payload.change_summary
    )
    revoked = publish_svc.revoke_tokens_for_key(db, key)
    return ok({
        "version": ver.version,
        "published_at": ver.published_at.isoformat() if ver.published_at else None,
        "revoked_preview_tokens": revoked,
    }, "发布成功，线上已生效")


@router.post("/content/{key}/rollback", summary="回滚到历史版本")
def rollback(
    key: str,
    payload: RollbackIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """回滚到指定历史版本。

    回滚不是「指针回拨」，而是**用旧内容创建一个新版本**，因此：
      - 历史链条只增不减，任何版本都还在
      - 这次回滚本身也能被再次回滚
    返回的 version 是本次回滚**新产生**的版本号，不是 target_version。
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    ver = publish_svc.rollback_to_version(
        db, key, payload.target_version, current_user.id, current_user.name, payload.reason
    )
    publish_svc.revoke_tokens_for_key(db, key)
    return ok({
        "version": ver.version,
        "rollback_from_version": ver.rollback_from_version,
        "published_at": ver.published_at.isoformat() if ver.published_at else None,
    }, f"已回滚：内容取自 v{ver.rollback_from_version}，生成为新版本 v{ver.version}")


@router.post("/content/{key}/offline", summary="紧急下线当前内容")
def offline(
    key: str,
    payload: OfflineIn,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """紧急下线：把内容置空，前台按「区块为空即隐藏」规则立刻消失。

    内容本身仍在版本历史里，随时可用 rollback 恢复。
    用于「发布后发现内容有严重问题，先撤下来再慢慢修」的场景。
    """
    if key not in ALL_KEYS:
        raise not_found("内容不存在")
    publish_svc.set_offline(db, key, current_user.id, current_user.name, payload.reason)
    publish_svc.revoke_tokens_for_key(db, key)
    return ok(None, "已下线，前台该区块立即隐藏（内容仍保留在历史版本中）")

