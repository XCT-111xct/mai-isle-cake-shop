// ============================================================
// 文件功能：面包屑（UI-UX §4.8）
// 用法：<Breadcrumb items={[{label:'首页', to:'/'},{label:'蛋糕展示'}]} />
// ============================================================

import { Link } from 'react-router-dom'
import styles from './Common.module.css'

interface Crumb {
  label: string
  to?: string // 有 to 显示为链接，无 to 为当前页纯文本
}

export function Breadcrumb({ items }: { items: Crumb[] }) {
  return (
    <nav className={styles.breadcrumb} aria-label="面包屑导航">
      {items.map((c, i) => (
        <span key={i} className={styles.crumbItem}>
          {c.to ? <Link to={c.to}>{c.label}</Link> : <span className={styles.crumbCurrent}>{c.label}</span>}
          {i < items.length - 1 && <span className={styles.crumbSep}>/</span>}
        </span>
      ))}
    </nav>
  )
}

// ============================================================
// 文件功能：空状态（UI-UX §4.10）
// ============================================================
export function Empty({ title = '暂无内容', desc }: { title?: string; desc?: string }) {
  return (
    <div className={styles.empty}>
      <div className={styles.emptyIcon} aria-hidden="true">◌</div>
      <p className={styles.emptyTitle}>{title}</p>
      {desc && <p className={styles.emptyDesc}>{desc}</p>}
    </div>
  )
}

// ============================================================
// 文件功能：分页（UI-UX §4.9：12/页，当前页高亮，首末页禁用）
// ============================================================
export function Pagination({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (p: number) => void
}) {
  if (totalPages <= 1) return null
  return (
    <nav className={styles.pagination} aria-label="分页">
      <button
        type="button"
        className={styles.pageBtn}
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        aria-label="上一页"
      >
        ‹
      </button>
      {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
        <button
          key={p}
          type="button"
          className={`${styles.pageBtn} ${p === page ? styles.pageActive : ''}`}
          onClick={() => onChange(p)}
          aria-current={p === page ? 'page' : undefined}
        >
          {p}
        </button>
      ))}
      <button
        type="button"
        className={styles.pageBtn}
        disabled={page >= totalPages}
        onClick={() => onChange(page + 1)}
        aria-label="下一页"
      >
        ›
      </button>
    </nav>
  )
}

// ============================================================
// 文件功能：区块头（eyebrow 英文小标 + 大标题 + 右侧说明）
// ============================================================
export function SectionHead({
  eyebrow,
  title,
  em,
  right,
}: {
  eyebrow?: string
  title: string
  em?: string // 标题中需要斜体强调的词
  right?: React.ReactNode
}) {
  return (
    <div className={styles.secHead}>
      <div>
        {eyebrow && <p className={styles.eyebrow}>{eyebrow}</p>}
        <h2 className={styles.secTitle}>
          {em ? (
            <>
              {title.replace(em, '')}
              <em className={styles.secEm}>{em}</em>
            </>
          ) : (
            title
          )}
        </h2>
      </div>
      {right && <div className={styles.secRight}>{right}</div>}
    </div>
  )
}

// ============================================================
// 文件功能：静态页 Banner（深色底 + 大标题 + 英文装饰，支持图片背景）
// ============================================================
export function PageBanner({
  title,
  en,
  height = '52vh',
  imageUrl,
  eyebrow,
}: {
  title: string
  en: string
  height?: string
  imageUrl?: string
  /** 顶部装饰英文小标（带图片时显示） */
  eyebrow?: string
}) {
  if (imageUrl) {
    return (
      <section
        className={styles.pageHero}
        style={{ height, backgroundImage: `url(${imageUrl})` }}
        aria-label={title}
      >
        {/* 左→右暗化蒙版保证文字可读 */}
        <div className={styles.pageHeroShade} aria-hidden="true" />
        <div className={styles.pageHeroContent}>
          {eyebrow && <p className={styles.pageHeroEyebrow}>{eyebrow}</p>}
          <h1 className={styles.pageHeroTitle}>{title}</h1>
          <p className={styles.pageHeroEn}>{en}</p>
        </div>
      </section>
    )
  }
  return (
    <section className={styles.pageBanner} style={{ height }}>
      <div className={styles.bannerInner}>
        <h1 className={styles.bannerTitle}>{title}</h1>
        <p className={styles.bannerEn}>{en}</p>
      </div>
    </section>
  )
}

// ============================================================
// 文件功能：加载占位（禁止白屏，BUG-002 验收项）
// ============================================================
export function Spinner({ text = '加载中…' }: { text?: string }) {
  return (
    <div className={styles.spinner} role="status" aria-live="polite">
      <span className={styles.spinnerRing} aria-hidden="true" />
      <span className={styles.spinnerText}>{text}</span>
    </div>
  )
}
