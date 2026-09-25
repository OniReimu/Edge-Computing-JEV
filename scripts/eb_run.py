#!/usr/bin/env python3
"""CLI runner for Edgebench evaluations."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repo root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.edgebench.runner import run_benchmark

# A self-hosted server went down (or stayed unhealthy after a client timeout, or kept answering 5xx)
# mid-condition; eb_selfhosted.pbs restarts it once and resumes.
EXIT_SELF_HOSTED_SERVER_DOWN = 3
SERVER_STOP_REASONS = ("self_hosted_server_down", "self_hosted_server_error")
# The condition ended with rows != expected or duplicate rows (integrity.json); PBS marks it FAILED.
EXIT_INTEGRITY = 4


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Edgebench runner CLI")
    parser.add_argument(
        "--cases", required=True, help="Path to jsonl file containing evaluation cases"
    )
    parser.add_argument("--rq", required=True, help="Research question tag (e.g. RQ1)")
    parser.add_argument("--condition", required=True, help="Experimental condition name")
    parser.add_argument(
        "--models",
        required=True,
        help="Comma-separated display names of models to evaluate",
    )
    parser.add_argument("--out", required=True, help="Output directory for ledger and integrity report")
    parser.add_argument(
        "--repeats-subset",
        default="none",
        help="Path to file containing case IDs for repeats 1-2, or 'none'",
    )
    parser.add_argument("--workers", type=int, default=4, help="Number of worker threads")
    parser.add_argument("--seed", type=int, default=20260924, help="Evaluation random seed")
    parser.add_argument(
        "--spend-cap-usd",
        type=float,
        default=20.0,
        help="Spend cap in USD before stopping the run",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running with modified tracked git files",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Optional path to custom models.json manifest",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the manifest base_url of the self-hosted model(s), e.g. http://127.0.0.1:8654",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model_names = [m.strip() for m in args.models.split(",") if m.strip()]
    if not model_names:
        print("Error: No models specified.", file=sys.stderr)
        sys.exit(1)

    print(
        f"Starting Edgebench: RQ={args.rq}, Condition={args.condition}, Models={model_names}, "
        f"Workers={args.workers}, SpendCap=${args.spend_cap_usd:.2f}"
    )

    report = run_benchmark(
        cases_path=args.cases,
        rq=args.rq,
        condition=args.condition,
        model_names=model_names,
        out_dir=args.out,
        repeats_subset_path=args.repeats_subset,
        workers=args.workers,
        seed=args.seed,
        spend_cap_usd=args.spend_cap_usd,
        allow_dirty=args.allow_dirty,
        manifest_path=args.manifest,
        base_url=args.base_url,
    )

    print(f"Run completed. Stop reason: {report['stop_reason']}. Total spend: ${report['total_spend_usd']:.4f}")
    print(f"Integrity report written to {args.out}/integrity.json")
    if report["stop_reason"] in SERVER_STOP_REASONS:
        sys.exit(EXIT_SELF_HOSTED_SERVER_DOWN)
    if (
        report["actual_rows_per_model_repeat"] != report["expected_rows_per_model_repeat"]
        or report["duplicates"] > 0
    ):
        print(
            f"Integrity failure: rows {report['actual_rows_per_model_repeat']} != expected "
            f"{report['expected_rows_per_model_repeat']} or duplicates={report['duplicates']}",
            file=sys.stderr,
        )
        sys.exit(EXIT_INTEGRITY)


if __name__ == "__main__":
    main()
