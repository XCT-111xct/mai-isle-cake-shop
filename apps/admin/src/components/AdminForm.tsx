// ============================================================
// 文件功能：后台表单组件（UI-UX §4.4 表单 / §4.7 上传 / §4.12 搜索下拉）
//   Button / FormField / SearchInput / Select / Upload
// ============================================================

import { useRef, useState } from 'react'
import { client } from '@/api/client'
import styles from './AdminForm.module.css'

// ---------- 按钮（主/幽灵/危险/小） ----------
export function Button({ variant = 'primary', size = 'md', children, ...rest }: {
  variant?: 'primary' | 'ghost' | 'danger' | 'text'
  size?: 'md' | 'sm'
  children: React.ReactNode
} & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`${styles.btn} ${styles[`btn${variant[0].toUpperCase()}${variant.slice(1)}`]} ${size === 'sm' ? styles.btnSm : ''}`}
      {...rest}
    >
      {children}
    </button>
  )
}

// ---------- 表单字段（label + 必填星 + 错误提示） ----------
export function FormField({ label, required, error, children, help }: {
  label: string
  required?: boolean
  error?: string
  help?: string
  children: React.ReactNode
}) {
  return (
    <div className={styles.field}>
      <label className={styles.label}>
        {label} {required && <span className={styles.required}>*</span>}
      </label>
      {children}
      {error && <p className={styles.fieldError}>{error}</p>}
      {help && !error && <p className={styles.fieldHelp}>{help}</p>}
    </div>
  )
}

// ---------- 搜索框 ----------
export function SearchInput({ value, onChange, placeholder, onSearch }: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  onSearch?: (v: string) => void
}) {
  return (
    <div className={styles.searchBox}>
      <span className={styles.searchIcon} aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
      </span>
      <input
        className={styles.searchInput}
        type="search"
        value={value}
        placeholder={placeholder ?? '搜索…'}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') onSearch?.(value) }}
        aria-label="搜索"
      />
    </div>
  )
}

// ---------- 下拉选择 ----------
export function Select({ value, onChange, options, placeholder, ariaLabel }: {
  value: string | number | undefined
  onChange: (v: string) => void
  options: { value: string | number; label: string }[]
  placeholder?: string
  ariaLabel?: string
}) {
  return (
    <select
      className={styles.select}
      value={value === undefined || value === '' ? '' : String(value)}
      onChange={(e) => onChange(e.target.value)}
      aria-label={ariaLabel}
    >
      {placeholder && <option value="">{placeholder}</option>}
      {options.map((o) => (
        <option key={o.value} value={String(o.value)}>{o.label}</option>
      ))}
    </select>
  )
}

// ---------- 图片上传（虚线框、≤5MB、jpg/png/webp、回填 URL） ----------
export function Upload({ value, onChange, onUploading, dir = 'cakes' }: {
  value: string
  onChange: (url: string) => void
  onUploading?: (b: boolean) => void
  dir?: 'cakes' | 'banners' | 'stores' | 'brand'
}) {
  const inputRef = useRef<HTMLInputElement>(null)

  async function handleFile(file: File | undefined) {
    if (!file) return
    // 前端预校验（后端也会校验，双保险）
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
      alert('图片格式仅支持 jpg/png/webp')
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      alert('图片大小不能超过 5MB')
      return
    }
    const form = new FormData()
    form.append('file', file)
    form.append('dir', dir)
    onUploading?.(true)
    try {
      const res = await client.post('/upload', form)
      onChange(res.data.data.url as string)
    } catch {
      alert('上传失败，请重试')
    } finally {
      onUploading?.(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <div className={styles.upload}>
      {value ? (
        <div className={styles.uploadPreview}>
          <img src={value} alt="上传预览" />
          <div className={styles.uploadActions}>
            <button type="button" className={styles.uploadBtn} onClick={() => inputRef.current?.click()}>更换</button>
            <button type="button" className={styles.uploadRemove} onClick={() => onChange('')}>移除</button>
          </div>
        </div>
      ) : (
        <button type="button" className={styles.uploadDrop} onClick={() => inputRef.current?.click()}>
          <span className={styles.uploadPlus} aria-hidden="true">＋</span>
          <span>点击上传图片</span>
          <span className={styles.uploadHint}>jpg/png/webp · ≤5MB · 建议 800×600</span>
        </button>
      )}
      <input
        ref={inputRef}
        type="file"
        accept="image/jpeg,image/png,image/webp"
        style={{ display: 'none' }}
        onChange={(e) => handleFile(e.target.files?.[0])}
      />
    </div>
  )
}
