"""
AI 内容生成平台 - 后端主入口

核心功能：
1. POST /api/auth/register - 用户注册
2. POST /api/auth/login    - 用户登录（返回 JWT）
3. GET  /api/auth/me       - 获取当前用户信息
4. POST /api/generate      - 调用 DeepSeek 流式生成（需登录）
5. GET  /api/history       - 获取当前用户的历史（需登录）
6. GET  /api/history/{id}  - 获取单条详情（需登录，校验归属）
7. PUT  /api/history/{id}  - 修改内容（需登录，校验归属）
8. DELETE /api/history/{id}- 删除记录（需登录，校验归属）
9. GET  /api/search        - RAG 语义搜索（需登录，仅搜自己的）
10. GET /api/health        - 健康检查

技术要点（面试可讲）：
- JWT 无状态认证：令牌本身携带用户身份，服务端不存 session
- 用户数据隔离：所有 CRUD 都按 user_id 过滤，防止越权
- SSE 流式推送 LLM 逐字输出
- pgvector 向量存储 + 余弦相似度语义检索
"""
import json
import logging
from typing import AsyncGenerator

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from config import settings
from database import init_db, get_db
from models import (
    Generation,
    User,
    create_generation,
    create_user,
    delete_generation,
    get_generation_by_id,
    get_generations_by_user,
    get_user_by_username,
    get_user_by_email,
    search_similar_generations,
    update_generation_content,
)
from schemas import (
    GenerationCreate,
    GenerationResponse,
    GenerationUpdate,
    HealthResponse,
    SearchResponse,
    SearchResultItem,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)

# ---------------- 日志配置 ----------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ai-content-platform")

# ---------------- FastAPI 应用 ----------------
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="基于 DeepSeek 的 AI 内容生成平台，支持用户认证、流式输出与向量存储。",
)

# CORS 配置：允许前端跨域访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: 生产环境替换为 ["https://你的前端域名"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------- 启动事件：初始化数据库 ----------------
@app.on_event("startup")
def on_startup() -> None:
    logger.info("应用启动，开始初始化数据库...")
    try:
        init_db()
        logger.info("数据库初始化完成")
    except Exception as e:
        logger.error(f"数据库初始化失败：{e}")
        logger.warning("应用将继续启动，但数据库相关功能可能不可用")


# ---------------- 健康检查 ----------------
@app.get("/api/health", response_model=HealthResponse, tags=["系统"])
def health_check() -> HealthResponse:
    """健康检查接口，用于部署平台探活。"""
    return HealthResponse(status="ok", version=settings.APP_VERSION)


# ============ 用户认证接口 ============
@app.post(
    "/api/auth/register",
    response_model=UserResponse,
    status_code=201,
    tags=["用户认证"],
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    """
    用户注册。
    - 用户名/邮箱唯一校验
    - 密码 bcrypt 哈希后存储，绝不存明文
    """
    if get_user_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="用户名已被注册")
    if get_user_by_email(db, payload.email):
        raise HTTPException(status_code=400, detail="邮箱已被注册")

    user = create_user(
        db,
        username=payload.username,
        email=payload.email,
        password_hash=hash_password(payload.password),
    )
    logger.info(f"新用户注册：{user.username} (id={user.id})")
    return user


