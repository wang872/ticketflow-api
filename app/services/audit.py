from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import AuditLog


def log_audit(
    db: Session,
    *,
    actor_id: int | None,
    action: str,
    ticket_id: int | None = None,
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_id=actor_id,
        ticket_id=ticket_id,
        action=action,
        extra=json.dumps(extra or {}, ensure_ascii=False),
        created_at=utcnow(),
    )
    db.add(entry)
    return entry


def parse_extra(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}
