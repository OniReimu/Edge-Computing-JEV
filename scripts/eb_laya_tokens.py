#!/usr/bin/env python3
"""Offline Laya token accounting for an Edgebench ledger (kept out of the server's timed path).

For every (condition, case_id) among the ledger rows of the Laya model (every manifest entry serving
laya-typed-decisions@bc76315b), the request the decisions client sent is rebuilt from the case
(build_request on the case text and questions) and usage.input_tokens / truncated are computed with
the server's own compute_untruncated_token_count on the Laya checkpoint pinned to bc76315b.
The result is written, sorted by key, to <ledger>.laya_tokens.jsonl for the analysis to join.

  eb_laya_tokens.py --ledger runs/<rq>/<condition>/ledger.jsonl --cases <cases.jsonl>
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.eb_serve_laya import MODEL_REVISION, RESOLVED_MODEL_ID, compute_untruncated_token_count, load_agent
from src.edgebench.contract import Case, load_cases_jsonl
from src.edgebench.manifest import build_interpreter, load_manifest


def sidecar_path(ledger: str | Path) -> Path:
    return Path(f"{ledger}.laya_tokens.jsonl")


def laya_model_names(manifest: dict[str, Any]) -> set[str]:
    """Manifest display names whose model is the pinned Laya checkpoint (any device)."""
    return {name for name, entry in manifest.items() if str(entry.get("model", "")).startswith(RESOLVED_MODEL_ID)}


def compute_sidecar(
    rows: list[dict[str, Any]], cases: list[Case], agent: Any, manifest: dict[str, Any]
) -> list[dict[str, Any]]:
    """One record per (condition, case_id) of the Laya rows, sorted by key."""
    names = laya_model_names(manifest)
    by_id = {case.case_id: case for case in cases}
    keys: dict[tuple[str, str], str] = {}
    for row in rows:
        if row.get("model") in names:
            keys.setdefault((str(row["condition"]), str(row["case_id"])), row["model"])
    records = []
    for (condition, case_id), model in sorted(keys.items()):
        if case_id not in by_id:
            raise KeyError(f"Case {case_id!r} of condition {condition!r} is not in the cases file")
        request = build_interpreter(model, manifest=manifest).build_request(by_id[case_id])
        input_tokens, truncated = compute_untruncated_token_count(agent, request["state"], request["questions"])
        records.append({
            "condition": condition,
            "case_id": case_id,
            "input_tokens": input_tokens,
            "truncated": truncated,
            "model_revision": MODEL_REVISION,
        })
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Recompute Laya input_tokens / truncated for a ledger, offline")
    parser.add_argument("--ledger", required=True, help="ledger.jsonl")
    parser.add_argument("--cases", required=True, help="Cases JSONL the ledger was run on")
    parser.add_argument("--manifest", default=None, help="Optional models.json path")
    args = parser.parse_args(argv)

    with open(args.ledger, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    manifest = load_manifest(args.manifest)
    records = compute_sidecar(rows, load_cases_jsonl(args.cases), load_agent("cpu"), manifest)
    out = sidecar_path(args.ledger)
    with open(out, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, sort_keys=True) + "\n")
    print(f"{len(records)} (condition, case_id) records -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
