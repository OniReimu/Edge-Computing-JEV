#!/usr/bin/env python3
"""Live check script for all Edgebench self-hosted local model servers.

Runs in turn (start -> evaluate -> stop):
  1. SemIf-Qwen3.5-4B (port 8601, MLX shared-state mode)
  2. Laya (port 8602, MPS)
  3. Qwen3.5-4B-JSON (port 8603, MLX greedy chat completion)

Evaluates:
  - 20 handcrafted diverse cases (tests/fixtures/eb_local_20.jsonl)
  - Valid rate, exact match (EM) vs handwritten truth, p50 latency, peak RSS (ps -o rss=)
  - 64-option catalog question (validity, latency)
  - 254-option catalog question (validity, latency)
  - ~8K-token state case (validity, latency, tokens)
  - SemIf shared-vs-direct mode 20-case agreement check
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any

# Ensure repository root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.eb_local import cmd_start, cmd_stop
from src.edgebench.contract import (
    Case,
    FIELD_SETS,
    load_cases_jsonl,
)
from src.edgebench.manifest import build_interpreter, load_manifest

FIXTURE_PATH = _repo_root / "tests" / "fixtures" / "eb_local_20.jsonl"


def get_process_rss_mb(pid: int) -> float:
    """Read process Resident Set Size in MB using ps."""
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        if out:
            # ps rss on macOS is in KiB
            return float(out) / 1024.0
    except Exception:
        pass
    return 0.0


def make_catalog_case(n_options: int, target_idx: int = 5) -> Case:
    """Build a catalog choice case with n_options entries including 'unsupported'."""
    opts = {f"srv_{i:03d}": f"Service operation number {i} in registry" for i in range(n_options - 1)}
    opts["unsupported"] = "unsupported service"
    target_srv = f"srv_{target_idx:03d}"
    text = (
        f"Execute operation {target_srv} on local sensor stream. "
        f"Keep processing local to the edge node, standard quality is acceptable."
    )
    return Case(
        case_id=f"catalog-{n_options}",
        text=text,
        fields=["service_type"],
        service_options=opts,
        bundle_size=1,
        truth=[{"service_type": target_srv}],
        meta={"catalog_size": n_options},
    )


def make_8k_state_case() -> Case:
    """Build a case with approximately 8000 tokens in the state description."""
    base_paragraph = (
        "Log record: Sensor node alpha reported intermittent telemetry during batch execution. "
        "Environmental sensors indicate ambient temperature within nominal parameters at 21.4 degrees Celsius. "
        "Vibration monitoring detected low-amplitude harmonics across axis Z, well below the alert threshold. "
        "Storage subsystems retain 84 percent unallocated capacity with error-correcting memory active. "
        "Network telemetry confirms continuous bidirectional heartbeat to the local orchestrator node. "
    )
    # 50 words per paragraph * 120 repetitions ~= 6000 words ~= 8000 BPE tokens
    full_state = (
        base_paragraph * 120
        + "\nPlease read the text on this final inspection photo, keep data on site, urgent priority, standard quality is fine."
    )
    return Case(
        case_id="state-8k",
        text=full_state,
        fields=list(FIELD_SETS[4]),
        bundle_size=1,
        truth=[
            {
                "service_type": "ocr",
                "locality": "site_only",
                "quality_floor": "standard",
                "urgency": "urgent",
            }
        ],
        meta={"approx_tokens": 8000},
    )


def check_semif_shared_vs_direct_agreement(cases: list[Case]) -> tuple[int, int, float]:
    """Verify agreement between direct and shared scoring for SemIf across all cases."""
    from semif_phase1.mlx_backend import load_model, score, score_shared
    from scripts.eb_serve_semif import translate_request_to_semif_rows, MODEL_SOURCE, MODEL_REVISION
    from src.edgebench.contract import get_field_instruction, DEFAULT_CRITERIA

    print("\n--- Running SemIf Shared vs Direct Mode Agreement Check ---")
    model, tokenizer, metadata = load_model(MODEL_SOURCE, revision=MODEL_REVISION)

    total_questions = 0
    matched_questions = 0

    for case in cases:
        questions = {}
        for f in case.fields:
            qid = f"r1__{f}"
            questions[qid] = {
                "type": "choice",
                "instructions": get_field_instruction(f, request_index=1, bundle_size=1),
                "criteria": DEFAULT_CRITERIA[f],
            }

        rows = translate_request_to_semif_rows(case.text, questions)

        # Direct mode
        d_choices = {}
        for r in rows:
            res = score(model, tokenizer, r, metadata, max_tokens=4096)
            best_idx = max(range(len(res["probabilities"])), key=lambda i: res["probabilities"][i])
            d_choices[r["id"]] = res["option_ids"][best_idx]

        # Shared mode
        s_choices = {}
        results, _ = score_shared(model, tokenizer, rows, metadata, max_tokens=4096)
        for r, res in zip(rows, results):
            best_idx = max(range(len(res["probabilities"])), key=lambda i: res["probabilities"][i])
            s_choices[r["id"]] = res["option_ids"][best_idx]

        for qid in d_choices:
            total_questions += 1
            if d_choices[qid] == s_choices[qid]:
                matched_questions += 1
            else:
                print(f"  [MISMATCH] Case {case.case_id} {qid}: direct={d_choices[qid]}, shared={s_choices[qid]}")

    del model
    rate = (matched_questions / total_questions * 100.0) if total_questions > 0 else 0.0
    print(f"SemIf Agreement: {matched_questions}/{total_questions} ({rate:.1f}%)\n")
    return matched_questions, total_questions, rate


def run_server_check(
    name: str,
    display_name: str,
    cases: list[Case],
) -> dict[str, Any]:
    print(f"\n{'='*80}\nStarting Live Evaluation for: {display_name} ({name})\n{'='*80}")

    # 1. Start server
    start_res = cmd_start(name, [])
    if start_res != 0:
        raise RuntimeError(f"Failed to start server '{name}'")

    # Read server pid
    meta_path = _repo_root / "runs" / "_local" / f"{name}.json"
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    pid = int(meta["pid"])
    backend = meta.get("backend", "unknown")

    peak_rss_mb = get_process_rss_mb(pid)
    interpreter = build_interpreter(display_name)

    print(f"\n--- Evaluating 20 Handcrafted Cases ---")
    print(f"{'Case ID':<8} | {'Valid':<5} | {'Latency (ms)':<12} | {'EM':<5} | {'Labels'}")
    print("-" * 80)

    latencies_ms: list[float] = []
    valid_count = 0
    em_count = 0
    case_results = []

    for case in cases:
        decision = interpreter.decide(case)
        rss = get_process_rss_mb(pid)
        if rss > peak_rss_mb:
            peak_rss_mb = rss

        lat_ms = decision.latency_s * 1000.0
        latencies_ms.append(lat_ms)
        if decision.valid:
            valid_count += 1

        # Check Exact Match against truth
        em = (decision.valid and decision.labels == case.truth)
        if em:
            em_count += 1

        labels_str = str(decision.labels[0]) if decision.labels else "{}"
        print(f"{case.case_id:<8} | {str(decision.valid):<5} | {lat_ms:<12.1f} | {str(em):<5} | {labels_str}")
        if decision.error_type:
            print(f"  --> Error: {decision.error_type} (HTTP {decision.http_status})")

        case_results.append({
            "case_id": case.case_id,
            "valid": decision.valid,
            "error_type": decision.error_type,
            "latency_ms": lat_ms,
            "em": em,
            "labels": decision.labels,
        })

    p50_latency_ms = statistics.median(latencies_ms) if latencies_ms else 0.0
    valid_rate = (valid_count / len(cases)) * 100.0
    em_rate = (em_count / len(cases)) * 100.0

    print(f"\n20-Case Summary: Valid={valid_count}/{len(cases)} ({valid_rate:.1f}%), EM={em_count}/{len(cases)} ({em_rate:.1f}%), p50={p50_latency_ms:.1f}ms, Peak RSS={peak_rss_mb:.1f}MB")

    # 2. 64-option catalog test
    print(f"\n--- Running 64-Option Catalog Question ---")
    case_64 = make_catalog_case(64)
    dec_64 = interpreter.decide(case_64)
    rss = get_process_rss_mb(pid)
    if rss > peak_rss_mb:
        peak_rss_mb = rss
    lat_64_ms = dec_64.latency_s * 1000.0
    print(f"64-Option Result: Valid={dec_64.valid}, Latency={lat_64_ms:.1f}ms, Labels={dec_64.labels}, Error={dec_64.error_type}")

    # 3. 254-option catalog test
    print(f"\n--- Running 254-Option Catalog Question ---")
    case_254 = make_catalog_case(254)
    dec_254 = interpreter.decide(case_254)
    rss = get_process_rss_mb(pid)
    if rss > peak_rss_mb:
        peak_rss_mb = rss
    lat_254_ms = dec_254.latency_s * 1000.0
    print(f"254-Option Result: Valid={dec_254.valid}, Latency={lat_254_ms:.1f}ms, Labels={dec_254.labels}, Error={dec_254.error_type}")

    # 4. ~8K-token state test
    print(f"\n--- Running ~8K-Token State Question ---")
    case_8k = make_8k_state_case()
    dec_8k = interpreter.decide(case_8k)
    rss = get_process_rss_mb(pid)
    if rss > peak_rss_mb:
        peak_rss_mb = rss
    lat_8k_ms = dec_8k.latency_s * 1000.0
    print(f"8K-State Result: Valid={dec_8k.valid}, Latency={lat_8k_ms:.1f}ms, Tokens={dec_8k.input_tokens}, Error={dec_8k.error_type}")

    # 5. Stop server
    cmd_stop(name)

    return {
        "server": name,
        "display_name": display_name,
        "backend": backend,
        "valid_rate": valid_rate,
        "valid_count": valid_count,
        "total_cases": len(cases),
        "em_rate": em_rate,
        "em_count": em_count,
        "p50_latency_ms": p50_latency_ms,
        "peak_rss_mb": peak_rss_mb,
        "catalog_64": {
            "valid": dec_64.valid,
            "latency_ms": lat_64_ms,
            "error_type": dec_64.error_type,
        },
        "catalog_254": {
            "valid": dec_254.valid,
            "latency_ms": lat_254_ms,
            "error_type": dec_254.error_type,
        },
        "state_8k": {
            "valid": dec_8k.valid,
            "latency_ms": lat_8k_ms,
            "input_tokens": dec_8k.input_tokens,
            "error_type": dec_8k.error_type,
        },
        "case_results": case_results,
    }


def main() -> None:
    cases = load_cases_jsonl(FIXTURE_PATH)
    print(f"Loaded {len(cases)} handcrafted cases from {FIXTURE_PATH}")

    # SemIf shared-vs-direct check first (offline/in-process verification)
    semif_agreement = check_semif_shared_vs_direct_agreement(cases)

    # Roster of local servers to evaluate
    servers = [
        ("semif", "SemIf-Qwen3.5-4B"),
        ("laya", "Laya"),
        ("qwen_json", "Qwen3.5-4B-JSON"),
    ]

    all_results = []
    for name, disp in servers:
        res = run_server_check(name, disp, cases)
        all_results.append(res)

    # Final summary table
    print("\n" + "=" * 110)
    print("LIVE CHECK SUMMARY TABLE ACROSS LOCAL SERVERS")
    print("=" * 110)
    print(
        f"{'Server':<18} | {'Backend':<7} | {'Valid Rate':<10} | {'EM Rate':<8} | {'p50 (ms)':<9} | {'Peak RSS':<10} | "
        f"{'64-Opt':<12} | {'254-Opt':<12} | {'8K-State'}"
    )
    print("-" * 110)

    for r in all_results:
        c64 = "Valid" if r["catalog_64"]["valid"] else f"Fail ({r['catalog_64']['error_type']})"
        c64_str = f"{c64} ({r['catalog_64']['latency_ms']:.0f}ms)"
        c254 = "Valid" if r["catalog_254"]["valid"] else f"Fail ({r['catalog_254']['error_type']})"
        c254_str = f"{c254} ({r['catalog_254']['latency_ms']:.0f}ms)"
        c8k = "Valid" if r["state_8k"]["valid"] else f"Fail ({r['state_8k']['error_type']})"
        c8k_str = f"{c8k} ({r['state_8k']['latency_ms']:.0f}ms)"

        valid_str = f"{r['valid_count']}/{r['total_cases']} ({r['valid_rate']:.0f}%)"
        em_str = f"{r['em_count']}/{r['total_cases']} ({r['em_rate']:.0f}%)"
        rss_str = f"{r['peak_rss_mb']:.1f} MB"
        p50_str = f"{r['p50_latency_ms']:.1f}"

        print(
            f"{r['display_name']:<18} | {r['backend']:<7} | {valid_str:<10} | {em_str:<8} | {p50_str:<9} | {rss_str:<10} | "
            f"{c64_str:<12} | {c254_str:<12} | {c8k_str}"
        )

    print("=" * 110)

    out_file = _repo_root / "runs" / "_local" / "local_check_summary.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "semif_agreement": {
                    "matched": semif_agreement[0],
                    "total": semif_agreement[1],
                    "rate": semif_agreement[2],
                },
                "servers": all_results,
            },
            f,
            indent=2,
        )
    print(f"Results written to {out_file}")


if __name__ == "__main__":
    main()
