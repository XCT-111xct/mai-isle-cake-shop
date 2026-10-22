// ============================================================
// 文件功能：门店信息页（UI-UX §5.5，PRD F5）
// 说明：
//   1. 数据 GET /api/v1/stores：后端已过滤仅启用门店
//   2. 3 列竖版门店卡：5:4 图 + 编号角标 + 名称 + 三行信息
//   3. 本期不做地图（已确认）
// ============================================================

import { useEffect, useState } from 'react'
import { client } from '@/api/client'
import type { StoreItem } from '@/api/types'
import { Empty, PageBanner, Spinner } from '@/components/Common'
import styles from './StorePage.module.css'

export default function StorePage() {
  const [stores, setStores] = useState<StoreItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    client.get('/stores')
      .then((r) => setStores(r.data.data.items as StoreItem[]))
      .catch(() => setStores([]))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <PageBanner
        title="门店信息"
        en="OUR STORES · 门店"
        eyebrow="麦屿门店 · STORES"
        imageUrl="https://images.unsplash.com/photo-1555396273-367ea4eb4db5?w=1600&q=80"
      />

      <div className={styles.wrap}>
        {loading ? (
          <Spinner text="门店加载中…" />
        ) : stores.length > 0 ? (
          <div className={styles.grid}>
            {stores.map((s, i) => (
              <div key={s.id} className={styles.card}>
                {/* 5:4 门店图 + 编号角标 */}
                <div className={styles.cover}>
                  <span className={styles.no}>No.0{i + 1}</span>
                  {s.image_url ? (
                    <img src={s.image_url} alt={s.name} loading="lazy" />
                  ) : (
                    <div className={styles.noImg} aria-label={`${s.name}暂无图片`} />
                  )}
                </div>
                {/* 信息区 */}
                <div className={styles.info}>
                  <h2 className={styles.name}>{s.name}</h2>
                  <p className={styles.nameEn}>MAI·ISLE STORE</p>
                  <ul className={styles.rows}>
                    <li><span className={styles.rowIcon} aria-hidden="true">📍</span><span>{s.address}</span></li>
                    <li><span className={styles.rowIcon} aria-hidden="true">📞</span><span>{s.phone}</span></li>
                    {s.hours && <li><span className={styles.rowIcon} aria-hidden="true">🕒</span><span>{s.hours}</span></li>}
                  </ul>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <Empty title="暂无门店信息" desc="门店筹备中，敬请期待" />
        )}
      </div>
    </div>
  )
}
