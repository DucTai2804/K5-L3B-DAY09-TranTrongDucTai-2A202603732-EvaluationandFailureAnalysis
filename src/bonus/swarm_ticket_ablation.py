"""R2 ablation: do not let ticket text replace the order's delay_days.

The reference swarm is unchanged. Benchmark trials run sequentially, so the
temporary patch is restored before the next trial begins.
"""

from __future__ import annotations

from unittest.mock import patch

from lab8.schemas import RunResult, make_run_id
from lab8.shapes import swarm_reference

SHAPE = "swarm_order_only"


def run_claim(
    claim_id: str,
    *,
    seed: int,
    store_path: str,
    crash_at: str | None = None,
) -> RunResult:
    def variant_run_id(_shape: str, current_claim_id: str, current_seed: int) -> str:
        return make_run_id(SHAPE, current_claim_id, current_seed)

    with (
        patch.object(swarm_reference, "parse_delay_days", return_value=None),
        patch.object(swarm_reference, "make_run_id", side_effect=variant_run_id),
    ):
        result = swarm_reference.run_claim(
            claim_id, seed=seed, store_path=store_path, crash_at=crash_at
        )
    result.shape = SHAPE
    return result
