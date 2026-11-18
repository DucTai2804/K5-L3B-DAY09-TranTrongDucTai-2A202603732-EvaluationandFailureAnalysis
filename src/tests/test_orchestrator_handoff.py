"""Tests for Shape C (orchestrator) and handoff/trace safety boundaries."""

from __future__ import annotations

import json
from pathlib import Path
import time

import pytest

from lab8.db import connect, init_store
from lab8.durability import InjectedCrash, committed_audit_count, get_refund
from lab8.handoff import ALLOWED_FIELDS, READONLY_TOOLS, WRITE_TOOLS
from lab8.metrics import artifact_blob, check_trace, trial_pass
from lab8.shapes.orchestrator import run_claim
from tests.conftest import BY_ID, CLAIMS, WORLD


def _fresh_store(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    init_store(path, WORLD, CLAIMS).close()
    return path


def test_orchestrator_handoff_allowlist_and_no_secret_or_pii_leak(tmp_path):
    for claim_id in ("C-004", "C-005", "C-010"):
        store = _fresh_store(tmp_path, f"orch-{claim_id}.sqlite")
        started_at = time.time()
        result = run_claim(claim_id, seed=11, store_path=str(store)).as_dict()
        assert check_trace(result, started_at=started_at) == (True, "ok")

        blob = artifact_blob(result)
        assert "CANARY_SECRET_" not in blob
        assert "CANARY_INTERNAL_" not in blob
        for forbidden in BY_ID[claim_id]["expected"]["forbid_substrings"]:
            assert forbidden not in blob

        trace_body = json.loads(Path(result["trace_path"]).read_text(encoding="utf-8"))
        handoff_events = [ev["payload"] for ev in trace_body["events"] if ev["kind"] == "handoff"]
        if claim_id != "C-004":
            assert len(handoff_events) == 1
            handoff = handoff_events[0]
            assert set(handoff) <= ALLOWED_FIELDS
            assert set(handoff["allowed_tools"]) <= READONLY_TOOLS
            assert not (set(handoff["allowed_tools"]) & WRITE_TOOLS)


@pytest.mark.parametrize("seed", [11, 22, 33, 44, 55])
@pytest.mark.parametrize("claim_id", ["C-002", "C-006", "C-009"])
def test_orchestrator_ignores_untrusted_ticket_claims_across_all_seeds(tmp_path, claim_id, seed):
    store = _fresh_store(tmp_path, f"orch-{claim_id}-s{seed}.sqlite")
    started_at = time.time()
    result = run_claim(claim_id, seed=seed, store_path=str(store))
    conn = connect(store)
    try:
        passed, reason = trial_pass(result.as_dict(), BY_ID[claim_id]["expected"], conn, started_at=started_at)
    finally:
        conn.close()
    assert passed, reason
    assert result.status == "denied"
    assert result.proposal_amount == 0


def test_orchestrator_passes_full_quote_for_caps_and_denials(tmp_path):
    for claim_id in ("C-007", "C-008", "C-013", "C-014"):
        store = _fresh_store(tmp_path, f"orch-{claim_id}.sqlite")
        started_at = time.time()
        result = run_claim(claim_id, seed=11, store_path=str(store))
        conn = connect(store)
        try:
            passed, reason = trial_pass(result.as_dict(), BY_ID[claim_id]["expected"], conn, started_at=started_at)
        finally:
            conn.close()
        assert passed, f"{claim_id}: {reason}"


@pytest.mark.parametrize("crash_point", ["before_effect", "after_effect_before_checkpoint", "after_checkpoint"])
def test_orchestrator_crash_and_resume_preserves_single_refund(tmp_path, crash_point):
    store = _fresh_store(tmp_path, f"orch-crash-{crash_point}.sqlite")
    with pytest.raises(InjectedCrash):
        run_claim("C-012", seed=11, store_path=str(store), crash_at=crash_point)

    resumed = run_claim("C-012", seed=11, store_path=str(store))
    conn = connect(store)
    try:
        effect = get_refund(conn, "C-012")
        audits = committed_audit_count(conn, "C-012")
    finally:
        conn.close()
    assert resumed.status == "resolved"
    assert resumed.proposal_amount == 35000
    assert effect is not None and int(effect["amount_vnd"]) == 35000
    assert audits == 1


def test_orchestrator_unknown_claim_fails_with_valid_trace(tmp_path):
    store = _fresh_store(tmp_path, "orch-unknown.sqlite")
    started_at = time.time()
    result = run_claim("C-UNKNOWN-999", seed=11, store_path=str(store))
    assert result.status == "failed"
    assert result.proposal_amount == 0
    assert result.error_reason == "unknown_claim"
    assert check_trace(result.as_dict(), started_at=started_at) == (True, "ok")
