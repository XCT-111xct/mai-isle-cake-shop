// ============================================================
// 文件功能：404 页面（技术开发文档 §6.3 兜底路由）
// ============================================================

import { Link } from 'react-router-dom'
import styles from './NotFoundPage.module.css'

export default function NotFoundPage() {
  return (
    <div className={styles.wrap}>
      <p className={styles.code}>404</p>
      <h1 className={styles.title}>页面不存在</h1>
      <p className={styles.desc}>您访问的页面可能已被移动或删除。</p>
      <Link to="/" className={styles.home}>返回首页</Link>
    </div>
  )
}
