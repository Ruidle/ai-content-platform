# AI 内容生成平台

> 基于 DeepSeek + FastAPI + PostgreSQL(pgvector) 的 AI 内容生成平台，支持 SSE 流式输出、JWT 用户认证与 RAG 语义检索。

**在线 Demo**: https://6a152bc7.ai-content-platform-6w4.pages.dev/

---

## 🏗 架构设计

```
┌─────────────────────────────────────────────────────────┐
│                     用户浏览器                          │
│  ┌─────────────────────────────────────────────────┐   │
│  │  前端 (Cloudflare Pages)                        │   │
│  │  原生 HTML/CSS/JS · SSE 流式接收 · JWT 管理     │   │
│  │  打字机效果 · 深浅主题 · 语音输入 · 增删改查     │   │
│  └──────────────────────┬──────────────────────────┘   │
│                         │ Authorization: Bearer <token> │
└─────────────────────────┼───────────────────────────────┘
                          │ HTTPS
┌─────────────────────────┼───────────────────────────────┐
│                         ▼                               │
│  ┌──────────────────────────────────────────────────┐   │
│  │  cloudflared Tunnel (内网穿透 → 公网)           │   │
│  └──────────────────────┬──────────────────────────┘   │
│                         │ 转发到 localhost:8000          │
│  ┌──────────────────────▼──────────────────────────┐   │
│  │  后端 (FastAPI)                                  │   │
│  │  ├─ POST /api/auth/register  注册               │   │
│  │  ├─ POST /api/auth/login     登录(JWT)          │   │
│  │  ├─ GET  /api/auth/me        当前用户           │   │
│  │  ├─ POST /api/generate       SSE 流式生成       │   │
│  │  ├─ GET  /api/history        我的历史记录       │   │
│  │  ├─ PUT  /api/history/{id}   修改内容           │   │
│  │  ├─ DELETE /api/history/{id} 删除记录           │   │
│  │  └─ GET  /api/search         RAG 语义搜索       │   │
│  │                                                  │   │
│  │  外部 API:                                       │   │
│  │  ├─ DeepSeek API → 流式内容生成                 │   │
│  │  └─ 硅基流动 bge-m3 → 向量嵌入                  │   │
│  └──────────────────────┬──────────────────────────┘   │
│                         │ SQLAlchemy ORM                │
│  ┌──────────────────────▼──────────────────────────┐   │
│  │  数据库 (Supabase PostgreSQL + pgvector)          │   │
│  │  ├─ users 表: 注册用户（bcrypt 密码哈希）        │   │
│  │  └─ generations 表: 内容 + 1024 维向量 + user_id │   │
│  └─────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 🛠 技术栈

| 层级 | 技术 | 选型理由 |
|------|------|---------|
| 后端框架 | **Python + FastAPI** | 异步高性能，自带 OpenAPI 文档，依赖注入优雅 |
| ORM | **SQLAlchemy 2.0** | 成熟稳定，支持异步，与 pgvector 无缝集成 |
| 数据库 | **PostgreSQL + pgvector** | 关系型 + 向量一体化，减少架构复杂度 |
| 向量模型 | **BAAI/bge-m3** (硅基流动) | 1024 维，支持中文，8192 tokens 窗口，国内直连 |
| 流式协议 | **SSE** (sse-starlette) | 比 WebSocket 简单，天然适配 HTTP，浏览器原生支持 |
| 大模型 | **DeepSeek** | 国产大模型，API 兼容 OpenAI，性价比高 |
| 认证 | **JWT + bcrypt** | 无状态认证，密码哈希存储，适合前后端分离 |
| 前端 | **原生 HTML/CSS/JS** | 零构建依赖，单文件即可部署 |
| 前端部署 | **Cloudflare Pages** | 全球 CDN，免费，国内可访问 |
| 后端部署 | **cloudflared Tunnel** | 内网穿透快速演示，生产可替换为 Render/Railway |
| 数据库托管 | **Supabase** | 托管 PostgreSQL + pgvector，免运维 |

---

## ✨ 核心功能

### 1. SSE 流式内容生成
- 调用 DeepSeek Chat API，使用 `stream: true` 参数
- 后端逐块解析 `data: ` 前缀，通过 SSE 推送给前端
- 前端用 `fetch` + `ReadableStream` 实现打字机效果
- 首字延迟 < 1s，支持中途断开

### 2. JWT 用户认证
- 注册时 bcrypt 哈希密码（自带盐值，抗彩虹表）
- 登录签发 JWT（payload 含用户 ID，HS256 签名）
- 后续请求通过 `Authorization: Bearer <token>` 鉴权
- FastAPI 依赖注入 `get_current_user` 自动验证

### 3. RAG 语义搜索
- 内容生成后自动调用 bge-m3 生成 1024 维 embedding
- 存入 pgvector 字段，支持余弦相似度检索
- 用户搜索时：查询文本 → embedding → 向量检索 → 返回 Top-K
- 只在当前用户的数据中检索，保护隐私

### 4. 用户数据隔离
- 所有 CRUD 接口按 `user_id` 过滤
- 查看/修改/删除前校验归属，防止越权
- 历史记录按时间倒序，支持分页

### 5. 前端体验
- 打字机流式输出（Markdown 渲染）
- 深浅主题一键切换（CSS 变量）
- 浏览器语音输入（Web Speech API，中文识别）
- 一键复制、编辑、删除

---

## 📁 项目结构

```
ai-content-platform/
├── backend/
│   ├── main.py          # FastAPI 入口 + 10 个 API 接口
│   ├── auth.py          # JWT + bcrypt 认证模块
│   ├── database.py      # 数据库连接与初始化
│   ├── models.py        # User/Generation ORM 模型 + CRUD
│   ├── schemas.py       # Pydantic 请求/响应校验
│   ├── config.py        # 环境变量配置
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── index.html       # 单页应用（含所有 HTML/CSS/JS）
├── render.yaml          # Render 部署配置（生产用）
├── vercel.json          # Vercel 部署配置
├── .gitignore
└── README.md
```

---

## 🚀 本地运行

### 前置准备

- Python 3.10+
- Supabase 账号（https://supabase.com）或本地 PostgreSQL + pgvector
- DeepSeek API Key（https://platform.deepseek.com）
- 硅基流动 API Key（https://cloud.siliconflow.cn，用于 embedding）

### 步骤

```bash
# 1. 进入后端目录
cd ai-content-platform/backend

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
copy .env.example .env         # Windows
# cp .env.example .env         # macOS/Linux
# 编辑 .env 填入 DATABASE_URL, DEEPSEEK_API_KEY, OPENAI_API_KEY, SECRET_KEY

