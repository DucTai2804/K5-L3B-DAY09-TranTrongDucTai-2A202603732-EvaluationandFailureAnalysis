"""Shape B — one ReAct agent. Student work.

Use `lab8.runtime.run_react` with max_steps=8. `decide` may pick a read tool.
It must not call `issue_refund`. After the loop, the host validates the quote
and is the only writer.

A decide() that trusts ticket text over the order row will fail hidden claims
where the customer overstates the delay or cites a superseded clause.

Per-order cap: an order may already have been refunded by an earlier claim.
The read tool `lookup_refund_history` shows how much. The host still enforces
the cap, so pass the full quote to `durability.issue_refund`, not a net amount.

Caps: stop at 8 steps. Count model calls in the Budget so cost stays comparable.

Trace contract v1 (docs/contracts.md): return a trace_path to a JSON file written in this run,
{"run_id": <same run_id>, "events": [...]}, on every return path including early
ones. `lab8.trace.Trace` does this; your own tracer is fine if it matches.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from lab8.db import connect
from lab8.durability import InjectedCrash, issue_refund
from lab8.mock_llm import complete
from lab8.runtime import run_react
from lab8.schemas import Budget, RunResult, make_run_id
from lab8.shapes.common import finish, safe_dump
from lab8.tools import get_claim_view, tool_cost


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    conn = connect(store_path)
    try:
        return _run(conn, claim_id, seed=seed, crash_at=crash_at)
    finally:
        conn.close()


def _run(conn: sqlite3.Connection, claim_id: str, *, seed: int, crash_at: str | None) -> RunResult:
    budget = Budget()
    run_id = make_run_id("single", claim_id, seed)
    trace = _Trace(run_id)

    budget.add_tool(tool_cost())
    claim = get_claim_view(conn, claim_id)
    if not claim.get("found"):
        trace.add("error", {"reason": "unknown_claim"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="unknown_claim",
        )

    ticket = claim.get("ticket", "")
    complete(budget, seed=seed, purpose="parse", prompt=ticket)

    if not claim.get("order_id"):
        complete(budget, seed=seed, purpose="draft", prompt="needs_info")
        trace.add("decision", {"status": "needs_info"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="needs_info",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="missing_order_id",
        )

    def decide(seen: dict[str, Any]) -> dict[str, Any]:
        last_tool = seen.get("last_tool")
        complete(budget, seed=seed, purpose="react", prompt=f"step:{last_tool}")

        if last_tool is None:
            return {
                "tool": "lookup_order",
                "args": {
                    "order_id": claim.get("order_id"),
                    "principal_id": claim.get("principal_id"),
                },
            }

        if last_tool == "lookup_order":
            order_view = seen.get("last_result", {})
            trace.add("tool_call", {"tool": "lookup_order", "result": safe_dump(order_view)})
            if not order_view.get("visible"):
                return {
                    "final": {
                        "status": "escalated",
                        "error_reason": order_view.get("reason"),
                    }
                }
            order = dict(order_view["order"])
            return {
                "tool": "compute_compensation",
                "args": {"order": order},
            }

        if last_tool == "compute_compensation":
            quote_payload = seen.get("last_result", {})
            trace.add("tool_call", {"tool": "compute_compensation", "result": safe_dump(quote_payload)})
            proposal = int(quote_payload.get("amount_vnd", 0))
            return {
                "final": {
                    "status": "ready",
                    "proposal": proposal,
                    "quote": quote_payload,
                    "reason": quote_payload.get("reason"),
                }
            }

        return {"final": {"status": "failed", "error_reason": f"unknown_last_tool_{last_tool}"}}

    react_result = run_react(
        conn,
        budget,
        observation={"claim": claim},
        decide=decide,
        max_steps=8,
        worker=False,
    )

    if react_result.get("stopped") == "step_cap":
        trace.add("error", {"reason": "step_cap"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason="step_cap",
        )

    final = react_result.get("final", {})
    status = final.get("status")

    if status == "escalated":
        complete(budget, seed=seed, purpose="draft", prompt="escalated")
        trace.add("decision", {"status": "escalated"})
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="escalated",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=final.get("error_reason"),
        )

    if status != "ready":
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="failed",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=final.get("error_reason", "unexpected_status"),
        )

    proposal = int(final["proposal"])
    quote_payload = final["quote"]
    trace.add("quote", quote_payload)
    complete(budget, seed=seed, purpose="draft", prompt=f"proposal={proposal}")

    if proposal <= 0:
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status="denied",
            proposal_amount=0,
            budget=budget,
            trace=trace,
            error_reason=quote_payload.get("reason"),
        )

    try:
        outcome = issue_refund(conn, claim_id, proposal, crash_at=crash_at)
    except InjectedCrash:
        trace.add("crash", {"at": crash_at})
        trace.write()
        raise

    if not outcome["ok"]:
        refund_status = "failed" if outcome["conflict"] else "denied"
        return finish(
            conn,
            shape="single",
            claim_id=claim_id,
            seed=seed,
            status=refund_status,
            proposal_amount=proposal,
            budget=budget,
            trace=trace,
            error_reason=outcome["reason"],
        )

    return finish(
        conn,
        shape="single",
        claim_id=claim_id,
        seed=seed,
        status="resolved",
        proposal_amount=proposal,
        budget=budget,
        trace=trace,
        error_reason=None,
    )


class _Trace:
    """Local alias so a crash can still flush. Wraps lab8.trace.Trace."""

    def __init__(self, run_id: str) -> None:
        from lab8.trace import Trace

        self._inner = Trace(run_id)

    def add(self, kind: str, payload: dict) -> None:
        self._inner.add(kind, payload)

    def write(self) -> str:
        return self._inner.write()

    @property
    def run_id(self) -> str:
        return self._inner.run_id
