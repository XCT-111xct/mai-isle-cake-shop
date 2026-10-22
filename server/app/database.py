# ============================================================
# 文件功能：数据库引擎与会话管理（技术开发文档 §7.4）
# 说明：
#   1. SQLite 单文件数据库（database/mai_isle.db，路径来自 config.py）
#   2. 【关键】SQLite 默认不启用外键约束！必须显式 PRAGMA foreign_keys=ON，
#      否则 cake_spec 的 ON DELETE CASCADE、category/cake 外键校验全部静默失效
#      （技术开发文档 §7.4 + 评审清单 B1 类坑）
#   3. 提供 get_db 依赖（FastAPI 每个请求独立会话）
# ============================================================

from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.config import settings

# ---------- 确保数据库目录存在（SQLite 不会自动创建目录） ----------
Path(settings.DB_PATH).parent.mkdir(parents=True, exist_ok=True)

# ---------- 数据库连接 ----------
# SQLite 特殊参数 check_same_thread=False：
# FastAPI 是多线程处理的，SQLite 默认只允许创建连接的线程使用，必须放开
engine = create_engine(
    f"sqlite:///{settings.DB_PATH}",
    connect_args={"check_same_thread": False},
)


# ---------- 【关键】启用 SQLite 外键约束 ----------
# 每个数据库连接建立时执行 PRAGMA foreign_keys=ON
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# ---------- 会话工厂 ----------
# autoflush=False：查询前不自动刷写未提交改动，避免隐式写库
# autocommit=False：显式 commit 才提交（配合路由里 try/commit/rollback）
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# ---------- ORM 基类 ----------
class Base(DeclarativeBase):
    """所有 ORM 模型继承此基类（SQLAlchemy 2.x 声明式风格）"""

    pass


# ---------- 建表 ----------
def init_db():
    """首次运行建表（幂等：已存在的表跳过）。
    注意：本项目未引入 Alembic 迁移工具（技术开发文档 §4.3 变更管理），
    改表结构时需同步更新 DDL 文档并重建或手工 ALTER。"""
    Base.metadata.create_all(bind=engine)


# ---------- FastAPI 依赖：请求级会话 ----------
def get_db():
    """FastAPI 依赖注入：每个请求获取一个独立数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
