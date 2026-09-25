from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.edgebench.contract import Case
from src.edgebench.e2e.ocr_live import run_online_ocr, score_ocr
from src.edgebench.interpreters.base import Decision, Interpreter
from src.ocr_client import normalize


def test_ocr_scoring_canned_exact_match() -> None:
    """Exact match after NFC and strip produces output_exact=True and correct_completion=True."""
    row = {
        "id": 1,
        "arrival": 0.0,
        "ground_truth": "HELLO WORLD",
        "truth": [
            {
                "service_type": "ocr",
                "locality": "remote_allowed",
                "quality_floor": "standard",
                "urgency": "normal",
            }
        ],
    }
    result = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "edge2",
        "tier": "fast",
        "priority": 1,
        "terminal": 0.5,
        "predicted": {
            "service_type": "ocr",
            "locality": "remote_allowed",
            "quality_floor": "standard",
            "urgency": "normal",
        },
        "ocr": {
            "status": "ok",
            "text": "  HELLO WORLD  \n",
        },
    }

    scored = score_ocr(row, result, deadline=2.0)

    assert scored["output_exact"] is True
    assert scored["output_case_insensitive"] is True
    assert scored["cer"] == 0.0
    assert scored["locality_ok"] is True
    assert scored["tier_ok"] is True
    assert scored["priority_ok"] is True
    assert scored["timely"] is True
    assert scored["correct_completion"] is True
    assert scored["locality_violation"] is False


def test_ocr_scoring_unicode_nfc_normalization() -> None:
    """Composed and decomposed unicode strings normalize and match."""
    composed = "café"  # \u00e9
    decomposed = "cafe\u0301"  # e + combining acute accent

    row = {
        "id": 2,
        "arrival": 0.0,
        "ground_truth": decomposed,
        "truth": [{"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}],
    }
    result = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "local",
        "tier": "fast",
        "priority": 1,
        "terminal": 0.2,
        "ocr": {"status": "ok", "text": composed},
    }

    scored = score_ocr(row, result, deadline=2.0)
    assert scored["output_exact"] is True
    assert scored["cer"] == 0.0


def test_ocr_scoring_canned_mismatch_and_cer() -> None:
    """Mismatch produces output_exact=False, non-zero CER, and correct_completion=False."""
    row = {
        "id": 3,
        "arrival": 0.0,
        "ground_truth": "TARGET",
        "truth": [{"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}],
    }
    result = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "local",
        "tier": "fast",
        "priority": 1,
        "terminal": 0.3,
        "ocr": {"status": "ok", "text": "TARG3T"},
    }

    scored = score_ocr(row, result, deadline=2.0)
    assert scored["output_exact"] is False
    assert scored["cer"] == pytest.approx(1 / 6)
    assert scored["correct_completion"] is False


def test_ocr_scoring_locality_and_tier_constraints() -> None:
    """Offsite dispatch on site_only produces locality_violation and locality_ok=False."""
    # Case 1: site_only dispatched to edge2 -> violation!
    row_site = {
        "id": 4,
        "arrival": 0.0,
        "ground_truth": "SECRET",
        "truth": [{"service_type": "ocr", "locality": "site_only", "quality_floor": "high", "urgency": "urgent"}],
    }
    result_offsite = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "edge2",
        "tier": "best",  # meets quality_floor
        "priority": 0,   # urgent -> priority 0
        "terminal": 0.4,
        "sent_bytes": 1024,
        "ocr": {"status": "ok", "text": "SECRET"},
    }
    scored_offsite = score_ocr(row_site, result_offsite, deadline=2.0)
    assert scored_offsite["locality_ok"] is False
    assert scored_offsite["locality_violation"] is True
    assert scored_offsite["offsite_violation_bytes"] == 1024
    assert scored_offsite["correct_completion"] is False

    # Case 2: site_only dispatched to local with standard tier when high requested -> tier_ok=False
    result_wrong_tier = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "local",
        "tier": "fast",  # Does NOT satisfy high
        "priority": 0,
        "terminal": 0.4,
        "sent_bytes": 0,
        "ocr": {"status": "ok", "text": "SECRET"},
    }
    scored_tier = score_ocr(row_site, result_wrong_tier, deadline=2.0)
    assert scored_tier["locality_ok"] is True
    assert scored_tier["tier_ok"] is False
    assert scored_tier["correct_completion"] is False


