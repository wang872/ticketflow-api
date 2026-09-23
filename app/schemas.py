from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Priority, Role, TicketStatus


class RegisterIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    role: Role
    created_at: datetime


class AgentCreateIn(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=6, max_length=128)


class TicketCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=10000)
    priority: Priority = Priority.P3


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body: str
    status: TicketStatus
    priority: Priority
    creator_id: int
    assignee_id: int | None
    sla_due_at: datetime
    sla_breached: bool
    created_at: datetime
    updated_at: datetime


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    is_internal: bool = False


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: int
    author_id: int
    body: str
    is_internal: bool
    created_at: datetime


class TicketListOut(BaseModel):
    items: list[TicketOut]
    total: int
    page: int
    page_size: int


class StatusUpdate(BaseModel):
    status: TicketStatus


class AssignIn(BaseModel):
    user_id: int


class AuditOut(BaseModel):
    id: int
    actor_id: int | None
    ticket_id: int | None
    action: str
    extra: dict
    created_at: datetime


class AuditListOut(BaseModel):
    items: list[AuditOut]
    total: int
    page: int
    page_size: int
