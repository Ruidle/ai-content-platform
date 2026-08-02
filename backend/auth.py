"""
认证模块：密码哈希 + JWT 令牌 + FastAPI 鉴权依赖

技术要点（面试可讲）：
- 密码绝不明文存储，使用 bcrypt 哈希（自带盐值，抗彩虹表）
- JWT（JSON Web Token）实现无状态认证：服务端不存 session，
  令牌本身携带用户身份，适合前后端分离 & 多实例部署
- OAuth2PasswordBearer：FastAPI 标准流程，自动从
  Authorization: Bearer <token> 头提取令牌
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from config import settings
from database import get_db
from models import User

# 密码哈希上下文（bcrypt 算法，自带盐值）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 令牌提取器，tokenUrl 指向登录接口（供 OpenAPI 文档交互用）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与哈希是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    签发 JWT 令牌。
    - data 中放用户标识（如 {"sub": user_id}）
    - exp 过期时间由 ACCESS_TOKEN_EXPIRE_MINUTES 控制
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    FastAPI 鉴权依赖：解析令牌 → 查询用户 → 返回 User 对象。

    用法：在路由参数中写 current_user: User = Depends(get_current_user)
    未带令牌或令牌无效时返回 401。
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证，请重新登录",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
        user_id = int(user_id)
    except (JWTError, ValueError):
        raise credentials_exception

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise credentials_exception
    return user
