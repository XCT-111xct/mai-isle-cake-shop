// ============================================================
// 文件功能：前台全局布局（Navbar + 页面内容 + Footer）
// 说明：React Router 的 Outlet 是"子路由内容插槽"，
//       各页面渲染在 Navbar 与 Footer 之间
// ============================================================

import { Outlet, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import Navbar from '@/components/Navbar'
import Footer from '@/components/Footer'

export default function MainLayout() {
  const location = useLocation()

  // 路由切换时回到页面顶部（#/about#anchor 锚点场景由 AboutPage 自行处理）
  useEffect(() => {
    const { hash } = location
    // 只有 hash 是页面锚点（anchor-）时不滚动到顶，交给 AboutPage 平滑滚动
    if (!hash || !hash.startsWith('#anchor')) {
      window.scrollTo({ top: 0 })
    }
  }, [location.pathname, location.hash])

  return (
    <>
      <Navbar />
      <main>
        {/* Outlet：当前路由对应的页面组件 */}
        <Outlet />
      </main>
      <Footer />
    </>
  )
}
