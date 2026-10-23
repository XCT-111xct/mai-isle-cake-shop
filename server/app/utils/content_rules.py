# ============================================================
# 文件功能：内容 key 契约与校验规则（单一事实源）
#
# 为什么单独抽出来：
#   现在同一份内容有两条写入路径——「直接保存生效」和「存草稿后发布」。
#   如果两条路径各自写一份校验，早晚会走偏：比如直接保存允许 banner 空数组，
#   草稿保存却拒绝，运营会遇到「同一个值，换个按钮就报错」的鬼现象。
#   所以校验只此一份，两条路径都调它。
# ============================================================

import json
from typing import Any

from app.utils.response import bad_request

# 内容 key：JSON 解析型 vs Markdown 原样型（技术文档 §4.3 key 一览表）
JSON_KEYS = {
    "banners", "brand_chars", "brand_journey",
    "hardware", "software", "order_info", "contact_info",
}
MARKDOWN_KEYS = {"brand_story", "brand_value", "custom_tips"}
ALL_KEYS = JSON_KEYS | MARKDOWN_KEYS

MAX_MARKDOWN_LEN = 20000   # 富文本 ≤20000 字
MAX_BANNERS = 4            # Hero 轮播 ≤4 张（PRD v2.3）


def load_json_value(raw: str) -> Any:
    """解析 JSON 字符串，保留原类型（dict / list）。

    修复历史问题：早期写成 `dict if isinstance(data, dict) else {}` 会把数组
    强行转成空对象，导致 hardware/software 这类数组型内容读取时返回 {}。
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        data = {}
    return data if isinstance(data, (dict, list)) else {}


def validate_and_normalize(key: str, value: Any) -> Any:
    """按 key 类型校验并规范化，返回最终要存储的值（dict/list/str）。

    校验失败抛 BizError(400, 40001)，与接口层其它字段校验保持同一套错误码。
    """
    if key not in ALL_KEYS:
        raise bad_request("内容不存在")

    if key in JSON_KEYS:
        if not isinstance(value, (dict, list)):
            raise bad_request("该内容需为 JSON 对象或数组")
        if key == "banners":
            # 兼容 {"banners":[...]} 与裸数组两种历史写法
            banners = value.get("banners", value) if isinstance(value, dict) else value
            if not isinstance(banners, list) or len(banners) > MAX_BANNERS:
                raise bad_request("banners 需为数组，最多 4 张")
            value = {"banners": banners}
        return value

    # Markdown 型
    if not isinstance(value, str):
        raise bad_request("该内容需为文本（Markdown）")
    if len(value) > MAX_MARKDOWN_LEN:
        raise bad_request("内容长度不能超过 20000 字")
    return value


def serialize(value: Any) -> str:
    """把规范化后的值序列化成入库字符串（str 原样，其余转 JSON）"""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def deserialize(key: str, raw: str) -> Any:
    """读取时的反序列化（与 serialize 对称）"""
    if key in JSON_KEYS:
        return load_json_value(raw)
    return raw


def content_hash(raw: str) -> str:
    """内容快照的 SHA256，用于判断「草稿和线上内容是否真的不同」"""
    import hashlib
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()
