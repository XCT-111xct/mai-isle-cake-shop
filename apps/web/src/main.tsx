// ============================================================
// 文件功能：前台官网的程序入口
// 作用：
//   1. 找到 HTML 里的挂载点（id 为 root 的 div）
//   2. 用 React 的 createRoot 启动 React 应用
//   3. 引入全局样式（Design Token 变量 + 全局基础样式）
//   注意：路由容器（HashRouter）统一放在 App.tsx 里管理，这里不重复包裹
// ============================================================

import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'

// 引入全局样式文件（注意：样式文件没有导出任何东西，import 只是为了"加载"它）
import './styles/tokens.css'
import './styles/global.css'

// 找到 HTML 中 id 为 root 的元素（在 index.html 里定义的挂载点）
const rootElement = document.getElementById('root')!

// 创建 React 根实例，并把整个应用渲染进去
//
// 【历史说明】这里原本还传了第二个参数 `{ onUncaughtError, onCaughtError }`，
// 目的是把 React 渲染错误抛到 window 上方便开发期调试。已移除，原因有二：
//   ① 这两个选项是 React 19 的 API，本项目用的是 React 18，
//      传给 createRoot 会在 `tsc` 类型检查阶段直接报错 TS2353，导致 npm run build 失败；
//   ② 把内部错误堆栈挂到 window 上是调试脚手架，生产环境留着既无用也有信息泄露风险。
ReactDOM.createRoot(rootElement).render(
  // React.StrictMode：开发模式下的严格检查（帮你提前发现潜在问题，生产环境无影响）
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
