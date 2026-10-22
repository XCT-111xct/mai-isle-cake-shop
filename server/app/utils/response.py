# ============================================================
# 文件功能：统一响应封装 + 业务异常（技术开发文档 §7.3）
# 说明：
#   所有接口返回 { "code": 0, "message": "success", "data": {...} }
#   HTTP 状态码与业务 code 配合使用（错误码表见技术开发文档 §5.1.4）
# ============================================================


def ok(data=None, message="success"):
    """成功响应：code=0"""
    return {"code": 0, "message": message, "data": data}


class BizError(Exception):
    """业务异常：携带 HTTP 状态码与业务 code，由 main.py 全局处理器统一转 JSON。

    用法示例：
        raise BizError(400, 40001, "姓名需为 2-20 个字符")
        raise BizError(404, 40400, "产品不存在或已下架")
    """

    def __init__(self, http_status: int, code: int, message: str):
        self.http_status = http_status
        self.code = code
        self.message = message
        super().__init__(message)


# ---------- 常用业务异常快捷构造（减少重复参数） ----------
def bad_request(message: str, code: int = 40001) -> BizError:
    """参数校验失败 400/40001"""
    return BizError(400, code, message)


def not_found(message: str = "记录不存在") -> BizError:
    """资源不存在 404/40400"""
    return BizError(404, 40400, message)


def conflict(message: str) -> BizError:
    """数据冲突 409/40900（如产品/分类重名）"""
    return BizError(409, 40900, message)


def forbidden(message: str = "权限不足") -> BizError:
    """权限不足 403/40300"""
    return BizError(403, 40300, message)


def unauthorized(message: str = "未登录", code: int = 40100) -> BizError:
    """未登录 / Token 过期 401"""
    return BizError(401, code, message)
