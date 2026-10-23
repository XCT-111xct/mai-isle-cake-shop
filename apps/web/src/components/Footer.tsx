// ============================================================
// 文件功能：页脚（UI-UX §5.0）
// 说明：
//   1. 底 --brown-deep，顶部 3px 渐变线
//   2. 四栏网格：品牌区 / NAVIGATION / CONTACT / JOIN US
//   3. CONTACT 数据来自后台 content（order_info + contact_info），
//      空内容时隐藏对应区块（PRD F7-1）
// ============================================================

import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '@/api/client'
import type { ContactInfo, OrderInfo } from '@/api/types'
import { useHotline } from '@/hooks/useHotline'
import { trackHotlineClick } from '@/utils/tracker'
import styles from './Footer.module.css'

// 固定导航链接（不可后台配置）
const NAV_LINKS = [
  { to: '/', label: '首页' },
  { to: '/about', label: '关于麦屿' },
  { to: '/cakes', label: '蛋糕展示' },
  { to: '/stores', label: '门店信息' },
  { to: '/contact', label: '联系我们' },
]

const JOIN_LINKS = ['企业订购', '媒体合作', '门店加盟', '供应商联系']

export default function Footer() {
  const [orderInfo, setOrderInfo] = useState<OrderInfo | null>(null)
  const [contactInfo, setContactInfo] = useState<ContactInfo | null>(null)
  // 渠道专属号优先，后台订购信息兜底
  const hotline = useHotline(orderInfo?.hotline)

  // 页脚加载：并发拉取订购信息 + 联系方式（空内容隐藏对应区块）
  useEffect(() => {
    Promise.all([
      client.get('/content/order_info').then((r) => (r.data.data as { value: OrderInfo }).value ?? null).catch(() => null),
      client.get('/content/contact_info').then((r) => (r.data.data as { value: ContactInfo }).value ?? null).catch(() => null),
    ]).then(([o, c]) => {
      setOrderInfo(o)
      setContactInfo(c)
    })
  }, [])

  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        {/* ---- 第 1 栏：品牌区 ---- */}
        <div className={styles.brand}>
          <div className={styles.brandLogo}>
            <span className={styles.brandMark}>M</span>
            <span className={styles.brandName}>
              <span>麦屿手作</span>
              <span className={styles.brandEn}>MAI·ISLE</span>
            </span>
          </div>
          <p className={styles.brandSlogan}>
            手作每一份甜蜜，让重要时刻更有仪式感。
          </p>
          {/* 社交图标（占位） */}
          <div className={styles.socials} aria-hidden="true">
            {['WX', 'WB', 'IG'].map((s) => (
              <span key={s} className={styles.social}>{s}</span>
            ))}
          </div>
        </div>

        {/* ---- 第 2 栏：NAVIGATION ---- */}
        <div className={styles.col}>
          <h4 className={styles.colTitle}>NAVIGATION</h4>
          <ul className={styles.colList}>
            {NAV_LINKS.map((l) => (
              <li key={l.to}><Link to={l.to}>{l.label}</Link></li>
            ))}
          </ul>
        </div>

        {/* ---- 第 3 栏：CONTACT（数据来自后台，空则整栏隐藏） ---- */}
        {(orderInfo || contactInfo) && (
          <div className={styles.col}>
            <h4 className={styles.colTitle}>CONTACT</h4>
            <ul className={styles.colList}>
              {hotline.phone && (
                <li>
                  <span className={styles.colLabel}>订购专线</span>
                  <a
                    href={`tel:${hotline.phone}`}
                    onClick={() => trackHotlineClick('footer', 'footer')}
                    style={{ color: 'inherit' }}
                  >
                    {hotline.phone}
                  </a>
                </li>
              )}
              {orderInfo?.hours && (
                <li><span className={styles.colLabel}>服务时间</span>{orderInfo.hours}</li>
              )}
              {contactInfo?.email && (
                <li><span className={styles.colLabel}>邮箱</span>{contactInfo.email}</li>
              )}
              {contactInfo?.address && (
                <li><span className={styles.colLabel}>地址</span>{contactInfo.address}</li>
              )}
            </ul>
          </div>
        )}

        {/* ---- 第 4 栏：JOIN US ---- */}
        <div className={styles.col}>
          <h4 className={styles.colTitle}>JOIN US</h4>
          <ul className={styles.colList}>
            {JOIN_LINKS.map((l) => (
              <li key={l}><a href="#/contact" onClick={(e) => e.preventDefault()}>{l}</a></li>
            ))}
          </ul>
        </div>
      </div>

      {/* ---- 版权条 ---- */}
      <div className={styles.copyright}>
        © 2026 MAI·ISLE · 沪 ICP 备 12345678 号 · 沪公网安备 31010402000000 号
      </div>
    </footer>
  )
}
