# 麦屿手作（Mai-Isle）前后端 API 接口契约文档

| 项目 | 内容 |
|------|------|
| 品牌名称 | 麦屿手作 Mai-Isle |
| 文档名称 | 前后端 API 接口契约文档 |
| 版本 | v1.0 |
| 创建日期 | 2026-08-27 |
| 文档状态 | 待评审 |
| 关联文档 | 蛋糕店官网PRD.md（v2.2） |
| 技术栈 | 前端 React（前台官网）/ 后端 FastAPI / 数据库 SQLite |

---

## 0. 一句话看懂这份文档

**前端（前台官网 + 后台管理）通过 HTTP 请求访问后端接口，后端返回 JSON 数据。**
这份文档就是"前后端之间的传菜口规格说明"——约定每道菜（接口）叫什么、传什么进、出什么。

```
┌─────────────┐   HTTP 请求 (JSON)   ┌──────────────┐   SQL    ┌─────────┐
│  前台官网 React │ ─────────────────▶ │   FastAPI 后端  │ ──────▶ │  SQLite  │
│  后台管理 React │ ◀───────────────── │               │ ◀────── │  数据库   │
└─────────────┘    HTTP 响应 (JSON)   └──────────────┘  结果集   └─────────┘
```

- **前端**（两个站点）只负责"看和点"，不碰数据库
- **后端**（FastAPI）负责一切数据存取与校验，是唯一的"数据仓库管理员"
- 前端和后端约定好 JSON 格式，前后端可并行开发、独立部署

---

## 1. 通用约定

### 1.1 接口地址（Base URL）

| 环境 | 前台 API | 后台 API |
|------|----------|----------|
| 本地开发 | `http://localhost:8000/api/v1` | 同左（后台接口加 `/admin` 前缀） |
| 生产（建议） | `https://api.mai-isle.com/api/v1` | 同左 |

> 说明：前后台两个站点**共用同一套后端 API**。区分"前台接口"（访客可访问）与"后台接口"（需登录）靠接口路径前缀与认证 Token。

### 1.2 认证方式（后台接口）

- 登录成功后，后端返回 `access_token`（JWT）
- 后续请求在 HTTP 头携带：`Authorization: Bearer <access_token>`
- Token 有效期：**30 分钟无操作自动失效**（PRD §6.3.1 F8-2）
- 连续 5 次密码错误，账号锁定 **15 分钟**（PRD §6.3.1）

### 1.3 统一响应格式

所有接口返回统一的 JSON 包裹：

```json
{
  "code": 0,
  "message": "success",
  "data": { }
}
```

- `code = 0` 表示成功；非 0 表示业务错误
- `message` 给前端直接展示的错误提示文案（中文）
- `data` 为业务数据（可以是对象 / 数组 / null）

### 1.4 错误码表

| code | 含义 | 前端处理 |
|------|------|----------|
| 0 | 成功 | 正常流程 |
| 40001 | 参数校验失败 | 在对应字段下方提示 `message` |
| 40002 | 验证码错误 | 提示"验证码错误，请重新输入"，刷新验证码 |
| 40100 | 未登录或 Token 过期 | 跳转后台登录页 |
| 40101 | 账号或密码错误 | 登录页提示 `message` |
| 40102 | 账号已停用 | 登录页提示"账号已停用" |
| 40103 | 账号已锁定 | 提示"请 15 分钟后再试" |
| 40300 | 权限不足 | 提示无权限，隐藏菜单 |
| 40400 | 资源不存在 | 前台跳 404 / 后台提示"记录不存在" |
| 40900 | 数据冲突（如产品重名） | 提示"名称已存在" |
| 50000 | 服务器内部错误 | 提示"操作失败，请稍后重试" |

### 1.5 分页约定

