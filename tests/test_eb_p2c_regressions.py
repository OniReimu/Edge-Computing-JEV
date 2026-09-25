"""Regression tests for Edgebench P2c review findings (P0/P1)."""
from __future__ import annotations

import json
from pathlib import Path
import time
from unittest.mock import patch

import numpy as np
import pytest

from src.edgebench.contract import Case, FIELD_SETS
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.ledger import LedgerWriter
from src.edgebench.runner import run_benchmark
from src.edgebench.scoring import (
    aggregate_metrics,
    score_decision,
)


# ---------------------------------------------------------------------------
# Finding 1 (P0): In-flight calls not discarded on stop
# ---------------------------------------------------------------------------
def test_p0_1_inflight_calls_written_on_stop(tmp_path: Path):
    """When a stop condition fires, in-flight calls must be written to the ledger."""
    out_dir = tmp_path / "out_p0_1"
    cases_file = tmp_path / "cases.jsonl"

    case1 = Case(
        case_id="c1",
        text="Case 1 text",
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
    )
    case2 = Case(
        case_id="c2",
        text="Case 2 text",
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
    )
    with open(cases_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(case1.to_dict()) + "\n")
        f.write(json.dumps(case2.to_dict()) + "\n")

    class InflightMockInterpreter(Interpreter):
        def decide(self, case: Case) -> Decision:
            if case.case_id == "c1":
                # Case 1 costs 1.0, triggering spend cap immediately
                return Decision(
                    labels=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
                    valid=True,
                    cost_usd=1.0,
                )
            else:
                # Case 2 takes a moment so Case 1 finishes first and sets stop_requested
                time.sleep(0.08)
                return Decision(
                    labels=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
                    valid=True,
                    cost_usd=0.2,
                )

    with patch("src.edgebench.runner.build_interpreter", return_value=InflightMockInterpreter("mock", "hosted")):
        report = run_benchmark(
            cases_path=cases_file,
            rq="RQ1a",
            condition="base",
            model_names=["mock"],
            out_dir=out_dir,
            workers=2,
            spend_cap_usd=0.5,
            allow_dirty=True,
        )

    ledger_file = out_dir / "ledger.jsonl"
    with open(ledger_file, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    # Both calls were sent, so both must be written to the ledger
    assert len(rows) == 2, f"Expected 2 rows in ledger, got {len(rows)}"
    case_ids = {r["case_id"] for r in rows}
    assert case_ids == {"c1", "c2"}
    assert report["total_spend_usd"] == pytest.approx(1.2, rel=1e-3)


# ---------------------------------------------------------------------------
# Finding 2 (P0): Score outputs persisted in ledger and aggregate raises if missing
# ---------------------------------------------------------------------------
def test_p0_2_scoring_outputs_persisted_and_aggregate_raises_if_missing(tmp_path: Path):
    """score_decision outputs must be persisted in ledger, and aggregate_metrics must raise if missing."""
    # 1. aggregate_metrics must raise KeyError if row lacks scoring outputs
    incomplete_row = {
        "case_id": "c1",
        "repeat": 0,
        "em": True,
        "valid": True,
    }
    with pytest.raises(KeyError, match="unsafe_locality|spurious_count|missed_count"):
        aggregate_metrics([incomplete_row])

    # 2. LedgerWriter must persist scoring outputs
    ledger_path = tmp_path / "ledger.jsonl"
    writer = LedgerWriter(
        path=ledger_path,
        run_id="run1",
        git_sha="sha",
        rq="RQ1a",
        condition="base",
    )
    decision = Decision(labels=[{"service_type": "count"}], valid=True)
    row = writer.write_row(
        model="m1",
        case_id="c1",
        repeat=0,
        decision=decision,
        correct={"service_type": True},
        em=True,
        unsafe_locality=False,
        spurious_count=1,
        missed_count=2,
        unspecified_truth_count=3,
        specified_truth_count=4,
    )
    writer.close()

    assert "unsafe_locality" in row
    assert row["unsafe_locality"] is False
    assert row["spurious_count"] == 1
    assert row["missed_count"] == 2
    assert row["unspecified_truth_count"] == 3
    assert row["specified_truth_count"] == 4


# ---------------------------------------------------------------------------
# Finding 3 (P0): Invalid decisions compute spurious and missed from labels
# ---------------------------------------------------------------------------
def test_p0_3_invalid_decision_spurious_and_missed_labels():
    """Invalid decisions must compute spurious and missed from Decision labels, not hardcode 0."""
    case = Case(
        case_id="c1",
        text="Test",
        fields=["service_type", "locality", "quality_floor", "urgency"],
        bundle_size=1,
        truth=[{
            "service_type": "ocr",
            "locality": "site_only",
            "quality_floor": "high",
            "urgency": "unspecified",
        }],
    )

    # Failed call: default labels are all unspecified.
    # truth has 3 specified fields (ocr, site_only, high) and 1 unspecified field (urgency).
    # All 3 specified fields are missed!
    failed_decision = Decision(
        labels=[{
            "service_type": "unspecified",
            "locality": "unspecified",
            "quality_floor": "unspecified",
            "urgency": "unspecified",
        }],
        valid=False,
        error_type="HTTP_500",
    )
    res = score_decision(failed_decision, case)
    # res = (correct, em, unsafe_locality, spurious_count, missed_count, unspecified_truth_count, specified_truth_count)
    correct, em, unsafe, spur, miss, unspec_t, spec_t = res[:7]

    assert em is False
    assert miss == 3, f"Expected 3 missed fields for failed call, got {miss}"
    assert spur == 0
    assert spec_t == 3
    assert unspec_t == 1

    # Invalid decision with spurious prediction
    spurious_decision = Decision(
        labels=[{
            "service_type": "unspecified",
            "locality": "unspecified",
            "quality_floor": "unspecified",
            "urgency": "urgent",  # spurious!
        }],
        valid=False,
        error_type="schema_violation",
    )
    res2 = score_decision(spurious_decision, case)
    _, _, _, spur2, miss2, _, _ = res2[:7]
    assert spur2 == 1, f"Expected 1 spurious field, got {spur2}"
    assert miss2 == 3, f"Expected 3 missed fields, got {miss2}"


# ---------------------------------------------------------------------------
# Finding 4 (P0): Per-call adapter exception converted to invalid Decision
# ---------------------------------------------------------------------------
def test_p0_4_adapter_exception_converted_to_invalid_decision(tmp_path: Path):
    """An exception raised inside adapter during decide() must be converted to an invalid Decision."""
    out_dir = tmp_path / "out_p0_4"
    cases_file = tmp_path / "cases.jsonl"

    case1 = Case(
        case_id="c1",
        text="Case 1 text",
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
    )
    case2 = Case(
        case_id="c2",
        text="Case 2 text",
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
    )
    with open(cases_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(case1.to_dict()) + "\n")
        f.write(json.dumps(case2.to_dict()) + "\n")

    class CrashingInterpreter(Interpreter):
        def decide(self, case: Case) -> Decision:
            if case.case_id == "c1":
                raise KeyError("choices[0] malformed secret_key=12345")
            return Decision(
                labels=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
                valid=True,
            )

    with patch("src.edgebench.runner.build_interpreter", return_value=CrashingInterpreter("crash_model", "hosted")):
        report = run_benchmark(
            cases_path=cases_file,
            rq="RQ1a",
            condition="base",
            model_names=["crash_model"],
            out_dir=out_dir,
            workers=1,
            allow_dirty=True,
        )

    ledger_file = out_dir / "ledger.jsonl"
    with open(ledger_file, "r", encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]

    assert len(rows) == 2
    row_c1 = next(r for r in rows if r["case_id"] == "c1")
    row_c2 = next(r for r in rows if r["case_id"] == "c2")

    assert row_c1["valid"] is False
    assert row_c1["error_type"] == "KeyError"
    # Exception message must be redacted
    assert "secret_key" not in json.dumps(row_c1)
    assert row_c2["valid"] is True


# ---------------------------------------------------------------------------
# Finding 5 (P1): Full schema validation in chat_json
# ---------------------------------------------------------------------------
def test_p1_5_chat_json_schema_validation_k1_wrapper_and_extra_keys():
    """chat_json must validate against full schema: k=1 requests wrapper and extra keys are invalid."""
    client = ChatJsonClient(
        name="DeepSeek-V4.1-Flash",
        model="deepseek/deepseek-v4.1-flash",
        provider_slug="together",
    )
    case_k1 = Case(
        case_id="c1",
        text="Count cars",
        fields=["service_type", "locality"],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "unspecified"}],
    )

    # 1. k=1 with a requests wrapper should be invalid
    resp_with_wrapper = {
        "model": "deepseek/deepseek-v4.1-flash",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"requests": [{"service_type": "count", "locality": "unspecified"}]})},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10},
    }
    with patch("src.edgebench.interpreters.chat_json.make_request") as mock_make:
        mock_make.return_value = (200, json.dumps(resp_with_wrapper), 0.1, 1000.0, 1000.1, None, {})
        dec_wrapper = client.decide(case_k1)

    assert dec_wrapper.valid is False
    assert dec_wrapper.error_type == "schema_violation"

    # 2. Extra keys must be invalid
    resp_with_extra = {
        "model": "deepseek/deepseek-v4.1-flash",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"service_type": "count", "locality": "unspecified", "extra_key": "not_allowed"})},
        }],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10},
    }
    with patch("src.edgebench.interpreters.chat_json.make_request") as mock_make:
        mock_make.return_value = (200, json.dumps(resp_with_extra), 0.1, 1000.0, 1000.1, None, {})
        dec_extra = client.decide(case_k1)

    assert dec_extra.valid is False
    assert dec_extra.error_type == "schema_violation"


