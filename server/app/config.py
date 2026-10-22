# ============================================================
# 文件功能：后端全局配置（集中管理所有可调参数）
# 说明：所有环境相关的配置都放这里，代码其他地方引用 settings.xxx
#
# 【重要】配置读取顺序：环境变量 > 开发默认值
#   为什么这么设计？
#   —— 同一份代码要能在"老大的笔记本"和"线上服务器"上跑，
#      但两台机器的密钥、域名、调试开关必然不同。
#      写死在代码里就只能改代码（改代码就会把密钥提交进 git）；
#      放进环境变量，代码库永远是干净的，密钥只活在服务器上。
# ============================================================

import os
from pathlib import Path

# ---------- 运行环境标识 ----------
# 作用：区分"本地开发"和"线上生产"两套行为
# 取值：dev（默认）/ production
# 用法：启动后端时带上环境变量 MAI_ISLE_ENV=production 即进入生产模式
APP_ENV = os.getenv("MAI_ISLE_ENV", "dev").strip().lower()

# 是否生产环境的布尔标记（下面多处安全校验都以它为开关）
IS_PROD = APP_ENV == "production"

# ---------- 路径配置 ----------
# 后端根目录（server/），用 Path 处理跨平台路径
BASE_DIR = Path(__file__).resolve().parent.parent

# ---------- 可选加载 .env 文件 ----------
# 作用：让密钥可以写在 server/.env 文件里，不用每次启动前手动设环境变量
# 说明①：用 try/except 包起来 —— 没装 python-dotenv 也能正常跑，不会报错
# 说明②：load_dotenv 默认【不覆盖】已存在的环境变量，
#        所以"服务器上设的真实环境变量"优先级永远高于".env 文件"，这正是我们要的顺序
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # 没安装 python-dotenv 时静默跳过
    pass

# 上传图片根目录：server/uploads/
# 允许用环境变量覆盖，因为线上通常把图片放在独立的数据盘（挂载卷）上，
# 而不是放在代码目录里（代码目录重新部署会被覆盖，图片就丢了）
UPLOAD_DIR = Path(os.getenv("MAI_ISLE_UPLOAD_DIR") or (BASE_DIR / "uploads"))

# SQLite 数据库文件：项目根/database/mai_isle.db
# 说明：实施方案约定数据库放在独立 database/ 目录（交付物清单 #4）
# 同样允许环境变量覆盖，理由同上：数据库属于"数据"，不该跟着代码目录走
DB_PATH = Path(os.getenv("MAI_ISLE_DB_PATH") or (BASE_DIR.parent / "database" / "mai_isle.db"))

# ---------- 服务配置 ----------
# 后端监听端口（对齐实施方案 §2 架构图）
PORT = int(os.getenv("MAI_ISLE_PORT", "8000"))

# 调试开关：控制 ① uvicorn 热重载 ② 报错详细堆栈 ③ 验证码演示后门
# 【安全要点】生产环境必须为 0，原因见下方验证码后门说明
# 取值逻辑：环境变量优先；取不到时按环境给默认值（本地默认开、生产默认关）
DEBUG = (os.getenv("MAI_ISLE_DEBUG") or ("0" if IS_PROD else "1")).strip() == "1"

# ---------- JWT 认证配置 ----------
# 开发用默认密钥：写死在代码里，允许公开，因为它只用于本地调试
DEV_SECRET_KEY = "mai-isle-dev-secret-key-change-in-production"

# 生产密钥：必须由环境变量 MAI_ISLE_SECRET 提供，代码里永不出现真值
# 语法说明：`os.getenv(...) or ""` 先取环境变量（取不到给空串），
#          `.strip()` 去掉首尾空格（防手滑多打个回车），
#          `or DEV_SECRET_KEY` 表示"前面全是空的才用开发默认值"
SECRET_KEY = (os.getenv("MAI_ISLE_SECRET") or "").strip() or DEV_SECRET_KEY

ALGORITHM = "HS256"          # JWT 签名算法
ACCESS_TOKEN_EXPIRE_MINUTES = 30   # Token 有效期 30 分钟（无操作失效，实施方案 §1.3）
# 无操作失效的实现：后端在每次鉴权时检查 Token 的 iat（签发时间），
# 超过 30 分钟即拒绝 —— 细节在阶段 1 security.py 中实现

# ---------- 登录锁定策略（技术文档 §7.6） ----------
LOGIN_MAX_FAIL = 5           # 连续错误 5 次触发锁定
LOGIN_LOCK_MINUTES = 15      # 锁定 15 分钟

# ---------- 图形验证码（技术文档 §7.7） ----------
CAPTCHA_EXPIRE_MINUTES = 5   # 验证码 5 分钟有效
CAPTCHA_LENGTH = 4           # 4 位字符

# ---------- 图片上传限制（技术文档 §7.4） ----------
MAX_UPLOAD_SIZE = 5 * 1024 * 1024  # 最大 5MB（单位：字节）
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}  # 允许的图片格式
# 上传目录白名单：dir 参数只允许这四个值，防止路径穿越
UPLOAD_DIRS = ["cakes", "banners", "stores", "brand"]

