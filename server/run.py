# ============================================================
# 文件功能：后端启动入口
# 用法：
#   python run.py           # 等价于 uvicorn app.main:app --port 8000（热重载）
#   python run.py --seed    # 先执行种子数据初始化，再启动（单进程，推荐首次使用）
# 说明：
#   --seed 模式在【同一进程】内完成 seed + 启动，避免多进程先写后读
#   导致的 SQLite 文件锁冲突（本地开发最稳）。
# ============================================================

import sys

import uvicorn

# 项目配置（端口、调试开关等，集中在这里改）
from app.config import settings


def main():
    seed_first = "--seed" in sys.argv

    if seed_first:
        # 在【当前进程】内执行种子数据（幂等：已存在的数据跳过）
        from seed import seed
        seed()

        # 单进程模式：直接传入 app 对象，不启用热重载（reload 会 fork 子进程，
        # 子进程与 seed 进程分离，可能触发沙箱/文件锁问题）
        from app.main import app
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=settings.PORT,
            reload=False,
        )
    else:
        # 普通开发模式：热重载（代码改动自动重启）
        uvicorn.run(
            "app.main:app",  # 加载路径：app 包下的 main.py 里的 app 实例
            host="0.0.0.0",
            port=settings.PORT,
            reload=settings.DEBUG,
        )


# 程序主入口：被 python run.py 调用时才执行（被 import 时不执行）
if __name__ == "__main__":
    main()
