"""The R2 ablation changes only swarm's trust in ticket delay text."""

import time

import pytest

from lab8.app import prepare_store
from lab8.db import connect
from lab8.metrics import check_trace
from lab8.shapes.swarm_reference import run_claim as run_swarm


def _run_variant(claim_id, *, seed, store_path):
    try:
        from bonus.swarm_ticket_ablation import run_claim
    except ModuleNotFoundError:
        pytest.fail("R2 ablation runner has not been implemented")
    return run_claim(claim_id, seed=seed, store_path=str(store_path))


def test_order_only_variant_avoids_t02_ticket_override(tmp_path):
    baseline_store = tmp_path / "baseline.sqlite"
    variant_store = tmp_path / "variant.sqlite"
    prepare_store(baseline_store)
    prepare_store(variant_store)

    baseline = run_swarm("C-002", seed=55, store_path=str(baseline_store))
    started_at = time.time()
    variant = _run_variant("C-002", seed=55, store_path=variant_store)
    conn = connect(variant_store)
    try:
        refund_count = conn.execute(
            "SELECT COUNT(*) AS n FROM refund_ledger WHERE claim_id = 'C-002'"
        ).fetchone()["n"]
    finally:
        conn.close()

    assert baseline.status == "resolved"
    assert variant.status == "denied"
    assert variant.proposal_amount == 0
    assert refund_count == 0
    assert variant.model_calls == baseline.model_calls
    assert variant.run_id == "R-swarm_order_only-C-002-s55"
    assert check_trace(variant.as_dict(), started_at=started_at)[0]


def test_order_only_variant_keeps_unaffected_claim_result(tmp_path):
    store = tmp_path / "unaffected.sqlite"
    prepare_store(store)
    variant = _run_variant("C-001", seed=11, store_path=store)
    assert variant.status == "resolved"
    assert variant.proposal_amount == 35000
