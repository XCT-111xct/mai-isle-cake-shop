// ============================================================
// 文件功能：前台埋点与预览令牌（归因链路的「数据入口」）
//
// 三条设计原则：
//   1. **绝不打扰用户**：所有上报 fire-and-forget，失败静默。
//      埋点挂了最多是数据少一条，不能让页面白屏或弹错。
//   2. **演示模式完全禁用**：GitHub Pages 上的静态演示站没有后端，
//      若照常上报，浏览器控制台会刷满 404，还会拖慢首屏。
//   3. **不采集个人信息**：只记设备类型、页面、来源，不记 IP（后端只存哈希）、
//      不记任何可识别到人的字段。手机号只在用户主动留言时由后端绑定，
//      且以哈希形式存储。
// ============================================================

import { IS_DEMO } from '@/api/demoAdapter'

// ---------- 常量 ----------
const LS_VISITOR = 'mi_vid'          // 持久访客 ID（localStorage）
const LS_VISITOR_AT = 'mi_vid_at'    // 访客 ID 创建时间（用于 365 天刷新）
const SS_SESSION = 'mi_sid'          // 会话 ID（sessionStorage）
const SS_SESSION_AT = 'mi_sid_at'    // 会话最后活动时间
const SS_UTM = 'mi_utm'              // 首次进入的渠道参数（整个会话保留）
const SS_PREVIEW = 'mi_preview'      // 预览令牌

const VISITOR_TTL_MS = 365 * 24 * 60 * 60 * 1000   // 访客 ID 有效期 1 年
const SESSION_IDLE_MS = 30 * 60 * 1000             // 会话空闲 30 分钟重建

const API_BASE = '/api/v1'

// ---------- 工具 ----------

