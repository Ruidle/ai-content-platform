"""
数据库连接与初始化
- 使用 SQLAlchemy 连接 PostgreSQL
- 启用 pgvector 扩展以支持向量存储与相似度检索
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

# 创建数据库引擎
# echo=False 关闭 SQL 日志，需要调试可改为 True
engine = create_engine(
    settings.SYNC_DATABASE_URL,
    echo=False,
    pool_pre_ping=True,  # 连接前检查是否有效，避免长时间空闲后断连
    pool_size=5,         # 连接池大小
    max_overflow=10,     # 允许超出连接池大小的连接数
)

# 会话工厂：每个请求通过 SessionLocal() 创建独立会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 模型基类
Base = declarative_base()


def init_db() -> None:
    """
    初始化数据库：
    1. 启用 pgvector 扩展（若数据库未安装会抛错，需先在 PostgreSQL 执行 CREATE EXTENSION vector）
    2. 创建所有表
    """
    from sqlalchemy import text

    with engine.connect() as conn:
        # 启用 pgvector 扩展（需要超级用户权限或扩展已预装）
        # 使用 try-except 避免扩展已存在时报错
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.commit()
        except Exception as e:
            print(f"[警告] 启用 pgvector 扩展失败：{e}")
            print("请确认 PostgreSQL 已安装 pgvector，并以有权限的账号执行。")
            conn.rollback()

    # 导入模型，确保 create_all 能感知到表定义
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def get_db():
    """
    FastAPI 依赖项：提供数据库会话，请求结束自动关闭。
    用法：db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
