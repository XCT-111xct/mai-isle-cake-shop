// ============================================================
// 文件功能：前台 API 请求封装（技术开发文档 §6.4.1）
// 说明：
//   1. baseURL 指向 /api/v1，开发时经 Vite 代理转发到后端 8000
//   2. 响应拦截器：后端统一 {code, message, data}，非 0 code 一律
//      转为 Error（message 即后端中文提示），页面 catch 即可展示
// ============================================================

import axios from 'axios'
import type { ApiResponse } from './types'
import { IS_DEMO, demoAdapter } from './demoAdapter'
import { getPreviewToken } from '@/utils/tracker'

// 创建 axios 实例：所有前台请求统一走这里
export const client = axios.create({
  baseURL: '/api/v1', // 开发环境经 Vite 代理 → http://localhost:8000/api/v1
  timeout: 10000,     // 10 秒超时，避免请求挂死
})

// ---------- 演示模式开关 ----------
// 构建时设 VITE_DEMO=1 即启用：所有请求改由本地数据应答，不访问后端。
// 用途是部署成"纯静态可浏览版"（GitHub Pages 等），让人不必装环境就能看效果。
// 正常开发与生产构建时 IS_DEMO 为 false，这一行不会执行，行为与原来完全一致。
if (IS_DEMO) {
  client.defaults.adapter = demoAdapter
}

// ---------- 请求拦截器：预览令牌 ----------
// 处于预览模式时，给内容接口自动附上 preview_token。
// 后端校验通过则返回「草稿内容」，校验失败会降级返回线上内容并标记
// preview_invalid，页面据此横条提示——不会让人误以为看到的就是草稿。
// 为什么只在 /content 上加：其它接口（蛋糕、门店…）不参与版本化发布，
// 多带一个参数只会污染日志。
client.interceptors.request.use((config) => {
  const token = getPreviewToken()
  const isContentGet =
    (config.method || '').toLowerCase() === 'get' &&
    typeof config.url === 'string' &&
    config.url.startsWith('/content')
  if (token && isContentGet) {
    config.params = { ...(config.params || {}), preview_token: token }
  }
  return config
})

// ---------- 响应拦截器 ----------
// 作用：把"业务失败"统一转成 Error 对象，页面代码只需 try/catch
client.interceptors.response.use(
  // 2xx 响应：直接返回（页面自己取 res.data.data）
  (res) => res,
  // 非 2xx / 网络错误：提取后端 message 作为错误信息
  (error) => {
    // 网络异常（后端没响应 / 超时）
    if (!error.response) {
      return Promise.reject(new Error('网络异常，请稍后重试'))
    }
    // 后端返回了错误：取 message 字段（如"验证码错误，请重新输入"）
    const data = error.response.data as ApiResponse<unknown> | undefined
    return Promise.reject(new Error(data?.message || '操作失败，请稍后重试'))
  }
)
