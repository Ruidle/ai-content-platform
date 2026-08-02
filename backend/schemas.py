"""
Pydantic 数据模型（Schema）
用于请求体校验和响应体序列化，与 ORM 模型解耦。
"""
from datetime import datetime

from pydantic import BaseModel, Field


class GenerationCreate(BaseModel):
    """创建生成内容的请求体。"""

    topic: str = Field(
        ..., min_length=1, max_length=255, description="用户输入的主题",
        examples=["人工智能在教育领域的应用"],
    )


class GenerationResponse(BaseModel):
    """单条历史记录的响应结构。"""

    id: int
    topic: str
    content: str
    created_at: datetime

    # 允许从 ORM 对象读取属性（如 Generation.to_dict 之外的方式）
    model_config = {"from_attributes": True}


class HealthResponse(BaseModel):
    """健康检查响应。"""

    status: str
    version: str


class SearchResultItem(BaseModel):
    """单条语义搜索结果。"""

    id: int
    topic: str
    # 内容预览：搜索列表只返回前 200 字，点击后再加载全文，减少传输量
    content_preview: str
    created_at: datetime
    similarity: float = Field(..., description="相似度分数，0~1，越接近 1 越相关")

    model_config = {"from_attributes": True}


class SearchResponse(BaseModel):
    """语义搜索响应。"""

    query: str = Field(..., description="用户的查询语句")
    total: int = Field(..., description="返回结果数")
    results: list[SearchResultItem]


# ============ 用户认证相关 ============
class UserCreate(BaseModel):
    """注册请求体。"""

    username: str = Field(..., min_length=2, max_length=50, description="用户名")
    email: str = Field(..., description="邮箱")
    password: str = Field(..., min_length=6, max_length=128, description="密码（至少6位）")


class UserLogin(BaseModel):
    """登录请求体。"""

    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(BaseModel):
    """用户信息响应。"""

    id: int
    username: str
    email: str
    created_at: datetime
    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    """登录成功返回的令牌。"""

    access_token: str
    token_type: str = "bearer"
    user: UserResponse


class GenerationUpdate(BaseModel):
    """修改生成内容的请求体。"""

    content: str = Field(..., min_length=1, description="修改后的内容")
