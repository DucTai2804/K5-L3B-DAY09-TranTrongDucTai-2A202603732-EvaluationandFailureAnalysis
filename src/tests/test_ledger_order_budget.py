"""Regression checks for refund limits across claims on one order."""

import json

from lab8.db import connect
from lab8.durability import committed_audit_count, get_refund, issue_refund
from lab8.policy import order_refunded_vnd


def _add_approved_claim(conn, claim_id: str, approval_id: str, approved_vnd: int) -> None:
    conn.execute(
        """
        INSERT INTO claims (claim_id, principal_id, order_id, ticket, parent_secret,
                            raw_headers_json, approval_id)
        VALUES (?, 'P-100', 'O-515', 'verified damage', 'CANARY_SECRET_TEST', '{}', ?)
        """,
        (claim_id, approval_id),
    )
    conn.execute(
        """
        INSERT INTO approvals (approval_id, claim_id, approved_vnd, status, expires_at)
        VALUES (?, ?, ?, 'valid', '2027-12-31')
        """,
        (approval_id, claim_id, approved_vnd),
    )


def test_approval_and_order_caps_apply_across_successive_claims(public_db):
    """A low approval pays less; a later claim gets only the remaining entitlement."""
    conn = connect(public_db)
    try:
        _add_approved_claim(conn, "C-CAP1", "A-CAP1", 50000)
        _add_approved_claim(conn, "C-CAP2", "A-CAP2", 200000)
        conn.commit()

        first = issue_refund(conn, "C-CAP1", 150000)
        second = issue_refund(conn, "C-CAP2", 150000)
        repeat = issue_refund(conn, "C-CAP2", 150000)

        assert first["ok"] is True
        assert second["ok"] is True
        assert repeat["reason"] == "idempotent_replay"
        assert get_refund(conn, "C-CAP1")["amount_vnd"] == 50000
        assert get_refund(conn, "C-CAP2")["amount_vnd"] == 70000
        assert order_refunded_vnd(conn, "O-515") == 150000
        assert committed_audit_count(conn, "C-CAP1") == 1
        assert committed_audit_count(conn, "C-CAP2") == 1
    finally:
        conn.close()


def test_repeated_expired_approval_denial_never_writes_refund(public_db):
    """Retrying a denied claim keeps one denial audit and zero money effects."""
    conn = connect(public_db)
    try:
        first = issue_refund(conn, "C-007", 35000)
        second = issue_refund(conn, "C-007", 35000)
        denials = conn.execute(
            """
            SELECT details_json FROM audit_events
            WHERE claim_id = 'C-007' AND event_type = 'policy_denied'
            """
        ).fetchall()

        assert first["reason"] == second["reason"] == "approval_expired"
        assert get_refund(conn, "C-007") is None
        assert committed_audit_count(conn, "C-007") == 0
        assert len(denials) == 1
        assert json.loads(denials[0]["details_json"]) == {"reason": "approval_expired"}
    finally:
        conn.close()