# ---------------------------------------------------------------------------
# Finding 6 (P1): Bundled scoring keeps per-request correctness & RQ1b aggregation
# ---------------------------------------------------------------------------
def test_p1_6_bundled_scoring_per_request_and_rq1b_aggregation():
    """Bundled scoring must store request_em and request_field_correct, and support RQ1b aggregation."""
    from src.edgebench.scoring import aggregate_rq1b_metrics

    case = Case(
        case_id="c_bundle",
        text="1. Count. 2. Detect.",
        fields=["service_type", "locality"],
        bundle_size=2,
        truth=[
            {"service_type": "count", "locality": "site_only"},
            {"service_type": "detection", "locality": "site_only"},
        ],
    )
    # Request 0 is completely correct. Request 1 has wrong locality.
    decision = Decision(
        labels=[
            {"service_type": "count", "locality": "site_only"},
            {"service_type": "detection", "locality": "remote_allowed"},
        ],
        valid=True,
    )
    res = score_decision(decision, case)
    assert hasattr(res, "request_em"), "score_decision result must have request_em"
    assert res.request_em == [True, False]
    assert hasattr(res, "request_field_correct")
    assert res.request_field_correct == [
        {"service_type": True, "locality": True},
        {"service_type": True, "locality": False},
    ]

    # RQ1b aggregation
    row1 = {
        "case_id": "c1",
        "repeat": 0,
        "em": False,
        "valid": True,
        "request_em": [True, False],
        "request_field_correct": [{"service_type": True, "locality": True}, {"service_type": True, "locality": False}],
        "unsafe_locality": True,
        "spurious_count": 0,
        "missed_count": 0,
        "unspecified_truth_count": 0,
        "specified_truth_count": 4,
        "latency_s": 0.4,
    }
    row2 = {
        "case_id": "c2",
        "repeat": 0,
        "em": True,
        "valid": True,
        "request_em": [True, True],
        "request_field_correct": [{"service_type": True, "locality": True}, {"service_type": True, "locality": True}],
        "unsafe_locality": False,
        "spurious_count": 0,
        "missed_count": 0,
        "unspecified_truth_count": 0,
        "specified_truth_count": 4,
        "latency_s": 0.6,
    }
    rq1b = aggregate_rq1b_metrics([row1, row2], seed=20260924)
    # Total requests = 4, correct = 3 -> request_level_em = 0.75
    assert rq1b["request_level_em"] == 0.75
    assert "request_level_em_ci95" in rq1b
    assert rq1b["message_em"] == 0.5


