#!/usr/bin/env python3
"""Cross-platform alignment check for the self-hosted Edgebench servers.

  run      Send the 20 fixture cases (tests/fixtures/eb_local_20.jsonl) to a running server through the
           manifest adapter and write per-case choices + probabilities to a JSON file, with the sha256
           of each request (platform-specific fields excluded) and their combined contract_sha256.
           Exits 1 when fewer than all cases are valid (the file is still written).
  compare  Compare two such files (e.g. MLX vs CUDA) and report choice agreement and probability gaps.
           With --gate, exits 1 when the per-case request hashes differ ("reference stale"), else unless
           B has all 20 cases valid and per-field agreement >= 0.95.

The MLX references are tracked in configs/edgebench/align/mlx_{semif,laya,qwen_json}.json.

Examples:
  eb_align_check.py run --model SemIf-Qwen3.5-4B@cuda --out align/semif.cuda.json
  eb_align_check.py compare configs/edgebench/align/mlx_semif.json align/semif.cuda.json \
      --out align/semif.compare.json --gate
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
from typing import Any

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.edgebench.contract import load_cases_jsonl
from src.edgebench.manifest import build_interpreter, load_manifest

FIXTURE_PATH = _repo_root / "tests" / "fixtures" / "eb_local_20.jsonl"
# Compare gate (eb_selfhosted.pbs, before any corpus condition): B valid on all cases, field agreement.
GATE_N = 20
GATE_MIN_FIELD_AGREEMENT = 0.95
STALE_REFERENCE = "reference stale: request hashes differ"
# Request fields that legitimately differ between platforms (MLX vs CUDA model id). The base URL is not
# part of the request body.
PLATFORM_REQUEST_FIELDS = frozenset({"model"})


def request_sha256(interpreter: Any, case: Any) -> str | None:
    """sha256 of the canonical JSON of the request the interpreter sends for `case`, platform fields excluded.

    None for an interpreter that sends no request (no build_request).
    """
    build = getattr(interpreter, "build_request", None)
    if build is None:
        return None
    payload = {k: v for k, v in build(case).items() if k not in PLATFORM_REQUEST_FIELDS}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def contract_sha256(case_hashes: list[str | None]) -> str | None:
    """sha256 of the concatenated per-case request hashes (None when any case has none)."""
    if not case_hashes or any(h is None for h in case_hashes):
        return None
    return hashlib.sha256("".join(case_hashes).encode("utf-8")).hexdigest()


def run_check(
    model: str,
    cases_path: str | Path = FIXTURE_PATH,
    manifest_path: str | Path | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Decide every fixture case with one model and collect choices and probabilities."""
    manifest = load_manifest(manifest_path)
    interpreter = build_interpreter(model, manifest=manifest, base_url=base_url)
    cases = load_cases_jsonl(cases_path)
    rows = []
    for case in cases:
        d = interpreter.decide(case)
        rows.append({
            "case_id": case.case_id,
            "valid": d.valid,
            "error_type": d.error_type,
            "labels": d.labels,
            "probabilities": d.probabilities,
            "truth": case.truth,
            "resolved_model": d.resolved_model,
            "latency_s": d.latency_s,
            "request_sha256": request_sha256(interpreter, case),
        })
    latencies = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    return {
        "model": model,
        "platform": interpreter.platform,
        "base_url": getattr(interpreter, "base_url", None),
        # EB_GIT_SHA on the cluster; a placeholder for a local run of an uncommitted tree
        "code_sha": os.environ.get("EB_GIT_SHA") or "UNCOMMITTED",
        "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "resolved_models": sorted({r["resolved_model"] for r in rows if r["resolved_model"]}),
        "latency_p50_s": statistics.median(latencies) if latencies else None,
        "n": len(rows),
        "valid": sum(r["valid"] for r in rows),
        "em": sum(bool(r["valid"]) and r["labels"] == r["truth"] for r in rows),
        "contract_sha256": contract_sha256([r["request_sha256"] for r in rows]),
        "cases": rows,
    }


