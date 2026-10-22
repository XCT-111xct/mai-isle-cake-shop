// ============================================================
// 文件功能：蛋糕展示页（UI-UX §5.3，PRD F2）
// ⚠️ BUG-002 强约束落点（实施方案 §7.2）：
//   1. select onChange 必须绑定 → 触发重新请求
//   2. sort 作为请求参数传给后端（服务端排序）
//   3. 切换分类/排序必须重置 page = 1
//   4. 排序与分类筛选叠加生效（条件同时传）
//   5. 加载中显示 loading 占位，禁止白屏
//   6. 9 个/页（与设计稿分页器一致）
// ============================================================

import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { client } from '@/api/client'
import type { CakeListItem, CategoryItem, PageResult } from '@/api/types'
import CakeCard from '@/components/CakeCard'
import { Breadcrumb, Empty, Pagination, PageBanner, Spinner } from '@/components/Common'
import styles from './CakeListPage.module.css'

// 排序选项（与后端 sort 参数一一对应，技术文档 §5.2.1）
const SORT_OPTIONS = [
  { value: 'recommend', label: '推荐' },
  { value: 'price_asc', label: '价格低到高' },
  { value: 'price_desc', label: '价格高到低' },
  { value: 'newest', label: '新品优先' },
]

type SortKey = 'recommend' | 'price_asc' | 'price_desc' | 'newest'

// 一页 9 个（老大确认：与设计稿分页器一致，3 列 × 3 行）
const PAGE_SIZE = 9

export default function CakeListPage() {
  // URL 参数：支持分享/刷新保留筛选状态（category_id/page/sort）
  const [searchParams, setSearchParams] = useSearchParams()
  const categoryId = searchParams.get('category_id') ? Number(searchParams.get('category_id')) : undefined
  const page = Number(searchParams.get('page') || '1')
  const sort = (searchParams.get('sort') || 'recommend') as SortKey

  const [categories, setCategories] = useState<CategoryItem[]>([])
  const [data, setData] = useState<PageResult<CakeListItem> | null>(null)
  const [loading, setLoading] = useState(true)
  const gridRef = useRef<HTMLDivElement>(null)

  // ---------- 修改筛选条件：一律重置 page=1（BUG-002 关键） ----------
  function changeCategory(id?: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      if (id === undefined) next.delete('category_id')
      else next.set('category_id', String(id))
      next.set('page', '1') // 切分类回第 1 页
      return next
    })
  }

  // ---------- 排序下拉：onChange 必绑定（BUG-002 根因修复） ----------
  function changeSort(value: string) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('sort', value)
      next.set('page', '1') // 切排序回第 1 页
      return next
    })
  }

  function changePage(p: number) {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('page', String(p))
      return next
    })
    // 翻页后平滑滚动到产品区顶部（UI-UX §5.3）
    gridRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  // ---------- 分类列表（一次性加载） ----------
  useEffect(() => {
    client.get('/categories').then((r) => setCategories(r.data.data.items as CategoryItem[])).catch(() => setCategories([]))
  }, [])

  // ---------- 数据请求：分类 + 分页 + 排序 叠加传参（BUG-002） ----------
  useEffect(() => {
    setLoading(true) // loading 占位，禁止白屏
    client
      .get('/cakes', {
        params: {
          category_id: categoryId,
          page,
          page_size: PAGE_SIZE,
          sort,
        },
      })
      .then((r) => setData(r.data.data as PageResult<CakeListItem>))
      .catch(() => setData({ items: [], total: 0, page, page_size: PAGE_SIZE, total_pages: 0 }))
      .finally(() => setLoading(false))
  }, [categoryId, page, sort])

  // 当前分类名（用于头部标题，无效 id 容错为"全部蛋糕"）
  const currentCategoryName = useMemo(() => {
    const found = categories.find((c) => c.id === categoryId)
    return found ? found.name : undefined
  }, [categories, categoryId])

  return (
    <div>
      {/* 静态 Banner */}
      <PageBanner
        title="蛋糕展示"
        en="CAKES · 手作甜点"
        eyebrow="SELECTED · 精选"
        imageUrl="https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=1600&q=80"
      />

      <div className={styles.wrap}>
        {/* 面包屑 */}
        <div className={styles.crumbWrap}>
          <Breadcrumb items={[{ label: '首页', to: '/' }, { label: '蛋糕展示' }]} />
        </div>

        <div className={styles.body}>
          {/* ---------- 左侧分类导航（sticky） ---------- */}
          <aside className={styles.sidebar}>
            <p className={styles.cateTitle}>CATEGORIES</p>
            {/* "全部"项 */}
            <button
              type="button"
              className={`${styles.cateItem} ${categoryId === undefined ? styles.cateActive : ''}`}
              onClick={() => changeCategory(undefined)}
            >
              <span>全部</span>
              <span className={styles.cateCount}>{data?.total ?? 0}</span>
            </button>
            {/* 8 个分类（含数量角标） */}
            {categories.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`${styles.cateItem} ${categoryId === c.id ? styles.cateActive : ''}`}
                onClick={() => changeCategory(c.id)}
              >
                <span>{c.name}</span>
                <span className={styles.cateCount}>{c.count}</span>
              </button>
            ))}
          </aside>

          {/* ---------- 右侧产品区 ---------- */}
          <div className={styles.main} ref={gridRef}>
            {/* 头部：当前分类 + 排序下拉 */}
            <div className={styles.toolbar}>
              <h2 className={styles.listTitle}>
                <em className={styles.titleEn}>Cakes</em>
                {currentCategoryName || '全部蛋糕'}
              </h2>
              {/* 排序下拉：onChange 绑定 changeSort（BUG-002） */}
              <label className={styles.sortLabel}>
                <span className={styles.sortText}>排序</span>
                <select
                  className={styles.sortSelect}
                  value={sort}
                  onChange={(e) => changeSort(e.target.value)}
                  aria-label="排序方式"
                >
                  {SORT_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </label>
            </div>

            {/* 加载态 / 内容 */}
            {loading ? (
              <Spinner text="蛋糕加载中…" />
            ) : data && data.items.length > 0 ? (
              <>
                <div className={styles.grid}>
                  {data.items.map((cake) => (
                    <CakeCard
                      key={cake.id}
                      id={cake.id}
                      name={cake.name}
                      imageUrl={cake.image_url}
                      priceFrom={cake.price_from}
                      category={cake.category}
                    />
                  ))}
                </div>
                {/* 分页（分类/排序联动自动由 URL 驱动） */}
                <Pagination page={page} totalPages={data.total_pages} onChange={changePage} />
              </>
            ) : (
              <Empty title="该分类暂无产品" desc="我们会尽快上新，敬请期待" />
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