# ---------------------------------------------------------------------------
# Finding 7 (P1): Primary aggregation repeat 0 only; within-case latency variability
# ---------------------------------------------------------------------------
def test_p1_7_primary_aggregation_repeat_0_only_and_within_case_cv():
    """aggregate_metrics must use repeat 0 only; compute_within_case_latency_variability over repeats 0-2."""
    from src.edgebench.scoring import compute_within_case_latency_variability

    rows = [
        # Repeat 0: correct, latency 0.1
        {
            "case_id": "c1",
            "repeat": 0,
            "em": True,
            "valid": True,
            "latency_s": 0.10,
            "unsafe_locality": False,
            "spurious_count": 0,
            "missed_count": 0,
            "unspecified_truth_count": 2,
            "specified_truth_count": 2,
        },
        # Repeat 1: incorrect, latency 0.12
        {
            "case_id": "c1",
            "repeat": 1,
            "em": False,
            "valid": True,
            "latency_s": 0.12,
            "unsafe_locality": False,
            "spurious_count": 0,
            "missed_count": 0,
            "unspecified_truth_count": 2,
            "specified_truth_count": 2,
        },
        # Repeat 2: incorrect, latency 0.11
        {
            "case_id": "c1",
            "repeat": 2,
            "em": False,
            "valid": True,
            "latency_s": 0.11,
            "unsafe_locality": False,
            "spurious_count": 0,
            "missed_count": 0,
            "unspecified_truth_count": 2,
            "specified_truth_count": 2,
        },
    ]

    agg = aggregate_metrics(rows)
    # Must use repeat 0 only, so EM should be 1.0 (not 1/3)
    assert agg["em"] == 1.0
    assert agg["n"] == 1

    # Within-case variability over repeats 0-2
    cv_info = compute_within_case_latency_variability(rows, subset_ids={"c1"})
    assert "mean_cv" in cv_info
    # Mean of [0.10, 0.12, 0.11] is 0.11, std is 0.01 -> CV ~ 0.0909
    assert cv_info["mean_cv"] == pytest.approx(0.01 / 0.11, rel=1e-3)


