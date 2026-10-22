// ============================================================
// 文件功能：联系我们页（UI-UX §5.6，PRD F6）
// ⚠️ BUG-001 强约束落点（实施方案 §7.1）：
//   1. 错误提示由 state 派生、每次校验【整体覆盖】（禁止 DOM 追加/merge 旧值）
//   2. onChange 即时清除该字段错误（输入即消失）
//   3. 验证码错误（API 40002）自动刷新图形验证码
//   4. 成功：清空表单 + 提示条（4s 自动消失）+ 刷新验证码
//   5. 网络异常："提交失败，请重试"
// ============================================================

import { useCallback, useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { ContactInfo, OrderInfo } from '@/api/types'
import { PageBanner } from '@/components/Common'
import styles from './ContactPage.module.css'

// 字段错误结构（BUG-001：由 state 派生）
interface FormErrors {
  name?: string
  phone?: string
  content?: string
  captcha?: string
}

export default function ContactPage() {
  // ---------- 表单字段 ----------
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [content, setContent] = useState('')
  const [captcha, setCaptcha] = useState('')
  const [captchaId, setCaptchaId] = useState('')   // 来自响应头 X-Captcha-Id
  const [captchaUrl, setCaptchaUrl] = useState('') // blob 图片地址

  // ---------- 错误 state（BUG-001：单一数据源） ----------
  const [errors, setErrors] = useState<FormErrors>({})

  // ---------- 提交状态 / 提示条 ----------
  const [submitting, setSubmitting] = useState(false)
  const [toast, setToast] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  // 联系方式数据
  const [orderInfo, setOrderInfo] = useState<OrderInfo | null>(null)
  const [contactInfo, setContactInfo] = useState<ContactInfo | null>(null)

  // ---------- 获取图形验证码（blob 图片 + X-Captcha-Id 响应头） ----------
  const refreshCaptcha = useCallback(() => {
    client
      .get('/captcha', { responseType: 'blob' })
      .then((res) => {
        const id = res.headers['x-captcha-id']
        if (id) setCaptchaId(String(id))
        // blob 转可显示地址（注意：使用后需 revokeObjectURL 释放）
        setCaptchaUrl((old) => {
          if (old) URL.revokeObjectURL(old)
          return URL.createObjectURL(res.data)
        })
        setCaptcha('') // 刷新验证码时清空输入
        setErrors((e) => ({ ...e, captcha: undefined }))
      })
      .catch(() => {
        /* 验证码加载失败：静默，用户可刷新重试 */
      })
  }, [])

  // 页面加载：拉取验证码 + 联系方式
  useEffect(() => {
    refreshCaptcha()
    Promise.all([
      client.get('/content/order_info').then((r) => (r.data.data as { value: OrderInfo }).value ?? null).catch(() => null),
      client.get('/content/contact_info').then((r) => (r.data.data as { value: ContactInfo }).value ?? null).catch(() => null),
    ]).then(([o, c]) => { setOrderInfo(o); setContactInfo(c) })
    // 卸载时释放 blob 地址
    return () => { if (captchaUrl) URL.revokeObjectURL(captchaUrl) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // ---------- 校验：每次整体覆盖 errors（BUG-001 核心） ----------
  function validate(): boolean {
    const next: FormErrors = {}
    if (name.trim().length < 2 || name.trim().length > 20) next.name = '姓名需为 2-20 个字符'
    if (!/^1[3-9]\d{9}$/.test(phone.trim())) next.phone = '请输入 11 位有效手机号'
    if (!content.trim() || content.trim().length > 500) next.content = '留言内容不能为空，且不超过 500 字'
    if (captcha.trim().length !== 4) next.captcha = '验证码错误，请重新输入'
    setErrors(next) // 整体覆盖（新对象），不是 merge —— 杜绝堆叠
    return Object.keys(next).length === 0
  }

  // ---------- 字段修改：即时清除该字段错误（BUG-001） ----------
  function onFieldChange(field: keyof FormErrors, value: string) {
    if (field === 'name') setName(value)
    else if (field === 'phone') setPhone(value)
    else if (field === 'content') setContent(value)
    else if (field === 'captcha') setCaptcha(value)
    // 有错误才清（避免无谓 setState）
    if (errors[field]) setErrors((prev) => ({ ...prev, [field]: undefined }))
  }

  // ---------- 提交 ----------
  async function onSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    setSubmitting(true)
    try {
      await client.post('/messages', {
        name: name.trim(),
        phone: phone.trim(),
        content: content.trim(),
        captcha: captcha.trim(),
        captcha_id: captchaId,
      })
      // 成功：清空表单 + 成功提示 + 刷新验证码（BUG-001 验收）
      setName(''); setPhone(''); setContent(''); setCaptcha('')
      refreshCaptcha()
      showToast('success', '提交成功，我们会尽快与您联系')
    } catch (err) {
      const msg = (err as Error).message
      if (msg.includes('验证码')) {
        // 验证码错误/过期：刷新验证码 + 字段级提示（BUG-001）
        refreshCaptcha()
        setErrors((prev) => ({ ...prev, captcha: msg }))
      } else {
        showToast('error', '提交失败，请重试')
      }
    } finally {
      setSubmitting(false)
    }
  }

  // 提示条：4s 自动消失
  function showToast(type: 'success' | 'error', text: string) {
    setToast({ type, text })
    setTimeout(() => setToast(null), 4000)
  }

  return (
    <div>
      <PageBanner
        title="联系我们"
        en="CONTACT US · 联系我们"
        eyebrow="麦屿联系 · CONTACT"
        imageUrl="https://images.unsplash.com/photo-1559925393-8be0ec4767c8?w=1600&q=80"
      />

      <div className={styles.wrap}>
        {/* 两栏：左联系方式 + 右留言表单 */}
        <div className={styles.contactWrap}>
          {/* ---------- 左：联系方式卡 ---------- */}
          <div className={styles.infoCard}>
            <p className={styles.eyebrow}>CONTACT · 联系我们</p>
            <h2 className={styles.infoTitle}>始终在这里</h2>
            <p className={styles.infoEn}>Always Here</p>

            <ul className={styles.infoList}>
              {orderInfo?.hotline && (
                <li>
                  <span className={styles.infoIcon} aria-hidden="true">📞</span>
                  <div>
                    <p className={styles.infoLabel}>订购专线</p>
                    <p className={styles.infoValue}>{orderInfo.hotline}</p>
                    <p className={styles.infoSub}>多门店统一订购</p>
                  </div>
                </li>
              )}
              {orderInfo?.hours && (
                <li>
                  <span className={styles.infoIcon} aria-hidden="true">🕒</span>
                  <div>
                    <p className={styles.infoLabel}>服务时间</p>
                    <p className={styles.infoValue}>{orderInfo.hours}</p>
                    <p className={styles.infoSub}>全年无休</p>
                  </div>
                </li>
              )}
              {contactInfo?.address && (
                <li>
                  <span className={styles.infoIcon} aria-hidden="true">📍</span>
                  <div>
                    <p className={styles.infoLabel}>总部地址</p>
                    <p className={styles.infoValue}>{contactInfo.address}</p>
                  </div>
                </li>
              )}
              {contactInfo?.email && (
                <li>
                  <span className={styles.infoIcon} aria-hidden="true">✉️</span>
                  <div>
                    <p className={styles.infoLabel}>邮箱</p>
                    <p className={styles.infoValue}>{contactInfo.email}</p>
                  </div>
                </li>
              )}
            </ul>
          </div>

          {/* ---------- 右：留言表单卡 ---------- */}
          <div className={styles.formCard}>
            <h2 className={styles.formTitle}>给我们留言</h2>

            <form onSubmit={onSubmit} noValidate>
              {/* 姓名 + 电话（双列） */}
              <div className={styles.formRow2}>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="msg-name">
                    姓名 <span className={styles.required}>*</span>
                  </label>
                  <input
                    id="msg-name"
                    className={`${styles.input} ${errors.name ? styles.inputError : ''}`}
                    type="text"
                    value={name}
                    placeholder="请输入姓名"
                    maxLength={20}
                    onChange={(e) => onFieldChange('name', e.target.value)}
                    aria-invalid={!!errors.name}
                    aria-describedby={errors.name ? 'msg-name-err' : undefined}
                  />
                  {errors.name && <p id="msg-name-err" className={styles.fieldError}>{errors.name}</p>}
                </div>
                <div className={styles.field}>
                  <label className={styles.label} htmlFor="msg-phone">
                    联系电话 <span className={styles.required}>*</span>
                  </label>
                  <input
                    id="msg-phone"
                    className={`${styles.input} ${errors.phone ? styles.inputError : ''}`}
                    type="tel"
                    value={phone}
                    placeholder="请输入 11 位手机号"
                    maxLength={11}
                    onChange={(e) => onFieldChange('phone', e.target.value)}
                    aria-invalid={!!errors.phone}
                    aria-describedby={errors.phone ? 'msg-phone-err' : undefined}
                  />
                  {errors.phone && <p id="msg-phone-err" className={styles.fieldError}>{errors.phone}</p>}
                </div>
              </div>

              {/* 留言内容 */}
              <div className={styles.field}>
                <label className={styles.label} htmlFor="msg-content">
                  留言内容 <span className={styles.required}>*</span>
                </label>
                <textarea
                  id="msg-content"
                  className={`${styles.textarea} ${errors.content ? styles.inputError : ''}`}
                  rows={5}
                  value={content}
                  placeholder="想咨询什么？告诉我们吧"
                  maxLength={500}
                  onChange={(e) => onFieldChange('content', e.target.value)}
                  aria-invalid={!!errors.content}
                  aria-describedby={errors.content ? 'msg-content-err' : undefined}
                />
                {errors.content && <p id="msg-content-err" className={styles.fieldError}>{errors.content}</p>}
              </div>

              {/* 验证码 */}
              <div className={styles.field}>
                <label className={styles.label} htmlFor="msg-captcha">
                  验证码 <span className={styles.required}>*</span>
                </label>
                <div className={styles.captchaRow}>
                  <input
                    id="msg-captcha"
                    className={`${styles.input} ${styles.captchaInput} ${errors.captcha ? styles.inputError : ''}`}
                    type="text"
                    value={captcha}
                    placeholder="请输入验证码"
                    maxLength={4}
                    onChange={(e) => onFieldChange('captcha', e.target.value)}
                    aria-invalid={!!errors.captcha}
                    aria-describedby={errors.captcha ? 'msg-captcha-err' : undefined}
                  />
                  {/* 图形验证码框（点击刷新） */}
                  {captchaUrl ? (
                    <button
                      type="button"
                      className={styles.captchaImg}
                      onClick={refreshCaptcha}
                      aria-label="刷新验证码"
                      title="看不清？点击刷新"
                    >
                      <img src={captchaUrl} alt="图形验证码" />
                    </button>
                  ) : (
                    <span className={styles.captchaImg}>加载中…</span>
                  )}
                </div>
                {errors.captcha && <p id="msg-captcha-err" className={styles.fieldError}>{errors.captcha}</p>}
              </div>

              {/* 提交按钮 */}
              <button
                type="submit"
                className={styles.submitBtn}
                disabled={submitting}
              >
                {submitting ? '提交中…' : '提交留言'}
              </button>
              <p className={styles.formHint}>提交留言后我们将在 24 小时内回复</p>
            </form>
          </div>
        </div>
      </div>

      {/* 成功/错误提示条（4s 自动消失） */}
      {toast && (
        <div
          className={`${styles.toast} ${toast.type === 'success' ? styles.toastSuccess : styles.toastError}`}
          role="status"
          aria-live="polite"
        >
          {toast.text}
        </div>
      )}
    </div>
  )
}
