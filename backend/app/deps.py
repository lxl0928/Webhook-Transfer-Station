import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_db
from app.models import User

bearer = HTTPBearer(auto_error=False)


async def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(401, "请先登录", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(
            credentials.credentials,
            get_settings().jwt_secret,
            algorithms=["HS256"],
            issuer="webhook-station",
            options={"require": ["exp", "sub", "ver", "iat"]},
        )
        user = await db.get(User, claims["sub"])
        if user is None or claims["ver"] != user.token_version:
            raise ValueError
        return user
    except (jwt.PyJWTError, ValueError, TypeError):
        raise HTTPException(401, "登录已失效", headers={"WWW-Authenticate": "Bearer"}) from None
