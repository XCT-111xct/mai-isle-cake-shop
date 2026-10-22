# ============================================================
# 文件功能：订单号生成（技术开发文档 §7.8）
# 说明：
#   订单号 = YYYYMMDD + 当日 3 位序号（如 20260827001）
#   同日自增：查当日最大 order_no 后 +1（单 worker 部署，无并发冲突；
#   若未来多进程需加锁或改数据库自增）
# ============================================================

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import Order


def gen_order_no(db: Session, now: datetime) -> str:
    """生成当日订单号：YYYYMMDD + 3 位补零序号"""
    prefix = now.strftime("%Y%m%d")
    last = (
        db.query(Order.order_no)
        .filter(Order.order_no.like(f"{prefix}%"))
        .order_by(Order.order_no.desc())
        .first()
    )
    seq = int(last[0][-3:]) + 1 if last else 1
    return f"{prefix}{seq:03d}"
