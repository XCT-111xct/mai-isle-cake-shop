// ============================================================
// 文件功能：前台官网路由表（技术开发文档 §6.3）
// 说明：
//   1. HashRouter：hash 路由（URL 形如 #/cakes），对齐原型
//   2. 所有页面包在 MainLayout 里（共享 Navbar + Footer）
// ============================================================

import { HashRouter, Routes, Route } from 'react-router-dom'
import MainLayout from '@/layouts/MainLayout'
import HomePage from '@/pages/HomePage'
import AboutPage from '@/pages/AboutPage'
import CakeListPage from '@/pages/CakeListPage'
import CakeDetailPage from '@/pages/CakeDetailPage'
import StorePage from '@/pages/StorePage'
import ContactPage from '@/pages/ContactPage'
import NotFoundPage from '@/pages/NotFoundPage'

export default function App() {
  return (
    <HashRouter>
      <Routes>
        {/* MainLayout 包裹全部前台页面（共享导航与页脚） */}
        <Route element={<MainLayout />}>
          {/* 首页 */}
          <Route path="/" element={<HomePage />} />
          {/* 关于麦屿（支持 #anchor-story/value/chars 锚点） */}
          <Route path="/about" element={<AboutPage />} />
          {/* 蛋糕展示（query: category_id/page/sort） */}
          <Route path="/cakes" element={<CakeListPage />} />
          {/* 蛋糕详情 */}
          <Route path="/cakes/:id" element={<CakeDetailPage />} />
          {/* 门店信息 */}
          <Route path="/stores" element={<StorePage />} />
          {/* 联系我们 + 留言表单 */}
          <Route path="/contact" element={<ContactPage />} />
          {/* 兜底：404 */}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}
