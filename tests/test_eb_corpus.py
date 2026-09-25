"""Offline tests for EdgeIntent v1 corpus builder (mocked LLM transport)."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import re
from typing import Any

import pytest
import tiktoken

from src.edgebench.contract import (
    Case,
    DEFAULT_CRITERIA,
    SERVICE_PRECEDENCE_RULE,
    dump_cases_jsonl,
    load_cases_jsonl,
)
from src.edgebench.corpus.assemble import (
    compute_sha256,
    generate_manifest,
    generate_stats_markdown,
    select_stratified_timing_subset,
)
from src.edgebench.corpus.bundle import BUNDLE_SIZES, create_bundle_messages
from src.edgebench.corpus.catalog import (
    build_nested_and_churn_catalogs,
    get_services_catalog,
    is_valid_unsupported_target,
    verify_catalog_invariants,
)
from src.edgebench.corpus.catalog_data import FAMILIES, RAW_NOVEL_SERVICES, RAW_SERVICES
from src.edgebench.corpus.client import CorpusLLMClient
from src.edgebench.corpus.noise import (
    NEGATORS,
    apply_noise_to_text,
    derive_noise_cases,
    is_negator,
)
from src.edgebench.corpus.pad import (
    STOP_PATTERNS,
    TARGET_LENGTHS,
    assert_padding_clean,
    create_padded_dataset,
    get_tokenizer,
)
from src.edgebench.corpus.lints import (
    check_catalog_leak_lint,
    check_copy_4gram_lint,
    check_diversity_lint,
    check_scaffold_lint,
    get_top_repeated_5grams,
)
from src.edgebench.corpus.pipeline import CorpusPipeline, VerifiedCase
from src.edgebench.corpus.prompts import (
    build_generator_batch_prompt,
    build_single_item_generator_prompt,
    build_verifier_batch_prompt,
)
from src.edgebench.corpus.tuples import (
    ALL_SERVICES_MAP,
    EDGE_SCENARIOS,
    RQ4_CONDITIONS,
    WORDING_FAMILIES,
    TupleItem,
    is_rq4_condition,
    sample_balanced_sequence,
    sample_tuples_for_condition,
)
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.interpreters.decisions import DecisionsClient


def test_nested_catalogs_and_subsets():
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    services_data = get_services_catalog()
    verify_catalog_invariants(services_data, catalogs)

    c4 = catalogs["C_4"]
    c15 = catalogs["C_15"]
    c64 = catalogs["C_64"]
    c128 = catalogs["C_128"]
    c254 = catalogs["C_254"]

    assert len(c4) == 4
    assert len(c15) == 15
    assert len(c64) == 64
    assert len(c128) == 128
    assert len(c254) == 254

    # Strict subset chaining
    assert set(c4).issubset(set(c15))
    assert set(c15).issubset(set(c64))
    assert set(c64).issubset(set(c128))
    assert set(c128).issubset(set(c254))

    # Base services present in C_4
    assert "count" in c4
    assert "detection" in c4
    assert "ocr" in c4


def test_churn_replacement_counts_exact():
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    v0 = set(catalogs["v0"])
    v25 = set(catalogs["v25"])
    v50 = set(catalogs["v50"])
    c254 = set(catalogs["C_254"])

    assert len(v0) == 64
    assert len(v25) == 64
    assert len(v50) == 64

    # v25 replaces 16 services
    assert len(v0 - v25) == 16
    assert len(v25 - v0) == 16

    # v50 replaces 32 services
    assert len(v0 - v50) == 32
    assert len(v50 - v0) == 32

    # All services in v25 and v50 are from C_254
    assert v25.issubset(c254)
    assert v50.issubset(c254)


def test_balanced_marginals():
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    novel_ids = [s["id"] for s in RAW_NOVEL_SERVICES]

    # Test balanced marginals for RQ2, RQ3, and RQ4
    test_conditions = ["clean", "F4_low", "F6_medium", "F8_high", "K4", "K64", "churn25"]

    for cond in test_conditions:
        for split, n in [("test", 300), ("dev", 60)]:
            tuples = sample_tuples_for_condition(
                condition=cond,
                split=split,
                n=n,
                base_seed=20260924,
                catalogs=catalogs,
                novel_service_ids=novel_ids,
            )
            assert len(tuples) == n

            # Check marginals for non-service fields
            fields = list(tuples[0].tuple_labels.keys())
            if cond == "clean":
                # RQ2 shared set: every tuple has >= 1 unspecified non-service field, and the tuples are
                # balanced over the 19 admissible (locality, quality_floor, urgency) combinations.
                non_svc = [f for f in fields if f != "service_type"]
                combos = Counter(tuple(t.tuple_labels[f] for f in non_svc) for t in tuples)
                assert all("unspecified" in c for c in combos)
                assert len(combos) == 3 ** len(non_svc) - 2 ** len(non_svc)
                assert all(cnt in (n // len(combos), n // len(combos) + 1) for cnt in combos.values())
                fields = ["service_type"]
            for f in fields:
                if f == "service_type" and is_rq4_condition(cond):
                    # RQ4 service distribution is 90% catalog + 10% unsupported
                    unsupp = [t for t in tuples if t.tuple_labels[f] == "unsupported"]
                    assert len(unsupp) == round(n * 0.10)
                    continue

                vals = [t.tuple_labels[f] for t in tuples]
                counts = Counter(vals)
                k = len(counts)
                base = n // k
                for val, cnt in counts.items():
                    assert cnt in (base, base + 1), (
                        f"Condition {cond} split {split} field {f} val {val} count {cnt} not in ({base}, {base+1})"
                    )


def test_dev_test_disjointness():
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    novel_ids = [s["id"] for s in RAW_NOVEL_SERVICES]

    test_tuples = sample_tuples_for_condition(
        condition="clean", split="test", n=300, base_seed=20260924, catalogs=catalogs
    )
    dev_tuples = sample_tuples_for_condition(
        condition="clean", split="dev", n=60, base_seed=20260924, catalogs=catalogs
    )

    test_ids = {t.tuple_id for t in test_tuples}
    dev_ids = {t.tuple_id for t in dev_tuples}
    assert test_ids.isdisjoint(dev_ids), "Dev and test tuple IDs must be completely disjoint"

    # Separate seeds by construction
    assert len(test_tuples) == 300
    assert len(dev_tuples) == 60


def test_noise_never_touches_negators_and_is_deterministic():
    clean_cases = [
        Case(
            case_id="clean_test_0001",
            text="Please do not send image to cloud. We never want offsite execution.",
            truth=[{"service_type": "ocr", "locality": "site_only"}],
        ),
        Case(
            case_id="clean_test_0002",
            text="Ensure data cannot leave without approval. Nobody should transfer it.",
            truth=[{"service_type": "detection", "locality": "site_only"}],
        ),
        Case(
            case_id="clean_test_0003",
            text="Don't retain photos and won't tolerate delay. Can't allow storage.",
            truth=[{"service_type": "count", "retention": "discard_after_use"}],
        ),
    ]

    # Determinism
    noisy_a = derive_noise_cases(clean_cases, seed=20260924)
    noisy_b = derive_noise_cases(clean_cases, seed=20260924)
    for ca, cb in zip(noisy_a, noisy_b):
        assert ca.text == cb.text, "Noise derivation must be deterministic under seed"

    # Preserves negators across 200 random seeds
    sample_text = (
        "We do not want remote. Never send offsite. Nobody can transfer without notice. "
        "It cannot leave. Don't store data. Won't tolerate failure. Can't allow delay."
    )
    for s in range(200):
        rng = random.Random(s)
        noisy = apply_noise_to_text(sample_text, rng, p=0.08)
        noisy_words = set(noisy.lower().split())
        for neg in ["not", "never", "nobody", "cannot", "without"]:
            assert neg in noisy_words, f"Negator '{neg}' was altered or deleted under seed {s}!"


def test_padding_lengths_and_stop_list():
    clean_cases = [
        Case(
            case_id="clean_test_0001",
            text="Count items on the factory line. High precision is needed right now.",
            truth=[{"service_type": "count"}],
        )
    ]

    for target in TARGET_LENGTHS:
        padded = create_padded_dataset(clean_cases, target_length=target, seed=20260924)
        assert len(padded) == 1
        p_case = padded[0]

        enc = get_tokenizer()
        tok_len = len(enc.encode(p_case.text))
        err = abs(tok_len - target) / target
        assert err <= 0.03, f"Padded tokens {tok_len} error {err:.4f} > 3% for target {target}"

        # Stop-words lint on the padded context
        assert_padding_clean(p_case.text.replace(clean_cases[0].text, ""))


def test_bundle_truth_order_and_distinctness():
    clean_cases = [
        Case(
            case_id=f"clean_test_{i:04d}",
            text=f"Process request payload {i}",
            truth=[{"service_type": "ocr", "item": str(i)}],
        )
        for i in range(60)
    ]

    for k in BUNDLE_SIZES:
        bundles = create_bundle_messages(clean_cases, k=k, n_messages=30, seed=20260924)
        for b in bundles:
            assert b.bundle_size == k
            assert len(b.truth) == k
            src_ids = b.meta["source_case_ids"]

            # Distinct cases within message
            assert len(src_ids) == len(set(src_ids)), f"Duplicate case found in bundle k={k}"

            # Truth order matches numbering
            for req_idx, t in enumerate(b.truth, start=1):
                assert f"Request {req_idx}:" in b.text


def test_verifier_accept_reject_regenerate_and_replacement(tmp_path: Path):
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    services_data = get_services_catalog()
    all_svcs = {s["id"]: s for s in services_data["services"] + services_data["novel_services"]}

    tuples = [
        TupleItem(
            condition="clean",
            split="test",
            tuple_id="clean_test_0001",
            tuple_labels={"service_type": "ocr", "locality": "site_only"},
            meta={"wording_family": "operator ticket"},
        ),
        TupleItem(
            condition="clean",
            split="test",
            tuple_id="clean_test_0002",
            tuple_labels={"service_type": "count", "locality": "remote_allowed"},
            meta={"wording_family": "casual chat"},
        ),
    ]

    call_count = 0

    # Mock transport
    def mock_transport(payload: dict[str, Any]):
        nonlocal call_count
        call_count += 1
        model = payload["model"]

        if "claude-sonnet-5" in model:
            # Generator response
            user_msg = payload["messages"][1]["content"]
            specs = json.loads(user_msg.split("specifications:\n\n")[1])
            items = []
            for sp in specs:
                items.append({"id": sp["id"], "text": f"Generated text for {sp['id']}"})
            resp_body = {
                "model": model,
                "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001},
                "choices": [{"message": {"content": json.dumps({"items": items})}}],
            }
        else:
            # Blind verifier response
            user_msg = payload["messages"][1]["content"]
            batch_input = json.loads(user_msg.split("the batch:\n\n")[1])
            items = []
            for b in batch_input:
                tid = b["id"]
                if tid == "clean_test_0001":
                    # Correct labels on attempt 1
                    items.append({
                        "id": tid,
                        "labels": {"service_type": "ocr", "locality": "site_only"},
                    })
                elif tid == "clean_test_0002":
                    # Reject on first attempt, match on second attempt
                    if call_count <= 2:
                        items.append({
                            "id": tid,
                            "labels": {"service_type": "count", "locality": "unspecified"},  # wrong
                        })
                    else:
                        items.append({
                            "id": tid,
                            "labels": {"service_type": "count", "locality": "remote_allowed"},  # match
                        })
            resp_body = {
                "model": model,
                "usage": {"prompt_tokens": 80, "completion_tokens": 40, "cost": 0.0008},
                "choices": [{"message": {"content": json.dumps({"items": items})}}],
            }

        return 200, json.dumps(resp_body), 0.1, None

    client = CorpusLLMClient(
        log_dir=tmp_path / "runs",
        transport_override=mock_transport,
    )
    pipeline = CorpusPipeline(
        client=client,
        service_catalog=all_svcs,
        catalogs=catalogs,
        accepted_dir=tmp_path / "accepted",
        batch_size=10,
    )

    cases, yield_rate = pipeline.run_condition_split(
        condition="clean", split="test", tuples=tuples
    )

    assert len(cases) == 2
    assert yield_rate == 0.5  # 1 accepted first pass, 1 required retry
    assert cases[0].attempts == 1
    assert cases[1].attempts == 2


def test_resume_skips_accepted_items(tmp_path: Path):
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    services_data = get_services_catalog()
    all_svcs = {s["id"]: s for s in services_data["services"] + services_data["novel_services"]}

    tuples = [
        TupleItem(
            condition="clean",
            split="test",
            tuple_id="clean_test_0001",
            tuple_labels={"service_type": "ocr", "locality": "site_only"},
            meta={},
        )
    ]

    calls_made = 0

    def mock_transport(payload: dict[str, Any]):
        nonlocal calls_made
        calls_made += 1
        model = payload["model"]
        if "claude" in model:
            items = [{"id": "clean_test_0001", "text": "OCR locally"}]
        else:
            items = [{"id": "clean_test_0001", "labels": {"service_type": "ocr", "locality": "site_only"}}]
        resp_body = {
            "model": model,
            "usage": {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.0001},
            "choices": [{"message": {"content": json.dumps({"items": items})}}],
        }
        return 200, json.dumps(resp_body), 0.05, None

    client = CorpusLLMClient(
        log_dir=tmp_path / "runs",
        transport_override=mock_transport,
    )
    pipeline = CorpusPipeline(
        client=client,
        service_catalog=all_svcs,
        catalogs=catalogs,
        accepted_dir=tmp_path / "accepted",
        batch_size=10,
    )

    # First run: processes item
    cases1, _ = pipeline.run_condition_split("clean", "test", tuples)
    assert len(cases1) == 1
    assert calls_made == 2  # 1 gen + 1 ver

    # Second run: item is already in accepted dir -> skips LLM calls
    cases2, _ = pipeline.run_condition_split("clean", "test", tuples)
    assert len(cases2) == 1
    assert calls_made == 2  # No new calls made!


def test_manifest_hashes_match_file_bytes(tmp_path: Path):
    # Create sample corpus directory structure
    cond_dir = tmp_path / "RQ2" / "clean"
    cond_dir.mkdir(parents=True)
    sample_cases = [
        Case(case_id="case_1", text="Sample request 1", truth=[{"service_type": "ocr"}]),
        Case(case_id="case_2", text="Sample request 2", truth=[{"service_type": "detection"}]),
    ]
    dump_cases_jsonl(sample_cases, cond_dir / "test.jsonl")
    dump_cases_jsonl(sample_cases, cond_dir / "dev.jsonl")

    # Generate manifest
    yields = {"clean": {"target_n": 2, "first_pass_accepted": 1, "accepted": 2, "first_pass": 0.5, "final": 1.0}}
    manifest = generate_manifest(tmp_path, yields=yields, total_cost_usd=1.23, seed=20260924)

    # Verify every hash matches actual file bytes
    for rel_path, expected_hash in manifest["files"].items():
        file_path = tmp_path / rel_path
        assert file_path.exists()
        actual_hash = compute_sha256(file_path)
        assert actual_hash == expected_hash, f"SHA-256 mismatch for {rel_path}"

    # Verify stats markdown generation
    stats_md = generate_stats_markdown(tmp_path, yields=yields)
    assert (tmp_path / "stats.md").exists()
    assert "RQ2/clean" in stats_md
    assert "| 50.0% | 100.0% |" in stats_md


def test_scenario_balance():
    assert len(EDGE_SCENARIOS) >= 40, f"Expected >= 40 distinct scenarios, got {len(EDGE_SCENARIOS)}"
    n = len(EDGE_SCENARIOS) * 2  # 90 items
    tuples = sample_tuples_for_condition(
        condition="clean", split="test", n=n, base_seed=20260924
    )
    assert len(tuples) == n
    scenarios = [t.meta["scenario"] for t in tuples]
    counts = Counter(scenarios)
    assert len(counts) == len(EDGE_SCENARIOS)
    for sc, cnt in counts.items():
        assert cnt == 2, f"Scenario {sc} expected count 2, got {cnt}"


def test_forbidden_scaffold_regexes():
    bad_texts = [
        "Please process camera stream 1 and alert security.",
        "Camera stream 4 must be processed site only.",
        "Inspect camera 2 immediately.",
        "This request is for shift A operations.",
        "Shift B requires high priority execution.",
        "Ticket #1024 requires OCR on site.",
        "Correction: process on site, not remotely.",
        "CORRECTION: keep data in the cloud.",
    ]
    for bad in bad_texts:
        ok, reason = check_scaffold_lint(bad)
        assert not ok, f"Scaffold should have been caught in: {bad}"
        assert reason is not None and "Forbidden scaffold" in reason

    good_texts = [
        "Monitor patient vital sensors in the ward with high urgency.",
        "Keep drone footage strictly on site and process with high quality.",
        "We initially considered remote execution, but keep everything on site.",
        "Inspect cargo container integrity for the evening shift.",
    ]
    for good in good_texts:
        ok, reason = check_scaffold_lint(good)
        assert ok, f"Valid text falsely rejected: {good} (reason: {reason})"


def test_revision_instruction_targets_specified_field_and_diff_value():
    for cond in ("F8_high", "revised"):
        tuples = sample_tuples_for_condition(
            condition=cond, split="test", n=20, base_seed=20260924
        )
        assert len(tuples) == 20
        for t in tuples:
            assert "revision_field" in t.meta, f"Missing revision_field in {t.tuple_id}"
            assert "revision_initial_value" in t.meta, f"Missing revision_initial_value in {t.tuple_id}"

            rev_field = t.meta["revision_field"]
            init_val = t.meta["revision_initial_value"]
            target_val = t.tuple_labels[rev_field]

            # Targets a specified field
            assert target_val != "unspecified", (
                f"{t.tuple_id}: revision_field {rev_field} must be specified (got unspecified)"
            )
            # Initial value != target value
            assert init_val != target_val, (
                f"{t.tuple_id}: initial value {init_val} must not equal target value {target_val}"
            )

        # Check prompt formatting
        sys_p, user_p, _ = build_generator_batch_prompt(tuples[:2], service_descriptions={})
        assert "REVISION of" in user_p
        assert "Do NOT use 'Correction:'" in user_p


def test_diversity_lint_rejects_synthetic_duplicates():
    # 20 texts: 2 share the same opening 4-word span -> 2/20 = 10% > 5% limit -> reject!
    texts_dup_opening = [
        f"Text number {i} with completely unique words here for diversity testing"
        for i in range(18)
    ]
    texts_dup_opening.append("Please monitor the hospital ward camera with urgent attention")
    texts_dup_opening.append("Please monitor the hospital ward scanner with normal priority")

    passed, viol_indices, details = check_diversity_lint(
        texts_dup_opening, max_5gram_ratio=0.10, max_opening_4gram_ratio=0.05
    )
    assert not passed
    assert 19 in viol_indices

    # 20 texts: 3 share the same 5-gram -> 3/20 = 15% > 10% limit -> reject!
    texts_dup_5gram = [
        f"Unique sentence number {i} for testing n-gram diversity independently"
        for i in range(17)
    ]
    texts_dup_5gram.append("first run must keep all data on premise now")
    texts_dup_5gram.append("second run must keep all data on premise today")
    texts_dup_5gram.append("third run must keep all data on premise always")

    passed_5g, viol_5g, _ = check_diversity_lint(
        texts_dup_5gram, max_5gram_ratio=0.10, max_opening_4gram_ratio=0.05
    )
    assert not passed_5g
    assert 19 in viol_5g

    # 20 completely distinct texts pass
    unique_texts = [
        f"Subject {i} operates in scenario {i * 7} requiring capability {i * 13} cleanly"
        for i in range(20)
    ]
    passed_clean, viol_clean, _ = check_diversity_lint(
        unique_texts, max_5gram_ratio=0.10, max_opening_4gram_ratio=0.05
    )
    assert passed_clean
    assert len(viol_clean) == 0


def test_precedence_rule_in_three_consumers():
    cat_case = Case(
        case_id="case_cat",
        text="Count vehicles at gate.",
        fields=["service_type", "locality", "quality_floor", "urgency"],
        service_options={"count": "count objects fallback", "unsupported": "unsupported service"},
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
    )

    non_cat_case = Case(
        case_id="case_non_cat",
        text="Count vehicles at gate.",
        fields=["service_type", "locality", "quality_floor", "urgency"],
        service_options=None,
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
    )

    # 1. Decision question
    dec_client = DecisionsClient()
    cat_req = dec_client.build_request(cat_case)
    non_cat_req = dec_client.build_request(non_cat_case)
    assert SERVICE_PRECEDENCE_RULE in cat_req["questions"]["r1__service_type"]["instructions"]
    assert SERVICE_PRECEDENCE_RULE not in non_cat_req["questions"]["r1__service_type"]["instructions"]

    # 2. Chat system prompt
    chat_client = ChatJsonClient(name="test", model="m", provider_slug="p")
    cat_sys = chat_client.build_system_prompt(cat_case)
    non_cat_sys = chat_client.build_system_prompt(non_cat_case)
    assert SERVICE_PRECEDENCE_RULE in cat_sys
    assert SERVICE_PRECEDENCE_RULE not in non_cat_sys

    # 3. Verifier prompt
    cat_ver_sys, _, _ = build_verifier_batch_prompt(
        [("c1", "text")], fields=cat_case.fields, service_options=cat_case.service_options
    )
    non_cat_ver_sys, _, _ = build_verifier_batch_prompt(
        [("c1", "text")], fields=non_cat_case.fields, service_options=None
    )
    assert SERVICE_PRECEDENCE_RULE in cat_ver_sys
    assert SERVICE_PRECEDENCE_RULE not in non_cat_ver_sys


def test_novel_service_prefilter():
    # All 40 novel services in catalog_data must pass
    for s in RAW_NOVEL_SERVICES:
        assert is_valid_unsupported_target(s), (
            f"Novel service {s['id']} failed unsupported pre-filter: {s['description']}"
        )

    # Counter / detector / OCR tasks must fail
    invalid_services = [
        {"id": "inv1", "name": "Bee Counter", "family": "agriculture", "description": "count bees entering hive"},
        {"id": "inv2", "name": "Sea Lice Counter", "family": "marine", "description": "identify and count sea lice"},
        {"id": "inv3", "name": "Drone Detector", "family": "security", "description": "detect and localize rogue drones"},
        {"id": "inv4", "name": "Sign Reader", "family": "transport", "description": "read text on highway speed signs"},
        {"id": "inv5", "name": "Object Tally", "family": "object_counting", "description": "tally items in box"},
        {"id": "inv6", "name": "Box Locator", "family": "object_detection", "description": "find bounding box for items"},
        {"id": "inv7", "name": "OCR Tool", "family": "text_reading", "description": "perform optical character recognition"},
    ]
    for inv in invalid_services:
        assert not is_valid_unsupported_target(inv), f"Service should have been rejected: {inv['id']}"

    # Sample RQ4 tuples and verify out-of-catalog picks pass
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    services_data = get_services_catalog()
    all_svcs = {s["id"]: s for s in services_data["services"] + services_data["novel_services"]}
    novel_ids = [s["id"] for s in services_data["novel_services"]]

    for cond in ("K15", "K254", "churn50"):
        tuples = sample_tuples_for_condition(
            condition=cond, split="test", n=20, base_seed=20260924,
            catalogs=catalogs, novel_service_ids=novel_ids,
        )
        for t in tuples:
            if t.meta.get("is_unsupported"):
                target_svc = all_svcs[t.meta["target_service"]]
                assert is_valid_unsupported_target(target_svc), (
                    f"Condition {cond}: unsupported target {target_svc['id']} must pass prefilter"
                )


def test_4gram_copy_lint():
    criteria_descs = [
        "data must stay at the originating site",
        "remote processing explicitly allowed",
        "high quality explicitly required",
    ]
    target_svc_desc = "read courier tracking barcode text and shipping addresses from package labels"

    # Verbatim 4-word span from criteria description -> reject
    bad_criteria_text = "Please ensure data must stay at the originating site for compliance."
    ok1, reason1 = check_copy_4gram_lint(bad_criteria_text, criteria_descs, target_svc_desc)
    assert not ok1
    assert "Verbatim 4-word span copied" in str(reason1)

    # Verbatim 4-word span from target service description -> reject
    bad_service_text = "The system should read courier tracking barcode text from the carton."
    ok2, reason2 = check_copy_4gram_lint(bad_service_text, criteria_descs, target_svc_desc)
    assert not ok2
    assert "Verbatim 4-word span copied" in str(reason2)

    # Clean text with original wording and common terms (on site, OCR, urgent) -> pass
    clean_text = "Keep all camera frames on site. Execute OCR with high quality and urgent priority."
    ok3, reason3 = check_copy_4gram_lint(clean_text, criteria_descs, target_svc_desc)
    assert ok3
    assert reason3 is None


def test_catalog_wording_leak_and_lint():
    # 1. Non-RQ4 prompt check: RQ2 prompt uses DEFAULT_CRITERIA and none of the catalog leak words
    services_data = get_services_catalog()
    catalog_service_descs = {s["id"]: s["description"] for s in services_data["services"]}

    tuples = [
        TupleItem(
            condition="clean",
            split="test",
            tuple_id="clean_test_0001",
            tuple_labels={"service_type": "count", "locality": "site_only", "quality_floor": "high", "urgency": "normal"},
            meta={"scenario": "retail shelf scanner", "wording_family": "casual chat"},
        ),
        TupleItem(
            condition="revised",
            split="test",
            tuple_id="revised_test_0001",
            tuple_labels={"service_type": "ocr", "locality": "remote_allowed"},
            meta={
                "scenario": "parcel locker kiosk",
                "wording_family": "operator ticket",
                "revision_field": "service_type",
                "revision_initial_value": "detection",
            },
        ),
    ]

    sys_p, user_p, _ = build_generator_batch_prompt(tuples, catalog_service_descs)
    # Default description should be present
    assert DEFAULT_CRITERIA["service_type"]["count"] in user_p
    assert DEFAULT_CRITERIA["service_type"]["ocr"] in user_p
    assert DEFAULT_CRITERIA["service_type"]["detection"] in user_p

    # Forbidden leak words should NOT appear in the RQ2 user prompt
    leak_words = ["fallback", "generic", "general-purpose", "specialized", "specialised", "dedicated"]
    for w in leak_words:
        assert not re.search(r"\b" + re.escape(w) + r"\b", user_p, re.IGNORECASE), (
            f"Forbidden catalog wording '{w}' found in RQ2 generator prompt!"
        )

    # 2. check_catalog_leak_lint tests
    bad_texts = [
        "Please run the generic counting fallback since none apply.",
        "Use a specialized detector for this camera.",
        "Run the specialised tool for our tasks.",
        "This requires a dedicated pipeline on site.",
        "A general-purpose fallback model is sufficient.",
        "A general purpose model will do fine.",
    ]
    for bad in bad_texts:
        ok, reason = check_catalog_leak_lint(bad)
        assert not ok, f"Catalog leak lint failed to catch: {bad}"
        assert reason is not None and "Catalog wording leak" in reason

    good_texts = [
        "Count all items on the shelf accurately.",
        "Read text from the delivery slip on site.",
        "Detect objects in the frame with bounding boxes.",
        "Keep the data strictly on premise with normal urgency.",
    ]
    for good in good_texts:
        ok, reason = check_catalog_leak_lint(good)
        assert ok, f"Valid non-RQ4 text falsely rejected: {good} (reason: {reason})"


def test_rq4_conditions_membership():
    # 1. keyvalue is explicitly NOT RQ4
    assert "keyvalue" not in RQ4_CONDITIONS
    assert not is_rq4_condition("keyvalue")
    assert not is_rq4_condition("RQ2/keyvalue")

    # 2. All RQ4 conditions are in RQ4_CONDITIONS and is_rq4_condition
    expected_rq4 = {"K4", "K15", "K64", "K128", "K254", "churn25", "churn50"}
    assert RQ4_CONDITIONS == expected_rq4
    for cond in expected_rq4:
        assert cond in RQ4_CONDITIONS
        assert is_rq4_condition(cond)
        assert is_rq4_condition(f"RQ4/{cond}")
        assert is_rq4_condition(f"RQ4_{cond}")

    # 3. Non-RQ4 conditions are not RQ4
    non_rq4 = [
        "clean", "colloquial", "negation", "codeswitch", "defaultbait", "revised", "keyvalue",
        "F4_low", "F4_medium", "F4_high",
        "F6_low", "F6_medium", "F6_high",
        "F8_low", "F8_medium", "F8_high",
    ]
    for c in non_rq4:
        assert c not in RQ4_CONDITIONS
        assert not is_rq4_condition(c)


def test_rq4_scenario_and_prompt_setting():
    catalogs = build_nested_and_churn_catalogs(seed=20260924)
    services_data = get_services_catalog()
    all_svcs = {s["id"]: s["description"] for s in services_data["services"] + services_data["novel_services"]}
    novel_ids = [s["id"] for s in services_data["novel_services"]]

    expected_setting_line = (
        "- Setting: choose one concrete, realistic deployment setting in which the needed capability is naturally used "
        "(vary the setting; do not default to a retail store, warehouse or factory unless the capability belongs there)."
    )

    # 1. Test all RQ4 conditions: tuples have generator-chosen, prompts contain Setting line and NO Scenario line
    for cond in RQ4_CONDITIONS:
        tuples = sample_tuples_for_condition(
            condition=cond,
            split="test",
            n=20,
            base_seed=20260924,
            catalogs=catalogs,
            novel_service_ids=novel_ids,
        )
        for t in tuples:
            assert t.meta["scenario"] == "generator-chosen", (
                f"Tuple {t.tuple_id} under {cond} had scenario '{t.meta.get('scenario')}' instead of 'generator-chosen'"
            )
            p = build_single_item_generator_prompt(t, all_svcs)
            assert expected_setting_line in p, f"Missing setting line in prompt for {t.tuple_id}"
            assert "- Scenario:" not in p, f"Forbidden - Scenario: line in prompt for {t.tuple_id}"

        # Also check batch prompt
        _, user_p, _ = build_generator_batch_prompt(tuples[:5], all_svcs)
        assert '"setting":' in user_p
        assert '"scenario":' not in user_p

    # 2. Golden comparison for RQ2 and RQ3: prompts unchanged, contain - Scenario: and NO - Setting:
    golden_rq2_clean = (
        "You are an expert synthetic data generator creating realistic edge service request texts. "
        "Write a single natural request text meeting the exact specifications below.\n\n"
        "HARD RULES:\n"
        "1. State every specified requirement exactly once in natural language.\n"
        "2. Do NOT state or imply any requirement for unspecified fields.\n"
        "3. NEVER use field names (service_type, locality, quality_floor, urgency, retention, energy, redundancy, latency_class) "
        "or internal option IDs (site_only, remote_allowed, discard_after_use, standard, high, normal, urgent) verbatim.\n"
        "4. Length: 1–3 sentences (email or formal SLA clause may be up to 4 sentences).\n"
        "5. English unless code-switching instructions specify another language.\n"
        "6. FORBIDDEN SCAFFOLDS: Never use fixed scaffolds or repetitive framing. DO NOT use 'camera stream N' or 'camera N', "
        "'shift A/B' (or lettered shifts), 'Ticket #NNNN' or ticket headers, or 'Correction:' / 'CORRECTION:' prefix. "
        "Express operational context naturally without these scaffolds.\n"
        "7. NO VERBATIM PHRASE COPYING: Never copy contiguous 4-word spans from field criteria or service descriptions. "
        "Express requirements in your own words. Common 1-3 word terms like 'OCR', 'on site', 'urgent' alone are fine.\n\n"
        "SPECIFICATIONS:\n"
        "- Scenario: petrochemical pipeline pressure sensor\n"
        "- Wording family: operator ticket\n"
        "- Condition instructions: Write the request cleanly, directly, and unambiguously.\n"
        "- Specified requirements:\n"
        "- Needed service capability: count objects: return only a number\n"
        "- Processing quality tier: standard quality explicitly sufficient\n"
        "- Urgency / priority: urgent or priority processing explicitly requested\n"
        "- Fields to leave unmentioned:\n"
        "- Data locality / processing location\n"
    )

    golden_rq3_f8_low = (
        "You are an expert synthetic data generator creating realistic edge service request texts. "
        "Write a single natural request text meeting the exact specifications below.\n\n"
        "HARD RULES:\n"
        "1. State every specified requirement exactly once in natural language.\n"
        "2. Do NOT state or imply any requirement for unspecified fields.\n"
        "3. NEVER use field names (service_type, locality, quality_floor, urgency, retention, energy, redundancy, latency_class) "
        "or internal option IDs (site_only, remote_allowed, discard_after_use, standard, high, normal, urgent) verbatim.\n"
        "4. Length: 1–3 sentences (email or formal SLA clause may be up to 4 sentences).\n"
        "5. English unless code-switching instructions specify another language.\n"
        "6. FORBIDDEN SCAFFOLDS: Never use fixed scaffolds or repetitive framing. DO NOT use 'camera stream N' or 'camera N', "
        "'shift A/B' (or lettered shifts), 'Ticket #NNNN' or ticket headers, or 'Correction:' / 'CORRECTION:' prefix. "
        "Express operational context naturally without these scaffolds.\n"
        "7. NO VERBATIM PHRASE COPYING: Never copy contiguous 4-word spans from field criteria or service descriptions. "
        "Express requirements in your own words. Common 1-3 word terms like 'OCR', 'on site', 'urgent' alone are fine.\n\n"
        "SPECIFICATIONS:\n"
        "- Scenario: ferry terminal passenger gangway\n"
        "- Wording family: operator ticket\n"
        "- Condition instructions: State each specified requirement directly and clearly once.\n"
        "- Specified requirements:\n"
        "- Needed service capability: OCR: read text from an image\n"
        "- Data locality / processing location: data must stay at the originating site\n"
        "- Processing quality tier: standard quality explicitly sufficient\n"
        "- Urgency / priority: normal priority explicitly requested, including not urgent\n"
        "- Energy profile / mode: maximum performance or low-latency mode explicitly required\n"
        "- Instance redundancy / availability: replicated execution or high availability explicitly required\n"
        "- Latency deadline class: interactive processing latency explicitly requested\n"
        "- Fields to leave unmentioned:\n"
        "- Data retention / storage\n"
    )

    t_clean = sample_tuples_for_condition("clean", "test", 1, base_seed=20260924)[0]
    p_clean = build_single_item_generator_prompt(t_clean, all_svcs)
    assert p_clean == golden_rq2_clean, f"RQ2 clean prompt changed unexpectedly:\n{p_clean}"

    t_f8_low = sample_tuples_for_condition("F8_low", "test", 1, base_seed=20260924)[0]
    p_f8_low = build_single_item_generator_prompt(t_f8_low, all_svcs)
    assert p_f8_low == golden_rq3_f8_low, f"RQ3 F8_low prompt changed unexpectedly:\n{p_f8_low}"


def test_revision_example_wording_no_criteria_copy():
    services_data = get_services_catalog()
    all_svcs = {s["id"]: s["description"] for s in services_data["services"]}

    expected_agnostic_instruction = (
        "The earlier statement and the later update must both concern the revised field only; "
        "phrase the update the way a real operator would (e.g. a follow-up remark, a changed decision, a clarification from a colleague). "
        'Paraphrase both values; do not copy their wording, and do not mention any field listed under "Fields to leave unmentioned".'
    )
    expected_unmentioned_phrase = 'do not mention any field listed under "Fields to leave unmentioned"'

    for cond in ("revised", "F4_high", "F6_high", "F8_high"):
        tuples = sample_tuples_for_condition(cond, "test", 30, base_seed=20260924)
        for t in tuples:
            p = build_single_item_generator_prompt(t, all_svcs)
            rev_field = t.meta.get("revision_field")
            if rev_field:
                assert "overnight" not in p, f"Found 'overnight' in {t.tuple_id}"
                assert "operator waits" not in p, f"Found 'operator waits' in {t.tuple_id}"
                assert expected_agnostic_instruction in p, f"Missing agnostic revision instruction in {t.tuple_id}"
                assert expected_unmentioned_phrase in p, f"Missing unmentioned field restriction in {t.tuple_id}"

        # Verify batch generator prompt format as well
        _, user_p, _ = build_generator_batch_prompt(tuples[:5], all_svcs)
        assert "overnight" not in user_p, f"Found 'overnight' in batch prompt for {cond}"
        assert "operator waits" not in user_p, f"Found 'operator waits' in batch prompt for {cond}"
        batch_specs = json.loads(user_p.split("specifications:\n\n")[1])
        for sp in batch_specs:
            assert expected_agnostic_instruction in sp["condition_instructions"]
            assert expected_unmentioned_phrase in sp["condition_instructions"]

