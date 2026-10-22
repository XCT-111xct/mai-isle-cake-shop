// ============================================================
// 文件功能：后台接口类型定义（与后端技术文档 §5 后台部分一一对应）
// ============================================================

// ---------- 通用 ----------
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

/** 分页结构 */
export interface PageResult<T> {
  items: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// ---------- 认证 ----------
export interface AdminUser {
  id: number
  username: string
  name: string
  role: 'super' | 'ops'
  is_active: boolean
  last_login_at: string | null
}

export interface LoginResult {
  access_token: string
  token_type: string
  user: AdminUser
}

export interface LoginPayload {
  username: string
  password: string
  captcha: string
  captcha_id: string
}

// ---------- 仪表盘 ----------
export interface DashboardStats {
  cake_count: number
  cake_month_new: number
  month_order_count: number
  month_order_growth: number
  store_count: number
  store_active: number
  store_inactive: number
  pending_message_count: number
  need_follow_count: number
  order_status_distribution: { pending: number; confirmed: number; completed: number; cancelled: number }
  recent_orders: RecentOrder[]
  recent_messages: RecentMessage[]
}

export interface RecentOrder {
  id: number
  order_no: string
  customer_name: string
  cake_name: string
  amount: number
  status: string
}

export interface RecentMessage {
  id: number
  name: string
  phone: string
  content: string
  created_at: string
  status: string
}

// ---------- 商品 ----------
export interface CakeSpecInput {
  name: string
  price: number
}

export interface CakeRow {
  id: number
  name: string
  category_id: number
  category: string
  image_url: string
  spec_count: number
  price_from: number
  sort_order: number
  is_featured: boolean
  is_active: boolean
}

export interface CakeDetail {
  id: number
  name: string
  category_id: number
  image_url: string
  description: string
  specs: { name: string; price: number }[]
  is_featured: boolean
  is_active: boolean
  sort_order: number
}

// ---------- 分类 ----------
export interface CategoryRow {
  id: number
  name: string
  sort_order: number
  cake_count: number
}

// ---------- 订单 ----------
export type OrderStatus = 'pending' | 'confirmed' | 'completed' | 'cancelled'

export interface OrderRow {
  id: number
  order_no: string
  customer_name: string
  customer_phone: string // 列表已脱敏
  cake_name: string
  spec_name: string
  quantity: number
  amount: number
  pickup_type: 'self' | 'delivery'
  status: OrderStatus
  created_at: string
}

export interface OrderDetail {
  id: number
  order_no: string
  customer_name: string
  customer_phone: string // 详情完整
  cake_snapshot: { cake_id: number; cake_name: string; spec_name: string; price: number }
  quantity: number
  amount: number
  pickup_type: 'self' | 'delivery'
  delivery_address: string | null
  custom_note: string | null
  remark: string | null
  status: OrderStatus
  created_at: string
  updated_at: string
}

export interface OrderPayload {
  customer_name: string
  customer_phone: string
  cake_id: number
  spec_name: string
  quantity: number
  pickup_type: 'self' | 'delivery'
  delivery_address?: string | null
  custom_note?: string | null
  remark?: string | null
}

// ---------- 门店 ----------
export interface StoreRow {
  id: number
  name: string
  address: string
  phone: string
  hours: string | null
  image_url: string | null
  sort_order: number
  is_active: boolean
}

// ---------- 内容 ----------
export interface ContentKeyItem {
  key: string
  updated_at: string | null
}

export interface BannerItem {
  id: number
  image_url: string
  slogan: string | null
  subtitle: string | null
  sort_order: number
  is_active: boolean
}

// ---------- 留言 ----------
export interface MessageRow {
  id: number
  name: string
  phone: string // 列表脱敏
  content: string
  created_at: string
  status: 'pending' | 'done'
}

// ---------- 管理员管理 ----------
export interface UserManageRow {
  id: number
  username: string
  name: string
  role: 'super' | 'ops'
  is_active: boolean
  last_login_at: string | null
}

export interface UserPayload {
  username: string
  name: string
  password?: string
  role: 'super' | 'ops'
  is_active: boolean
}

// ---------- 上传 ----------
export interface UploadResult {
  url: string
}
