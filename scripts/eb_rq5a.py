#!/usr/bin/env python3
"""CLI runner for Edgebench RQ5 Part A (live admission + N-node modeled execution).

Usage:
  scripts/eb_rq5a.py --cells load_4 --seeds 1 --models oracle Jev-1.13.0 --out runs/EXP-2026-002/rq5a
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import random
import shutil
import sys
import time
from typing import Any

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.credentials import load_openrouter_key
from src.edgebench.e2e.admission import run_live_admission_arm
from src.edgebench.e2e.sim import simulate, summarize
from src.edgebench.e2e.traces import (
    CELLS_A,
    generate_trace_a,
    load_pool,
    normalize_cell_name,
)
from src.edgebench.ledger import LedgerWriter, resolve_git_provenance
from src.edgebench.manifest import build_interpreter, load_manifest

# Ensure OPENROUTER_API_KEY is available in os.environ if saved in config
_openrouter_key = load_openrouter_key()
if _openrouter_key and "OPENROUTER_API_KEY" not in os.environ:
    os.environ["OPENROUTER_API_KEY"] = _openrouter_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Edgebench RQ5 Part A experiments.")
    parser.add_argument(
        "--cells",
        nargs="+",
        default=["all"],
        help="Cell name(s) to evaluate, or 'all' for all 15 Part A cells",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=[1],
        help="Seed(s) to evaluate (default: 1)",
    )
    parser.add_argument(
        "--models",
        nargs="+",
        required=True,
        help="Model display name(s) to evaluate",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="runs/EXP-2026-002/rq5a",
        help="Output directory",
    )
    parser.add_argument(
        "--traces-dir",
        type=str,
        default="traces",
        help="Directory with pre-generated traces (will be generated if missing)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit arrivals for smoke testing (e.g. 30)",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running with uncommitted changes in git worktree",
    )
    return parser.parse_args()


def check_models_deployment(models: list[str], manifest: dict[str, Any]) -> None:
    """Ensure hosted and self-hosted models are never mixed in the same invocation."""
    deployments = set()
    for m in models:
        norm_name = "Oracle" if m == "oracle" else m
        if norm_name in manifest:
            deployments.add(manifest[norm_name].get("deployment", "hosted"))
        elif m.startswith("fixed-latency") or m == "oracle":
            deployments.add("reference")

    has_self_hosted = "self-hosted" in deployments
    has_hosted = "hosted" in deployments
    if has_self_hosted and has_hosted:
        raise ValueError(
            f"Hosted and self-hosted models cannot be run in the same invocation: {models}. "
            "Run self-hosted models in a dedicated invocation per design D-5."
        )


def compute_percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    sorted_vals = sorted(values)
    idx = int(round((len(sorted_vals) - 1) * (p / 100.0)))
    return sorted_vals[idx]


def main() -> None:
    args = parse_args()
    manifest = load_manifest()
    check_models_deployment(args.models, manifest)

    # Determine cells
    if "all" in [c.lower() for c in args.cells]:
        cell_keys = list(CELLS_A.keys())
    else:
        cell_keys = [normalize_cell_name(c) for c in args.cells]

    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    traces_root = Path(args.traces_dir)

    git_sha, is_dirty, git_source, prov_tree = resolve_git_provenance()
    if is_dirty and not args.allow_dirty:
        raise RuntimeError("Worktree is dirty. Pass --allow-dirty to override.")

    # Process per (cell, seed)
    for cell in cell_keys:
        cfg = CELLS_A[cell]
        deadline = cfg["deadline"]
        n_edges = cfg["nodes"]
        cache_enabled = cfg["cache"]

        for seed in args.seeds:
            # Load or generate trace
            trace_path = traces_root / cell / f"{seed}.jsonl"
            if trace_path.exists():
                with open(trace_path, "r", encoding="utf-8") as f:
                    arrivals = [json.loads(line) for line in f if line.strip()]
            else:
                arrivals = generate_trace_a(cell=cell, seed=seed)

            if args.limit is not None and args.limit > 0:
                arrivals = arrivals[: args.limit]

            # Seeded random order of models for this arm
            models = list(args.models)
            rng_order = random.Random(f"{cell}/{seed}")
            rng_order.shuffle(models)

            for model_name in models:
                arm_id = f"{cell}-s{seed}-{model_name}"
                arm_dir = out_root / cell / f"seed_{seed}" / model_name
                outcomes_path = arm_dir / "outcomes.jsonl"
                integrity_path = arm_dir / "integrity.json"
                ledger_path = arm_dir / "ledger.jsonl"

                # Resume check
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
                print(f"[{arm_id}] Running {len(arrivals)} arrivals (N={n_edges}, D={deadline}s, cache={cache_enabled})...")

                # Build interpreter
                lookup_name = "Oracle" if model_name == "oracle" else model_name
                interpreter = build_interpreter(lookup_name, manifest=manifest, condition=cell)

                # Initialize ledger writer
                with LedgerWriter(
                    path=ledger_path,
                    run_id=arm_id,
                    git_sha=git_sha,
                    rq="RQ5A",
                    condition=cell,
                    allow_dirty=args.allow_dirty,
                    git_source=git_source,
                    provenance_tree_sha256=prov_tree,
                ) as ledger_writer:
                    # Run live admission
                    admission_results = run_live_admission_arm(
                        arrivals=arrivals,
                        interpreter=interpreter,
                        cache_enabled=cache_enabled,
                        concurrency=4,
                        deadline=deadline,
                        queue_limit=32,
                        ledger_writer=ledger_writer,
                        out_dir=arm_dir,
                        seed=seed,
                        cell=cell,
                    )

                # Replay admission timeline through simulator
                sim_results = simulate(
                    arrivals=arrivals,
                    controller_trace=admission_results,
                    deadline=deadline,
                    n_edges=n_edges,
                )

                # Write outcomes.jsonl
                with open(outcomes_path, "w", encoding="utf-8") as f:
                    for r in sim_results:
                        truth = r.get("truth", [])
                        truth_dict = truth[0] if isinstance(truth, list) else truth
                        meta = r.get("decision_metadata", {}) or {}
                        outcome_row = {
                            "id": r["id"],
                            "case_id": r.get("case_id"),
                            "status": r["status"],
                            "arrival": r["arrival"],
                            "terminal": r["terminal"],
                            "deadline": r.get("deadline"),
                            "origin": r.get("origin"),
                            "T": round(r["T"], 6),
                            "queue_wait_s": round(r.get("queue_wait_s", 0.0), 6),
                            "decision_elapsed_s": round(r.get("decision_elapsed_s", 0.0), 6),
                            "transfer_s": round(r.get("transfer_s", 0.0), 6),
                            "service_s": round(r.get("service_s", 0.0), 6),
                            "service_queue_s": round(r.get("service_queue_s", 0.0), 6),
                            "node": r.get("node"),
                            "locality_violation": bool(r.get("locality_violation", False)),
                            "cost_usd": r.get("cost_usd", 0.0),
                            "predicted": r.get("predicted"),
                            "truth": truth_dict,
                            "priority": r.get("priority"),
                            "joint_correct": bool(r.get("joint_correct", False)),
                            "locality_ok": bool(r.get("locality_ok", False)),
                            "quality_ok": bool(r.get("quality_ok", False)),
                            "decision_start": r.get("decision_start"),
                            "decision_end": r.get("decision_end"),
                            "decision_timed_out": bool(r.get("decision_timed_out", False)),
                            "cache_hit": bool(meta.get("cache_hit", False)),
                            "api_calls": int(meta.get("api_calls", 0)),
                            "network_ready": r.get("network_ready"),
                            "service_start": r.get("service_start"),
                            "model": model_name,
                            "cell": cell,
                            "seed": seed,
                        }
                        f.write(json.dumps(outcome_row) + "\n")

                # Integrity check
                counts = Counter(r["status"] for r in sim_results)
                all_T = [r["T"] for r in sim_results]
                success_T = [r["T"] for r in sim_results if r["status"] == "success"]
                loc_violations = sum(bool(r.get("locality_violation")) for r in sim_results)

                # Check that every arrival id appears exactly once with valid terminal status
                seen_ids = set()
                single_terminal = True
                for r in sim_results:
                    if r["id"] in seen_ids or r["status"] == "pending":
                        single_terminal = False
                    seen_ids.add(r["id"])
                if seen_ids != {a["id"] for a in arrivals}:
                    single_terminal = False

                integrity_data = {
                    "arm": arm_id,
                    "model": model_name,
                    "cell": cell,
                    "seed": seed,
                    "arrivals": len(arrivals),
                    "completed": len(sim_results),
                    "single_terminal_status_per_arrival": single_terminal,
                    "status_counts": dict(counts),
                    "success_count": counts.get("success", 0),
                    "success_rate": counts.get("success", 0) / len(arrivals) if arrivals else 0.0,
                    "p50_T_all": compute_percentile(all_T, 50.0),
                    "p95_T_all": compute_percentile(all_T, 95.0),
                    "p50_T_success": compute_percentile(success_T, 50.0),
                    "p95_T_success": compute_percentile(success_T, 95.0),
                    "locality_violations": loc_violations,
                    "complete": True,
                }

                with open(integrity_path, "w", encoding="utf-8") as f:
                    json.dump(integrity_data, f, indent=2)

                print(
                    f"[{arm_id}] Finished: success {counts.get('success', 0)}/{len(arrivals)} "
                    f"({counts.get('success', 0)/len(arrivals):.1%}), "
                    f"p50_T={integrity_data['p50_T_all']:.3f}s, "
                    f"p95_T={integrity_data['p95_T_all']:.3f}s"
                )


if __name__ == "__main__":
    main()
