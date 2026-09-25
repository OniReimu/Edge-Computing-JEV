#!/usr/bin/env python3
"""Live smoke test for all hosted models in Edgebench manifest."""
from __future__ import annotations

import json
from pathlib import Path
import sys

# Ensure repo root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.edgebench.contract import Case, FIELD_SETS
from src.edgebench.manifest import build_interpreter, load_manifest

SMOKE_TEXT = (
    "Please read the text on this parcel photo, keep the image on site, "
    "it is urgent, standard quality is fine."
)


def run_smoke() -> list[dict]:
    manifest = load_manifest()
    hosted_models = [
        name
        for name, cfg in manifest.items()
        if cfg.get("deployment") == "hosted"
    ]

    case = Case(
        case_id="smoke-p2a",
        text=SMOKE_TEXT,
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[
            {
                "service_type": "ocr",
                "locality": "site_only",
                "quality_floor": "standard",
                "urgency": "urgent",
            }
        ],
    )

    results = []
    print(
        f"{'Model':<22} | {'Valid':<5} | {'Latency (s)':<11} | {'In/Out Tok':<10} | {'Cost (USD)':<10} | {'Resolved Model':<28} | {'Provider'}"
    )
    print("-" * 110)

    for model_name in hosted_models:
        interpreter = build_interpreter(model_name, manifest=manifest)
        decision = interpreter.decide(case)

        rec = {
            "display_name": model_name,
            "valid": decision.valid,
            "error_type": decision.error_type,
            "labels": decision.labels,
            "latency_s": round(decision.latency_s, 4),
            "input_tokens": decision.input_tokens,
            "output_tokens": decision.output_tokens,
            "reasoning_tokens": decision.reasoning_tokens,
            "cost_usd": decision.cost_usd,
            "resolved_model": decision.resolved_model,
            "provider": decision.provider,
        }
        results.append(rec)

        in_out = f"{decision.input_tokens}/{decision.output_tokens}"
        cost_str = f"${decision.cost_usd:.6f}"
        print(
            f"{model_name:<22} | {str(decision.valid):<5} | {decision.latency_s:<11.4f} | {in_out:<10} | {cost_str:<10} | {decision.resolved_model:<28} | {decision.provider}"
        )
        if decision.error_type:
            print(f"  --> Error: {decision.error_type} (HTTP {decision.http_status})")
        if decision.labels:
            print(f"  --> Labels: {decision.labels}")

    out_path = Path("runs/_smoke/smoke-P2a.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print("-" * 110)
    total_cost = sum(r["cost_usd"] for r in results)
    print(f"Smoke test complete. Results written to {out_path}. Total cost: ${total_cost:.6f}")
    return results


if __name__ == "__main__":
    run_smoke()