# 5. 启动后端
uvicorn main:app --reload --port 8000

# 6. 启动前端（新终端）
python -m http.server 3000 --directory frontend
```

访问 http://localhost:3000 使用。

---

## ☁️ 部署架构

### 当前演示环境

| 组件 | 部署方式 | 地址 |
|------|---------|------|
| 前端 | Cloudflare Pages | https://6a152bc7.ai-content-platform-6w4.pages.dev/ |
| 后端 | cloudflared Tunnel → localhost:8000 | https://kitty-excerpt-because-opponents.trycloudflare.com |
| 数据库 | Supabase PostgreSQL | 托管服务 |

### 生产部署方案

| 组件 | 推荐平台 | 说明 |
|------|---------|------|
| 前端 | Cloudflare Pages / Vercel | 静态托管，全球 CDN |
| 后端 | Railway / Render | PaaS 托管，自动扩缩容 |
| 数据库 | Supabase / Neon | 托管 PostgreSQL + pgvector |

### 后端部署到 Railway（生产推荐）

1. 创建 Railway Project → 从 GitHub 导入仓库
2. **Root Directory**: `/backend`（关键！）
3. **Build Command**: `pip install -r requirements.txt`
4. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. 添加 11 个环境变量（参考 `.env.example`）
6. 部署成功后更新前端 `API_BASE`

---

## 📡 API 接口

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| POST | `/api/auth/register` | ❌ | 用户注册 |
| POST | `/api/auth/login` | ❌ | 用户登录，返回 JWT |
| GET | `/api/auth/me` | ✅ | 获取当前用户 |
| POST | `/api/generate` | ✅ | SSE 流式生成内容 |
| GET | `/api/history` | ✅ | 我的历史记录列表 |
| GET | `/api/history/{id}` | ✅ | 单条记录详情 |
| PUT | `/api/history/{id}` | ✅ | 修改内容 |
| DELETE | `/api/history/{id}` | ✅ | 删除记录 |
| GET | `/api/search?q=` | ✅ | RAG 语义搜索 |
| GET | `/api/health` | ❌ | 健康检查 |

### 核心接口示例

**POST /api/generate（SSE 流式）**
```json
// 请求
POST /api/generate
Authorization: Bearer <token>
Content-Type: application/json