分页类接口统一返回：

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "items": [ ],
    "total": 28,
    "page": 1,
    "page_size": 12,
    "total_pages": 3
  }
}
```

请求参数统一：`page`（页码，默认 1）、`page_size`（每页条数，默认 12）。

---

## 2. 数据模型（核心表）

### 2.1 关系总览

```
分类 category 1 ──── * 蛋糕 cake
蛋糕 cake     1 ──── * 规格 spec（多规格价格）
蛋糕 cake     1 ──── * 订单项（订单快照：名称/规格/价格）
门店 store    1 ──── * 门店（独立表）
留言 message  （前台表单产生）
管理员 admin  （角色：超管 / 运营）
内容 content  （banner / 品牌故事 / 订购信息等 key-value）
```

### 2.2 蛋糕（cake）

| 字段 | 类型 | 必填 | 规则（PRD §6.3.3） |
|------|------|------|------|
| id | int | - | 主键，自增 |
| name | string | 是 | 2–50 字，唯一 |
| category_id | int | 是 | 外键，关联分类 |
| specs | array | 是 | 至少 1 个；每项：name(≤20字) + price(>0, 两位小数) |
| description | string | 否 | ≤2000 字 |
| image_url | string | 是 | jpg/png/webp，≤5MB |
| is_featured | bool | 否 | 默认 false（首页推荐） |
| is_active | bool | 否 | 默认 true（上架） |
| sort_order | int | 否 | 默认 0，越小越靠前 |
| created_at | datetime | - | 创建时间 |

### 2.3 订单（order）

| 字段 | 类型 | 必填 | 规则（PRD §6.3.4） |
|------|------|------|------|
| id | int | - | 主键 |
| order_no | string | - | 自动生成 `YYYYMMDD+序号`，如 `20260827001` |
| customer_name | string | 是 | 2–20 字 |
| customer_phone | string | 是 | 11 位手机号 |
| cake_snapshot | object | 是 | 订单快照：{name, spec_name, price}（改规格不影响历史订单） |
| quantity | int | 是 | ≥ 1 |
| amount | number | - | 自动计算 = 快照价格 × 数量，不可手改 |
| pickup_type | enum | 是 | `self`（到店自提）/ `delivery`（配送） |
| delivery_address | string | 条件 | 配送时必填，≤200 字 |
| custom_note | string | 否 | 定制需求，≤500 字 |
| remark | string | 否 | 备注，≤500 字 |
| status | enum | - | `pending / confirmed / completed / cancelled` |
| created_at | datetime | - | 下单时间 |

### 2.4 其他模型（简表）

| 模型 | 关键字段 |
|------|----------|
| category | id, name(唯一), sort_order |
| store | id, name(2-30), address(≤100), phone(≤20), hours(≤50), sort_order, is_active |
| message | id, name(2-20), phone(11), content(≤500), status(pending/done), created_at |
| admin | id, username(唯一), name, password_hash, role(super/ops), is_active, last_login_at |
| content | id, key(唯一), value(JSON/富文本), updated_at |

---

## 3. 前台接口（访客，无需登录）

### 3.1 蛋糕列表（分类筛选 + 分页 + 排序）

```
GET /api/cakes
```

**请求参数（Query）**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category_id | int | 否 | 不传=全部；传=按分类筛选 |
| page | int | 否 | 默认 1 |
| page_size | int | 否 | 默认 12（PRD F2-3） |
| sort | string | 否 | `recommend`(默认) / `price_asc` / `price_desc` / `newest` |

**响应 data**

```json
{
  "items": [
    {
      "id": 1,
      "name": "醇香红丝绒",
      "category": "红丝绒系列",
      "image_url": "/uploads/cakes/red_velvet.jpg",
      "price_from": 168.00,
      "is_featured": true
    }
  ],
  "total": 28,
  "page": 1,
  "page_size": 12,
  "total_pages": 3
}
```

> `price_from` = 该产品最低规格价格（前台卡片展示"¥168 起"用）
> 仅返回 `is_active = true` 的产品（PRD F2 规则）；排序：`sort_order` 升序 → `created_at` 倒序

**业务错误**：无（普通查询）

---

### 3.2 蛋糕详情

```
GET /api/cakes/{id}
```

**响应 data**

```json
{
  "id": 1,
  "name": "醇香红丝绒",
  "category": "红丝绒系列",
  "description": "比利时可可与马达加斯加香草的曼妙碰撞……",
  "image_url": "/uploads/cakes/red_velvet.jpg",
  "specs": [
    { "name": "6 寸", "price": 168.00 },
    { "name": "8 寸", "price": 228.00 },
    { "name": "10 寸", "price": 288.00 }
  ],
  "related": [
    { "id": 4, "name": "经典芝士蛋糕", "price_from": 178.00, "image_url": "/uploads/cakes/cheese.jpg" }
  ],
  "custom_tips": "支持尺寸/口味/图案/祝福语定制，建议提前 1 天电话预约"
}
```

- `related`：同分类下其他上架产品，最多 4 个（PRD F3-4）
- `custom_tips`：来自后台"内容管理"的定制说明文案
- 产品下架 → 返回 `40400`（PRD F3 规则）

---

### 3.3 分类列表

```
GET /api/categories
```

**响应 data**

```json
{
  "items": [
    { "id": 1, "name": "红丝绒系列", "count": 4 },
    { "id": 2, "name": "慕斯系列", "count": 5 }
  ]
}
```

> `count` = 该分类下"上架"产品数（左侧分类导航角标用）

---

### 3.4 门店列表

```
GET /api/stores
```

**响应 data**

```json
{
  "items": [
    {
      "id": 1,
      "name": "联洋店",
      "address": "上海市浦东新区迎春路 767 号",
      "phone": "021-58388761",
      "hours": "08:00-21:00"
    }
  ]
}
```

> 仅返回 `is_active = true`，按 `sort_order` 升序（PRD F5）

---

### 3.5 提交留言

```
POST /api/messages
Content-Type: application/json
```

**请求体（PRD §6.2.7 字段校验）**

```json
{
  "name": "林小姐",
  "phone": "13863210086",
  "content": "想预订一款 8 寸生日蛋糕，希望 9 月 1 日送到浦东",
  "captcha": "M8A2"
}
```

**校验规则**

| 字段 | 规则 | 失败提示 |
|------|------|----------|
| name | 2–20 字 | "姓名需为 2-20 个字符" |
| phone | 11 位手机号 | "请输入 11 位有效手机号" |
| content | 1–500 字 | "留言内容不能为空，且不超过 500 字" |
| captcha | 4 位，与图形验证码一致 | "验证码错误，请重新输入" |

**成功响应**

```json
{ "code": 0, "message": "success", "data": { "id": 23 } }
```

前端收到后提示：**"提交成功，我们会尽快与您联系"**（PRD §6.2.7）
留言默认状态 `pending`（未处理），进入后台留言管理（PRD F14）。

---

### 3.6 内容区块（Banner / 品牌故事 / 订购信息等）

```
GET /api/content/{key}
```

`key` 取值（对应 PRD §6.3.6 内容管理）：

| key | 内容 |
|-----|------|
| `banners` | 首页轮播图数组（1–3 张） |
| `brand_story` | 品牌故事（富文本 + 图片） |
| `brand_value` | 品牌理念（富文本） |
| `brand_chars` | 品牌特色卡片条目 |
| `brand_journey` | 品牌历程时间线条目 |
| `hardware` / `software` | 硬件保障 / 软件实力列表 |
| `order_info` | 订购专线 / 服务时间 / 配送说明 |
| `contact_info` | 门店地址 / 邮箱 |

**响应 data（以 banners 为例）**

```json
{
  "banners": [
    { "id": 1, "image_url": "/uploads/banners/b1.jpg", "slogan": "麦屿手作，手作每一份甜蜜", "sort_order": 1, "is_active": true }
  ],
  "order_info": {
    "hotline": "021-XXXXXXX",
    "hours": "08:00-18:00",
    "delivery_note": "11 点前订购当日送达 · 市内免费配送"
  }
}
```

> 区块内容为空 → 前台该区块整体隐藏（PRD §6.2.2 规则约束）

---

## 4. 后台接口（需登录，`Authorization: Bearer <token>`）

### 4.1 登录 / 退出 / 当前用户

```
POST /api/admin/login
```

**请求体**

```json
{ "username": "admin", "password": "admin123" }
```

**成功响应**

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIs...",
    "user": { "id": 1, "username": "admin", "name": "系统管理员", "role": "super" }
  }
}
```

