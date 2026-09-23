from __future__ import annotations

import logging
import threading
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.config import get_settings
from app.db import get_session_factory, utcnow
from app.errors import AppError
from app.models import Comment, Priority, Role, Ticket, TicketStatus, User
from app.schemas import (
    AssignIn,
    CommentCreate,
    CommentOut,
    TicketCreate,
    TicketListOut,
    TicketOut,
)
from app.services.audit import log_audit

logger = logging.getLogger("ticketflow.sla")

SLA_HOURS: dict[Priority, int] = {
    Priority.P1: 1,
    Priority.P2: 8,
    Priority.P3: 24,
}

TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.open: {TicketStatus.assigned, TicketStatus.cancelled},
    TicketStatus.assigned: {TicketStatus.in_progress, TicketStatus.cancelled},
    TicketStatus.in_progress: {TicketStatus.resolved, TicketStatus.cancelled},
    TicketStatus.resolved: {TicketStatus.closed, TicketStatus.in_progress},
    TicketStatus.closed: set(),
    TicketStatus.cancelled: set(),
}

CUSTOMER_CANCELLABLE = {TicketStatus.open, TicketStatus.assigned, TicketStatus.in_progress}


def _ticket_out(ticket: Ticket) -> TicketOut:
    return TicketOut.model_validate(ticket)


def _ticket_query():
    return select(Ticket).options(joinedload(Ticket.creator), joinedload(Ticket.assignee))


def get_ticket_for_user(db: Session, user: User, ticket_id: int) -> Ticket:
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise AppError(404, "not_found", "Ticket not found")
    if user.role == Role.customer and ticket.creator_id != user.id:
        raise AppError(404, "not_found", "Ticket not found")
    return ticket


