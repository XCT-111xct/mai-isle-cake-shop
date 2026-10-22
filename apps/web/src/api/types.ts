// ============================================================
// 文件功能：前台接口类型定义（与后端技术文档 §5 一一对应）
// 说明：所有金额字段均为 number（单位：元）
// ============================================================

// ---------- 通用 ----------
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

/** 分页结构（技术文档 §5.1.5） */
export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ---------- 蛋糕（前台 §5.2.1/§5.2.2） ----------
export interface CakeListItem {
  id: number
  name: string
  category: string
  image_url: string
  price_from: number
  is_featured: boolean
}

export interface CakeSpec {
  name: string
  price: number
}

export interface RelatedCake {
  id: number
  name: string
  price_from: number
  image_url: string
}

export interface CakeDetail {
  id: number
  name: string
  category: string
  description: string
  image_url: string
  specs: CakeSpec[]
  related: RelatedCake[]
  custom_tips: string
}

// ---------- 分类 ----------
export interface CategoryItem {
  id: number
  name: string
  count: number
}

// ---------- 门店 ----------
export interface StoreItem {
  id: number
  name: string
  address: string
  phone: string
  hours: string | null
  image_url: string | null
}

// ---------- 内容区块 ----------
export interface BannerItem {
  id: number
  image_url: string
  slogan: string | null
  subtitle: string | null
  sort_order: number
  is_active: boolean
}

export interface OrderInfo {
  hotline: string
  hours: string
  delivery_note: string
}

export interface ContactInfo {
  address: string
  email: string
}

export interface BrandChar {
  title: string
  desc: string
}

export interface BrandJourney {
  year: string
  title: string
  desc: string
}

export interface HardwareSoftwareItem {
  name: string
  desc: string
}

/** 内容接口统一响应：JSON 型 value 是对象，Markdown 型 value 是字符串 */
export type ContentValue =
  | { banners: BannerItem[] }
  | { brand_chars: BrandChar[] }
  | { brand_journey: BrandJourney[] }
  | { hardware: HardwareSoftwareItem[] }
  | { software: HardwareSoftwareItem[] }
  | OrderInfo
  | ContactInfo
  | string

// ---------- 留言提交 ----------
export interface MessageSubmit {
  name: string
  phone: string
  content: string
  captcha: string
  captcha_id: string
}