{"topic": "大模型微调技术"}

// 响应（逐块推送）
data: {"content": "微调"}
data: {"content": "是大模型"}
data: {"content": "落地的关键技术..."}
event: done
data: {"id": 42, "message": "生成完成"}
```

**GET /api/search（RAG 语义搜索）**
```json
// 请求
GET /api/search?q=怎么训练自己的模型&top_k=5

// 响应
{
  "query": "怎么训练自己的模型",
  "total": 3,
  "results": [
    {
      "id": 15,
      "topic": "大模型微调技术",
      "content_preview": "微调是大模型落地的关键技术...",
      "similarity": 0.7823
    }
  ]
}
```

---

## 🔒 安全设计

- **密码哈希**：bcrypt 自带盐值，绝不存储明文
- **JWT 无状态认证**：服务端不存 session，支持水平扩展
- **用户数据隔离**：所有查询按 user_id 过滤，防止越权
- **环境变量**：所有密钥通过环境变量注入，`.env` 已加入 `.gitignore`
- **CORS**：生产环境需限制 `allow_origins` 为前端域名
- **输入校验**：Pydantic 严格校验请求参数，防止注入

---

## 🎯 面试高频考点

### 1. 为什么用 SSE 而不是 WebSocket？
> SSE 基于 HTTP，浏览器原生支持，无需握手升级。适合单向推送（LLM 流式输出），实现更简单。WebSocket 适合双向通信场景。

### 2. JWT vs Session 的区别？
> JWT 是无状态的，令牌本身携带用户信息，服务端不存 session。适合前后端分离和多实例部署。缺点是无法主动失效，需配合短过期时间。

### 3. pgvector 向量检索的原理？
> 将文本转为高维向量（如 1024 维），存入 PostgreSQL 的 Vector 字段。检索时计算余弦距离，ORDER BY 距离 + LIMIT K 取最相似的 K 条。数据量大时可建 IVFFlat/HNSW 索引加速。

### 4. embedding 为什么用 bge-m3 而不是 text-embedding-3-small？
> bge-m3 支持中文更好，窗口 8192 tokens（远超 OpenAI 的 512），且硅基流动国内直连无需翻墙，价格更低。

### 5. passlib + bcrypt 5.0 兼容性问题？
> bcrypt 5.0 改了 72 字节限制行为，与 passlib 1.7.4 不兼容。解决方案：固定 `bcrypt==4.2.1`。这是依赖版本管理的真实工程问题。

### 6. Supabase IPv6 问题？
> Supabase 新项目的直连地址只有 IPv6，国内网络不通。解决方案：改用 Connection Pooler（IPv4），在 Project Settings → Database 获取 pooler 地址。

---

## 📄 交付物清单

- [x] 完整后端代码（FastAPI + 认证 + CRUD + RAG）
- [x] 完整前端代码（单页应用 + 流式 + 语音 + 主题）
- [x] GitHub 仓库：https://github.com/Ruidle/ai-content-platform
- [x] 在线 Demo：https://6a152bc7.ai-content-platform-6w4.pages.dev/
- [x] 部署配置文件（render.yaml + vercel.json）
- [x] 完整 API 文档
- [x] 面试考点整理