# ---------- CORS 白名单 ----------
# 默认值：本地开发的两个 Vite 端口（前端通过 Vite 代理访问后端，同源其实无需 CORS）
# 生产值：环境变量 MAI_ISLE_CORS 用英文逗号分隔多个域名
#   例：MAI_ISLE_CORS="https://mai-isle.com,https://admin.mai-isle.com"
_cors_env = (os.getenv("MAI_ISLE_CORS") or "").strip()
CORS_ORIGINS = [x.strip() for x in _cors_env.split(",") if x.strip()] or [
    "http://localhost:5173",  # 前台
    "http://localhost:5174",  # 后台
]


# ---------- 启动前安全体检（生产环境不合格就拒绝启动） ----------
def _validate_production_config() -> None:
    """生产环境安全体检：任何一项不合格，进程直接起不来。

    为什么要在启动时"炸掉"，而不是打条警告继续跑？
    —— 因为警告躺在日志里没人看，等到被入侵才发现就晚了。
       "起不来"会逼着部署的人当场解决，"能跑但不安全"则会被一直忽略。
       这就是业界的 fail fast（快速失败）原则。

    检查三件事：
      1. JWT 密钥是否还是代码里的开发默认值
      2. JWT 密钥长度是否够（HS256 建议 ≥32 字符随机串）
      3. DEBUG 是否被误开（会连带打开验证码后门，见下方说明）
    """
    problems = []   # 收集所有问题，一次性全告诉部署的人，免得改一个重启一次

    if SECRET_KEY == DEV_SECRET_KEY:
        problems.append(
            "SECRET_KEY 仍是代码里的开发默认值 —— 这个值已经公开在 GitHub 上，"
            "任何人都能拿它伪造管理员登录凭证"
        )
    if len(SECRET_KEY) < 32:
        problems.append(
            f"SECRET_KEY 长度只有 {len(SECRET_KEY)} 字符，HS256 建议至少 32 字符随机串"
        )
    if DEBUG:
        problems.append(
            "DEBUG=True —— 生产环境开启调试会打开两个口子："
            "① 接口报错时向客户端返回详细堆栈（可能泄露表结构、服务器文件路径）"
            "② 验证码后门（captcha_id=DEMO + captcha=8888 可直接绕过图形验证码登录）"
        )

    # 说明：接口文档页 /docs 由 main.py 按 IS_PROD 独立关闭，
    #      不受本开关控制 —— 这里不重复检查，避免出现"以为关了其实没关"的错觉

    if problems:
        raise RuntimeError(
            "【生产环境安全配置不合格，已拒绝启动】\n  - "
            + "\n  - ".join(problems)
            + "\n\n修复方法：启动前设置以下环境变量后重试\n"
            + "  MAI_ISLE_SECRET=<32 位以上随机串>   生成命令：python -c \"import secrets;print(secrets.token_urlsafe(48))\"\n"
            + "  MAI_ISLE_DEBUG=0\n"
            + "（开发环境不需要设这些，本地跑会自动用默认值）"
        )


# ---------- 配置命名空间对象 settings ----------
# 文件功能：把上面全部模块级常量聚合为一个 settings 对象，
#           供 run.py / main.py 通过 `from app.config import settings` 统一引用。
# 说明：阶段 0 骨架期用 SimpleNamespace 轻量聚合；
#       阶段 1 如需要环境变量覆盖，可升级为 Pydantic Settings（对齐技术文档风格）。
from types import SimpleNamespace

settings = SimpleNamespace(
    APP_ENV=APP_ENV,              # 运行环境标识（dev / production）
    IS_PROD=IS_PROD,              # 是否生产环境
    PORT=PORT,                    # 后端监听端口（uvicorn.run 使用）
    DEBUG=DEBUG,                  # 调试开关（uvicorn 热重载使用）
    UPLOAD_DIR=str(UPLOAD_DIR),   # 上传图片根目录（静态挂载使用）
    DB_PATH=str(DB_PATH),         # SQLite 数据库文件路径
    SECRET_KEY=SECRET_KEY,        # JWT 签名密钥
    ALGORITHM=ALGORITHM,          # JWT 签名算法
    ACCESS_TOKEN_EXPIRE_MINUTES=ACCESS_TOKEN_EXPIRE_MINUTES,  # Token 有效期（分钟）
    LOGIN_MAX_FAIL=LOGIN_MAX_FAIL,          # 登录最大错误次数
    LOGIN_LOCK_MINUTES=LOGIN_LOCK_MINUTES,  # 登录锁定分钟数
    CAPTCHA_EXPIRE_MINUTES=CAPTCHA_EXPIRE_MINUTES,  # 验证码有效期（分钟）
    CAPTCHA_LENGTH=CAPTCHA_LENGTH,          # 验证码字符数
    MAX_UPLOAD_SIZE=MAX_UPLOAD_SIZE,        # 图片上传大小上限（字节）
    ALLOWED_EXTENSIONS=ALLOWED_EXTENSIONS,  # 允许的图片扩展名集合
    UPLOAD_DIRS=UPLOAD_DIRS,                # 上传子目录白名单
    CORS_ORIGINS=CORS_ORIGINS,              # CORS 允许的来源列表
)

# 最后一步：如果当前是生产环境，跑一遍安全体检（不合格则此处抛异常，进程退出）
if IS_PROD:
    _validate_production_config()