def create_ticket(db: Session, user: User, payload: TicketCreate) -> TicketOut:
    if user.role != Role.customer:
        raise AppError(403, "forbidden", "Only customers can create tickets")
    now = utcnow()
    ticket = Ticket(
        title=payload.title.strip(),
        body=payload.body.strip(),
        status=TicketStatus.open,
        priority=payload.priority,
        creator_id=user.id,
        assignee_id=None,
        sla_due_at=now + timedelta(hours=SLA_HOURS[payload.priority]),
        sla_breached=False,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    log_audit(
        db,
        actor_id=user.id,
        action="ticket.created",
        ticket_id=ticket.id,
        extra={"status": ticket.status.value, "priority": ticket.priority.value},
    )
    db.flush()
    return _ticket_out(ticket)


def list_tickets(db: Session, user: User, page: int, page_size: int) -> TicketListOut:
    stmt = select(Ticket)
    count_stmt = select(func.count()).select_from(Ticket)
    if user.role == Role.customer:
        stmt = stmt.where(Ticket.creator_id == user.id)
        count_stmt = count_stmt.where(Ticket.creator_id == user.id)

    total = db.scalar(count_stmt) or 0
    items = db.scalars(
        stmt.order_by(Ticket.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return TicketListOut(
        items=[_ticket_out(t) for t in items],
        total=total,
        page=page,
        page_size=page_size,
    )


def get_ticket(db: Session, user: User, ticket_id: int) -> TicketOut:
    ticket = get_ticket_for_user(db, user, ticket_id)
    return _ticket_out(ticket)


def claim_ticket(db: Session, user: User, ticket_id: int) -> TicketOut:
    if user.role not in (Role.agent, Role.admin):
        raise AppError(403, "forbidden", "Only agents can claim tickets")
    ticket = get_ticket_for_user(db, user, ticket_id)
    if ticket.assignee_id is not None:
        raise AppError(409, "conflict", "Ticket already assigned")
    if ticket.status != TicketStatus.open:
        raise AppError(409, "conflict", "Only open tickets can be claimed")
    now = utcnow()
    old_status = ticket.status.value
    ticket.assignee_id = user.id
    ticket.status = TicketStatus.assigned
    ticket.updated_at = now
    log_audit(
        db,
        actor_id=user.id,
        action="ticket.claimed",
        ticket_id=ticket.id,
        extra={"assignee_id": user.id, "from_status": old_status, "to_status": ticket.status.value},
    )
    db.flush()
    return _ticket_out(ticket)


def assign_ticket(db: Session, user: User, ticket_id: int, payload: AssignIn) -> TicketOut:
    if user.role not in (Role.agent, Role.admin):
        raise AppError(403, "forbidden", "Only agents or admins can assign tickets")
    ticket = get_ticket_for_user(db, user, ticket_id)
    if ticket.status in (TicketStatus.closed, TicketStatus.cancelled):
        raise AppError(409, "conflict", "Cannot assign a closed or cancelled ticket")

    assignee = db.get(User, payload.user_id)
    if assignee is None or assignee.role not in (Role.agent, Role.admin):
        raise AppError(400, "bad_request", "Assignee must be an existing agent or admin")

    if user.role == Role.agent and payload.user_id != user.id:
        raise AppError(403, "forbidden", "Agents can only assign tickets to themselves")

    now = utcnow()
    old_assignee = ticket.assignee_id
    old_status = ticket.status.value
    ticket.assignee_id = assignee.id
    ticket.updated_at = now
    if ticket.status == TicketStatus.open:
        ticket.status = TicketStatus.assigned
    log_audit(
        db,
        actor_id=user.id,
        action="ticket.assigned",
        ticket_id=ticket.id,
        extra={
            "from_assignee_id": old_assignee,
            "to_assignee_id": assignee.id,
            "from_status": old_status,
            "to_status": ticket.status.value,
        },
    )
    db.flush()
    return _ticket_out(ticket)


def change_status(db: Session, user: User, ticket_id: int, target: TicketStatus) -> TicketOut:
    ticket = get_ticket_for_user(db, user, ticket_id)

    if user.role == Role.customer:
        if target != TicketStatus.cancelled:
            raise AppError(403, "forbidden", "Customers can only cancel their own tickets")
        if ticket.status not in CUSTOMER_CANCELLABLE:
            raise AppError(409, "conflict", "Ticket cannot be cancelled in its current state")
    else:
        if user.role == Role.agent and ticket.assignee_id != user.id:
            raise AppError(403, "forbidden", "Agent can only update assigned tickets")
        if ticket.status == TicketStatus.open and target == TicketStatus.assigned:
            raise AppError(409, "conflict", "Use claim or assign to move a ticket to assigned")
        allowed = TRANSITIONS[ticket.status]
        if target not in allowed:
            raise AppError(
                409,
                "conflict",
                f"Cannot transition from {ticket.status.value} to {target.value}",
            )

    now = utcnow()
    old_status = ticket.status.value
    ticket.status = target
    ticket.updated_at = now
    log_audit(
        db,
        actor_id=user.id,
        action="ticket.status_changed",
        ticket_id=ticket.id,
        extra={"from_status": old_status, "to_status": target.value},
    )
    db.flush()
    return _ticket_out(ticket)


def add_comment(db: Session, user: User, ticket_id: int, payload: CommentCreate) -> CommentOut:
    ticket = get_ticket_for_user(db, user, ticket_id)
    if payload.is_internal and user.role == Role.customer:
        raise AppError(403, "forbidden", "Customers cannot add internal comments")
    if ticket.status == TicketStatus.cancelled:
        raise AppError(409, "conflict", "Cannot comment on a cancelled ticket")
    comment = Comment(
        ticket_id=ticket.id,
        author_id=user.id,
        body=payload.body.strip(),
        is_internal=payload.is_internal,
        created_at=utcnow(),
    )
    db.add(comment)
    db.flush()
    log_audit(
        db,
        actor_id=user.id,
        action="comment.created",
        ticket_id=ticket.id,
        extra={"comment_id": comment.id, "is_internal": comment.is_internal},
    )
    db.flush()
    return CommentOut.model_validate(comment)


def list_comments(db: Session, user: User, ticket_id: int) -> list[CommentOut]:
    ticket = get_ticket_for_user(db, user, ticket_id)
    comments = db.scalars(
        select(Comment)
        .where(Comment.ticket_id == ticket.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
    ).all()
    if user.role == Role.customer:
        comments = [c for c in comments if not c.is_internal]
    return [CommentOut.model_validate(c) for c in comments]


def scan_overdue_tickets(db: Session) -> int:
    now = utcnow()
    tickets = db.scalars(
        select(Ticket).where(
            Ticket.sla_breached.is_(False),
            Ticket.sla_due_at <= now,
            Ticket.status.notin_([TicketStatus.closed, TicketStatus.cancelled]),
        )
    ).all()
    count = 0
    for ticket in tickets:
        ticket.sla_breached = True
        ticket.updated_at = now
        log_audit(
            db,
            actor_id=None,
            action="sla.breached",
            ticket_id=ticket.id,
            extra={"priority": ticket.priority.value, "sla_due_at": ticket.sla_due_at.isoformat()},
        )
        count += 1
    if count:
        db.commit()
        logger.info("Marked %s ticket(s) as SLA breached", count)
    return count


def start_sla_checker() -> threading.Event:
    stop = threading.Event()
    interval = max(5, get_settings().sla_check_interval_seconds)

    def _loop() -> None:
        while not stop.is_set():
            db = get_session_factory()()
            try:
                scan_overdue_tickets(db)
            except Exception:
                db.rollback()
                logger.exception("SLA scan failed")
            finally:
                db.close()
            stop.wait(interval)

    thread = threading.Thread(target=_loop, name="sla-checker", daemon=True)
    thread.start()
    logger.info("SLA checker started (interval=%ss)", interval)
    return stop
