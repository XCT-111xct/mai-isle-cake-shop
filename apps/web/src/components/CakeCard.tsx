// ============================================================
// 文件功能：蛋糕卡片（首页精选 + 展示页 + 详情相关推荐复用）
// 说明：4:3 图 + 分类角标 + 名称 + 起价 + VIEW；hover 上浮 + 图片放大
// ============================================================

import { Link } from 'react-router-dom'
import styles from './CakeCard.module.css'

interface Props {
  id: number
  name: string
  imageUrl: string
  priceFrom: number
  category?: string
  /** 可选角标文案（如 BEST·招牌），无则不显示 */
  badge?: string
}

export default function CakeCard({ id, name, imageUrl, priceFrom, category, badge }: Props) {
  return (
    <Link to={`/cakes/${id}`} className={styles.card} aria-label={`查看蛋糕详情：${name}`}>
      {/* 图片区：4:3 */}
      <div className={styles.imgWrap}>
        <img
          src={imageUrl || `${import.meta.env.BASE_URL}placeholder-cake.svg`}
          alt={name}
          loading="lazy"
          className={styles.img}
        />
        {/* 分类标签 / 角标 */}
        <span className={styles.catTag}>{badge || category || ''}</span>
      </div>
      {/* 文字区 */}
      <div className={styles.info}>
        <h3 className={styles.name}>{name}</h3>
        <div className={styles.priceRow}>
          <span className={styles.price}>
            <span className={styles.yen}>¥</span>
            {priceFrom.toFixed(2).replace(/\.00$/, '')}
            <span className={styles.qi}>起</span>
          </span>
          <span className={styles.view}>VIEW →</span>
        </div>
      </div>
    </Link>
  )
}
