// ============================================================
// 文件功能：前台官网的 Vite 构建配置
// 作用：
//   1. 告诉 Vite 用 React 插件编译 JSX/TSX
//   2. 设定开发服务器端口为 5173（对齐实施方案 §2 架构图）
//   3. 配置路径别名：@/ 指向 src/（与 tsconfig.json 的 paths 保持一致）
//   4. 配置代理：前端请求 /api 开头的接口时，自动转发到后端 8000 端口
//      （这样前端代码里写 /api/v1/... 就能直接访问后端，不用写完整的 http://localhost:8000）
//   5. 支持"演示模式"构建（--mode demo）：产出一份纯静态、可放任意子路径的站点，
//      数据由 src/api/demoAdapter.ts 本地提供，不需要后端
// ============================================================

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

// Vite 的配置可以写成函数，参数里带着当前"模式"（mode）
// 模式来源：命令行 --mode xxx（默认 development / production）
export default defineConfig(({ mode }) => {
  // 演示模式：npm run build:demo 时 mode 为 'demo'
  // 判断依据是 apps/web/.env.demo 里的 VITE_DEMO=1，Vite 会自动加载该文件
  const isDemo = mode === 'demo'

  return {
    // ---------- 部署基础路径 ----------
    // 正常构建用 '/'：站点部署在域名根目录（如 https://mai-isle.com/）
    // 演示构建用 './'：所有资源走相对路径，这样放在 GitHub Pages 的
    //   /仓库名/ 子路径下也能正常加载（用绝对路径会 404）
    base: isDemo ? './' : '/',

    // 插件列表：react 插件负责把 JSX 语法编译成浏览器能识别的 JavaScript
    plugins: [react()],

    // 路径解析配置：让 import 语句里的 @/ 能正确找到 src/ 下的文件
    resolve: {
      alias: {
        // '@' 别名 → 项目根目录下的 src 目录
        // 例：import api from '@/api' 等价于 import api from '/绝对路径/src/api'
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },

    // 开发服务器配置
    server: {
      // 端口固定为 5173，避免和后台（5174）、后端（8000）冲突
      port: 5173,
      // 代理配置：解决开发时的跨域问题（浏览器限制跨域，但服务器之间没有这个限制）
      proxy: {
        // 所有以 /api 开头的请求……
        '/api': {
          // ……都转发到本地后端的 8000 端口
          target: 'http://localhost:8000',
          // 保持原始路径不变（即 /api/v1/cakes 还是 /api/v1/cakes）
          changeOrigin: true
        },
        // 所有以 /uploads 开头的请求（图片访问）同样转发到后端静态目录
        '/uploads': {
          target: 'http://localhost:8000',
          changeOrigin: true
        }
      }
    },

    // ---------- 构建配置 ----------
    build: isDemo
      ? {
          // 演示产物输出到仓库的 docs/demo/，GitHub Pages 可直接托管该目录
          outDir: '../../docs/demo',
          // 每次构建先清空，避免旧文件残留导致"改了没生效"的错觉
          emptyOutDir: true
        }
      : {}
  }
})