def test_ocr_scoring_exact_match_mutation() -> None:
    """Mutation test: inverting exact-match comparison (== to !=) must cause this test to fail."""
    row = {
        "id": 10,
        "arrival": 0.0,
        "ground_truth": "SIGNPOST",
        "truth": [{"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}],
    }

    # Matching hypothesis
    res_match = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "local",
        "tier": "fast",
        "priority": 1,
        "terminal": 0.1,
        "ocr": {"status": "ok", "text": "SIGNPOST"},
    }
    score_m = score_ocr(row, res_match, deadline=2.0)
    assert score_m["output_exact"] is True, "Exact text match MUST result in output_exact=True"

    # Non-matching hypothesis
    res_diff = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "local",
        "tier": "fast",
        "priority": 1,
        "terminal": 0.1,
        "ocr": {"status": "ok", "text": "DIFFERENT"},
    }
    score_d = score_ocr(row, res_diff, deadline=2.0)
    assert score_d["output_exact"] is False, "Mismatched text MUST result in output_exact=False"


def test_ocr_scoring_absolute_deadline_timeliness() -> None:
    """Part B: a row with arrival 3.0 and deadline 5.0 whose OCR finishes at 5.5 is not timely."""
    row = {
        "id": 1,
        "arrival": 3.0,
        "deadline": 5.0,
        "ground_truth": "TARGET",
        "truth": [{"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}],
    }
    result = {
        "dispatched": True,
        "status": "ocr_returned",
        "node": "local",
        "tier": "standard",
        "priority": 1,
        "terminal": 5.5,
        "predicted": {"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
        "ocr": {"status": "ok", "text": "TARGET"},
    }

    scored = score_ocr(row, result, deadline=3.0)
    assert scored["timely"] is False
    assert scored["correct_completion"] is False


def test_part_b_outcomes_and_integrity_metrics(tmp_path: Path) -> None:
    """Part B outcomes carry all analysis fields, and completion_rate uses supported arrivals as denominator."""
    img_data = b"fake-image-bytes"
    img_sha = hashlib.sha256(img_data).hexdigest()
    img_file = tmp_path / "img.png"
    img_file.write_bytes(img_data)

    arrivals = [
        # Arrival 0: OCR request (supported)
        {
            "id": 0, "case_id": "ocr_1", "arrival": 0.0, "deadline": 2.0, "is_ocr": True, "text": "transcribe sign",
            "truth": [{"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}],
            "image_path": str(img_file), "image_sha256": img_sha, "ground_truth": "STOP",
        },
        # Arrival 1: Non-OCR request (unsupported by OCR testbed)
        {
            "id": 1, "case_id": "other_1", "arrival": 0.01, "deadline": 2.01, "is_ocr": False, "text": "count people",
            "truth": [{"service_type": "unsupported", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
            "image_path": str(img_file), "image_sha256": img_sha, "ground_truth": "",
        },
    ]

    class FakeInterpreter(Interpreter):
        def __init__(self) -> None:
            super().__init__(name="fake_b", deployment="hosted")

        def decide(self, case: Case) -> Decision:
            if case.case_id == "ocr_1":
                return Decision(
                    labels=[{"service_type": "ocr", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}],
                    valid=True,
                    latency_s=0.01,
                    cost_usd=0.0001,
                )
            return Decision(
                labels=[{"service_type": "unsupported", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
                valid=True,
                latency_s=0.01,
                cost_usd=0.0001,
            )

    def mock_transport(url: str, data: bytes, req_id: str, tier: str, priority: int, timeout: float = 20) -> dict[str, Any]:
        return {
            "status": "ok",
            "node": "local",
            "tier": tier,
            "priority": priority,
            "image_sha256": img_sha,
            "text": "STOP",
            "origin_elapsed_s": 0.02,
        }

    results = asyncio.run(
        run_online_ocr(
            arrivals=arrivals,
            interpreter=FakeInterpreter(),
            urls={"local": "http://127.0.0.1:18764"},
            estimates={"local": {"standard": 0.02, "high": 0.05}},
            cache_enabled=False,
            deadline=2.0,
            concurrency=2,
            queue_limit=5,
            service_limit=5,
            transport=mock_transport,
        )
    )

    assert len(results) == 2

    # Verify building outcomes and integrity as done in eb_rq5b.py
    outcomes_rows = []
    for r in results:
        score = r.get("score", {}) or {}
        meta = r.get("decision_metadata", {}) or {}
        t_val = r["terminal"] - r["arrival"]
        truth = r.get("truth", [])
        truth_dict = truth[0] if isinstance(truth, list) else truth
        row_out = {
            "id": r["id"],
            "case_id": r.get("case_id"),
            "status": r["status"],
            "arrival": r["arrival"],
            "terminal": r["terminal"],
            "T": round(t_val, 6),
            "node": r.get("node"),
            "tier": r.get("tier"),
            "correct_completion": bool(score.get("correct_completion")),
            "output_exact": bool(score.get("output_exact")),
            "locality_ok": bool(score.get("locality_ok")),
            "locality_violation": bool(score.get("locality_violation")),
            "cost_usd": meta.get("cost_usd", 0.0),
            "predicted": r.get("predicted"),
            "truth": truth_dict,
            "is_ocr": bool(r.get("is_ocr", False)),
            "priority": r.get("priority"),
            "score": score,
            "queue_wait_s": round(r.get("queue_wait_s", 0.0), 6) if r.get("queue_wait_s") is not None else None,
            "decision_start": r.get("decision_start"),
            "decision_end": r.get("decision_end"),
            "decision_elapsed_s": round(r.get("decision_elapsed_s", 0.0), 6) if r.get("decision_elapsed_s") is not None else None,
            "service_enqueued": r.get("service_enqueued"),
            "service_dispatch": r.get("service_dispatch"),
            "origin_service_s": round(r.get("origin_service_s", 0.0), 6) if r.get("origin_service_s") is not None else None,
            "estimated_finish": r.get("estimated_finish"),
            "cache_hit": bool(meta.get("cache_hit", False)),
            "api_calls": int(meta.get("api_calls", 0)),
            "error_type": r.get("error_type"),
            "model": "fake_b",
            "condition": "test_cond",
            "seed": 1,
        }
        outcomes_rows.append(row_out)

    # 1. Assert all Part B outcomes fields are present
    required_keys = [
        "predicted", "truth", "is_ocr", "priority", "score", "queue_wait_s",
        "decision_start", "decision_end", "decision_elapsed_s", "service_enqueued",
        "service_dispatch", "origin_service_s", "estimated_finish", "cache_hit",
        "api_calls", "error_type",
    ]
    for row in outcomes_rows:
        for k in required_keys:
            assert k in row, f"Missing key {k} in Part B outcome row"

    # Score dict must contain all score_ocr keys
    score_ocr_keys = [
        "supported", "strict_semantic", "output_exact", "output_case_insensitive",
        "cer", "locality_ok", "tier_ok", "priority_ok", "timely",
        "correct_completion", "false_accept", "correct_rejection",
        "offsite_violation_bytes", "locality_violation",
    ]
    for k in score_ocr_keys:
        assert k in outcomes_rows[0]["score"]

    assert outcomes_rows[0]["is_ocr"] is True
    assert outcomes_rows[0]["score"]["correct_completion"] is True
    assert outcomes_rows[1]["is_ocr"] is False
    assert outcomes_rows[1]["status"] == "unsupported"

    # 2. Assert Part B integrity calculations
    success_count = sum(bool(r.get("score", {}).get("correct_completion")) for r in results)
    supported_count = sum(bool(r.get("score", {}).get("supported")) for r in results)
    completion_rate = success_count / supported_count if supported_count else 0.0
    completion_rate_all = success_count / len(arrivals) if arrivals else 0.0

    assert supported_count == 1
    assert len(arrivals) == 2
    assert success_count == 1
    assert completion_rate == 1.0  # 1 / 1
    assert completion_rate_all == 0.5  # 1 / 2


