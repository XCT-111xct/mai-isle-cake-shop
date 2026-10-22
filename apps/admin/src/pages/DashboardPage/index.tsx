// ============================================================
// 文件功能：仪表盘（UI-UX §6.2，PRD F9）
// 数据：GET /api/v1/admin/dashboard/stats（实时统计，无缓存）
//  统计卡×4 / 最近订单（左 1.4fr）/ 状态分布（右 1fr）/ 最近留言（通栏）
// ============================================================

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '@/api/client'
import type { DashboardStats } from '@/api/types'
import { PageHeader, StatCard, StatusBadge, Spinner } from '@/components/AdminComponents'
import { formatDateTime } from '@/utils/datetime'
import styles from './DashboardPage.module.css'

const STATUS_LABEL: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'var(--badge-pending-bg)' },
  confirmed: { label: '已确认', color: 'var(--badge-confirmed-bg)' },
  completed: { label: '已完成', color: 'var(--badge-completed-bg)' },
  cancelled: { label: '已取消', color: 'var(--badge-cancelled-bg)' },
}

export default function DashboardPage() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/dashboard/stats')
      .then((r) => setStats(r.data.data as DashboardStats))
      .catch(() => setStats(null))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <><PageHeader meta="DASHBOARD · 概览" title="仪表盘" /><Spinner text="统计数据加载中…" /></>
  if (!stats) return <><PageHeader meta="DASHBOARD · 概览" title="仪表盘" /><p>统计数据加载失败</p></>

  const dist = stats.order_status_distribution
  const distTotal = Math.max(dist.pending + dist.confirmed + dist.completed + dist.cancelled, 1)

  return (
    <div>
      <PageHeader meta="DASHBOARD · 概览" title="仪表盘" />

      {/* ========== 统计卡 ×4 ========== */}
      <div className={styles.statGrid}>
        <StatCard label="蛋糕总数" value={stats.cake_count}
          sub={<>本月新增 <b style={{ color: 'var(--brown)' }}>+{stats.cake_month_new}</b></>} icon="🍰" />
        <StatCard label="本月订单" value={stats.month_order_count}
          sub={<>较上月 <b style={{ color: 'var(--brown)' }}>+{stats.month_order_growth}%</b></>} icon="📦" />
        <StatCard label="门店总数" value={stats.store_count}
          sub={<>在营 {stats.store_active} · 停用 {stats.store_inactive}</>} icon="🏪" />
        <StatCard label="未处理留言" value={stats.pending_message_count}
          sub={<>需跟进 <b style={{ color: 'var(--brown)' }}>{stats.need_follow_count}</b> 条</>} icon="✉️" />
      </div>

      {/* ========== 最近订单 + 状态分布 ========== */}
      <div className={styles.midRow}>
        {/* 左：最近订单（1.4fr） */}
        <div className={styles.card}>
          <div className={styles.cardHead}>
            <h3 className={styles.cardTitle}>最近订单</h3>
            <Link to="/orders" className={styles.viewAll}>查看全部 →</Link>
          </div>
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr><th>订单号</th><th>客户</th><th>产品</th><th>金额</th><th>状态</th></tr>
              </thead>
              <tbody>
                {stats.recent_orders.slice(0, 10).map((o) => (
                  <tr key={o.id}>
                    <td className={styles.orderNo}>{o.order_no}</td>
                    <td>{o.customer_name}</td>
                    <td>{o.cake_name}</td>
                    <td className={styles.amount}>¥{o.amount}</td>
                    <td><StatusBadge status={o.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* 右：订单状态分布（1fr） */}
        <div className={styles.card}>
          <h3 className={styles.cardTitle}>订单状态分布</h3>
          <div className={styles.distList}>
            {(['pending', 'confirmed', 'completed', 'cancelled'] as const).map((k) => (
              <div key={k} className={styles.distRow}>
                <div className={styles.distLabelRow}>
                  <span>{STATUS_LABEL[k].label}</span>
                  <span className={styles.distCount}>{dist[k]}</span>
                </div>
                <div className={styles.distTrack}>
                  <div
                    className={styles.distFill}
                    style={{
                      width: `${(dist[k] / distTotal) * 100}%`,
                      background: STATUS_LABEL[k].color,
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
          <p className={styles.distNote}>本月转化率 {Math.round((dist.completed / distTotal) * 100)}%</p>
        </div>
      </div>

      {/* ========== 最近留言（通栏） ========== */}
      <div className={styles.card}>
        <div className={styles.cardHead}>
          <h3 className={styles.cardTitle}>最近留言</h3>
          <Link to="/messages" className={styles.viewAll}>查看全部 →</Link>
        </div>
        <div className={styles.tableWrap}>
          <table className={styles.table}>
            <thead>
              <tr><th>ID</th><th>姓名</th><th>电话</th><th>留言预览</th><th>提交时间</th><th>状态</th></tr>
            </thead>
            <tbody>
              {stats.recent_messages.map((m) => (
                <tr key={m.id}>
                  <td>#{m.id}</td>
                  <td>{m.name}</td>
                  <td>{m.phone}</td>
                  <td className={styles.preview}>{m.content}</td>
                  <td className={styles.time}>{formatDateTime(m.created_at)}</td>
                  <td><StatusBadge status={m.status} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
