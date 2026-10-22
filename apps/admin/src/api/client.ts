// ============================================================
// 文件功能：后台 API 请求封装（技术开发文档 §6.4.2）
// 说明：
//   1. baseURL 指向 /api/v1/admin（经 Vite 代理转发到后端 8000）
//   2. 请求拦截器：自动附加 Authorization: Bearer <token>
//   3. 响应拦截器：业务失败转 Error；40100 清登录态跳登录页
// ============================================================

import axios from 'axios'
import type { ApiResponse } from './types'

export const TOKEN_KEY = 'mai_isle_token'
export const USER_KEY = 'mai_isle_user'

// 创建 axios 实例：所有后台请求统一走这里
export const client = axios.create({
  baseURL: '/api/v1/admin', // 开发环境经 Vite 代理 → http://localhost:8000/api/v1/admin
  timeout: 10000,
})

// ---------- 请求拦截器：自动带 token ----------
client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// ---------- 响应拦截器：业务错误转 Error + 401 处理 ----------
client.interceptors.response.use(
  (res) => res,
  (error) => {
    const data = error.response?.data as ApiResponse<unknown> | undefined

    // Token 过期 / 无效（40100）→ 清空登录态并跳登录页
    if (data?.code === 40100) {
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
      // 不在登录页才跳转（避免循环）
      if (!window.location.hash.includes('/login')) {
        window.location.hash = '#/login'
      }
    }

    // 网络异常（后端没响应 / 超时）
    if (!error.response) {
      return Promise.reject(new Error('网络异常，请稍后重试'))
    }

    // 业务错误：取后端 message（如"账号或密码错误""产品名称已存在，请更换"）
    return Promise.reject(new Error(data?.message || '操作失败，请稍后重试'))
  }
)