**失败响应**

| 场景 | code | message |
|------|------|---------|
| 账号或密码错误 | 40101 | "账号或密码错误" |
| 账号已停用 | 40102 | "账号已停用" |
| 连续 5 次错误 | 40103 | "账号已锁定，请 15 分钟后再试" |

```
POST /api/admin/logout          → 登出（前端清除 token 即可）
GET  /api/admin/me              → 当前登录用户信息（含角色，用于权限判断）
```

---

### 4.2 仪表盘统计

```
GET /api/admin/dashboard/stats
```

**响应 data**

```json
{
  "cake_count": 28,
  "month_order_count": 136,
  "store_count": 5,
  "pending_message_count": 3,
  "recent_orders": [
    { "id": 1, "order_no": "20260826001", "customer_name": "张三",
      "cake_name": "醇香红丝绒", "amount": 228.00, "status": "pending" }
  ],
  "order_status_distribution": { "pending": 12, "confirmed": 38, "completed": 76, "cancelled": 10 }
}
```

> 统计为实时计算（PRD F9-2 规则约束：无缓存）

---

### 4.3 商品管理（PRD §6.3.3）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/cakes` | GET | 列表（搜索名称、按分类筛选、分页） |
| `/api/admin/cakes` | POST | 新增蛋糕 |
| `/api/admin/cakes/{id}` | PUT | 编辑蛋糕 |
| `/api/admin/cakes/{id}/status` | PATCH | 上下架切换（`{ "is_active": false }`） |
| `/api/admin/categories` | GET/POST | 分类列表 / 新增 |
| `/api/admin/categories/{id}` | PUT/DELETE | 编辑 / 删除分类（删除前需迁移产品） |