@app.post("/api/auth/login", response_model=TokenResponse, tags=["用户认证"])
def login(payload: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录。
    - 校验用户名 + 密码
    - 签发 JWT 令牌，前端存 localStorage 后续请求带上
    """
    user = get_user_by_username(db, payload.username)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 签发令牌：sub（subject）放用户 ID
    access_token = create_access_token(data={"sub": str(user.id)})
    logger.info(f"用户登录：{user.username} (id={user.id})")
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
    )


@app.get("/api/auth/me", response_model=UserResponse, tags=["用户认证"])
def get_me(current_user: User = Depends(get_current_user)):
    """获取当前登录用户信息（凭令牌识别）。"""
    return current_user


# ---------------- 工具函数：生成 embedding ----------------
def generate_embedding(text: str) -> list[float] | None:
    """
    调用 OpenAI 兼容接口生成文本向量。
    - 未配置 OPENAI_API_KEY 时返回 None，跳过向量存储
    - bge-m3 输出 1024 维向量
    """
    if not settings.OPENAI_API_KEY:
        logger.info("未配置 OPENAI_API_KEY，跳过 embedding 生成")
        return None

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                f"{settings.OPENAI_BASE_URL}/embeddings",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.EMBEDDING_MODEL,
                    "input": text,
                },
            )
            resp.raise_for_status()
            return resp.json()["data"][0]["embedding"]
    except Exception as e:
        logger.warning(f"生成 embedding 失败：{e}")
        return None


# ---------------- 核心接口：流式生成（需登录） ----------------
@app.post("/api/generate", tags=["内容生成"])
async def generate_content(
    payload: GenerationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    调用 DeepSeek 流式生成内容，以 SSE 形式推送给前端。
    生成完成后，将内容 + 向量存入数据库（绑定当前用户）。
    """
    topic = payload.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="主题不能为空")

    if not settings.DEEPSEEK_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="服务端未配置 DEEPSEEK_API_KEY，请联系管理员",
        )

    logger.info(f"用户 {current_user.username} 开始生成，主题：{topic}")

    async def event_generator() -> AsyncGenerator[dict, None]:
        """SSE 事件生成器：逐块推送 DeepSeek 返回的内容。"""
        full_content = []
        has_error = False

        try:
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你是一个专业的内容创作助手。请根据用户给定的主题，"
                        "生成结构清晰、内容充实、语言流畅的文章。"
                        "可适当使用 Markdown 格式增强可读性。"
                    ),
                },
                {"role": "user", "content": f"请围绕以下主题生成一篇文章：{topic}"},
            ]

            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream(
                    "POST",
                    f"{settings.DEEPSEEK_BASE_URL}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {settings.DEEPSEEK_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": settings.DEEPSEEK_MODEL,
                        "messages": messages,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code != 200:
                        body = await response.aread()
                        err_msg = body.decode("utf-8", errors="ignore")
                        logger.error(f"DeepSeek API 错误：{response.status_code} {err_msg}")
                        yield {
                            "event": "error",
                            "data": json.dumps(
                                {"error": f"AI 服务返回错误：{response.status_code}"},
                                ensure_ascii=False,
                            ),
                        }
                        has_error = True
                        return

                    async for line in response.aiter_lines():
                        if await request.is_disconnected():
                            logger.info("客户端已断开连接，停止生成")
                            return

                        if not line or not line.startswith("data: "):
                            continue

                        data_str = line[len("data: "):]
                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            piece = delta.get("content", "")
                            if piece:
                                full_content.append(piece)
                                yield {
                                    "event": "message",
                                    "data": json.dumps(
                                        {"content": piece}, ensure_ascii=False
                                    ),
                                }
                        except json.JSONDecodeError:
                            continue

        except httpx.ConnectError:
            logger.error("无法连接 DeepSeek API")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"error": "无法连接 AI 服务，请检查网络"}, ensure_ascii=False
                ),
            }
            has_error = True
        except httpx.ReadTimeout:
            logger.error("DeepSeek API 响应超时")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"error": "AI 服务响应超时，请重试"}, ensure_ascii=False
                ),
            }
            has_error = True
        except Exception as e:
            logger.exception(f"生成过程发生未知错误：{e}")
            yield {
                "event": "error",
                "data": json.dumps(
                    {"error": f"生成失败：{str(e)}"}, ensure_ascii=False
                ),
            }
            has_error = True

        # 生成成功后存储到数据库（绑定当前用户）
        if not has_error and full_content:
            content = "".join(full_content)
            try:
                embedding = generate_embedding(content)
                record = create_generation(
                    db, current_user.id, topic, content, embedding
                )
                logger.info(f"内容已存储，记录 ID：{record.id}，用户：{current_user.username}")
                yield {
                    "event": "done",
                    "data": json.dumps(
                        {"id": record.id, "message": "生成完成"}, ensure_ascii=False
                    ),
                }
            except Exception as e:
                logger.exception(f"存储到数据库失败：{e}")
                yield {
                    "event": "error",
                    "data": json.dumps(
                        {"error": "内容已生成但存储失败"}, ensure_ascii=False
                    ),
                }

    return EventSourceResponse(event_generator())


