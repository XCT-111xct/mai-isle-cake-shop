// ============================================================
// 文件功能：登录态 Context（技术开发文档 §6.7.1）
// 说明：
//   1. 登录成功 → 存 localStorage（mai_isle_token / mai_isle_user）
//   2. 刷新页面从 localStorage 恢复登录态（刷新不丢）
//   3. logout 清空并跳登录页
// ============================================================

import { createContext, useContext, useEffect, useState } from 'react'
import { TOKEN_KEY, USER_KEY } from '@/api/client'
import type { AdminUser } from '@/api/types'

interface AuthContextValue {
  user: AdminUser | null
  token: string | null
  isSuper: boolean
  login: (token: string, user: AdminUser) => void
  logout: () => void
}

// 创建 Context（默认值为 null，未登录）
const AuthContext = createContext<AuthContextValue>({
  user: null,
  token: null,
  isSuper: false,
  login: () => {},
  logout: () => {},
})

/** 从 localStorage 恢复登录态（刷新不丢的关键） */
function restoreFromStorage(): { user: AdminUser | null; token: string | null } {
  try {
    const token = localStorage.getItem(TOKEN_KEY)
    const userRaw = localStorage.getItem(USER_KEY)
    if (token && userRaw) {
      return { token, user: JSON.parse(userRaw) as AdminUser }
    }
  } catch {
    /* 数据损坏则视为未登录 */
  }
  return { user: null, token: null }
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  // 初始值：从 localStorage 恢复
  const [state, setState] = useState(() => restoreFromStorage())

  // 登录成功：写 localStorage + 更新内存状态
  function login(token: string, user: AdminUser) {
    localStorage.setItem(TOKEN_KEY, token)
    localStorage.setItem(USER_KEY, JSON.stringify(user))
    setState({ token, user })
  }

  // 退出：清空 localStorage + 内存状态
  function logout() {
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(USER_KEY)
    setState({ user: null, token: null })
  }

  return (
    <AuthContext.Provider
      value={{
        user: state.user,
        token: state.token,
        isSuper: state.user?.role === 'super',
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

// 使用登录态的 Hook（在组件里 const { user, logout } = useAuth()）
export function useAuth() {
  return useContext(AuthContext)
}
