"""RQ1b multi-request bundle messages with k in {1, 2, 4, 8}."""
from __future__ import annotations

import random
from typing import Any

from src.edgebench.contract import Case

BUNDLE_SEED = 20260924
BUNDLE_SIZES: list[int] = [1, 2, 4, 8]


def create_bundle_messages(
    clean_cases: list[Case],
    k: int,
    n_messages: int = 300,
    seed: int = BUNDLE_SEED,
) -> list[Case]:
    """Build n_messages bundle cases of size k from clean_cases of the same split.

    Guarantees:
    - No case reused within a single message.
    - Across messages, source cases are reused with balanced marginals.
    - Truth order strictly matches numbered request order.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    if len(clean_cases) < k:
        raise ValueError(
            f"Cannot build bundle of size {k} with only {len(clean_cases)} source cases"
        )

    sorted_clean = sorted(clean_cases, key=lambda c: c.case_id)
    rng = random.Random(seed + k * 1000 + n_messages)
    n_src = len(sorted_clean)

    # Permute source cases initially
    pool = list(sorted_clean)
    rng.shuffle(pool)

    bundle_cases: list[Case] = []
    split = sorted_clean[0].case_id.split("_")[1] if "_" in sorted_clean[0].case_id else "test"

    for msg_idx in range(n_messages):
        # Pick k distinct cases using cyclic offsets
        selected_cases = [pool[(msg_idx + step) % n_src] for step in range(k)]

        # Construct numbered text
        text_lines: list[str] = []
        truth_list: list[dict[str, str]] = []
        source_ids: list[str] = []

        for req_num, sc in enumerate(selected_cases, start=1):
            text_lines.append(f"Request {req_num}: {sc.text}")
            truth_list.append(dict(sc.truth[0]))
            source_ids.append(sc.case_id)

        full_text = "\n".join(text_lines)

        meta: dict[str, Any] = {
            "bundle_size": k,
            "source_case_ids": source_ids,
            "message_index": msg_idx,
            "derivation": f"bundle_k{k}",
            "generator": [sc.meta.get("generator", "") for sc in selected_cases],
            "verifier": [sc.meta.get("verifier", "") for sc in selected_cases],
            "generator_model": [sc.meta.get("generator_model", "") for sc in selected_cases],
            "verifier_model": [sc.meta.get("verifier_model", "") for sc in selected_cases],
            "prompt_sha256": [sc.meta.get("prompt_sha256") for sc in selected_cases],
        }

        b_case = Case(
            case_id=f"RQ1b_k{k}_{split}_{msg_idx:04d}",
            text=full_text,
            fields=list(selected_cases[0].fields),
            service_options=selected_cases[0].service_options,
            bundle_size=k,
            truth=truth_list,
            meta=meta,
        )
        bundle_cases.append(b_case)

    return bundle_cases
