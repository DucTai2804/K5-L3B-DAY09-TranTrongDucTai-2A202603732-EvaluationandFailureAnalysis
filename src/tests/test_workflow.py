from lab8.db import connect
from lab8.durability import committed_audit_count
from lab8.policy import order_refunded_vnd
from lab8.shapes.workflow import run_claim


def test_workflow_full_quote_is_capped_once_and_retry_is_idempotent(public_db):
    first = run_claim("C-014", seed=11, store_path=str(public_db))
    replay = run_claim("C-014", seed=11, store_path=str(public_db))

    conn = connect(public_db)
    try:
        ledger_count = conn.execute(
            "SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = ?",
            ("C-014",),
        ).fetchone()["n"]
        committed_count = committed_audit_count(conn, "C-014")
        order_total = order_refunded_vnd(conn, "O-515")
    finally:
        conn.close()

    assert first.status == replay.status == "resolved"
    assert first.proposal_amount == replay.proposal_amount == 150000
    assert first.refund_effects[0]["amount_vnd"] == 120000
    assert replay.refund_effects[0]["amount_vnd"] == 120000
    assert (ledger_count, committed_count, order_total) == (1, 1, 150000)
