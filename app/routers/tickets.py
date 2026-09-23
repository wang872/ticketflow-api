from __future__ import annotations

from fastapi import APIRouter, Query

from app.deps import CurrentUser, DbSession
from app.schemas import (
    AssignIn,
    CommentCreate,
    CommentOut,
    StatusUpdate,
    TicketCreate,
    TicketListOut,
    TicketOut,
)
from app.services import tickets as ticket_service

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", response_model=TicketOut, status_code=201)
def create_ticket(payload: TicketCreate, user: CurrentUser, db: DbSession) -> TicketOut:
    return ticket_service.create_ticket(db, user, payload)


@router.get("", response_model=TicketListOut)
def list_tickets(
    user: CurrentUser,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> TicketListOut:
    return ticket_service.list_tickets(db, user, page, page_size)


@router.get("/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: int, user: CurrentUser, db: DbSession) -> TicketOut:
    return ticket_service.get_ticket(db, user, ticket_id)


@router.post("/{ticket_id}/claim", response_model=TicketOut)
def claim_ticket(ticket_id: int, user: CurrentUser, db: DbSession) -> TicketOut:
    return ticket_service.claim_ticket(db, user, ticket_id)


@router.post("/{ticket_id}/assign", response_model=TicketOut)
def assign_ticket(
    ticket_id: int,
    payload: AssignIn,
    user: CurrentUser,
    db: DbSession,
) -> TicketOut:
    return ticket_service.assign_ticket(db, user, ticket_id, payload)


@router.post("/{ticket_id}/status", response_model=TicketOut)
def change_status(
    ticket_id: int,
    payload: StatusUpdate,
    user: CurrentUser,
    db: DbSession,
) -> TicketOut:
    return ticket_service.change_status(db, user, ticket_id, payload.status)


@router.post("/{ticket_id}/comments", response_model=CommentOut, status_code=201)
def add_comment(
    ticket_id: int,
    payload: CommentCreate,
    user: CurrentUser,
    db: DbSession,
) -> CommentOut:
    return ticket_service.add_comment(db, user, ticket_id, payload)


@router.get("/{ticket_id}/comments", response_model=list[CommentOut])
def list_comments(ticket_id: int, user: CurrentUser, db: DbSession) -> list[CommentOut]:
    return ticket_service.list_comments(db, user, ticket_id)