# ---------------- 历史记录接口（需登录，仅自己的） ----------------
@app.get("/api/history", response_model=list[GenerationResponse], tags=["历史记录"])
def list_history(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的历史记录（按时间倒序，默认最多 100 条）。"""
    return get_generations_by_user(db, current_user.id, limit=limit)


@app.get(
    "/api/history/{generation_id}",
    response_model=GenerationResponse,
    tags=["历史记录"],
)
def get_history(
    generation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取单条历史记录详情（校验归属，防止越权）。"""
    record = get_generation_by_id(db, generation_id, user_id=current_user.id)
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")
    return record


@app.put(
    "/api/history/{generation_id}",
    response_model=GenerationResponse,
    tags=["历史记录"],
)
def update_history(
    generation_id: int,
    payload: GenerationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    修改一条记录的内容（校验归属）。
    修改后重新生成 embedding，保持语义检索同步。
    """
    record = update_generation_content(
        db, generation_id, current_user.id, payload.content
    )
    if not record:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")

    # 重新生成 embedding（异步处理会更好，这里同步简单处理）
    new_embedding = generate_embedding(payload.content)
    if new_embedding is not None:
        record.embedding = new_embedding
        db.commit()
        db.refresh(record)

    logger.info(f"用户 {current_user.username} 修改记录 {generation_id}")
    return record


@app.delete(
    "/api/history/{generation_id}",
    tags=["历史记录"],
)
def delete_history(
    generation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除一条记录（校验归属）。"""
    success = delete_generation(db, generation_id, current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="记录不存在或无权访问")
    logger.info(f"用户 {current_user.username} 删除记录 {generation_id}")
    return {"message": "删除成功", "id": generation_id}


# ---------------- RAG 语义搜索接口（需登录） ----------------
@app.get("/api/search", response_model=SearchResponse, tags=["语义搜索"])
def semantic_search(
    q: str,
    top_k: int = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    RAG 语义搜索：在当前用户的历史记录中检索语义最相关的内容。
    流程：查询文本 → embedding → pgvector 余弦相似度检索 → 返回带分数的结果。
    """
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="查询内容不能为空")

    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="服务端未配置 OPENAI_API_KEY，无法生成查询向量",
        )

    query_embedding = generate_embedding(query)
    if query_embedding is None:
        raise HTTPException(
            status_code=500,
            detail="查询向量生成失败，请检查 API Key 配置",
        )

    # 只在当前用户的数据里检索
    results = search_similar_generations(
        db, query_embedding, current_user.id, top_k=top_k
    )

    items = [
        SearchResultItem(
            id=record.id,
            topic=record.topic,
            content_preview=record.content[:200] + ("..." if len(record.content) > 200 else ""),
            created_at=record.created_at,
            similarity=round(float(similarity), 4),
        )
        for record, similarity in results
    ]

    logger.info(
        f"用户 {current_user.username} 语义搜索：query={query!r}，命中 {len(items)} 条"
    )

    return SearchResponse(query=query, total=len(items), results=items)


# ---------------- 前端静态文件服务（同域部署，无需 CORS） ----------------
import os

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """所有非 /api 路径返回前端页面（SPA 单页应用）"""
        index_path = os.path.join(FRONTEND_DIR, "index.html")
        return FileResponse(index_path)


# ---------------- 本地直接运行 ----------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
