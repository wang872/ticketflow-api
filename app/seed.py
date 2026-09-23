from __future__ import annotations

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Priority, Role, Ticket, TicketStatus, User
from app.security import hash_password
from app.services.audit import log_audit
from app.services.tickets import SLA_HOURS


def seed_data(db: Session) -> None:
    existing = db.scalar(select(User.id).limit(1))
    if existing is not None:
        return

    now = utcnow()
    admin = User(username="admin", password_hash=hash_password("admin123"), role=Role.admin, created_at=now)
    agent = User(username="agent1", password_hash=hash_password("agent123"), role=Role.agent, created_at=now)
    alice = User(username="alice", password_hash=hash_password("alice123"), role=Role.customer, created_at=now)
    db.add_all([admin, agent, alice])
    db.flush()

    ticket = Ticket(
        title="Cannot log in to the portal",
        body="Alice cannot sign in after the weekend password rotation.",
        status=TicketStatus.open,
        priority=Priority.P2,
        creator_id=alice.id,
        assignee_id=None,
        sla_due_at=now + timedelta(hours=SLA_HOURS[Priority.P2]),
        sla_breached=False,
        created_at=now,
        updated_at=now,
    )
    db.add(ticket)
    db.flush()
    log_audit(
        db,
        actor_id=alice.id,
        action="ticket.created",
        ticket_id=ticket.id,
        extra={"status": ticket.status.value, "priority": ticket.priority.value},
    )
    db.commit()
