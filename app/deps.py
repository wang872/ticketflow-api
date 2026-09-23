from __future__ import annotations

from typing import Annotated, Callable

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import AppError
from app.models import Role, User
from app.security import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if creds is None or creds.scheme.lower() != "bearer":
        raise AppError(401, "unauthorized", "Not authenticated")
    try:
        payload = decode_token(creds.credentials)
        user_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError, TypeError):
        raise AppError(401, "unauthorized", "Invalid or expired token") from None
    user = db.get(User, user_id)
    if user is None:
        raise AppError(401, "unauthorized", "User not found")
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    def _inner(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in roles:
            raise AppError(403, "forbidden", "Insufficient permissions")
        return user

    return _inner


CurrentUser = Annotated[User, Depends(get_current_user)]
AgentOrAdmin = Annotated[User, Depends(require_roles(Role.agent, Role.admin))]
AdminUser = Annotated[User, Depends(require_roles(Role.admin))]
DbSession = Annotated[Session, Depends(get_db)]
