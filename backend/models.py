"""
ORM 数据模型
- User 表：注册用户（用户名、邮箱、密码哈希）
- Generation 表：存储用户生成的主题、内容及其向量表示，绑定 user_id
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Session

from config import settings
from database import Base
from pgvector.sqlalchemy import Vector

# 向量维度，从配置读取（硅基流动 bge-m3 为 1024 维）
EMBEDDING_DIM = settings.EMBEDDING_DIMENSION


class User(Base):
    """
    用户表
    - password_hash 存 bcrypt 哈希，绝不存明文
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True, comment="用户名")
    email = Column(String(255), unique=True, nullable=False, index=True, comment="邮箱")
    password_hash = Column(String(255), nullable=False, comment="bcrypt 密码哈希")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, comment="注册时间")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Generation(Base):
    """
    AI 生成内容记录表
    - user_id 外键关联 User，实现「每人只看自己的内容」
    - embedding 字段使用 pgvector 的 Vector 类型，支持语义相似度搜索
    """

    __tablename__ = "generations"

    id = Column(Integer, primary_key=True, index=True)
    topic = Column(String(255), nullable=False, comment="用户输入的主题")
    content = Column(Text, nullable=False, comment="AI 生成的内容")
    # 向量字段，nullable=True：未配置 Key 时可跳过
    embedding = Column(Vector(EMBEDDING_DIM), nullable=True, comment="内容向量")
    # 归属用户，nullable=True 兼容旧的匿名数据
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True, comment="归属用户ID")
    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="创建时间",
    )

    def __repr__(self) -> str:
        return f"<Generation id={self.id} topic={self.topic!r}>"

    def to_dict(self) -> dict:
        """转换为字典（embedding 不可序列化，需排除）。"""
        return {
            "id": self.id,
            "topic": self.topic,
            "content": self.content,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ============ 用户 CRUD ============
def get_user_by_username(db: Session, username: str) -> User | None:
    """按用户名查询用户（注册/登录时用）。"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> User | None:
    """按邮箱查询用户（注册时查重）。"""
    return db.query(User).filter(User.email == email).first()


def create_user(db: Session, username: str, email: str, password_hash: str) -> User:
    """创建新用户。"""
    user = User(username=username, email=email, password_hash=password_hash)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ============ Generation CRUD（带 user_id 隔离） ============
def create_generation(
    db: Session,
    user_id: int,
    topic: str,
    content: str,
    embedding: list[float] | None = None,
) -> Generation:
    """插入一条生成记录（绑定当前用户）。"""
    record = Generation(topic=topic, content=content, embedding=embedding, user_id=user_id)
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_generations_by_user(db: Session, user_id: int, limit: int = 100) -> list[Generation]:
    """获取指定用户的历史记录（按时间倒序）。"""
    return (
        db.query(Generation)
        .filter(Generation.user_id == user_id)
        .order_by(Generation.created_at.desc())
        .limit(limit)
        .all()
    )


def get_generation_by_id(
    db: Session, generation_id: int, user_id: int | None = None
) -> Generation | None:
    """
    根据 ID 获取单条记录。
    - 传 user_id 时，校验归属（防止越权访问他人内容）
    """
    query = db.query(Generation).filter(Generation.id == generation_id)
    if user_id is not None:
        query = query.filter(Generation.user_id == user_id)
    return query.first()


def delete_generation(db: Session, generation_id: int, user_id: int) -> bool:
    """
    删除一条记录（需校验归属）。
    返回是否删除成功。
    """
    record = get_generation_by_id(db, generation_id, user_id=user_id)
    if record is None:
        return False
    db.delete(record)
    db.commit()
    return True


def update_generation_content(
    db: Session, generation_id: int, user_id: int, content: str
) -> Generation | None:
    """
    修改一条记录的内容（需校验归属）。
    修改后重新生成 embedding，保持语义检索同步。
    """
    record = get_generation_by_id(db, generation_id, user_id=user_id)
    if record is None:
        return None
    record.content = content
    db.commit()
    db.refresh(record)
    return record


def search_similar_generations(
    db: Session,
    query_embedding: list[float],
    user_id: int,
    top_k: int = 5,
) -> list[tuple[Generation, float]]:
    """
    RAG 语义检索：基于向量余弦相似度搜索当前用户最相关的历史记录。

    原理（面试可讲）：
    - pgvector 提供 <=> 操作符计算余弦距离（范围 0~2，0 表示方向完全一致）
    - 相似度 = 1 - 余弦距离，范围 -1~1，越接近 1 越相似
    - 通过 ORDER BY 距离 + LIMIT top_k 取最相似的 N 条
    - PostgreSQL 会利用 ivfflat/hnsw 索引加速（数据量大时效果显著）

    返回：[(Generation 记录, 相似度分数), ...] 按相似度降序
    """
    results = (
        db.query(
            Generation,
            (1 - Generation.embedding.cosine_distance(query_embedding)).label(
                "similarity"
            ),
        )
        .filter(Generation.embedding.isnot(None))  # 排除没向量的记录
        .filter(Generation.user_id == user_id)  # 只检索当前用户的
        .order_by(Generation.embedding.cosine_distance(query_embedding))
        .limit(top_k)
        .all()
    )
    return results
