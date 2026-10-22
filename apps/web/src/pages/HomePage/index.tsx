// 完整版首页（修复数据解析路径 data.value）
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { client } from '@/api/client'
import type { BannerItem, CakeListItem, OrderInfo, StoreItem } from '@/api/types'
import CakeCard from '@/components/CakeCard'
import { SectionHead, Spinner } from '@/components/Common'
import styles from './HomePage.module.css'

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

export default function HomePage() {
  const [banners, setBanners] = useState<BannerItem[]>([])
  const [featuredCakes, setFeaturedCakes] = useState<CakeListItem[]>([])
  const [brandStory, setBrandStory] = useState('')
  const [stores, setStores] = useState<StoreItem[]>([])
  const [orderInfo, setOrderInfo] = useState<OrderInfo | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    Promise.all([
      // content/{key} 响应：{ key, value: <parsed JSON or string> }
      client.get('/content/banners').then((r) => (r.data.data as { value: { banners?: BannerItem[] } }).value?.banners ?? []).catch(() => []),
      // cake 列表响应：PageResult<T>
      client.get('/cakes', { params: { page_size: 6, sort: 'recommend' } }).then((r) => r.data.data.items as CakeListItem[]).catch(() => []),
      client.get('/content/brand_story').then((r) => (r.data.data as { value: string }).value ?? '').catch(() => ''),
      client.get('/stores').then((r) => (r.data.data.items as StoreItem[]).slice(0, 2)).catch(() => []),
      client.get('/content/order_info').then((r) => (r.data.data as { value: OrderInfo }).value ?? null).catch(() => null),
    ]).then(([b, c, s, st, o]) => {
      setBanners(b.filter((x) => x.is_active))
      setFeaturedCakes(c)
      setBrandStory(s)
      setStores(st)
      setOrderInfo(o)
      setLoading(false)
    }).catch(() => setLoading(false))
  }, [])

  const storyParagraphs = brandStory.split('\n\n').filter((p) => p.trim())

  return (
    <div>
      {loading ? (
        <Spinner text="正在加载首页…" />
      ) : (
        <>
          {banners.length > 0 && <HeroCarousel banners={banners} />}

          {featuredCakes.length > 0 && (
            <section className={styles.section}>
              <div className={styles.wrap}>
                <SectionHead eyebrow="SELECTED · 精选" title="今日精选" em="Selected"
                  right={<span className={styles.secHint}>手作限量 · 每日现烤</span>} />
                <div className={styles.cakeGrid}>
                  {featuredCakes.map((cake) => (
                    <CakeCard key={cake.id} id={cake.id} name={cake.name}
                      imageUrl={cake.image_url} priceFrom={cake.price_from} category={cake.category} />
                  ))}
                </div>
                <div className={styles.centerBtn}>
                  <Link to="/cakes" className={styles.ghostBtn}>查看全部蛋糕</Link>
                </div>
              </div>
            </section>
          )}

          {storyParagraphs.length > 0 && (
            <section className={`${styles.section} ${styles.sectionSoft}`}>
              <div className={styles.wrap}>
                <div className={styles.aboutSplit}>
                  <div className={styles.aboutText}>
                    <p className={styles.eyebrow}>BRAND STORY · 品牌故事</p>
                    <h2 className={styles.aboutTitle}>
                      用真材实料<em className={styles.titleEm}>手作</em>每一份甜蜜
                    </h2>
                    {storyParagraphs.slice(0, 2).map((p, i) => (
                      <p key={i} className={styles.aboutPara}>{p}</p>
                    ))}
                    <Link to="/about" className={styles.ghostBtn}>了解麦屿</Link>
                  </div>
                  <div className={styles.aboutImg}>
                    <img src="/brand-story.webp" alt="麦屿手作品牌故事" loading="lazy" />
                  </div>
                </div>
              </div>
            </section>
          )}

          {stores.length > 0 && (
            <section className={styles.section}>
              <div className={styles.wrap}>
                <SectionHead eyebrow="OUR STORES · 门店" title="门店概览" em="Stores" />
                <div className={styles.storeGrid}>
                  {stores.map((s, i) => (
                    <Link to="/stores" key={s.id} className={styles.storeCard}>
                      <div className={styles.storeCover}>
                        <span className={styles.storeNo}>No.0{i + 1}</span>
                        {s.image_url && <img src={s.image_url} alt={s.name} loading="lazy" />}
                      </div>
                      <div className={styles.storeInfo}>
                        <h3 className={styles.storeName}>{s.name}</h3>
                        <p className={styles.storeAddr}><span className={styles.icon}>📍</span>{s.address}</p>
                        <p className={styles.storePhone}><span className={styles.icon}>📞</span>{s.phone}</p>
                        {s.hours && <p className={styles.storeHours}><span className={styles.icon}>🕒</span>{s.hours}</p>}
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            </section>
          )}

          {orderInfo && (
            <section className={`${styles.section} ${styles.sectionOrder}`}>
              <div className={styles.wrap}>
                <SectionHead eyebrow="ORDER INFO · 订购" title="如何订购" em="Order" />
                <div className={styles.orderGrid}>
                  <div className={styles.orderCard}>
                    <p className={styles.orderLabel}>订购专线</p>
                    <p className={styles.orderValue}>{orderInfo.hotline}</p>
                    <p className={styles.orderDesc}>专业顾问为您一对一推荐</p>
                  </div>
                  <div className={styles.orderCard}>
                    <p className={styles.orderLabel}>服务时间</p>
                    <p className={styles.orderValue}>{orderInfo.hours}</p>
                    <p className={styles.orderDesc}>全年无休，节假日照常</p>
                  </div>
                  <div className={styles.orderCard}>
                    <p className={styles.orderLabel}>配送说明</p>
                    <p className={styles.orderValue}>11:00 截止</p>
                    <p className={styles.orderDesc}>{orderInfo.delivery_note}</p>
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  )
}

// Hero 轮播组件：5000ms 自动 + 悬停暂停 + 圆点/箭头（UI-UX §3.9）
function HeroCarousel({ banners }: { banners: BannerItem[] }) {
  const [current, setCurrent] = useState(0)
  const [paused, setPaused] = useState(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const total = banners.length
  const safeIndex = Math.min(current, total - 1)
  const active = banners[safeIndex]

  useEffect(() => {
    if (total <= 1 || prefersReducedMotion) return
    timerRef.current = setInterval(() => {
      if (!paused) setCurrent((c) => (c + 1) % total)
    }, 5000)
    return () => { if (timerRef.current) clearInterval(timerRef.current) }
  }, [total, paused])

  function goNext() { setCurrent((c) => (c + 1) % total) }
  function goPrev() { setCurrent((c) => (c - 1 + total) % total) }
  function goTo(i: number) { setCurrent(i) }

  return (
    <section className={styles.hero}
      onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)}
      aria-roledescription="轮播" aria-label="首页轮播">
      <div className={styles.heroBg} style={{ backgroundImage: `url(${active.image_url || '/placeholder-hero.svg'})` }} />
      <div className={styles.heroContent}>
        <p className={styles.heroEyebrow}>SLIDE {String(safeIndex + 1).padStart(2, '0')} · {active.subtitle || 'EST. 2020 SHANGHAI'}</p>
        <h1 className={styles.heroTitle}>{active.slogan || '麦屿手作，手作每一份甜蜜'}</h1>
        <div className={styles.heroCta}>
          <Link to="/cakes" className={styles.primaryBtn}>探索系列</Link>
          <Link to="/about" className={styles.ghostBtnLight}>了解我们</Link>
        </div>
      </div>
      <div className={styles.heroControls}>
        <div className={styles.heroDots} role="tablist" aria-label="轮播指示">
          {banners.map((b, i) => (
            <button key={b.id} type="button"
              className={`${styles.heroDot} ${i === safeIndex ? styles.heroDotActive : ''}`}
              onClick={() => goTo(i)}
              aria-label={`切换到第 ${i + 1} 张`} aria-selected={i === safeIndex} role="tab" />
          ))}
        </div>
        <span className={styles.heroCounter}>{String(safeIndex + 1).padStart(2, '0')} / {String(total).padStart(2, '0')}</span>
        <div className={styles.heroArrows}>
          <button type="button" className={styles.heroArrow} onClick={goPrev} aria-label="上一张">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M15 18l-6-6 6-6" /></svg>
          </button>
          <button type="button" className={styles.heroArrow} onClick={goNext} aria-label="下一张">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 18l6-6-6-6" /></svg>
          </button>
        </div>
      </div>
    </section>
  )
}