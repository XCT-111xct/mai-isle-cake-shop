// ============================================================
// 文件功能：前台官网路由表（技术开发文档 §6.3）
// 说明：
//   1. HashRouter：hash 路由（URL 形如 #/cakes），对齐原型
//   2. 所有页面包在 MainLayout 里（共享 Navbar + Footer）
//   3. 新增两件事：路由级埋点（归因数据入口）+ 预览模式提示条
// ============================================================

import { useEffect, useState } from 'react'
import { HashRouter, Routes, Route, useLocation } from 'react-router-dom'
import MainLayout from '@/layouts/MainLayout'
import HomePage from '@/pages/HomePage'
import AboutPage from '@/pages/AboutPage'
import CakeListPage from '@/pages/CakeListPage'
import CakeDetailPage from '@/pages/CakeDetailPage'
import StorePage from '@/pages/StorePage'
import ContactPage from '@/pages/ContactPage'
import NotFoundPage from '@/pages/NotFoundPage'
import { client } from '@/api/client'
import { readPreviewState, trackPageView, type PreviewState } from '@/utils/tracker'

/**
 * 路由级埋点：每次路径变化上报一次 page_view。
 * 放在 <Routes> 同级而不是各页面里，是因为「漏埋某个页面」是埋点最常见的
 * 失败方式——集中在一处就漏不掉。
 */
function RouteTracker() {
  const location = useLocation()
  useEffect(() => {
    trackPageView(`${location.pathname}${location.search}`)
  }, [location.pathname, location.search])
  return null
}

/**
 * 预览模式提示条。
 *
 * 为什么要真的去请求一次而不是只检查本地有没有 token：
 * 令牌可能已过期/被发布操作吊销，本地仍存着。此时页面显示的是**线上内容**，
 * 若还挂一条「预览中」，编辑者会把线上内容当成草稿确认掉——这是最危险的
 * 误导。所以这里以服务端返回的 preview 标记为准。
 */
function PreviewBanner() {
  const [state, setState] = useState<PreviewState | null>(null)
  const [status, setStatus] = useState<'checking' | 'active' | 'invalid' | 'none'>('none')

  useEffect(() => {
    const st = readPreviewState()
    if (!st?.token) return
    setState(st)
    setStatus('checking')
    // 用任意一个内容接口做校验即可：后端会校验 token 与 key 的绑定关系
    const key = st.key || 'brand_story'
    client
      .get(`/content/${key}`)
      .then((res) => {
        const data = res.data.data as { preview?: boolean }
        setStatus(data.preview ? 'active' : 'invalid')
      })
      .catch(() => setStatus('invalid'))
  }, [])

  if (status === 'none' || status === 'checking' || !state) return null

  const active = status === 'active'
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        padding: '8px 16px',
        fontSize: 13,
        lineHeight: 1.5,
        textAlign: 'center',
        color: active ? '#0b4a2f' : '#7a3b00',
        background: active ? '#d8f3e3' : '#fff4e0',
        borderBottom: `1px solid ${active ? '#8fd6b0' : '#f0c98a'}`,
      }}
    >
      {active ? (
        <>
          <strong>预览模式</strong>：当前展示的是<strong>未发布草稿</strong>
          （{state.key || '内容'}），顾客看到的仍是线上已发布版本。
        </>
      ) : (
        <>
          <strong>预览已失效</strong>：链接过期或已被发布操作吊销，
          当前展示的是<strong>线上内容</strong>。
        </>
      )}
    </div>
  )
}

export default function App() {
  return (
    <HashRouter>
      <PreviewBanner />
      <RouteTracker />
      <Routes>
        {/* MainLayout 包裹全部前台页面（共享导航与页脚） */}
        <Route element={<MainLayout />}>
          {/* 首页 */}
          <Route path="/" element={<HomePage />} />
          {/* 关于麦屿（支持 #anchor-story/value/chars 锚点） */}
          <Route path="/about" element={<AboutPage />} />
          {/* 蛋糕展示（query: category_id/page/sort） */}
          <Route path="/cakes" element={<CakeListPage />} />
          {/* 蛋糕详情 */}
          <Route path="/cakes/:id" element={<CakeDetailPage />} />
          {/* 门店信息 */}
          <Route path="/stores" element={<StorePage />} />
          {/* 联系我们 + 留言表单 */}
          <Route path="/contact" element={<ContactPage />} />
          {/* 兜底：404 */}
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </HashRouter>
  )
}
