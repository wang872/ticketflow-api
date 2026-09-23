from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient


def _auth_headers(login, username: str, password: str) -> dict[str, str]:
    return login(username, password)


def _create_ticket(client: TestClient, headers: dict[str, str], title: str = "Printer offline") -> dict:
    response = client.post(
        "/tickets",
        json={"title": title, "body": "The printer in building B is offline.", "priority": "P2"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_register_and_login(client: TestClient) -> None:
    reg = client.post("/auth/register", json={"username": "bob", "password": "bob12345"})
    assert reg.status_code == 201
    assert reg.json()["role"] == "customer"

    login_resp = client.post("/auth/login", json={"username": "bob", "password": "bob12345"})
    assert login_resp.status_code == 200
    assert login_resp.json()["token_type"] == "bearer"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {login_resp.json()['access_token']}"})
    assert me.status_code == 200
    assert me.json()["username"] == "bob"


def test_customer_cannot_see_others_tickets(client: TestClient, login) -> None:
    alice = _auth_headers(login, "alice", "alice123")
    agent = _auth_headers(login, "agent1", "agent123")

    alice_ticket = _create_ticket(client, alice, "Alice only ticket")
    alice_id = alice_ticket["id"]

    other = client.get(f"/tickets/{alice_id}", headers=agent)
    assert other.status_code == 200
    assert other.json()["id"] == alice_id

    bob_reg = client.post("/auth/register", json={"username": "carol", "password": "carol12345"})
    assert bob_reg.status_code == 201
    carol = _auth_headers(login, "carol", "carol12345")
    hidden = client.get(f"/tickets/{alice_id}", headers=carol)
    assert hidden.status_code == 404


def test_agent_can_list_all_tickets(client: TestClient, login) -> None:
    alice = _auth_headers(login, "alice", "alice123")
    agent = _auth_headers(login, "agent1", "agent123")
    _create_ticket(client, alice, "List visibility ticket")

    agent_list = client.get("/tickets", headers=agent)
    assert agent_list.status_code == 200
    assert agent_list.json()["total"] >= 2

    me = client.get("/auth/me", headers=alice)
    alice_id = me.json()["id"]
    alice_list = client.get("/tickets", headers=alice)
    assert alice_list.status_code == 200
    for item in alice_list.json()["items"]:
        assert item["creator_id"] == alice_id


def test_claim_and_invalid_status_transition(client: TestClient, login) -> None:
    alice = _auth_headers(login, "alice", "alice123")
    agent = _auth_headers(login, "agent1", "agent123")
    ticket = _create_ticket(client, alice)
    ticket_id = ticket["id"]

    claimed = client.post(f"/tickets/{ticket_id}/claim", headers=agent)
    assert claimed.status_code == 200
    assert claimed.json()["status"] == "assigned"
    assert claimed.json()["assignee_id"] is not None

    jumped = client.post(f"/tickets/{ticket_id}/status", json={"status": "closed"}, headers=agent)
    assert jumped.status_code == 409
    assert jumped.json()["code"] == "conflict"


def test_internal_comment_hidden_from_customer(client: TestClient, login) -> None:
    alice = _auth_headers(login, "alice", "alice123")
    agent = _auth_headers(login, "agent1", "agent123")
    ticket_id = _create_ticket(client, alice)["id"]
    assert client.post(f"/tickets/{ticket_id}/claim", headers=agent).status_code == 200

    public = client.post(
        f"/tickets/{ticket_id}/comments",
        json={"body": "I rebooted the printer.", "is_internal": False},
        headers=alice,
    )
    assert public.status_code == 201

    internal = client.post(
        f"/tickets/{ticket_id}/comments",
        json={"body": "Firmware bug, order replacement.", "is_internal": True},
        headers=agent,
    )
    assert internal.status_code == 201

    forbidden = client.post(
        f"/tickets/{ticket_id}/comments",
        json={"body": "secret", "is_internal": True},
        headers=alice,
    )
    assert forbidden.status_code == 403

    customer_comments = client.get(f"/tickets/{ticket_id}/comments", headers=alice)
    assert customer_comments.status_code == 200
    bodies = [c["body"] for c in customer_comments.json()]
    assert "I rebooted the printer." in bodies
    assert "Firmware bug, order replacement." not in bodies

    agent_comments = client.get(f"/tickets/{ticket_id}/comments", headers=agent)
    agent_bodies = [c["body"] for c in agent_comments.json()]
    assert "Firmware bug, order replacement." in agent_bodies


def test_admin_audit_readable(client: TestClient, login) -> None:
    alice = _auth_headers(login, "alice", "alice123")
    agent = _auth_headers(login, "agent1", "agent123")
    admin = _auth_headers(login, "admin", "admin123")

    ticket_id = _create_ticket(client, alice)["id"]
    assert client.post(f"/tickets/{ticket_id}/claim", headers=agent).status_code == 200

    denied = client.get("/admin/audit", headers=agent)
    assert denied.status_code == 403

    audit = client.get("/admin/audit", headers=admin)
    assert audit.status_code == 200
    payload = audit.json()
    assert payload["total"] >= 1
    actions = {item["action"] for item in payload["items"]}
    assert "ticket.created" in actions or "ticket.claimed" in actions


def test_sla_scanner_marks_overdue(client: TestClient, login) -> None:
    from sqlalchemy import select

    from app.db import get_session_factory, utcnow
    from app.models import Ticket
    from app.services.tickets import scan_overdue_tickets

    alice = _auth_headers(login, "alice", "alice123")
    ticket_id = _create_ticket(client, alice)["id"]

    db = get_session_factory()()
    try:
        ticket = db.get(Ticket, ticket_id)
        assert ticket is not None
        ticket.sla_due_at = utcnow() - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    db = get_session_factory()()
    try:
        marked = scan_overdue_tickets(db)
    finally:
        db.close()
    assert marked == 1

    viewed = client.get(f"/tickets/{ticket_id}", headers=alice)
    assert viewed.status_code == 200
    assert viewed.json()["sla_breached"] is True
