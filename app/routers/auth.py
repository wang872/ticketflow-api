from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.deps import CurrentUser, DbSession
from app.errors import AppError
from app.models import Role, User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut.model_validate(user)


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, db: DbSession) -> UserOut:
    taken = db.scalar(select(User.id).where(User.username == payload.username))
    if taken is not None:
        raise AppError(409, "conflict", "Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=Role.customer,
    )
    db.add(user)
    db.flush()
    return _user_out(user)


@router.post("/login", response_model=TokenOut)
def login(payload: LoginIn, db: DbSession) -> TokenOut:
    user = db.scalar(select(User).where(User.username == payload.username))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise AppError(401, "unauthorized", "Invalid username or password")
    token = create_access_token(user.id, user.username, user.role.value)
    return TokenOut(access_token=token)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return _user_out(user)
