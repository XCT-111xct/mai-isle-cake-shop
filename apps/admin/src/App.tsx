// ============================================================
// 文件功能：后台路由表（技术开发文档 §6.3）
// 说明：
//   1. HashRouter（与前台一致，部署简单）
//   2. 所有业务页面包在 AdminLayout 里（侧边栏 + 路由守卫）
//   3. /users 仅超管（RequireSuper 前端兜底，后端 40300 最终防线）
// ============================================================

import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import AdminLayout from '@/layouts/AdminLayout'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import ProductPage from '@/pages/ProductPage'
import OrderPage from '@/pages/OrderPage'
import StoreManagePage from '@/pages/StoreManagePage'
import ContentPage from '@/pages/ContentPage'
import MessagePage from '@/pages/MessagePage'
import UserManagePage from '@/pages/UserManagePage'

// 超管路由守卫：ops 访问 /users → 重定向仪表盘（前端兜底）
function RequireSuper({ children }: { children: React.ReactElement }) {
  const { isSuper } = useAuth()
  return isSuper ? children : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <HashRouter>
      <Routes>
        {/* 登录页（公开，无需登录） */}
        <Route path="/login" element={<LoginPage />} />

        {/* 业务页面（AdminLayout 内含未登录守卫） */}
        <Route element={<AdminLayout />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/products" element={<ProductPage />} />
          <Route path="/orders" element={<OrderPage />} />
          <Route path="/stores" element={<StoreManagePage />} />
          <Route path="/content" element={<ContentPage />} />
          <Route path="/messages" element={<MessagePage />} />
          <Route path="/users" element={<RequireSuper><UserManagePage /></RequireSuper>} />
        </Route>

        {/* 兜底：未匹配重定向仪表盘（仪表盘内部会再判断登录态） */}
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </HashRouter>
  )
}
