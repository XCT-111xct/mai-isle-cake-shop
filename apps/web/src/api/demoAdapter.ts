// ============================================================
// 文件功能：演示模式（纯静态）的接口模拟层
//
// 【为什么需要它】
//   本项目是"前端 + FastAPI 后端"的结构，而后端跑在服务器上。
//   GitHub Pages 这类静态托管服务跑不了 Python，所以做了一套"纯静态演示版"：
//   把数据库里的真实数据导出成 demo-data.json，前端在演示模式下用本地数据渲染，
//   完全不请求后端。数据是真的，只是不连后端。
//
// 【怎么启用】
//   构建时设置环境变量 VITE_DEMO=1，见 vite.config.ts 与 package.json 的 build:demo 命令。
//   正常开发/生产构建不受任何影响（IS_DEMO 为 false 时本文件完全不参与逻辑）。
//
// 【实现方式】
//   拦截 axios 的 adapter（最底层的一次请求），直接返回构造好的响应对象。
//   这样上层的页面代码、请求拦截器、错误处理逻辑全都不用改，
//   也不会出现"页面为了演示而写一堆 if"的坏味道。
// ============================================================

import type { AxiosAdapter, AxiosResponse, InternalAxiosRequestConfig } from 'axios'

import raw from './demo-data.json'

/** 是否处于演示模式（构建时由 VITE_DEMO 决定，打包后是常量，可被 tree-shaking） */
export const IS_DEMO = import.meta.env.VITE_DEMO === '1'

/** 静态资源基础路径：正常构建是 '/'，演示构建（子路径部署）是 './' */
const BASE = import.meta.env.BASE_URL

// ---------- 数据集（导出脚本生成，见 tools/export_demo_data.py）----------
interface DemoSpec {
  name: string
  price: number
}
interface DemoCake {
  id: number
  name: string
  category_id: number
  category: string
  description: string
  image_url: string
  specs: DemoSpec[]
  price_from: number
  is_featured: boolean
  is_active: boolean
  sort_order: number
  created_at: string
}
interface DemoStore {
  id: number
  name: string
  address: string
  phone: string
  hours: string
  image_url: string
}
interface DemoData {
  categories: { id: number; name: string; count: number }[]
  cakes: DemoCake[]
  stores: DemoStore[]
  contents: Record<string, unknown>
}

const DATA = raw as unknown as DemoData

// ---------- 图片路径修正 ----------
/**
 * 把数据库里存的 `/uploads/xxx.webp` 转成"能在当前部署位置访问到"的路径。
 *
 * 为什么需要：数据库存的是绝对路径（以 / 开头），部署在域名根目录时没问题；
 * 但 GitHub Pages 的项目站点在 /仓库名/ 子路径下，绝对路径会指到别人的目录去。
 * 拼上 BASE 之后：正常构建 → '/uploads/xxx'；演示构建 → './uploads/xxx'，两种都对。
 */
function assetUrl(u: string): string {
  if (!u) return u
  if (u.startsWith('/uploads/')) return BASE + u.slice(1)
  return u
}

/** 递归把所有字符串过一遍 assetUrl（非 /uploads/ 开头的字符串会原样返回，不影响文案内容） */
function fixDeep<T>(value: T): T {
  if (typeof value === 'string') return assetUrl(value) as unknown as T
  if (Array.isArray(value)) return value.map((v) => fixDeep(v)) as unknown as T
  if (value && typeof value === 'object') {
    const out: Record<string, unknown> = {}
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) out[k] = fixDeep(v)
    return out as unknown as T
  }
  return value
}

// ---------- 响应构造 ----------
/** 后端统一响应格式 {code, message, data}，业务成功时 code=0 */
function ok(data: unknown) {
  return { code: 0, message: 'success', data }
}

/** 拼一个 axios 格式的响应对象 */
function makeResponse(
  config: InternalAxiosRequestConfig,
  data: unknown,
  status = 200,
  headers: Record<string, string> = {}
): AxiosResponse {
  return {
    data,
    status,
    statusText: status === 200 ? 'OK' : 'ERROR',
    headers,
    config,
    request: {},
  } as AxiosResponse
}

/** 抛出与 axios 同构的错误，让上层拦截器能取到 error.response.data.message */
function httpError(config: InternalAxiosRequestConfig, status: number, message: string): never {
  const err = new Error(message) as Error & { response?: AxiosResponse }
  err.response = makeResponse(config, { code: status * 100, message, data: null }, status)
  throw err
}

/** 模拟一点网络延迟，让加载态、骨架屏在演示时也能看到效果 */
const wait = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))

// ---------- 演示用图形验证码 ----------
/**
 * 生成一张写着 DEMO 的 SVG 验证码，替代后端 Pillow 生成的图片。
 * 返回 Blob 是为了和真实接口保持一致（前端用 responseType:'blob' 接收）。
 *
 * 演示模式不校验验证码内容 —— 随便输 4 位都能提交成功，
 * 因为它连的是本地假数据，不会真的产生留言。
 */
