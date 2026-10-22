# ============================================================
# 文件功能：后台内容管理（技术开发文档 §5.3.7）
#   内容 key 列表/读取/保存 + banner 子接口（独立增删改单张）
#   注意：banners 子接口注册在前，避免被 /content/{key} 捕获
# ============================================================

import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Content
from app.schemas import BannerItem, ContentUpdate
from app.utils.response import BizError, bad_request, not_found, ok

router = APIRouter()

# 与前台一致：JSON 解析型 vs Markdown 原样型（技术文档 §4.3 key 一览表）
JSON_KEYS = {
    "banners", "brand_chars", "brand_journey",
    "hardware", "software", "order_info", "contact_info",
}
MARKDOWN_KEYS = {"brand_story", "brand_value", "custom_tips"}
ALL_KEYS = JSON_KEYS | MARKDOWN_KEYS

MAX_MARKDOWN_LEN = 20000   # 富文本 ≤20000 字
MAX_BANNERS = 4            # Hero 轮播 ≤4 张（PRD v2.3）


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
    修复：之前 isinstance(data, dict) else {} 会把数组强行转空对象，
    导致 hardware/software 这类数组型内容读取时返回 {}。"""
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        data = {}
    return data if isinstance(data, (dict, list)) else {}


def _save(db: Session, key: str, value) -> dict:
    """通用保存：str → 原样（Markdown）；dict/list → JSON 序列化"""
    row = _get_or_create(db, key)
    if isinstance(value, str):
        if len(value) > MAX_MARKDOWN_LEN:
            raise bad_request("内容长度不能超过 20000 字")
        row.value = value
    else:
        row.value = json.dumps(value, ensure_ascii=False)
    db.commit()
    db.refresh(row)
    return {"key": key, "updated_at": row.updated_at.isoformat() if row.updated_at else None}


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


def _write_banners(db: Session, banners: list):
    if len(banners) > MAX_BANNERS:
        raise bad_request("banner 最多 4 张")
    _save(db, "banners", {"banners": banners})


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
    _write_banners(db, banners)
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
    _write_banners(db, banners)
    return ok({"id": banner_id})


@router.delete("/content/banners/{banner_id}", summary="删除 banner")
def delete_banner(banner_id: int, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """删除单张 banner"""
    banners = _read_banners(db)
    new_list = [b for b in banners if b.get("id") != banner_id]
    if len(new_list) == len(banners):
        raise not_found("banner 不存在")
    _write_banners(db, new_list)
    return ok(None, "success")


# ============================================================
# 内容 key 管理
# ============================================================

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


@router.put("/content/{key}", summary="保存内容")
def update_content(key: str, payload: ContentUpdate, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    """保存某 key 的 value：保存后前台实时生效（前端每次进页面重新拉取）"""
    if key not in ALL_KEYS:
        raise not_found("内容不存在")

    value = payload.value
    if key in JSON_KEYS:
        if not isinstance(value, (dict, list)):
            raise bad_request("该内容需为 JSON 对象或数组")
        if key == "banners":
            # 兼容 {"banners":[...]} 或裸数组
            banners = value.get("banners", value) if isinstance(value, dict) else value
            if not isinstance(banners, list) or len(banners) > MAX_BANNERS:
                raise bad_request("banners 需为数组，最多 4 张")
            value = {"banners": banners}
    else:
        if not isinstance(value, str):
            raise bad_request("该内容需为文本（Markdown）")

    return ok(_save(db, key, value))