function uuid(): string {
  // crypto.randomUUID 在旧浏览器/非 HTTPS 下不可用，做降级
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID()
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

function safeGet(storage: Storage | undefined, key: string): string | null {
  try {
    return storage ? storage.getItem(key) : null
  } catch {
    // 隐私模式下访问 storage 会抛异常
    return null
  }
}

function safeSet(storage: Storage | undefined, key: string, value: string): void {
  try {
    storage?.setItem(key, value)
  } catch {
    /* 忽略：存不进去就退化为「本页有效」 */
  }
}

/** 取或创建持久访客 ID */
export function getVisitorId(): string {
  const now = Date.now()
  const vid = safeGet(window.localStorage, LS_VISITOR)
  const at = Number(safeGet(window.localStorage, LS_VISITOR_AT) || 0)
  if (vid && now - at < VISITOR_TTL_MS) return vid
  const fresh = uuid()
  safeSet(window.localStorage, LS_VISITOR, fresh)
  safeSet(window.localStorage, LS_VISITOR_AT, String(now))
  return fresh
}

/** 取或创建会话 ID（空闲超 30 分钟则重建，与后端归因时间窗一致） */
export function getSessionId(): string {
  const now = Date.now()
  const sid = safeGet(window.sessionStorage, SS_SESSION)
  const at = Number(safeGet(window.sessionStorage, SS_SESSION_AT) || 0)
  if (sid && now - at < SESSION_IDLE_MS) {
    safeSet(window.sessionStorage, SS_SESSION_AT, String(now))
    return sid
  }
  const fresh = uuid()
  safeSet(window.sessionStorage, SS_SESSION, fresh)
  safeSet(window.sessionStorage, SS_SESSION_AT, String(now))
  return fresh
}

/** 渠道参数：首次落地的 utm 在整个会话内保留，避免站内跳转后丢失来源 */
export function getUtm(): Record<string, string> {
  const cached = safeGet(window.sessionStorage, SS_UTM)
  if (cached) {
    try {
      return JSON.parse(cached)
    } catch {
      /* 损坏则重新采集 */
    }
  }
  const q = new URLSearchParams(window.location.search)
  const utm: Record<string, string> = {}
  ;['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'].forEach((k) => {
    const v = q.get(k)
    if (v) utm[k] = v
  })
  // 只有确实带了 utm 才缓存；否则每次都要重新判断 referrer
  if (Object.keys(utm).length) safeSet(window.sessionStorage, SS_UTM, JSON.stringify(utm))
  return utm
}

/** 当前页面路径（hash 路由取 hash 部分，便于报表按页面聚合） */
function currentPath(): string {
  const hash = window.location.hash || '#/'
  return hash.replace(/^#/, '') || '/'
}

/** 统一的 fire-and-forget 上报 */
function post(path: string, body: unknown): void {
  if (IS_DEMO) return
  try {
    fetch(`${API_BASE}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      // keepalive 让页面卸载时的最后一次上报也能发出去
      keepalive: true,
    }).catch(() => {
      /* 静默：埋点失败不影响任何用户可见行为 */
    })
  } catch {
    /* 忽略 */
  }
}

// ---------- 会话 ----------

let sessionReady = false

/** 建立/刷新会话（应用启动时调一次；页面切换不必重复调） */
export function initTracker(): void {
  if (IS_DEMO || sessionReady) return
  sessionReady = true
  const utm = getUtm()
  post('/track/session', {
    visitor_id: getVisitorId(),
    session_id: getSessionId(),
    page_path: currentPath(),
    referrer: document.referrer || '',
    ...utm,
  })
}

// ---------- 事件 ----------

export type TrackEventType =
  | 'page_view'
  | 'cake_view'
  | 'category_filter'
  | 'hotline_click'
  | 'message_submit'
  | 'map_click'
  | 'wechat_click'

export function trackEvent(
  eventType: TrackEventType,
  opts: {
    pagePath?: string
    refObjectType?: string
    refObjectId?: number
    durationMs?: number
    payload?: Record<string, unknown>
  } = {}
): void {
  if (IS_DEMO) return
  post('/track/event', {
    visitor_id: getVisitorId(),
    session_id: getSessionId(),
    event_type: eventType,
    page_path: opts.pagePath ?? currentPath(),
    ref_object_type: opts.refObjectType ?? '',
    ref_object_id: opts.refObjectId ?? null,
    duration_ms: opts.durationMs ?? 0,
    payload: opts.payload ?? null,
  })
}

/** 页面浏览（App 里在路由变化时调用） */
export function trackPageView(path?: string): void {
  initTracker()
  trackEvent('page_view', { pagePath: path ?? currentPath() })
}

/** 热线点击 —— 归因链路里最核心的转化动作，必须单独记 */
export function trackHotlineClick(source: string, pagePath?: string): void {
  trackEvent('hotline_click', {
    pagePath: pagePath ?? currentPath(),
    payload: { source },
  })
}

// ---------- 官网专属号码 ----------

export interface HotlineInfo {
  phone: string
  tracking_no: string
  label: string
  channel: string
  is_default: boolean
}

let hotlineCache: HotlineInfo | null = null

/**
 * 取当前访客应看到的订购号码。
 *
 * 这是归因能否成立的关键：不同渠道的访客看到不同号码，电话那头才知道
 * 这通电话从哪来。失败时返回 null，调用方应回落到「订购信息」里的号码
 * ——**绝不能因为埋点接口挂了就让页面上的电话变成空白**。
 */
export async function fetchHotline(): Promise<HotlineInfo | null> {
  if (IS_DEMO) return null
  if (hotlineCache) return hotlineCache
  try {
    const utm = getUtm()
    const q = new URLSearchParams({
      referrer: document.referrer || '',
      utm_source: utm.utm_source || '',
      utm_medium: utm.utm_medium || '',
      utm_campaign: utm.utm_campaign || '',
    })
    const res = await fetch(`${API_BASE}/track/hotline?${q.toString()}`)
    if (!res.ok) return null
    const json = await res.json()
    const data = json?.data as HotlineInfo | undefined
    if (data && data.phone) {
      hotlineCache = data
      return data
    }
    return null
  } catch {
    return null
  }
}

// ---------- 预览令牌 ----------
//
// 链接形如：https://站点/?preview_token=xxx&preview_key=brand_story
// 用 URL search（而非 hash 内参数）传，HashRouter 不会把它当成路由。
// 令牌存在 sessionStorage：刷新页面仍然有效，关掉标签页自动失效。

export interface PreviewState {
  token: string
  key: string
}

export function readPreviewState(): PreviewState | null {
  const q = new URLSearchParams(window.location.search)
  const token = q.get('preview_token')
  const key = q.get('preview_key') || ''
  if (token) {
    safeSet(window.sessionStorage, SS_PREVIEW, JSON.stringify({ token, key }))
    // 顺手把地址栏的 token 抹掉，避免被截图/复制传播出去
    q.delete('preview_token')
    q.delete('preview_key')
    const clean = window.location.pathname + (q.toString() ? `?${q}` : '') + window.location.hash
    window.history.replaceState({}, '', clean)
    return { token, key }
  }
  const cached = safeGet(window.sessionStorage, SS_PREVIEW)
  if (cached) {
    try {
      return JSON.parse(cached)
    } catch {
      return null
    }
  }
  return null
}

/** 当前预览令牌（供 axios 请求拦截器附加） */
export function getPreviewToken(): string {
  const st = readPreviewState()
  return st?.token || ''
}

export function clearPreview(): void {
  try {
    window.sessionStorage.removeItem(SS_PREVIEW)
  } catch {
    /* 忽略 */
  }
}
