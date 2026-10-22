// ============================================================
// 文件功能：后台登录页（UI-UX §6.1，PRD F8）
// 说明：
//   1. 账号 + 密码 + 图形验证码
//   2. 验证码错误（40002）→ 自动刷新验证码（实施方案验收要点）
//   3. 错误提示条：账号或密码错误 / 账号已停用 / 账号已锁定
//   4. 成功 → 跳转 /dashboard
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import axios from 'axios'
import { useNavigate } from 'react-router-dom'
import { client } from '@/api/client'
import { useAuth } from '@/context/AuthContext'
import type { LoginResult } from '@/api/types'
import styles from './LoginPage.module.css'

export default function LoginPage() {
  const navigate = useNavigate()
  const { login, user } = useAuth()

  // 已登录 → 直接进仪表盘
  useEffect(() => {
    if (user) navigate('/dashboard', { replace: true })
  }, [user, navigate])

  // ---------- 表单字段 ----------
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [captcha, setCaptcha] = useState('')
  const [captchaId, setCaptchaId] = useState('')
  const [captchaUrl, setCaptchaUrl] = useState('')

  // ---------- 状态 ----------
  const [error, setError] = useState('')      // 顶部错误提示条
  const [captchaErrorCount, setCaptchaErrorCount] = useState(0) // 验证码连续错误计数
  const [submitting, setSubmitting] = useState(false)

  // ---------- 获取图形验证码（blob + X-Captcha-Id 头） ----------
  // 注意：captcha 是前台接口 /api/v1/captcha（不属于 admin 前缀）
  const refreshCaptcha = useCallback(() => {
    axios
      .get('/api/v1/captcha', { responseType: 'blob' })
      .then((res) => {
        const id = res.headers['x-captcha-id']
        if (id) setCaptchaId(String(id))
        setCaptchaUrl((old) => {
          if (old) URL.revokeObjectURL(old)
          return URL.createObjectURL(res.data)
        })
        setCaptcha('')
      })
      .catch(() => { /* 静默，用户可点击刷新重试 */ })
  }, [])

  useEffect(() => {
    refreshCaptcha()
    return () => { if (captchaUrl) URL.revokeObjectURL(captchaUrl) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---------- 提交登录 ----------
  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    if (!username.trim() || !password || !captcha.trim()) {
      setError('请填写完整的账号、密码和验证码')
      return
    }
    setSubmitting(true)
    try {
      const res = await client.post('/login', {
        username: username.trim(),
        password,
        captcha: captcha.trim(),
        captcha_id: captchaId,
      })
      const data = res.data.data as LoginResult
      login(data.access_token, data.user)
      navigate('/dashboard', { replace: true })
    } catch (err) {
      const msg = (err as Error).message
      // 验证码错误 → 自动刷新验证码（验收要点）
      if (msg.includes('验证码')) {
        const next = captchaErrorCount + 1
        setCaptchaErrorCount(next)
        refreshCaptcha()
        // 第 4 次起在提示中说明已自动刷新
        setError(next >= 4 ? '验证码错误次数过多，验证码已自动刷新，请重新输入' : msg)
      } else {
        // 账号或密码错误 / 账号已停用 / 账号已锁定
        setError(msg)
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className={styles.loginWrap}>
      {/* ========== 左：品牌区（深棕渐变） ========== */}
      <div className={styles.brand}>
        {/* 奶油色径向光斑装饰圆 */}
        <div className={styles.orb1} aria-hidden="true" />
        <div className={styles.orb2} aria-hidden="true" />

        <div className={styles.brandInner}>
          <div className={styles.brandLogo}>
            <span className={styles.brandMark}>M</span>
            <span className={styles.brandName}>麦屿手作 <em>MAI·ISLE</em></span>
          </div>
          <h1 className={styles.brandTitle}>
            欢迎回到<br />麦屿<em>后台</em>
          </h1>
          <blockquote className={styles.brandQuote}>
            "手作每一份甜蜜，用数据守护品质。"
            <cite>—— 麦屿手作运营团队</cite>
          </blockquote>
        </div>
        <p className={styles.brandCopyright}>© 2026 MAI·ISLE · Back Office</p>
      </div>

      {/* ========== 右：表单区 ========== */}
      <div className={styles.formSide}>
        <div className={styles.formCard}>
          {/* eyebrow + 查看前台链接 */}
          <div className={styles.formTop}>
            <p className={styles.formEyebrow}>Sign In · 管理员登录</p>
            <a href="http://localhost:5173" target="_blank" rel="noreferrer" className={styles.backHome}>查看前台 →</a>
          </div>

          <h2 className={styles.formTitle}>您好，请登录</h2>

          {/* 错误提示条 */}
          {error && (
            <div className={styles.errorBar} role="alert">
              {error}
            </div>
          )}

          <form onSubmit={onSubmit} noValidate>
            {/* 账号 */}
            <div className={styles.field}>
              <label className={styles.label} htmlFor="login-username">账号</label>
              <input
                id="login-username"
                className={styles.input}
                type="text"
                value={username}
                placeholder="请输入管理员账号"
                autoComplete="username"
                onChange={(e) => setUsername(e.target.value)}
              />
            </div>

            {/* 密码 */}
            <div className={styles.field}>
              <label className={styles.label} htmlFor="login-password">密码</label>
              <input
                id="login-password"
                className={styles.input}
                type="password"
                value={password}
                placeholder="请输入密码（6-20 位）"
                autoComplete="current-password"
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            {/* 验证码 */}
            <div className={styles.field}>
              <label className={styles.label} htmlFor="login-captcha">验证码</label>
              <div className={styles.captchaRow}>
                <input
                  id="login-captcha"
                  className={styles.input}
                  type="text"
                  value={captcha}
                  placeholder="请输入图形验证码"
                  maxLength={4}
                  onChange={(e) => setCaptcha(e.target.value)}
                />
                {captchaUrl ? (
                  <button type="button" className={styles.captchaImg} onClick={refreshCaptcha} title="看不清？点击刷新" aria-label="刷新验证码">
                    <img src={captchaUrl} alt="图形验证码" />
                  </button>
                ) : (
                  <span className={styles.captchaImg}>加载中…</span>
                )}
              </div>
            </div>

            {/* 登录按钮 */}
            <button type="submit" className={styles.loginBtn} disabled={submitting}>
              {submitting ? '登录中…' : '登 录'}
            </button>
          </form>

          <p className={styles.formHint}>连续 5 次密码错误将锁定 15 分钟</p>
        </div>
      </div>
    </div>
  )
}
