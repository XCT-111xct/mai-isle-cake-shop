// ============================================================
// 文件功能：后台管理系统的 Vite 构建配置
// 作用：
//   1. React 插件编译 JSX/TSX
//   2. 端口 5174（与前台 5173、后端 8000 区分）
//   3. 路径别名 @/ → src/（与 tsconfig.json 的 paths 保持一致）
//   4. 代理 /api 与 /uploads → 后端 8000（解决跨域）
// ============================================================

import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath, URL } from 'node:url'

export default defineConfig({
  plugins: [react()],

  // 路径别名：@/ 指向 src/，让 import 更简洁统一
  resolve: {
    alias: {
      // '@' → 项目根目录下的 src 目录
      '@': fileURLToPath(new URL('./src', import.meta.url))
    }
  },

  server: {
    // 后台端口固定 5174
    port: 5174,
    proxy: {
      // 所有 /api 请求转发到后端 8000 端口
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      // 图片访问同样转发
      '/uploads': {
        target: 'http://localhost:8000',
        changeOrigin: true
      }
    }
  }
})