**POST /api/admin/cakes 请求体**

```json
{
  "name": "经典栗子蛋糕",
  "category_id": 9,
  "specs": [
    { "name": "6 寸", "price": 158.00 },
    { "name": "8 寸", "price": 198.00 }
  ],
  "description": "秋日限定款……",
  "image_url": "/uploads/cakes/chestnut.jpg",
  "is_featured": true,
  "is_active": true,
  "sort_order": 7
}
```

**校验失败示例**（产品重名 → 40900）

```json
{ "code": 40900, "message": "产品名称已存在，请更换", "data": null }
```

> 产品**不支持删除**，仅下架（PRD §6.3.3 边界与异常）

---

### 4.4 订单管理（PRD §6.3.4）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/orders` | GET | 列表（按状态筛选 / 按客户名或订单号搜索 / 分页） |
| `/api/admin/orders` | POST | 新增电话订单（手动录入） |
| `/api/admin/orders/{id}` | GET | 订单详情 |
| `/api/admin/orders/{id}` | PUT | 编辑订单（已完成后不可改产品与数量） |
| `/api/admin/orders/{id}/status` | PATCH | 状态流转 |

**POST /api/admin/orders 请求体**

```json
{
  "customer_name": "林小姐",
  "customer_phone": "13863210086",
  "cake_id": 3,
  "spec_name": "8 寸",
  "quantity": 1,
  "pickup_type": "delivery",
  "delivery_address": "上海市浦东新区迎春路 767 号",
  "custom_note": "顶部用草莓装饰，祝福语：生日快乐 · 小雅",
  "remark": "老客户"
}
```

**响应 data（金额自动计算）**

```json
{
  "id": 137,
  "order_no": "20260827001",
  "amount": 198.00,
  "status": "pending"
}
```

**订单状态机（PRD §6.3.4）**

```
待处理 pending ──确认──▶ 已确认 confirmed ──完成──▶ 已完成 completed
   │                        │
   └────取消────▶ 已取消     └────取消────▶ 已取消
        cancelled                cancelled

约束：已取消不可再变更；已完成不可再编辑产品与数量
```

`PATCH /api/admin/orders/{id}/status` 请求体：`{ "status": "confirmed" }`（仅允许合法流转）

---

### 4.5 门店管理（PRD §6.3.5）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/stores` | GET/POST | 列表 / 新增 |
| `/api/admin/stores/{id}` | PUT/DELETE | 编辑 / 删除 |
| `/api/admin/stores/{id}/status` | PATCH | 启用/停用（`{ "is_active": false }`） |

**POST 请求体**

```json
{
  "name": "联洋店",
  "address": "上海市浦东新区迎春路 767 号",
  "phone": "021-58388761",
  "hours": "08:00-21:00",
  "sort_order": 1,
  "is_active": true
}
```

---

### 4.6 内容管理（PRD §6.3.6）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/content` | GET | 全部内容列表（key / 更新时间 / 状态） |
| `/api/admin/content/{key}` | GET/PUT | 读取 / 编辑某一内容区块 |
| `/api/admin/content/banners` | POST | 新增 banner |
| `/api/admin/content/banners/{id}` | PUT/DELETE | 编辑 / 删除 banner |

