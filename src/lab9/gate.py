"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate."""
    problems: list[str] = []

    # 1. Any metric value in pr["metrics"] that is NaN or inf
    for k, v in pr.get("metrics", {}).items():
        if isinstance(v, (int, float)) and (math.isnan(v) or math.isinf(v)):
            problems.append(f"metric {k} has invalid value {v}")

    # 2. Row count check: len(pr["rows"]) != manifest items x len(manifest seeds)
    manifest = pr.get("manifest", {})
    items_count = manifest.get("items")
    seeds_count = len(manifest.get("seeds", []))
    if items_count is not None and seeds_count > 0:
        expected_rows = items_count * seeds_count
        if len(pr.get("rows", [])) != expected_rows:
            problems.append(f"row count {len(pr.get('rows', []))} != expected {expected_rows}")

    # 3. (item_id, seed) set of PR differs from baseline's
    pr_pairs = {(r.get("item_id"), r.get("seed")) for r in pr.get("rows", [])}
    base_pairs = {(r.get("item_id"), r.get("seed")) for r in base.get("rows", [])}
    if pr_pairs != base_pairs:
        problems.append("PR (item_id, seed) pairs differ from baseline")

    # 4. pr["evaluator_failures"] non-empty, or a row has None for a graded metric
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s)")

    spec_metric_ids = [m["id"] for m in spec.get("metrics", [])]
    for r in pr.get("rows", []):
        for mid in spec_metric_ids:
            if mid in r and r[mid] is None:
                problems.append(f"row {r.get('item_id')}@{r.get('seed')} has None for metric {mid}")
                break

    # 5. An item's slice tags in PR rows differ from baseline's
    base_slices = {r.get("item_id"): set(r.get("slices", [])) for r in base.get("rows", [])}
    for r in pr.get("rows", []):
        iid = r.get("item_id")
        if iid in base_slices and set(r.get("slices", [])) != base_slices[iid]:
            problems.append(f"slice tags for item {iid} differ from baseline")
            break

    # 6. Ratchet check: base_spec given and a threshold in spec is LOOSER than in base_spec
    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        base_m_map = {m["id"]: m for m in base_spec.get("metrics", [])}
        spec_m_map = {m["id"]: m for m in spec.get("metrics", [])}
        for mid, bm in base_m_map.items():
            if mid not in spec_m_map:
                problems.append(f"metric {mid} disappeared from spec")
                continue
            sm = spec_m_map[mid]
            if bm.get("blocking") and not sm.get("blocking"):
                problems.append(f"metric {mid} loosened from blocking to non-blocking")
            b_th = bm.get("threshold", {})
            s_th = sm.get("threshold", {})
            if "min" in b_th and s_th.get("min", -float("inf")) < b_th["min"]:
                problems.append(f"metric {mid} min threshold lowered from {b_th['min']} to {s_th.get('min')}")
            if "max" in b_th and s_th.get("max", float("inf")) > b_th["max"]:
                problems.append(f"metric {mid} max threshold raised from {b_th['max']} to {s_th.get('max')}")
            if b_th.get("no_significant_drop") and not s_th.get("no_significant_drop"):
                problems.append(f"metric {mid} dropped no_significant_drop")

        base_s_map = {s["name"]: s for s in base_spec.get("slices", [])}
        spec_s_map = {s["name"]: s for s in spec.get("slices", [])}
        for sname, bs_entry in base_s_map.items():
            if sname not in spec_s_map:
                problems.append(f"slice {sname} disappeared from spec")
                continue
            ss_entry = spec_s_map[sname]
            if bs_entry.get("blocking") and not ss_entry.get("blocking"):
                problems.append(f"slice {sname} loosened from blocking to non-blocking")
            if "min" in bs_entry and ss_entry.get("min", -float("inf")) < bs_entry["min"]:
                problems.append(f"slice {sname} min threshold lowered")
            if bs_entry.get("no_significant_drop") and not ss_entry.get("no_significant_drop"):
                problems.append(f"slice {sname} dropped no_significant_drop")

    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices", []):
        sname = s["name"]
        metric = s["metric"]
        a = per_item(pr, metric, slice_name=sname)
        b = per_item(base, metric, slice_name=sname)
        val = sum(a.values()) / len(a) if a else 0.0
        verdict, note = "ok", ""
        if "min" in s and val < s["min"]:
            verdict = "fail"
        if s.get("no_significant_drop") and a and b:
            keys = sorted(set(a) & set(b))
            if keys:
                d, lo, hi = stats.paired_bootstrap(
                    [a[k] for k in keys],
                    [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000),
                    rng=bs.get("rng", 2027),
                )
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
                if hi < 0:
                    verdict = "fail"
        slice_id = f"slice:{sname}/{metric}"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(slice_id)
        label = {"ok": "ok"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th_info = {k: v for k, v in s.items() if k not in ("name", "metric", "blocking")}
        lines.append(f"  {slice_id:<22} {val:<8.4f} {json.dumps(th_info):<40} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    spec = load_spec(Path(args.spec))
    blocked, lines = check(pr, base, spec, base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    for line in lines:
        print(line)
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
