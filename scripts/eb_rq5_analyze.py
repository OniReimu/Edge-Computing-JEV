#!/usr/bin/env python3
"""EXP-2026-002 RQ5 analysis (H6-H8).

Writes to --out: cells.csv, gaps.csv, hypotheses.csv, hypotheses.md, controls.csv, topology_replay.csv, paper_numbers.md.
Strict coverage: exits 2 when any expected (cell, model) arm is missing or incomplete, unless --allow-partial.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.edgebench.e2e.analysis import (
    HYP_COLUMNS,
    paper_numbers_md,
    render_hypotheses_md,
    run_analysis,
    to_csv,
)

DEFAULT_OUT = "experiments/rq5-end-to-end/results/"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root-a", default="runs/EXP-2026-002/rq5a")
    ap.add_argument("--root-b", default="runs/EXP-2026-002/rq5b")
    ap.add_argument("--traces-dir", default="traces")
    ap.add_argument("--out", default=DEFAULT_OUT)
    ap.add_argument("--allow-partial", action="store_true", help="analyse what exists and list the gaps")
    args = ap.parse_args()
    root_a, root_b, traces = (Path(p) if Path(p).is_absolute() else _repo_root / p
                              for p in (args.root_a, args.root_b, args.traces_dir))

    res = run_analysis(root_a, root_b, traces)
    gaps = res["coverage_gaps"]
    if gaps:
        print(f"Coverage: {len(gaps)} expected arm(s) missing or incomplete:", file=sys.stderr)
        for g in gaps:
            print(f"  Part {g['part']} / {g['cell']} / {g['model']}: {g['reason']}", file=sys.stderr)
        if not args.allow_partial:
            print("Strict coverage failed; rerun with --allow-partial to analyse what exists.", file=sys.stderr)
            return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tables = {
        "cells.csv": to_csv(res["cells"]),
        "gaps.csv": to_csv(res["gaps"]),
        "hypotheses.csv": to_csv(res["hypotheses"], HYP_COLUMNS),
        "controls.csv": to_csv(res["controls"], ["part", "cell", "model", "delay_s", "strict_completion",
                                                  "operational_completion", "max_interpreter_primary", "flag"]),
        "topology_replay.csv": to_csv(res["replay"]),
    }
    for name, text in tables.items():
        (out / name).write_text(text, encoding="utf-8")
    hyp_csv = (out / "hypotheses.csv").read_text(encoding="utf-8")
    (out / "hypotheses.md").write_text(render_hypotheses_md(hyp_csv, gaps, res["notes"]), encoding="utf-8")
    (out / "paper_numbers.md").write_text(paper_numbers_md(tables), encoding="utf-8")
    print(f"Wrote {len(tables) + 2} files to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