> 保存后前台实时生效（PRD §6.3.6 规则约束）；长文案支持富文本（Markdown/HTML 片段）

---

### 4.7 留言管理（PRD §6.3.7）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/messages` | GET | 列表（按状态筛选 / 分页） |
| `/api/admin/messages/{id}` | GET | 留言详情 |
| `/api/admin/messages/{id}/status` | PATCH | 标记已处理/未处理（`{ "status": "done" }`） |
| `/api/admin/messages/{id}` | DELETE | 删除留言 |

> 留言由前台表单产生，后台**不可新增**（PRD §6.3.7）

---

### 4.8 管理员管理（PRD §6.3.8，仅超级管理员）

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/admin/users` | GET/POST | 列表 / 新增管理员 |
| `/api/admin/users/{id}` | PUT | 编辑（姓名/角色/状态） |
| `/api/admin/users/{id}/password` | PATCH | 重置密码 |
| `/api/admin/users/{id}/status` | PATCH | 启用/停用 |
| `/api/admin/users/{id}` | DELETE | 删除（超管账号不可删除） |

**权限矩阵（PRD §6.3.9）**

| 模块 | 超级管理员 | 运营管理员 |
|------|:----------:|:----------:|
| 仪表盘 / 商品 / 订单 / 门店 / 内容 / 留言 | ✓ | ✓ |
| 管理员管理 | ✓ | ✗（前端隐藏菜单 + 后端 40300 双重拦截） |

> 运营管理员请求管理员管理接口 → 返回 `40300 权限不足`（**后端必须校验，不能只靠前端隐藏菜单**）

---

## 5. 前端对接示例（fetch）

### 5.1 前台：加载蛋糕列表

```javascript
// 前台官网 React 组件中
const res = await fetch(`/api/cakes?category_id=2&page=1&page_size=12`, {
  headers: { 'Content-Type': 'application/json' }
});
const json = await res.json();

if (json.code === 0) {
  setCakes(json.data.items);       // 更新产品网格
  setTotalPages(json.data.total_pages); // 更新分页器
} else {
  showToast(json.message);         // 错误提示
}
```

### 5.2 前台：提交留言（带校验）

```javascript
const res = await fetch('/api/messages', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ name, phone, content, captcha })
});
const json = await res.json();

if (json.code === 0) {
  showToast('提交成功，我们会尽快与您联系');
  form.reset();
} else if (json.code === 40001 || json.code === 40002) {
  showFieldError(json.message);    // 字段下方红字提示
} else {
  showToast('提交失败，请重试');
}
```

### 5.3 后台：登录并携带 Token

```javascript
// 1. 登录
const res = await fetch('/api/admin/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password })
});
const json = await res.json();
if (json.code === 0) {
  localStorage.setItem('token', json.data.access_token); // 保存 token
  router.push('/dashboard');
} else {
  setLoginError(json.message);     // "账号或密码错误" 等
}

// 2. 后续请求统一带 token
fetch('/api/admin/cakes', {
  headers: { 'Authorization': 'Bearer ' + localStorage.getItem('token') }
}).then(r => {
  if (r.status === 401) { location.href = '/admin/login'; } // token 过期 → 回登录页
  return r.json();
});
```

---

## 6. 开发建议

1. **先定契约、再写两端**：前端按本文档 mock 数据开发界面，后端按本文档实现接口，最后联调
2. **接口文档可自动生成**：FastAPI 自带 `/docs`（Swagger UI），开发时可直接在浏览器调试每个接口
3. **前端 Mock 方案**：联调前可用 `Mock.js` / `json-server` 按本契约生成假数据
4. **契约变更流程**：任何接口变更需更新本文档并通知双方，避免"前端等后端 / 后端等前端"

---

## 7. 待确认事项

| # | 事项 | 建议 |
|---|------|------|
| 1 | 生产环境 Base URL 域名 | `api.mai-isle.com` |
| 2 | 验证码实现 | 后端生成图形验证码（如 Pillow），返回图片 + 会话标识 |
| 3 | 图片上传接口 | 建议单独 `POST /api/admin/upload`（返回 URL），供商品/内容复用 |
| 4 | 富文本字段 | 品牌故事等建议存 Markdown，前端渲染 |
| 5 | CORS 配置 | 前后端分离需后端配置允许 `mai-isle.com` / `admin.mai-isle.com` 跨域 |
