// ============================================================
// 文件功能：后台全局布局（侧边栏 + 主区，UI-UX §6.0）
// 说明：
//   1. 240px 侧边栏：Logo + 7 菜单 + 底部用户信息 + 退出
//   2. 运营管理员（ops）不显示"管理员管理"菜单（前端隐藏 + 后端 40300 双重拦截）
//   3. ≤980px：侧边栏折叠为顶部静态区块
// ============================================================

import { NavLink, Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import styles from './AdminLayout.module.css'

// 菜单配置（superOnly: true 的仅超管可见）
const MENUS = [
  { key: 'dashboard', path: '/dashboard', label: '仪表盘', icon: <path d="M3 13h8V3H3v10zm0 8h8v-6H3v6zm10 0h8V11h-8v10zm0-18v6h8V3h-8z" /> },
  { key: 'products', path: '/products', label: '商品管理', icon: <path d="M4 7l8-4 8 4-8 4-8-4zm0 6v6l8 4 8-4v-6M4 7v6l8 4 8-4V7" /> },
  { key: 'orders', path: '/orders', label: '订单管理', icon: <path d="M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9l2 2 4-4" /> },
  { key: 'stores', path: '/stores', label: '门店管理', icon: <path d="M12 22s8-4 8-10a8 8 0 1 0-16 0c0 6 8 10 8 10zm0-7a3 3 0 1 1 0-6 3 3 0 0 1 0 6z" /> },
  { key: 'content', path: '/content', label: '内容管理', icon: <path d="M12 5v14M5 12h14" /> },
  { key: 'messages', path: '/messages', label: '留言管理', icon: <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" /> },
  { key: 'users', path: '/users', label: '管理员管理', icon: <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zm14 10v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />, superOnly: true },
]

// 菜单 Icon 包装：16px 线性图标
function MenuIcon({ d }: { d: React.ReactElement }) {
  return (
    <svg className={styles.menuIcon} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
      {d}
    </svg>
  )
}

export default function AdminLayout() {
  const { user, isSuper, logout } = useAuth()

  // 未登录 → 重定向登录页（路由守卫）
  if (!user) return <Navigate to="/login" replace />

  const visibleMenus = MENUS.filter((m) => !m.superOnly || isSuper)
  const roleLabel = isSuper ? 'Super Admin' : 'Operator'

  return (
    <div className={styles.layout}>
      {/* ---------- 侧边栏 ---------- */}
      <aside className={styles.sidebar}>
        {/* Logo 区 */}
        <div className={styles.logo}>
          <img src="/logo.webp" alt="麦屿手作 LOGO" className={styles.logoMark} />
          <span className={styles.logoText}>
            <span className={styles.logoZh}>麦屿手作</span>
            <span className={styles.logoEn}>BACK OFFICE</span>
          </span>
        </div>

        {/* 菜单列表 */}
        <nav className={styles.nav} aria-label="后台导航">
          {visibleMenus.map((m) => (
            <NavLink
              key={m.key}
              to={m.path}
              className={({ isActive }) => (isActive ? `${styles.navItem} ${styles.navActive}` : styles.navItem)}
            >
              <MenuIcon d={m.icon} />
              <span>{m.label}</span>
            </NavLink>
          ))}
        </nav>

        {/* 底部用户信息 + 退出 */}
        <div className={styles.footer}>
          <div className={styles.userRow}>
            <span className={styles.avatar}>{user.name.charAt(0)}</span>
            <span className={styles.userInfo}>
              <span className={styles.userName}>{user.name}</span>
              <span className={styles.userRole}>{roleLabel}</span>
            </span>
          </div>
          <button type="button" className={styles.logoutBtn} onClick={logout}>
            退出登录
          </button>
        </div>
      </aside>

      {/* ---------- 主区 ---------- */}
      <main className={styles.main}>
        <Outlet />
      </main>
    </div>
  )
}
