#!/usr/bin/env python3
"""Run Edgebench EXP-2026-001 analysis pipeline across hosted, self-hosted, reference, and sensitivity runs.

Generates:
  1. cells.csv
  2. comms.csv (Addendum A1)
  3. contrasts.csv
  4. hypotheses.csv + hypotheses.md (H1–H5)
  5. sensitivity.csv
  6. report.md
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure repo root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.edgebench.analysis import (
    ALL_EVAL_MODELS,
    ALL_TABLE_MODELS,
    check_coverage,
    check_oracle_control,
    evaluate_hypotheses,
    generate_cells_csv,
    generate_comms_csv,
    generate_contrasts_csv,
    generate_h5_classifier_reference,
    generate_hypotheses_csv,
    generate_report_md,
    generate_sensitivity_table,
    load_all_power_traces,
    load_all_runs,
    load_cases,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="EXP-2026-001 pre-registered analysis pipeline & Addendum A1"
    )
    parser.add_argument(
        "--runs-dir",
        type=Path,
        default=Path("runs/EXP-2026-001"),
        help="Path to runs directory (default: runs/EXP-2026-001)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/edgebench/v1"),
        help="Path to data directory (default: data/edgebench/v1)",
    )
    parser.add_argument(
        "--sensitivity-dir",
        type=Path,
        default=Path("runs/EXP-2026-001-sensitivity"),
        help="Path to sensitivity runs directory (default: runs/EXP-2026-001-sensitivity)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output directory for generated CSV and MD files",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Downgrade missing cell error to a warning and continue analysis",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=20260924,
        help="Random seed for bootstrap resampling (default: 20260924)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading test cases from {args.data_dir}...")
    cases = load_cases(args.data_dir)

    print(f"Loading ledger runs from {args.runs_dir}...")
    runs_by_cell = load_all_runs(args.runs_dir)

    print("Checking coverage across models and conditions...")
    try:
        coverage, missing, matrix_str = check_coverage(
            runs_by_cell,
            models=ALL_EVAL_MODELS,
            check_references=True,
            allow_missing=args.allow_missing,
        )
        print("\nCoverage Matrix:\n")
        print(matrix_str)
        print()
    except ValueError as e:
        print(f"\n[ERROR] {e}", file=sys.stderr)
        return 1

    print("Loading GPU power traces for self-hosted models...")
    power_traces = load_all_power_traces(args.runs_dir)

    print("Generating cells.csv...")
    cells_rows, cells_csv_str = generate_cells_csv(
        runs_by_cell, cases, models=ALL_TABLE_MODELS, seed=args.seed
    )
    (out_dir / "cells.csv").write_text(cells_csv_str, encoding="utf-8")

    print("Generating comms.csv (Addendum A1)...")
    comms_rows, comms_csv_str = generate_comms_csv(
        runs_by_cell, cases, power_traces=power_traces, models=ALL_TABLE_MODELS, seed=args.seed
    )
    (out_dir / "comms.csv").write_text(comms_csv_str, encoding="utf-8")

    print("Generating contrasts.csv...")
    contrasts_rows, contrasts_csv_str = generate_contrasts_csv(
        runs_by_cell, seed=args.seed
    )
    (out_dir / "contrasts.csv").write_text(contrasts_csv_str, encoding="utf-8")

    print("Evaluating confirmatory hypotheses H1–H5...")
    hypotheses_rows, hypotheses_md = evaluate_hypotheses(
        runs_by_cell, cases, runs_dir=args.runs_dir, seed=args.seed
    )
    (out_dir / "hypotheses.csv").write_text(
        generate_hypotheses_csv(hypotheses_rows), encoding="utf-8"
    )
    (out_dir / "hypotheses.md").write_text(hypotheses_md, encoding="utf-8")

    print("Generating h5_classifier_reference.csv (descriptive)...")
    clf_rows, clf_csv_str = generate_h5_classifier_reference(
        runs_by_cell, cases, runs_dir=args.runs_dir, seed=args.seed
    )
    (out_dir / "h5_classifier_reference.csv").write_text(clf_csv_str, encoding="utf-8")

    print("Generating sensitivity.csv (D-7 sensitivity re-run)...")
    sens_rows, sens_csv_str = generate_sensitivity_table(
        runs_by_cell, args.sensitivity_dir, seed=args.seed
    )
    (out_dir / "sensitivity.csv").write_text(sens_csv_str, encoding="utf-8")

    print("Checking Oracle positive control and generating report.md...")
    oracle_ok, oracle_details, oracle_md = check_oracle_control(args.runs_dir)
    report_md = generate_report_md(
        coverage_matrix_md=matrix_str,
        oracle_table_md=oracle_md,
        cells_rows=cells_rows,
        comms_rows=comms_rows,
        all_oracle_passed=oracle_ok,
        runs_by_cell=runs_by_cell,
    )
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")

    print(f"Analysis complete. Outputs written to {out_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
