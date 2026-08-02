"""
应用配置模块
从环境变量读取所有配置，绝不硬编码敏感信息（API Key 等）。
"""
import os
from dotenv import load_dotenv

# 加载 .env 文件中的环境变量（本地开发用，生产环境由平台注入）
load_dotenv()


class Settings:
    """全局配置单例，集中管理所有可配置项。"""

    # ---- 数据库 ----
    # PostgreSQL 连接串，格式：postgresql://user:password@host:port/dbname
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql://user:password@localhost:5432/ai_content_db",
    )

    # 为了兼容 SQLAlchemy 同步引擎，统一使用 postgresql:// 前缀
    # （asyncpg 需要 postgresql+asyncpg://，但本项目用同步方式更易理解）
    @property
    def SYNC_DATABASE_URL(self) -> str:
        url = self.DATABASE_URL
        # 兼容用户填入 postgresql+asyncpg:// 的情况
        if url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql+asyncpg://", "postgresql://")
        return url

    # ---- DeepSeek（用于内容生成） ----
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL: str = os.getenv(
        "DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"
    )
    DEEPSEEK_MODEL: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # ---- Embedding 服务（用于生成向量，OpenAI 兼容接口） ----
    # DeepSeek 不提供 embedding 接口，这里用硅基流动 SiliconFlow（国内免费、直连）。
    # 也兼容 OpenAI 官方、智谱、通义等任何 OpenAI 兼容的 embedding 服务。
    # 若未配置 OPENAI_API_KEY，则跳过向量存储，仅保存文本（内容生成不受影响）。
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_BASE_URL: str = os.getenv(
        "OPENAI_BASE_URL", "https://api.siliconflow.cn/v1"
    )
    EMBEDDING_MODEL: str = os.getenv(
        "EMBEDDING_MODEL", "BAAI/bge-m3"
    )

    # ---- 应用 ----
    APP_NAME: str = "AI 内容生成平台"
    APP_VERSION: str = "1.0.0"
    # 向量维度：bge-m3 输出 1024 维
    # 若改用 OpenAI text-embedding-3-small，需同步改为 1536
    EMBEDDING_DIMENSION: int = int(os.getenv("EMBEDDING_DIMENSION", "1024"))

    # ---- JWT 认证 ----
    # SECRET_KEY 生产环境务必通过环境变量注入随机长字符串
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-change-me-in-production")
    ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))


# 全局配置实例
settings = Settings()