# ---------------------------------------------------------------------------
# Finding 8 (P1): Bootstrap CIs for all metrics, paired contrasts, growth ratios, CI inversion
# ---------------------------------------------------------------------------
def test_p1_8_bootstrap_cis_and_paired_contrasts_and_ci_inversion():
    """Bootstrap CIs for all metrics, paired contrasts (EM, unsafe, latency), growth ratios, and CI inversion."""
    from src.edgebench.scoring import (
        compute_growth_ratio,
        compute_ratio_of_ratios,
        invert_bootstrap_pvalue,
    )

    rows_m = [
        {
            "case_id": f"c_{i}",
            "repeat": 0,
            "em": i % 2 == 0,
            "valid": True,
            "correct": {"service_type": i % 2 == 0, "locality": True},
            "unsafe_locality": i % 3 == 0,
            "spurious_count": 0,
            "missed_count": 1 if i % 2 != 0 else 0,
            "unspecified_truth_count": 2,
            "specified_truth_count": 2,
            "latency_s": 0.1 + 0.01 * i,
        }
        for i in range(10)
    ]

    agg = aggregate_metrics(rows_m, seed=20260924)
    # Check all required CIs are present
    assert "em_ci95" in agg
    assert "macro_field_accuracy_ci95" in agg
    assert "valid_rate_ci95" in agg
    assert "unsafe_rate_ci95" in agg
    assert "spurious_rate_ci95" in agg
    assert "missed_rate_ci95" in agg
    assert "latency_p50_ci95" in agg
    assert "latency_p95_ci95" in agg

    # Paired contrasts vs reference
    rows_ref = [
        {
            "case_id": f"c_{i}",
            "repeat": 0,
            "em": True,
            "valid": True,
            "correct": {"service_type": True, "locality": True},
            "unsafe_locality": False,
            "spurious_count": 0,
            "missed_count": 0,
            "unspecified_truth_count": 2,
            "specified_truth_count": 2,
            "latency_s": 0.05 + 0.01 * i,
        }
        for i in range(10)
    ]
    agg_paired = aggregate_metrics(rows_m, reference_rows=rows_ref, seed=20260924)
    p_info = agg_paired["paired_vs_ref"]
    assert "em_diff" in p_info
    assert "em_diff_ci95" in p_info
    assert "mcnemar_p" in p_info
    assert "unsafe_diff" in p_info
    assert "unsafe_diff_ci95" in p_info
    assert "unsafe_mcnemar_p" in p_info
    assert "latency_diff_median" in p_info
    assert "latency_diff_median_ci95" in p_info
    assert "wilcoxon_latency_p" in p_info

    # Growth ratio and ratio-of-ratios
    lats_level = [0.2, 0.22, 0.21, 0.25, 0.23]
    lats_ref_level = [0.1, 0.11, 0.10, 0.12, 0.11]
    g_point, g_ci = compute_growth_ratio(lats_level, lats_ref_level, seed=20260924)
    assert g_point == pytest.approx(2.0, rel=0.1)
    assert g_ci[0] <= g_point <= g_ci[1]

    ror_point, ror_ci = compute_ratio_of_ratios(
        lats_level, lats_ref_level, lats_level, lats_ref_level, seed=20260924
    )
    assert ror_point == pytest.approx(1.0, rel=0.1)
    assert ror_ci[0] <= ror_point <= ror_ci[1]

    # CI inversion p-value
    # Samples clearly above 0 -> p < 0.05
    boot_samples = np.array([1.0, 1.2, 0.9, 1.1, 1.3] * 2000)
    p_val = invert_bootstrap_pvalue(boot_samples, null_value=0.0)
    assert p_val < 0.05
    # Samples straddling 0 -> p ~ 1.0
    boot_samples_straddle = np.array([-1.0, 1.0] * 5000)
    p_val_straddle = invert_bootstrap_pvalue(boot_samples_straddle, null_value=0.0)
    assert p_val_straddle == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Finding 9 (P1): On resume, only current (rq, condition) scope counts toward spend
