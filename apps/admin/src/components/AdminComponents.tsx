// ============================================================
// 文件功能：后台通用组件（UI-UX §4 组件规范）
//   PageHeader / StatCard / Table / Modal / Switch /
//   StatusBadge / Tag / Empty / Pagination / Toast
// ============================================================

import { useEffect } from 'react'
import styles from './AdminComponents.module.css'

// ---------- 页头（meta 英文小标 + 标题） ----------
export function PageHeader({ meta, title, em, actions }: {
  meta: string
  title: string
  em?: string
  actions?: React.ReactNode
}) {
  return (
    <div className={styles.pageHeader}>
      <div>
        <p className={styles.pageMeta}>{meta}</p>
        <h1 className={styles.pageTitle}>
          {title}
          {em && <em className={styles.pageEm}>{em}</em>}
        </h1>
      </div>
      {actions && <div className={styles.pageActions}>{actions}</div>}
    </div>
  )
}

// ---------- 统计卡（仪表盘） ----------
export function StatCard({ label, value, sub, icon }: {
  label: string
  value: string | number
  sub?: React.ReactNode
  icon?: string
}) {
  return (
    <div className={styles.statCard}>
      <div className={styles.statTop}>
        <span className={styles.statLabel}>{label}</span>
        {icon && <span className={styles.statIcon} aria-hidden="true">{icon}</span>}
      </div>
      <p className={styles.statValue}>{value}</p>
      {sub && <p className={styles.statSub}>{sub}</p>}
    </div>
  )
}

// ---------- 表格（表头 --bg-soft 大写、行 hover） ----------
export function Table({ columns, data, rowKey, empty }: {
  columns: { key: string; title: string; width?: string; render?: (row: Record<string, unknown>, index: number) => React.ReactNode }[]
  data: Record<string, unknown>[]
  rowKey: string
  empty?: React.ReactNode
}) {
  if (data.length === 0) {
    return empty ?? <Empty title="暂无数据" />
  }
  return (
    <div className={styles.tableWrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} style={c.width ? { width: c.width } : undefined}>{c.title}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((row, i) => (
            <tr key={String(row[rowKey] ?? i)}>
              {columns.map((c) => (
                <td key={c.key}>{c.render ? c.render(row, i) : String(row[c.key] ?? '')}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ---------- Modal（遮罩 blur、ESC 关闭、body 滚动锁定） ----------
export function Modal({ open, title, onClose, children, footer, width = 640 }: {
  open: boolean
  title: string
  onClose: () => void
  children: React.ReactNode
  footer?: React.ReactNode
  width?: number
}) {
  // ESC 关闭 + body 滚动锁定
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className={styles.modalMask} onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div className={styles.modal} style={{ maxWidth: width }} role="dialog" aria-modal="true" aria-label={title}>
        <div className={styles.modalHead}>
          <h3 className={styles.modalTitle}>{title}</h3>
          <button type="button" className={styles.modalClose} onClick={onClose} aria-label="关闭弹窗">×</button>
        </div>
        <div className={styles.modalBody}>{children}</div>
        {footer && <div className={styles.modalFooter}>{footer}</div>}
      </div>
    </div>
  )
}

// ---------- Switch（42×24，开 --brown） ----------
export function Switch({ checked, onChange, label }: {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      className={`${styles.switch} ${checked ? styles.switchOn : ''}`}
      onClick={() => onChange(!checked)}
    >
      <span className={styles.switchDot} />
    </button>
  )
}

// ---------- 状态徽章（订单 4 态 + 留言 + 启用停用） ----------
export function StatusBadge({ status }: { status: string }) {
  const map: Record<string, { text: string; cls: string }> = {
    pending: { text: '待处理', cls: styles.badgePending },
    confirmed: { text: '已确认', cls: styles.badgeConfirmed },
    completed: { text: '已完成', cls: styles.badgeCompleted },
    cancelled: { text: '已取消', cls: styles.badgeCancelled },
    done: { text: '已处理', cls: styles.badgeCompleted },
    active: { text: '启用', cls: styles.badgeCompleted },
    inactive: { text: '停用', cls: styles.badgeCancelled },
  }
  const m = map[status] ?? { text: status, cls: styles.badgePending }
  return <span className={`${styles.badge} ${m.cls}`}>{m.text}</span>
}

// ---------- 角色徽章 ----------
export function RoleBadge({ role }: { role: string }) {
  return (
    <span className={`${styles.badge} ${role === 'super' ? styles.badgeConfirmed : styles.badgePending}`}>
      {role === 'super' ? '超级管理员' : '运营管理员'}
    </span>
  )
}

// ---------- Tag（筛选标签 + 分类管理 × 删除角标） ----------
export function Tag({ active, onClick, children, onRemove, count }: {
  active?: boolean
  onClick?: () => void
  children: React.ReactNode
  onRemove?: () => void
  count?: number
}) {
  return (
    <span
      className={`${styles.tag} ${active ? styles.tagActive : ''} ${onClick ? styles.tagClickable : ''}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
    >
      {children}
      {count !== undefined && <span className={styles.tagCount}>{count}</span>}
      {onRemove && (
        <button type="button" className={styles.tagRemove} onClick={(e) => { e.stopPropagation(); onRemove() }} aria-label="删除">×</button>
      )}
    </span>
  )
}

// ---------- 空状态 ----------
export function Empty({ title = '暂无数据', desc }: { title?: string; desc?: string }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon} aria-hidden="true">◌</div>
      <p className={styles.emptyTitle}>{title}</p>
      {desc && <p className={styles.emptyDesc}>{desc}</p>}
    </div>
  )
}

// ---------- 分页 ----------
export function Pagination({ page, totalPages, onChange }: {
  page: number
  totalPages: number
  onChange: (p: number) => void
}) {
  if (totalPages <= 1) return null
  return (
    <nav className={styles.pagination} aria-label="分页">
      <button type="button" className={styles.pageBtn} disabled={page <= 1} onClick={() => onChange(page - 1)}>‹</button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
        <button key={p} type="button"
          className={`${styles.pageBtn} ${p === page ? styles.pageActive : ''}`}
          onClick={() => onChange(p)}
          aria-current={p === page ? 'page' : undefined}>{p}</button>
      ))}
      <button type="button" className={styles.pageBtn} disabled={page >= totalPages} onClick={() => onChange(page + 1)}>›</button>
    </nav>
  )
}

// ---------- Toast（成功/错误提示条，4s 自动消失） ----------
export function Toast({ toast }: { toast: { type: 'success' | 'error'; text: string } | null }) {
  if (!toast) return null
  return (
    <div className={`${styles.toast} ${toast.type === 'success' ? styles.toastSuccess : styles.toastError}`}
      role="status" aria-live="polite">
      {toast.text}
    </div>
  )
}

// ---------- Loading 占位 ----------
export function Spinner({ text = '加载中…' }: { text?: string }) {
  return (
    <div className={styles.spinner} role="status" aria-live="polite">
      <span className={styles.spinnerRing} aria-hidden="true" />
      <span>{text}</span>
    </div>
  )
}
