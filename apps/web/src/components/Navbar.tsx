// ============================================================
// 文件功能：顶部导航栏（UI-UX §5.0）
// 说明：
//   1. sticky 吸顶 + 毛玻璃背景
//   2. 主导航 5 项，"关于麦屿"悬停展开二级菜单（跳转锚点）
//   3. CN/EN 按钮仅样式占位（本期不翻译，PRD F1-7）
//   4. ≤980px 变为汉堡菜单（三线 → X 动画）
// ============================================================

import { useEffect, useRef, useState } from 'react'
import { NavLink, useLocation, useNavigate } from 'react-router-dom'
import styles from './Navbar.module.css'

// 导航项配置：path 与标签
const NAV_ITEMS = [
  { to: '/', label: '首页' },
  { to: '/about', label: '关于麦屿', sub: [
      { label: '品牌故事', anchor: 'anchor-story' },
      { label: '品牌理念', anchor: 'anchor-value' },
      { label: '品牌特色', anchor: 'anchor-chars' },
  ]},
  { to: '/cakes', label: '蛋糕展示' },
  { to: '/stores', label: '门店信息' },
  { to: '/contact', label: '联系我们' },
]

export default function Navbar() {
  const [menuOpen, setMenuOpen] = useState(false) // 移动端汉堡菜单开关
  const location = useLocation()
  const navigate = useNavigate()
  const lastPathRef = useRef(location.pathname)

  // 路由切换后关闭汉堡菜单
  useEffect(() => {
    setMenuOpen(false)
  }, [location.pathname])

  // 点击"关于麦屿"的二级子项：进入关于页并滚动到锚点
  function goToAboutAnchor(anchor: string) {
    setMenuOpen(false)
    // 已在关于页 → 直接平滑滚动；否则先跳转（由 AboutPage 读取 hash 后滚动）
    if (location.pathname === '/about') {
      scrollToAnchor(anchor)
    } else {
      navigate(`/about#${anchor}`)
    }
  }

  // 平滑滚动到锚点（offset 130px 修正 sticky 导航遮挡）
  function scrollToAnchor(anchor: string) {
    const el = document.getElementById(anchor)
    if (!el) return
    const y = el.getBoundingClientRect().top + window.scrollY - 130
    window.scrollTo({ top: y, behavior: 'smooth' })
  }

  // 判断某个导航项是否"当前页"（用于高亮）
  function isActive(to: string): boolean {
    if (to === '/') return location.pathname === '/'
    return location.pathname.startsWith(to)
  }

  return (
    <header className={styles.header}>
      <div className={styles.inner}>
        {/* ---- Logo ---- */}
        <NavLink to="/" className={styles.logo} aria-label="麦屿手作首页">
          <img src={`${import.meta.env.BASE_URL}logo.webp`} alt="麦屿手作 LOGO" className={styles.logoMark} />
          <span className={styles.logoText}>
            <span className={styles.logoZh}>麦屿手作</span>
            <span className={styles.logoEn}>MAI·ISLE</span>
          </span>
        </NavLink>

        {/* ---- 主导航（桌面） ---- */}
        <nav className={styles.nav} aria-label="主导航">
          {NAV_ITEMS.map((item) =>
            item.sub ? (
              // 有二级菜单的项（关于麦屿）
              <div key={item.to} className={styles.navItemWrap}>
                <NavLink
                  to={item.to}
                  className={`${styles.navLink} ${isActive(item.to) ? styles.navActive : ''}`}
                >
                  {item.label}
                  <svg className={styles.caret} width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M6 9l6 6 6-6"/></svg>
                </NavLink>
                {/* 悬停下拉：品牌故事 / 品牌理念 / 品牌特色 */}
                <div className={styles.dropdown}>
                  {item.sub.map((s) => (
                    <button key={s.anchor} type="button" onClick={() => goToAboutAnchor(s.anchor)}>
                      {s.label}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <NavLink
                key={item.to}
                to={item.to}
                className={`${styles.navLink} ${isActive(item.to) ? styles.navActive : ''}`}
              >
                {item.label}
              </NavLink>
            )
          )}
        </nav>

        {/* ---- 右侧：CN/EN + 汉堡 ---- */}
        <div className={styles.aux}>
          {/* 语言切换：仅样式占位，本期不实际翻译（PRD F1-7） */}
          <div className={styles.lang} role="group" aria-label="语言切换（占位）">
            <span className={`${styles.langItem} ${styles.langActive}`}>CN</span>
            <span className={styles.langDivider}>/</span>
            <span className={styles.langItem}>EN</span>
          </div>
          {/* 汉堡按钮（≤980px 显示） */}
          <button
            type="button"
            className={`${styles.burger} ${menuOpen ? styles.burgerOpen : ''}`}
            aria-label={menuOpen ? '关闭菜单' : '打开菜单'}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen((v) => !v)}
          >
            <span /><span /><span />
          </button>
        </div>
      </div>

      {/* ---- 移动端全宽下拉菜单 ---- */}
      {menuOpen && (
        <div className={styles.mobileMenu}>
          {NAV_ITEMS.map((item) => (
            <div key={item.to} className={styles.mobileGroup}>
              <NavLink to={item.to} className={styles.mobileLink} onClick={() => setMenuOpen(false)}>
                {item.label}
              </NavLink>
              {/* 二级子项缩进 56px（UI-UX §5.0） */}
              {item.sub?.map((s) => (
                <button key={s.anchor} type="button" className={styles.mobileSub} onClick={() => goToAboutAnchor(s.anchor)}>
                  {s.label}
                </button>
              ))}
            </div>
          ))}
        </div>
      )}
    </header>
  )
}
