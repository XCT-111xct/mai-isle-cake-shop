# 麦屿手作（Mai-Isle）品牌官网

麦屿手作蛋糕店官网项目：前台官网 + 后台管理系统，前后台独立 React 应用，共用一套 FastAPI 后端。

## 技术栈

| 端 | 技术 |
|----|------|
| 前台官网（apps/web） | React 18 + TypeScript + Vite 5 + React Router v6（hash 路由）|
| 后台管理（apps/admin） | 同上（端口 5174）|
| 后端（server） | FastAPI + SQLAlchemy 2.x + SQLite + JWT + Pillow 验证码 |

## 目录结构

```
├── apps/
│   ├── web/          前台官网（端口 5173）
│   │   └── public/   品牌图与 logo（WebP）
│   └── admin/        后台管理（端口 5174）
├── server/           后端 FastAPI（端口 8000）
│   ├── app/          应用代码（routers/models/schemas/...）
│   ├── tests/        pytest 测试（105 用例）
│   ├── uploads/      上传图片（蛋糕/门店/banner，已全部转 WebP）
│   ├── .env.example  环境变量模板（复制为 .env 后填密钥）
│   ├── seed.py       种子数据（8 分类 / 超管 / 10 内容 key，幂等）
│   ├── seed_demo.py  演示数据（8 蛋糕 / 3 门店 / 2 banner，可选）
│   └── requirements.txt
├── database/         SQLite 数据库文件（含现成数据，可直接跑）
├── docs/internal/    过程文档（评审记录、汇报材料、Bug 反馈单）
├── images/           架构图与 ER 图（SVG + Mermaid 源码）
├── tools/            运维脚本（optimize_images.py 图片批量压缩）
└── *.md              产品与技术文档（PRD / UI-UX / 技术开发 / 数据库 / 接口契约 / 验收报告）
```

> 图片说明：原始素材为 1024px PNG，共 26MB；已用 `tools/optimize_images.py` 统一转为 WebP，
> 现为 1.4MB（省 94%），画质无明显差异。

## 本地开发（三端启动）

```bash
# 1. 后端（首次会自动建表 + 种子数据）
cd server
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt   # 首次
.venv/Scripts/python.exe run.py --seed        # 单进程 seed + uvicorn:8000

# 2. 前台官网
cd apps/web
npm install                                   # 首次
npm run dev                                   # http://localhost:5173

# 3. 后台管理
cd apps/admin
npm install                                   # 首次
npm run dev                                   # http://localhost:5174
```

**默认管理员**：`admin` / `admin123`

> ⚠️ **上线前必须改掉这个密码**。本仓库是公开的，默认账号密码写在本文档里，
> 任何人 clone 后都知道你的后台账号。登录后请立即在「系统设置 → 修改密码」中更换。

**演示数据（可选）**：`cd server && .venv/Scripts/python.exe seed_demo.py`，灌入 8 蛋糕 / 3 门店 / 2 banner 便于预览。

**运行测试**：`cd server && .venv/Scripts/python.exe -m pytest tests/`（105 用例）

## 生产部署

### 一、必配的环境变量（缺一不可）

生产环境启动前必须提供密钥，否则后端会**拒绝启动并打印缺失项**（这是保护机制，不是故障）。

```bash
# 生成一个随机密钥（每次结果都不同，不要照抄任何示例）
python -c "import secrets;print(secrets.token_urlsafe(48))"
```

把结果写进服务器上的 `server/.env`（该文件已被 .gitignore 忽略，不会进 git）：

```ini
MAI_ISLE_ENV=production
MAI_ISLE_SECRET=<上一步生成的随机串>
MAI_ISLE_DEBUG=0
MAI_ISLE_CORS=https://你的域名.com
```

配置项完整说明见 `server/.env.example`。

> **为什么必须这么做**：JWT 密钥一旦泄露，任何人都能伪造管理员登录凭证——不需要你的密码，也不需要经过登录页。代码里的默认值 `mai-isle-dev-secret-key-change-in-production` 已公开在本仓库，仅供本地调试。

### 二、构建与启动

```bash
# 前端构建（产物输出到 dist）
cd apps/web   && npm run build    # → apps/web/dist
cd apps/admin && npm run build    # → apps/admin/dist

# 后端生产启动（⚠️ 必须单 worker）
cd server && pip install -r requirements.txt
gunicorn -w 1 -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000 app.main:app
```

> **为什么必须单 worker**：① SQLite 单文件并发写会报 database is locked；② 图形验证码明文存进程内存缓存，多 worker 会跨进程失效（技术开发文档 §9.2）。

### Nginx 参考配置

```nginx
# 前台站点（mai-isle.com）
server {
    listen 443 ssl;
    server_name mai-isle.com;
    root /var/www/mai-isle-web/dist;
    location / { try_files $uri $uri/ /index.html; }        # SPA 路由回退
    location /api/ { proxy_pass http://127.0.0.1:8000; }    # 反向代理 API
    location /uploads/ { proxy_pass http://127.0.0.1:8000; }
}
# 后台站点（admin.mai-isle.com）配置同上，root 指向 admin dist
```

### 部署检查清单

- [ ] `MAI_ISLE_SECRET` 已设为 32 位以上随机串（**不设则后端拒绝启动**）
- [ ] `MAI_ISLE_DEBUG=0`（否则报错会返回详细堆栈，且验证码后门 `DEMO/8888` 会被打开）
- [ ] `MAI_ISLE_CORS` 已填正式域名（多个用英文逗号分隔，不带结尾斜杠）
- [ ] 后台默认密码 `admin123` 已修改
- [ ] `uploads/` 与 `database/` 目录放持久卷（避免重建丢失图片与数据）
- [ ] 定期备份 `database/mai_isle.db`（SQLite 单文件，直接拷贝）+ `uploads/`
- [ ] 全站强制 HTTPS
- [ ] 字体自托管（UI-UX §3.2：避免 Google Fonts 外链拖慢首屏）
- [ ] 前台站点不提供后台入口链接

> 已自动处理，无需手动操作：设 `MAI_ISLE_ENV=production` 后，接口文档页 `/docs`、`/redoc`、`/openapi.json` 会自动返回 404。

## 文档索引

**正式交付物（根目录）**

- PRD：`蛋糕店官网PRD.md`
- UI/UX 设计：`麦屿手作UI-UX设计文档.md`
- 技术开发文档（接口/数据库/部署）：`麦屿手作技术开发文档.md`
- API 契约：`API接口契约文档.md`
- 数据库设计：`麦屿手作数据库设计文档.md`
- 开发实施方案：`麦屿手作项目开发实施方案.md`
- 联调验收报告：`联调验收报告.md`
- 高保真原型：`前台官网原型.html`、`后台管理系统原型.html`

**过程文档（`docs/internal/`）**

- 已知问题规避（BUG-001/002）：`docs/internal/麦屿手作开发Bug反馈单.md`
- 文档评审 CheckList：`docs/internal/技术开发文档评审Checklist.md`
- 项目汇报材料：`docs/internal/麦屿手作项目汇报-演讲备注.md`
- 素材准备清单：`docs/internal/麦屿手作官网素材准备清单.md`
