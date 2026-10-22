// ============================================================
// 文件功能：关于麦屿页（UI-UX §5.2，PRD F4）
// 区块：品牌故事 / 品牌理念 / 品牌特色 / 品牌历程 / 硬件保障·软件实力
// 说明：
//   1. 顶栏二级菜单跳转锚点：#anchor-story / anchor-value / anchor-chars
//   2. 锚点平滑滚动 + 130px 偏移（sticky 导航遮挡修正）
//   3. 内容全部来自后台 content，为空则隐藏对应区块
//   4. 页面内不设独立二级导航条（PRD v2.3，原型残留样式不实现）
// ============================================================

import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import { client } from '@/api/client'
import type { BrandChar, BrandJourney, HardwareSoftwareItem } from '@/api/types'
import { PageBanner, Spinner } from '@/components/Common'
import styles from './AboutPage.module.css'

export default function AboutPage() {
  const location = useLocation()
  const [story, setStory] = useState('')
  const [value, setValue] = useState('')
  const [chars, setChars] = useState<BrandChar[]>([])
  const [journey, setJourney] = useState<BrandJourney[]>([])
  const [hardware, setHardware] = useState<HardwareSoftwareItem[]>([])
  const [software, setSoftware] = useState<HardwareSoftwareItem[]>([])
  const [loading, setLoading] = useState(true)

  // 并发加载 6 个内容区块（空内容 → 隐藏区块）
  useEffect(() => {
    Promise.all([
      client.get('/content/brand_story').then((r) => (r.data.data as { value: string }).value ?? '').catch(() => ''),
      client.get('/content/brand_value').then((r) => (r.data.data as { value: string }).value ?? '').catch(() => ''),
      client.get('/content/brand_chars').then((r) => (r.data.data as { value: { brand_chars?: BrandChar[] } }).value?.brand_chars ?? []).catch(() => []),
      client.get('/content/brand_journey').then((r) => (r.data.data as { value: { brand_journey?: BrandJourney[] } }).value?.brand_journey ?? []).catch(() => []),
      client.get('/content/hardware').then((r) => (r.data.data as { value: HardwareSoftwareItem[] }).value ?? []).catch(() => []),
      client.get('/content/software').then((r) => (r.data.data as { value: HardwareSoftwareItem[] }).value ?? []).catch(() => []),
    ]).then(([s, v, ch, j, hw, sw]) => {
      setStory(s); setValue(v); setChars(ch); setJourney(j); setHardware(hw); setSoftware(sw)
      setLoading(false)
    })
  }, [])

  // 锚点滚动：进入页面时若有 #anchor-xxx，平滑滚动到对应区块（offset 130px）
  useEffect(() => {
    const anchor = location.hash.replace('#', '')
    if (anchor.startsWith('anchor-')) {
      // 等数据渲染完成后滚动，避免目标区块还没出现
      setTimeout(() => {
        const el = document.getElementById(anchor)
        if (el) {
          const y = el.getBoundingClientRect().top + window.scrollY - 130
          window.scrollTo({ top: y, behavior: 'smooth' })
        }
      }, 100)
    }
  }, [location.hash, loading])

  if (loading) return <div><PageBanner title="关于麦屿" en="ABOUT MAI·ISLE" /><div className={styles.wrap}><Spinner text="内容加载中…" /></div></div>

  return (
    <div>
      <PageBanner
        title="关于麦屿"
        en="ABOUT MAI·ISLE"
        eyebrow="麦屿手作 · ABOUT"
        imageUrl="https://images.unsplash.com/photo-1568254183919-78a4f43a2877?w=1600&q=80"
      />

      {/* ========== ① 品牌故事 ========== */}
      {story && (
        <section className={styles.section} id="anchor-story">
          <div className={styles.wrap}>
            <div className={styles.split}>
              <div className={styles.textCol}>
                <p className={styles.eyebrow}>BRAND STORY · 品牌故事</p>
                <h1 className={styles.brandZh}>品牌故事</h1>
                <p className={styles.brandEn}>OUR · STORY</p>
                <div className={styles.markdown}><ReactMarkdown>{story}</ReactMarkdown></div>
              </div>
              <div className={styles.imgCol}>
                <img src="/brand-story.webp" alt="麦屿手作品牌故事" loading="lazy" />
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ========== ② 品牌理念（flip：右文左图） ========== */}
      {value && (
        <section className={`${styles.section} ${styles.sectionSoft}`} id="anchor-value">
          <div className={styles.wrap}>
            <div className={`${styles.split} ${styles.flip}`}>
              <div className={styles.imgCol}>
                <img src="/brand-value.webp" alt="麦屿手作品牌理念" loading="lazy" />
                {/* 漂浮卡片（UI-UX §5.2 品牌理念） */}
                <div className={styles.floatCard}>
                  <span className={styles.floatEn}>Brand Value</span>
                  <span className={styles.floatZh}>极致之道</span>
                </div>
              </div>
              <div className={styles.textCol}>
                <p className={styles.eyebrow}>BRAND VALUE · 品牌理念</p>
                <h1 className={styles.brandZh}>品牌理念</h1>
                <p className={styles.brandEn}>OUR · PHILOSOPHY</p>
                <div className={styles.markdown}><ReactMarkdown>{value}</ReactMarkdown></div>
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ========== ③ 品牌特色 ========== */}
      {chars.length > 0 && (
        <section className={styles.section} id="anchor-chars">
          <div className={styles.wrap}>
            <p className={styles.eyebrow}>BRAND CHARACTERISTICS · 品牌特色</p>
            <h1 className={styles.brandZh}>品牌特色</h1>
            <p className={styles.brandEn}>BRAND CHARACTERISTICS</p>
            <div className={`${styles.split} ${styles.charsSplit}`}>
              <div className={styles.charsList}>
                {chars.map((c, i) => (
                  <div key={i} className={styles.charItem}>
                    <span className={styles.charNo}>{String(i + 1).padStart(2, '0')}</span>
                    <div>
                      <h3 className={styles.charTitle}>{c.title}</h3>
                      <p className={styles.charDesc}>{c.desc}</p>
                    </div>
                  </div>
                ))}
              </div>
              <div className={styles.imgCol}>
                <img src="/brand-chars.webp" alt="麦屿手作品牌特色" loading="lazy" />
              </div>
            </div>
          </div>
        </section>
      )}

      {/* ========== ④ 品牌历程（时间线） ========== */}
      {journey.length > 0 && (
        <section className={`${styles.section} ${styles.sectionSoft}`}>
          <div className={styles.wrap}>
            <p className={styles.eyebrow}>BRAND JOURNEY · 品牌历程</p>
            <h2 className={styles.sectionTitle}>一路走来</h2>
            <div className={styles.timeline}>
              {journey.map((j, i) => (
                <div key={i} className={styles.timelineItem}>
                  <span className={styles.timelineYear}>{j.year}</span>
                  <div className={styles.timelineBody}>
                    <h3 className={styles.timelineTitle}>{j.title}</h3>
                    <p className={styles.timelineDesc}>{j.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* ========== ⑤ 硬件保障 / 软件实力 ========== */}
      {(hardware.length > 0 || software.length > 0) && (
        <section className={styles.section}>
          <div className={styles.wrap}>
            <div className={styles.hsGrid}>
              {hardware.length > 0 && (
                <div className={styles.hsCol}>
                  <p className={styles.eyebrow}>HARDWARE · 硬件保障</p>
                  <h3 className={styles.hsTitle}>硬件保障</h3>
                  {hardware.map((h, i) => (
                    <div key={i} className={styles.hsItem}>
                      <span className={styles.hsIcon} aria-hidden="true">◈</span>
                      <div>
                        <p className={styles.hsName}>{h.name}</p>
                        <p className={styles.hsDesc}>{h.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
              {software.length > 0 && (
                <div className={styles.hsCol}>
                  <p className={styles.eyebrow}>SOFTWARE · 软件实力</p>
                  <h3 className={styles.hsTitle}>软件实力</h3>
                  {software.map((s, i) => (
                    <div key={i} className={styles.hsItem}>
                      <span className={styles.hsIcon} aria-hidden="true">◈</span>
                      <div>
                        <p className={styles.hsName}>{s.name}</p>
                        <p className={styles.hsDesc}>{s.desc}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
      )}
    </div>
  )
}
