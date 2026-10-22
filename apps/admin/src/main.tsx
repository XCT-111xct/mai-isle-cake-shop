// ============================================================
// 文件功能：后台管理系统的程序入口
// 作用：
//   1. 挂载 React 应用到 root 节点
//   2. 引入全局样式（前后台共用同一套 Design Token）
//   3. AuthProvider 包裹全局（登录态持久化）
// ============================================================

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import { AuthProvider } from '@/context/AuthContext'

// 引入全局样式（前后台共用 Token，保证品牌认知统一）
import './styles/tokens.css'
import './styles/global.css'

// 找到 HTML 挂载点
const rootElement = document.getElementById('root')!

// 渲染 React 应用（AuthProvider 提供登录态）
ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </React.StrictMode>
)
