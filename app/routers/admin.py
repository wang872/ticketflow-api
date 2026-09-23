from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.deps import AdminUser, DbSession
from app.errors import AppError
from app.models import AuditLog, Role, User
from app.schemas import AgentCreateIn, AuditListOut, AuditOut, UserOut
from app.security import hash_password
from app.services.audit import parse_extra

router = APIRouter(prefix="/admin", tags=["admin"])


@router.post("/users", response_model=UserOut, status_code=201)
def create_agent(payload: AgentCreateIn, _admin: AdminUser, db: DbSession) -> UserOut:
    taken = db.scalar(select(User.id).where(User.username == payload.username))
    if taken is not None:
        raise AppError(409, "conflict", "Username already exists")
    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role=Role.agent,
    )
    db.add(user)
    db.flush()
    return UserOut.model_validate(user)


@router.get("/audit", response_model=AuditListOut)
def list_audit(
    _admin: AdminUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> AuditListOut:
    total = db.scalar(select(func.count()).select_from(AuditLog)) or 0
    rows = db.scalars(
        select(AuditLog)
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    items = [
        AuditOut(
            id=row.id,
            actor_id=row.actor_id,
            ticket_id=row.ticket_id,
            action=row.action,
            extra=parse_extra(row.extra),
            created_at=row.created_at,
        )
        for row in rows
    ]
    return AuditListOut(items=items, total=total, page=page, page_size=page_size)
