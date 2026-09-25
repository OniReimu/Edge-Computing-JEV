#!/usr/bin/env python3
"""CLI runner for Edgebench RQ5 Part B (real OCR testbed with 3 Dockerised workers).

Usage:
  scripts/eb_rq5b.py --conditions steady_changing_off --seeds 1 --models oracle Jev-1.13.0 --out runs/EXP-2026-002/rq5b
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random
import statistics
import sys
import time
from typing import Any

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.credentials import load_openrouter_key
from src.edgebench.e2e.admission import make_case_from_row
from src.edgebench.e2e.ocr_live import run_online_ocr, score_ocr
from src.edgebench.e2e.traces import (
    ALIAS_MAP_B,
    CONDITIONS_B,
    generate_trace_b,
    load_ocr_selection,
    load_pool,
    normalize_condition_b,
    select_repeated_8,
)
from src.edgebench.ledger import LedgerWriter, resolve_git_provenance
from src.edgebench.manifest import build_interpreter, load_manifest
from src.ocr_client import recognize

# Ensure OPENROUTER_API_KEY is available in os.environ if saved in config
_openrouter_key = load_openrouter_key()
if _openrouter_key and "OPENROUTER_API_KEY" not in os.environ:
    os.environ["OPENROUTER_API_KEY"] = _openrouter_key

DEFAULT_URLS = {
    "local": "http://127.0.0.1:18764",
    "edge2": "http://127.0.0.1:18765",
    "cloud": "http://127.0.0.1:18766",
}


def calibrate_nodes(
    urls: dict[str, str],
    calibration_images: list[dict[str, Any]],
    out_path: Path | None = None,
) -> dict[str, dict[str, float]]:
    """Measure median request-response time per (node, tier) on 40 calibration images."""
    print(f"Calibrating {len(urls)} nodes on {len(calibration_images)} images across standard and high tiers...")
    estimates: dict[str, dict[str, float]] = {n: {} for n in urls}

    for node, url in urls.items():
        for tier in ["standard", "high"]:
            latencies = []
            for i, img in enumerate(calibration_images):
                img_path = Path(img["path"])
                data = img_path.read_bytes()
                req_id = f"calib-{node}-{tier}-{i}"
                resp = recognize(url, data, req_id, tier=tier, priority=1, timeout=20)
                if resp.get("status") != "ok":
                    raise RuntimeError(f"Calibration request failed on {node} {tier}: {resp}")
                latencies.append(resp["origin_elapsed_s"])

            med = statistics.median(latencies)
            estimates[node][tier] = med
            print(f"[{node}][{tier}] median={med*1000.0:.2f}ms (min={min(latencies)*1000.0:.1f}ms, max={max(latencies)*1000.0:.1f}ms)")

    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(estimates, f, indent=2)
        print(f"Calibration frozen to {out_path}")

    return estimates





def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Edgebench RQ5 Part B OCR experiments.")
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=["steady_changing_off"],
        help="Condition(s) to evaluate (e.g. steady_changing_off, or 'all' for 8)",
    )
    parser.add_argument("--seeds", type=int, nargs="+", default=[1], help="Seed(s) (default: 1)")
    parser.add_argument("--models", nargs="+", required=True, help="Model(s) to evaluate")
    parser.add_argument("--out", default="runs/EXP-2026-002/rq5b", help="Output directory")
    parser.add_argument("--calibration", default="calibration.json", help="Path to calibration.json")
    parser.add_argument("--calibrate", action="store_true", help="Run live calibration before evaluation")
    parser.add_argument("--limit", type=int, default=None, help="Limit arrivals for smoke testing (e.g. 30)")
    parser.add_argument("--allow-dirty", action="store_true", help="Allow running with dirty git worktree")
    return parser.parse_args()


def compute_percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * (p / 100.0)))
    return sorted_vals[idx]


def main() -> None:
    args = parse_args()
    manifest = load_manifest()
    selection = load_ocr_selection()

    # Verify calibration
    calib_path = Path(args.calibration)
    if args.calibrate or not calib_path.exists():
        estimates = calibrate_nodes(DEFAULT_URLS, selection["calibration_images"], out_path=calib_path)
    else:
        with open(calib_path, "r", encoding="utf-8") as f:
            estimates = json.load(f)
        print(f"Loaded frozen calibration from {calib_path}")

    # Determine conditions
    if "all" in [c.lower() for c in args.conditions]:
        cond_keys = list(CONDITIONS_B.keys())
    else:
        cond_keys = [normalize_condition_b(c) for c in args.conditions]

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)

    git_sha, is_dirty, git_source, prov_tree = resolve_git_provenance()
    if is_dirty and not args.allow_dirty:
        raise RuntimeError("Worktree is dirty. Pass --allow-dirty to override.")

    for cond in cond_keys:
        cfg = CONDITIONS_B[cond]
        cache_enabled = cfg["cache"]

        for seed in args.seeds:
            arrivals = generate_trace_b(condition=cond, seed=seed, selection=selection)
            if args.limit is not None and args.limit > 0:
                arrivals = arrivals[: args.limit]

            models = list(args.models)
            rng_order = random.Random(f"{cond}/{seed}")
            rng_order.shuffle(models)

            for model_name in models:
                arm_id = f"{cond}-s{seed}-{model_name}"
                arm_dir = out_root / cond / f"seed_{seed}" / model_name
                outcomes_path = arm_dir / "outcomes.jsonl"
                integrity_path = arm_dir / "integrity.json"
                ledger_path = arm_dir / "ledger.jsonl"

                # Check resume
                if outcomes_path.exists() and integrity_path.exists():
                    try:
                        with open(integrity_path, "r", encoding="utf-8") as f:
                            integ = json.load(f)
                        if integ.get("complete") and integ.get("arrivals") == len(arrivals):
                            print(f"[{arm_id}] already complete, skipping.")
                            continue
                    except Exception:
                        pass

                arm_dir.mkdir(parents=True, exist_ok=True)
                print(f"[{arm_id}] Running {len(arrivals)} arrivals with {model_name}...")

                lookup_name = "Oracle" if model_name == "oracle" else model_name
                interpreter = build_interpreter(lookup_name, manifest=manifest, condition=cond)

                with LedgerWriter(
                    path=ledger_path,
                    run_id=arm_id,
                    git_sha=git_sha,
                    rq="RQ5B",
                    condition=cond,
                    allow_dirty=args.allow_dirty,
                    git_source=git_source,
                    provenance_tree_sha256=prov_tree,
                ) as ledger_writer:
                    results = asyncio.run(
                        run_online_ocr(
                            arrivals=arrivals,
                            interpreter=interpreter,
                            urls=DEFAULT_URLS,
                            estimates=estimates,
                            cache_enabled=cache_enabled,
                            deadline=2.0,
                            concurrency=4,
                            queue_limit=32,
                            service_limit=16,
                            ledger_writer=ledger_writer,
                            seed=seed,
                            condition=cond,
                        )
                    )

                # Write outcomes.jsonl
                with open(outcomes_path, "w", encoding="utf-8") as f:
                    for r in results:
                        score = r.get("score", {}) or {}
                        meta = r.get("decision_metadata", {}) or {}
                        t_val = r["terminal"] - r["arrival"]
                        truth = r.get("truth", [])
                        truth_dict = truth[0] if isinstance(truth, list) else truth
                        row_out = {
                            "id": r["id"],
                            "case_id": r.get("case_id"),
                            "status": r["status"],
                            "arrival": r["arrival"],
                            "terminal": r["terminal"],
                            "T": round(t_val, 6),
                            "node": r.get("node"),
                            "tier": r.get("tier"),
                            "correct_completion": bool(score.get("correct_completion")),
                            "output_exact": bool(score.get("output_exact")),
                            "locality_ok": bool(score.get("locality_ok")),
                            "locality_violation": bool(score.get("locality_violation")),
                            "cost_usd": meta.get("cost_usd", 0.0),
                            "predicted": r.get("predicted"),
                            "truth": truth_dict,
                            "is_ocr": bool(r.get("is_ocr", False)),
                            "priority": r.get("priority"),
                            "score": score,
                            "queue_wait_s": round(r.get("queue_wait_s", 0.0), 6) if r.get("queue_wait_s") is not None else None,
                            "decision_start": r.get("decision_start"),
                            "decision_end": r.get("decision_end"),
                            "decision_elapsed_s": round(r.get("decision_elapsed_s", 0.0), 6) if r.get("decision_elapsed_s") is not None else None,
                            "service_enqueued": r.get("service_enqueued"),
                            "service_dispatch": r.get("service_dispatch"),
                            "origin_service_s": round(r.get("origin_service_s", 0.0), 6) if r.get("origin_service_s") is not None else None,
                            "estimated_finish": r.get("estimated_finish"),
                            "cache_hit": bool(meta.get("cache_hit", False)),
                            "api_calls": int(meta.get("api_calls", 0)),
                            "error_type": r.get("error_type"),
                            "model": model_name,
                            "condition": cond,
                            "seed": seed,
                        }
                        f.write(json.dumps(row_out) + "\n")

                # Integrity check
                counts = Counter(r["status"] for r in results)
                all_T = [r["terminal"] - r["arrival"] for r in results]
                success_T = [
                    r["terminal"] - r["arrival"]
                    for r in results
                    if r.get("score", {}).get("correct_completion")
                ]
                success_count = sum(bool(r.get("score", {}).get("correct_completion")) for r in results)
                supported_count = sum(bool(r.get("score", {}).get("supported")) for r in results)
                completion_rate = success_count / supported_count if supported_count else 0.0
                completion_rate_all = success_count / len(arrivals) if arrivals else 0.0

                seen_ids = set(r["id"] for r in results)
                single_terminal = (seen_ids == set(a["id"] for a in arrivals))

                integrity_data = {
                    "arm": arm_id,
                    "model": model_name,
                    "condition": cond,
                    "seed": seed,
                    "arrivals": len(arrivals),
                    "completed": len(results),
                    "supported_arrivals": supported_count,
                    "single_terminal_status_per_arrival": single_terminal,
                    "status_counts": dict(counts),
                    "correct_completion_count": success_count,
                    "completion_rate": completion_rate,
                    "completion_rate_all": completion_rate_all,
                    "p50_T_all": compute_percentile(all_T, 50.0),
                    "p95_T_all": compute_percentile(all_T, 95.0),
                    "p50_T_success": compute_percentile(success_T, 50.0),
                    "p95_T_success": compute_percentile(success_T, 95.0),
                    "complete": True,
                }

                with open(integrity_path, "w", encoding="utf-8") as f:
                    json.dump(integrity_data, f, indent=2)

                print(
                    f"[{arm_id}] Finished: correct {success_count}/{supported_count} "
                    f"({completion_rate:.1%}, all: {completion_rate_all:.1%}), "
                    f"p50_T={integrity_data['p50_T_all']:.3f}s, "
                    f"p95_T={integrity_data['p95_T_all']:.3f}s"
                )


if __name__ == "__main__":
    import asyncio
    main()