# ---------------------------------------------------------------------------
def test_p1_9_resume_spend_scoped_to_current_rq_and_condition(tmp_path: Path):
    """On resume, pre-existing spend must be scoped to current (rq, condition)."""
    out_dir = tmp_path / "out_p1_9"
    out_dir.mkdir(parents=True)
    ledger_file = out_dir / "ledger.jsonl"

    # Pre-existing ledger has $15 spent on RQ1b (diff rq) and $15 spent on RQ1a / other_cond
    # and only $1 spent on RQ1a / base
    existing_rows = [
        {"rq": "RQ1b", "condition": "k8", "model": "m1", "case_id": "old1", "repeat": 0, "cost_usd": 15.0},
        {"rq": "RQ1a", "condition": "c_other", "model": "m1", "case_id": "old2", "repeat": 0, "cost_usd": 15.0},
        {"rq": "RQ1a", "condition": "base", "model": "m1", "case_id": "old3", "repeat": 0, "cost_usd": 1.0},
    ]
    with open(ledger_file, "w", encoding="utf-8") as f:
        for r in existing_rows:
            f.write(json.dumps(r) + "\n")

    cases_file = tmp_path / "cases.jsonl"
    case = Case(
        case_id="new_case",
        text="Case text",
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
    )
    with open(cases_file, "w", encoding="utf-8") as f:
        f.write(json.dumps(case.to_dict()) + "\n")

    class ResumeMockInterpreter(Interpreter):
        def decide(self, case: Case) -> Decision:
            return Decision(
                labels=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
                valid=True,
                cost_usd=0.5,
            )

    # Spend cap is $5.0. If out-of-scope spend is counted ($31.0), it stops immediately.
    # If scoped to RQ1a/base ($1.0), it should proceed and run new_case!
    with patch("src.edgebench.runner.build_interpreter", return_value=ResumeMockInterpreter("m1", "hosted")):
        report = run_benchmark(
            cases_path=cases_file,
            rq="RQ1a",
            condition="base",
            model_names=["m1"],
            out_dir=out_dir,
            workers=1,
            spend_cap_usd=5.0,
            allow_dirty=True,
        )

    assert report["stop_reason"] is None
    # total spend should be 1.0 (scoped existing) + 0.5 (new) = 1.5
    assert report["total_spend_usd"] == pytest.approx(1.5, rel=1e-3)


# ---------------------------------------------------------------------------
# Finding 10: Raw completion tokens and reasoning tokens
# ---------------------------------------------------------------------------
def test_p1_10_chat_json_output_tokens_raw_completion_tokens():
    """completion_tokens_raw must be recorded as reported; output_tokens must not be bumped to reasoning_tokens."""
    client = ChatJsonClient(
        name="GLM-5.3-Flash",
        model="z-ai/glm-5.3-flash",
        provider_slug="together",
        reasoning={"effort": "minimal"},
    )
    case = Case(
        case_id="c1",
        text="Count cars",
        fields=FIELD_SETS[4],
        bundle_size=1,
        truth=[{"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
    )
    # Provider reports completion_tokens = 12, but reasoning_tokens = 30
    mock_resp = {
        "model": "z-ai/glm-5.3-flash",
        "choices": [{
            "finish_reason": "stop",
            "message": {"content": json.dumps({"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"})},
        }],
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 12,
            "completion_tokens_details": {"reasoning_tokens": 30},
            "cost": 0.0005,
        },
        "provider": "together",
    }
    with patch("src.edgebench.interpreters.chat_json.make_request") as mock_make:
        mock_make.return_value = (200, json.dumps(mock_resp), 0.1, 1000.0, 1000.1, None, {})
        decision = client.decide(case)

    assert decision.valid is True
    assert decision.reasoning_tokens == 30
    assert hasattr(decision, "completion_tokens_raw"), "Decision must have completion_tokens_raw"
    assert decision.completion_tokens_raw == 12
    assert decision.output_tokens == 12  # Must NOT be raised to 30!
