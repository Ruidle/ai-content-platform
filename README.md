# AI 内容生成平台

基于 DeepSeek + FastAPI + PostgreSQL(pgvector) 的 AI 内容生成平台，支持 SSE 流式输出与向量存储。

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端框架 | Python + FastAPI |
| 数据库 | PostgreSQL + pgvector |
| 流式协议 | SSE (Server-Sent Events) |
| 大模型 | DeepSeek (内容生成) + OpenAI (向量生成) |
| 前端 | 原生 HTML + CSS + JavaScript (单页应用) |
| 前端部署 | Vercel |
| 后端部署 | Render |

## 项目结构

```
ai-content-platform/
├── backend/
│   ├── main.py          # FastAPI 应用入口 + SSE 流式接口
│   ├── database.py      # 数据库连接与初始化
│   ├── models.py        # ORM 模型 (Generation 表 + pgvector)
│   ├── schemas.py       # Pydantic 请求/响应模型
│   ├── config.py        # 环境变量配置
│   ├── requirements.txt # Python 依赖
│   └── .env.example     # 环境变量示例
├── frontend/
│   └── index.html       # 单页前端应用
├── vercel.json          # Vercel 部署配置
├── render.yaml          # Render 部署配置
├── .gitignore
└── README.md
```

## 本地运行

### 前置准备

1. **Python 3.10+**
2. **PostgreSQL 数据库**，并安装 pgvector 扩展：
   ```sql
   CREATE EXTENSION vector;
   ```
3. **DeepSeek API Key**：前往 https://platform.deepseek.com/ 注册获取

### 步骤

1. **克隆项目并进入目录**
   ```bash
   cd ai-content-platform/backend
   ```

2. **创建虚拟环境并安装依赖**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS/Linux
   source venv/bin/activate

   pip install -r requirements.txt
   ```

3. **配置环境变量**
   ```bash
   cp .env.example .env
   ```
   编辑 `.env`，填入你的 `DATABASE_URL` 和 `DEEPSEEK_API_KEY`。

4. **初始化数据库**
   ```sql
   -- 在 PostgreSQL 中创建数据库
   CREATE DATABASE ai_content_db;
   CREATE EXTENSION vector;
   ```

5. **启动后端服务**
   ```bash
   uvicorn main:app --reload --port 8000
   ```
   访问 http://localhost:8000/docs 查看 API 文档。

6. **启动前端**
   直接用浏览器打开 `frontend/index.html`，或使用任意静态服务器：
   ```bash
   python -m http.server 3000 --directory frontend
   ```
   访问 http://localhost:3000

## 部署

### 前端部署到 Vercel

1. 将项目推送到 GitHub
2. 在 Vercel 导入仓库，使用默认配置（已含 `vercel.json`）
3. 部署完成即可访问

### 后端部署到 Render

1. 在 Render 创建新 Web Service，连接 GitHub 仓库
2. 使用 `render.yaml` 中的配置（或手动填写）
3. 在环境变量中配置：
   - `DATABASE_URL`：使用 Render 提供的 PostgreSQL 连接串
   - `DEEPSEEK_API_KEY`：你的 DeepSeek Key
4. 部署完成后，更新前端 `index.html` 中的 `API_BASE` 为后端地址

> 提示：Render 自带 PostgreSQL 服务，创建后在数据库设置中执行 `CREATE EXTENSION vector;` 启用向量扩展。

## API 接口文档

### 1. 生成内容（流式）

```
POST /api/generate
Content-Type: application/json

请求体：
{
  "topic": "人工智能在教育领域的应用"
}

响应（SSE 流式）：
data: {"content": "片段1"}
data: {"content": "片段2"}
event: done
data: {"id": 1, "message": "生成完成"}
```

### 2. 获取历史记录列表

```
GET /api/history

响应：
[
  {
    "id": 1,
    "topic": "人工智能在教育领域的应用",
    "content": "...",
    "created_at": "2026-01-01T12:00:00"
  }
]
```

### 3. 获取单条历史详情

```
GET /api/history/{id}

响应：
{
  "id": 1,
  "topic": "人工智能在教育领域的应用",
  "content": "...",
  "created_at": "2026-01-01T12:00:00"
}
```

### 4. 健康检查

```
GET /api/health

响应：
{ "status": "ok", "version": "1.0.0" }
```

## 安全说明

- 所有 API Key 通过环境变量读取，绝不硬编码
- `.env` 已在 `.gitignore` 中排除
- 生产环境需将 CORS 的 `allow_origins` 限制为前端域名
