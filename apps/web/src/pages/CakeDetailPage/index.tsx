// ============================================================
// 文件功能：蛋糕详情页（UI-UX §5.4，PRD F3）
// 说明：
//   1. 数据 GET /cakes/{id}：规格、相关推荐（≤4）、定制说明
//   2. 产品不存在/已下架 → 后端 404，前端显示"蛋糕不存在"（不跳转，保留面包屑）
//   3. 订购引导卡：电话来自 order_info（最突出转化元素）
// ============================================================

import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { client } from '@/api/client'
import type { CakeDetail, OrderInfo } from '@/api/types'
import CakeCard from '@/components/CakeCard'
import { Breadcrumb, PageBanner, Spinner } from '@/components/Common'
import { useHotline } from '@/hooks/useHotline'
import { trackEvent, trackHotlineClick } from '@/utils/tracker'
import styles from './CakeDetailPage.module.css'

export default function CakeDetailPage() {
  const { id } = useParams<{ id: string }>()
  const [cake, setCake] = useState<CakeDetail | null>(null)
  const [notFound, setNotFound] = useState(false)
  const [orderInfo, setOrderInfo] = useState<OrderInfo | null>(null)
  const [loading, setLoading] = useState(true)
  // 订购号码：渠道专属号优先，后台订购信息兜底（归因依赖它）
  const hotline = useHotline(orderInfo?.hotline)

  // 详情页浏览事件：记到具体蛋糕，便于事后看「看了哪款才打的电话」
  useEffect(() => {
    const cakeId = Number(id)
    if (Number.isFinite(cakeId) && cakeId > 0) {
      trackEvent('cake_view', { refObjectType: 'cake', refObjectId: cakeId })
    }
  }, [id])

  // 加载蛋糕详情 + 订购信息
  useEffect(() => {
    setLoading(true)
    setNotFound(false)
    Promise.all([
      client.get(`/cakes/${id}`).then((r) => r.data.data as CakeDetail).catch((err: Error) => {
        // 404/40400：下架或不存在
        if (err.message.includes('不存在') || err.message.includes('下架')) setNotFound(true)
        return null
      }),
      client.get('/content/order_info').then((r) => (r.data.data as { value: OrderInfo }).value ?? null).catch(() => null),
    ]).then(([c, o]) => {
      setCake(c)
      setOrderInfo(o)
      setLoading(false)
    })
  }, [id])

  if (loading) return <div className={styles.wrap}><Spinner text="蛋糕详情加载中…" /></div>

  // 下架/不存在：显示友好提示（PRD F3：下架后详情不可访问）
  if (notFound || !cake) {
    return (
      <div>
        <PageBanner title="蛋糕不存在" en="CAKE NOT FOUND" height="32vh" />
        <div className={styles.wrap}>
          <Breadcrumb items={[{ label: '首页', to: '/' }, { label: '蛋糕展示', to: '/cakes' }]} />
          <div className={styles.notFound}>
            <p className={styles.notFoundTitle}>该蛋糕已下架或不存在</p>
            <p className={styles.notFoundDesc}>您可以逛逛其他蛋糕，或直接致电订购。</p>
            <Link to="/cakes" className={styles.backBtn}>返回蛋糕展示</Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div>
      {/* 矮版 Banner：标题为产品名 */}
      <PageBanner title={cake.name} en={cake.category} height="46vh" />

      <div className={styles.wrap}>
        {/* 面包屑：首页 / 蛋糕展示 / 产品名 */}
        <Breadcrumb items={[
          { label: '首页', to: '/' },
          { label: '蛋糕展示', to: '/cakes' },
          { label: cake.name },
        ]} />

        {/* 主体两栏 */}
        <div className={styles.body}>
          {/* 左：产品大图 4:5 */}
          <div className={styles.imgWrap}>
            <img src={cake.image_url || `${import.meta.env.BASE_URL}placeholder-cake.svg`} alt={cake.name} />
          </div>

          {/* 右：信息区 */}
          <div className={styles.info}>
            <h1 className={styles.name}>{cake.name}</h1>

            {/* 规格与价格卡 */}
            <div className={styles.specCard}>
              <p className={styles.specHead}>规格与价格 · SPECIFICATIONS</p>
              {cake.specs.map((s, i) => (
                <div key={i} className={styles.specRow}>
                  <span className={styles.specName}>{s.name}</span>
                  <span className={styles.specPrice}>
                    <span className={styles.specYen}>¥</span>{s.price.toFixed(2).replace(/\.00$/, '')}
                  </span>
                </div>
              ))}
            </div>

            {/* 产品描述 */}
            {cake.description && (
              <div className={styles.descBlock}>
                <h3 className={styles.descTitle}>产品介绍</h3>
                <p className={styles.descText}>{cake.description}</p>
              </div>
            )}

            {/* 定制说明（来自 content.custom_tips，空则隐藏） */}
            {cake.custom_tips && (
              <div className={styles.tipsBlock}>
                <h4 className={styles.tipsTitle}>定制说明</h4>
                <p className={styles.tipsText}>{cake.custom_tips}</p>
              </div>
            )}

            {/* 订购引导卡（最突出转化元素） */}
            <a
              className={styles.orderCard}
              href={`tel:${hotline.phone}`}
              // 这是归因链路里最关键的一次点击：记下「从哪款蛋糕点的电话」
              onClick={() => trackHotlineClick('detail_order_card', `/cakes/${id}`)}
            >
              <span className={styles.orderIcon} aria-hidden="true">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.91.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/></svg>
              </span>
              <span className={styles.orderText}>
                <span className={styles.orderLabel}>订购热线</span>
                <span className={styles.orderHotline}>{hotline.phone}</span>
                <span className={styles.orderSub}>
                  服务时间 {orderInfo?.hours || '08:00 — 18:00'}
                  {orderInfo?.delivery_note ? ` ｜ ${orderInfo.delivery_note}` : ''}
                </span>
              </span>
            </a>
          </div>
        </div>

        {/* 相关推荐：同系列其他上架产品，最多 4 个 */}
        {cake.related.length > 0 && (
          <section className={styles.related}>
            <h2 className={styles.relatedTitle}>同系列推荐</h2>
            <div className={styles.relatedGrid}>
              {cake.related.map((r) => (
                <CakeCard key={r.id} id={r.id} name={r.name} imageUrl={r.image_url} priceFrom={r.price_from} />
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