def compare_runs(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Choice agreement (per case and per field) and max/mean |p_a - p_b| over shared options."""
    rows_a = {r["case_id"]: r for r in a["cases"]}
    rows_b = {r["case_id"]: r for r in b["cases"]}
    common = sorted(set(rows_a) & set(rows_b))
    # Like with like: every case of either file must carry the same request hash in both (missing = differs).
    request_hash_mismatches = sum(
        rows_a.get(cid, {}).get("request_sha256") != rows_b.get(cid, {}).get("request_sha256")
        or rows_a.get(cid, {}).get("request_sha256") is None
        for cid in set(rows_a) | set(rows_b)
    )
    case_agree = 0
    field_total = 0
    field_agree = 0
    prob_diffs: list[float] = []
    disagreements = []
    for cid in common:
        ra, rb = rows_a[cid], rows_b[cid]
        if ra["labels"] == rb["labels"] and ra["valid"] == rb["valid"]:
            case_agree += 1
        else:
            disagreements.append({"case_id": cid, "a": ra["labels"], "b": rb["labels"],
                                  "a_valid": ra["valid"], "b_valid": rb["valid"]})
        for req_a, req_b in zip(ra["labels"] or [], rb["labels"] or []):
            for field in req_a:
                field_total += 1
                field_agree += int(req_a.get(field) == req_b.get(field))
        for pa_req, pb_req in zip(ra.get("probabilities") or [], rb.get("probabilities") or []):
            for field, pa in (pa_req or {}).items():
                pb = (pb_req or {}).get(field) or {}
                for opt in set(pa) & set(pb):
                    prob_diffs.append(abs(float(pa[opt]) - float(pb[opt])))
    return {
        "a": {"model": a["model"], "platform": a.get("platform"), "resolved_models": a.get("resolved_models"),
              "contract_sha256": a.get("contract_sha256")},
        "b": {"model": b["model"], "platform": b.get("platform"), "resolved_models": b.get("resolved_models"),
              "contract_sha256": b.get("contract_sha256")},
        "request_hash_mismatches": request_hash_mismatches,
        "n_common": len(common),
        "case_agreement": case_agree / len(common) if common else None,
        "field_agreement": field_agree / field_total if field_total else None,
        "prob_abs_diff_max": max(prob_diffs) if prob_diffs else None,
        "prob_abs_diff_mean": sum(prob_diffs) / len(prob_diffs) if prob_diffs else None,
        "n_prob_pairs": len(prob_diffs),
        "disagreements": disagreements,
    }


def gate_check(a: dict[str, Any], b: dict[str, Any], report: dict[str, Any]) -> dict[str, Any]:
    """Same requests in A and B; then B (the run under test) has all GATE_N cases valid and field agreement
    >= GATE_MIN_FIELD_AGREEMENT."""
    reasons = []
    if report["request_hash_mismatches"]:
        # Agreement between responses to different requests says nothing: refuse before evaluating it.
        return {"passed": False, "n_required": GATE_N, "min_field_agreement": GATE_MIN_FIELD_AGREEMENT,
                "a_valid": a.get("valid"), "b_valid": b.get("valid"), "reasons": [STALE_REFERENCE]}
    if not (b.get("n") == b.get("valid") == report["n_common"] == GATE_N):
        reasons.append(f"valid {b.get('valid')}/{b.get('n')} (common {report['n_common']}), need {GATE_N}/{GATE_N}")
    agreement = report["field_agreement"]
    if agreement is None or agreement < GATE_MIN_FIELD_AGREEMENT:
        reasons.append(f"field_agreement {agreement} < {GATE_MIN_FIELD_AGREEMENT}")
    return {"passed": not reasons, "n_required": GATE_N, "min_field_agreement": GATE_MIN_FIELD_AGREEMENT,
            "a_valid": a.get("valid"), "b_valid": b.get("valid"), "reasons": reasons}


def _write(obj: dict[str, Any], out: str | Path) -> None:
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Edgebench self-hosted alignment check")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run", help="Run the fixture cases against a running server")
    p_run.add_argument("--model", required=True, help="Manifest display name, e.g. SemIf-Qwen3.5-4B@cuda")
    p_run.add_argument("--out", required=True, help="Output JSON path")
    p_run.add_argument("--cases", default=str(FIXTURE_PATH), help="Cases JSONL (default: 20 fixture cases)")
    p_run.add_argument("--manifest", default=None, help="Optional models.json path")
    p_run.add_argument("--base-url", default=None, help="Override the manifest base_url (self-hosted only)")
    p_cmp = sub.add_parser("compare", help="Compare two run outputs")
    p_cmp.add_argument("a")
    p_cmp.add_argument("b")
    p_cmp.add_argument("--out", default=None, help="Optional output JSON path")
    p_cmp.add_argument("--gate", action="store_true",
                       help=f"Exit 1 if the request hashes differ, else unless B is {GATE_N}/{GATE_N} valid "
                            f"and field agreement >= {GATE_MIN_FIELD_AGREEMENT}")
    args = parser.parse_args(argv)

    if args.cmd == "run":
        result = run_check(args.model, args.cases, args.manifest, base_url=args.base_url)
        _write(result, args.out)
        print(f"{result['model']}: valid {result['valid']}/{result['n']}, EM {result['em']}/{result['n']}, "
              f"p50 {result['latency_p50_s']}, resolved {result['resolved_models']} -> {args.out}")
        return 0 if result["valid"] == result["n"] else 1

    with open(args.a, encoding="utf-8") as fa, open(args.b, encoding="utf-8") as fb:
        run_a, run_b = json.load(fa), json.load(fb)
    report = compare_runs(run_a, run_b)
    if args.gate:
        report["gate"] = gate_check(run_a, run_b, report)
    if args.out:
        _write(report, args.out)
    print(json.dumps({k: v for k, v in report.items() if k != "disagreements"}, indent=2))
    if args.gate and not report["gate"]["passed"]:
        if report["gate"]["reasons"] == [STALE_REFERENCE]:
            print(f"FATAL: {STALE_REFERENCE} (a {report['a']['contract_sha256']} vs b "
                  f"{report['b']['contract_sha256']}); regenerate the reference", file=sys.stderr)
        print(f"ALIGNMENT GATE FAILED: {report['gate']['reasons']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