function demoCaptchaBlob(): Blob {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="130" height="44" viewBox="0 0 130 44">
<rect width="130" height="44" fill="#fdfaf6"/>
<path d="M0 12 L130 26 M0 34 L130 8" stroke="#e0d3bf" stroke-width="1"/>
<text x="65" y="30" font-family="Menlo,Consolas,monospace" font-size="19" font-weight="700"
      fill="#8b6f47" text-anchor="middle" letter-spacing="3" transform="rotate(-2 65 22)">DEMO</text>
</svg>`
  return new Blob([svg], { type: 'image/svg+xml' })
}

// ---------- 核心：把请求路由到本地数据 ----------
export const demoAdapter: AxiosAdapter = async (config) => {
  await wait(160)

  // config.url 是不含 baseURL 的部分，例如 '/cakes'
  const full = (config.url || '').replace(/^\/+/, '')
  const [path, queryString] = full.split('?')
  const method = (config.method || 'get').toLowerCase()

  // ---------- 解析查询参数（有两个来源，都要读）----------
  // 来源①：config.params —— axios 的常规用法 client.get('/cakes', { params: {...} })
  //        此时 url 是干净的 '/cakes'，参数单独放在这个对象里。
  //        实测踩过的坑：只解析 url 上的 ?sort=xxx 会全部读到空值，
  //        导致筛选/排序/分页静默失效（页面不报错，只是排序不动）。
  // 来源②：url 里自带的 ?a=1&b=2 —— 手工拼查询串时会有
  const q = new URLSearchParams()
  if (config.params && typeof config.params === "object") {
    for (const [k, v] of Object.entries(config.params as Record<string, unknown>)) {
      if (v !== undefined && v !== null) q.set(k, String(v))
    }
  }
  // url 上的参数优先级更低（不覆盖 params 里已有的）
  new URLSearchParams(queryString || "").forEach((v, k) => {
    if (!q.has(k)) q.set(k, v)
  })

  // ========== GET /captcha ==========
  if (path === 'captcha' && method === 'get') {
    return makeResponse(config, demoCaptchaBlob(), 200, { 'x-captcha-id': 'DEMO' })
  }

  // ========== GET /categories ==========
  if (path === 'categories') {
    return makeResponse(config, ok({ items: fixDeep(DATA.categories) }))
  }

  // ========== GET /stores ==========
  if (path === 'stores') {
    return makeResponse(config, ok({ items: fixDeep(DATA.stores) }))
  }

  // ========== GET /content/{key} ==========
  if (path.startsWith('content/')) {
    const key = decodeURIComponent(path.slice('content/'.length))
    let value = DATA.contents[key]

    // 与后端保持一致：JSON 类 key 缺失返回 {}，Markdown 类返回 ""
    if (value === undefined) value = ''
    // banners 历史数据可能是裸数组，后端统一包成 {banners: [...]}
    if (key === 'banners' && Array.isArray(value)) value = { banners: value }

    return makeResponse(config, ok({ key, value: fixDeep(value) }))
  }

  // ========== POST /messages（提交留言）==========
  if (path === 'messages' && method === 'post') {
    // 演示模式不落库、不校验验证码，直接返回成功
    return makeResponse(config, ok({ id: Date.now() }))
  }

  // ========== GET /cakes/{id}（详情）==========
  const detailMatch = path.match(/^cakes\/(\d+)$/)
  if (detailMatch) {
    const id = Number(detailMatch[1])
    const cake = DATA.cakes.find((c) => c.id === id && c.is_active)
    if (!cake) httpError(config, 404, '产品不存在或已下架')

    // 相关推荐：同分类其他上架产品，最多 4 个（与后端一致）
    const related = DATA.cakes
      .filter((c) => c.category_id === cake.category_id && c.id !== cake.id && c.is_active)
      .slice(0, 4)
      .map((c) => ({
        id: c.id,
        name: c.name,
        price_from: c.price_from,
        image_url: c.image_url,
      }))

    const customTips = typeof DATA.contents['custom_tips'] === 'string' ? DATA.contents['custom_tips'] : ''

    return makeResponse(
      config,
      ok(
        fixDeep({
          id: cake.id,
          name: cake.name,
          category: cake.category,
          description: cake.description,
          image_url: cake.image_url,
          specs: cake.specs,
          related,
          custom_tips: customTips,
        })
      )
    )
  }

  // ========== GET /cakes（列表：筛选 + 排序 + 分页）==========
  if (path === 'cakes') {
    const categoryId = q.get('category_id')
    const featured = q.get('featured')
    const page = Math.max(1, Number(q.get('page') || 1))
    const pageSize = Math.max(1, Number(q.get('page_size') || 12))
    const sort = q.get('sort') || 'recommend'

    // 过滤：前台永远只看上架产品
    let list = DATA.cakes.filter((c) => c.is_active)
    if (categoryId) list = list.filter((c) => c.category_id === Number(categoryId))
    if (featured === '1') list = list.filter((c) => c.is_featured)

    // 排序：与后端 list_cakes 的四种规则保持一致
    // 注意 recommend 不需要再排 —— 导出数据时已按 sort_order + created_at 排好
    if (sort === 'price_asc') list = [...list].sort((a, b) => a.price_from - b.price_from)
    else if (sort === 'price_desc') list = [...list].sort((a, b) => b.price_from - a.price_from)
    else if (sort === 'newest') list = [...list].sort((a, b) => b.created_at.localeCompare(a.created_at))

    const total = list.length
    const start = (page - 1) * pageSize
    const items = list.slice(start, start + pageSize).map((c) => ({
      id: c.id,
      name: c.name,
      category: c.category,
      image_url: assetUrl(c.image_url),
      price_from: c.price_from,
      is_featured: c.is_featured,
    }))

    return makeResponse(
      config,
      ok({
        items,
        total,
        page,
        page_size: pageSize,
        total_pages: total ? Math.ceil(total / pageSize) : 0,
      })
    )
  }

  // 未覆盖的接口：明确报错，避免"悄悄返回空数据"导致页面空白却查不出原因
  httpError(config, 404, `演示模式未实现的接口：${method.toUpperCase()} /${path}`)
}
