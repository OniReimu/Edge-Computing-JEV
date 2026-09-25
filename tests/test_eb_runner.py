"""Tests for benchmark runner with mocked transport."""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from src.edgebench.contract import Case, FIELD_SETS, dump_cases_jsonl
from src.edgebench.runner import run_benchmark


def make_canned_decision_response(model_name: str, case: Case):
    answers = {}
    for req_idx in range(1, case.bundle_size + 1):
        for f in case.fields:
            qid = f"r{req_idx}__{f}"
            t_choice = (
                case.truth[req_idx - 1].get(f, "unspecified")
                if case.truth
                else "unspecified"
            )
            answers[qid] = {
                "type": "choice",
                "choice": t_choice,
                "probabilities": {t_choice: 0.99},
                "confidence": 0.99,
            }
    return {
        "model": model_name,
        "answers": answers,
        "usage": {"input_tokens": 50, "output_tokens": 10, "cost": 0.0001},
        "id": "gen-mock-123",
        "provider": "MockProvider",
    }


def test_runner_20_cases_3_models_5_repeats():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        cases_path = tmp / "cases.jsonl"
        subset_path = tmp / "subset.txt"
        manifest_path = tmp / "models.json"
        out_dir = tmp / "out"

        # 20 cases
        cases = [
            Case(
                case_id=f"case_{i:02d}",
                text=f"Text for case {i}",
                fields=FIELD_SETS[4],
                bundle_size=1,
                truth=[{"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
            )
            for i in range(20)
        ]
        dump_cases_jsonl(cases, cases_path)

        # 5-id subset
        subset_ids = [f"case_{i:02d}" for i in range(5)]
        subset_path.write_text("\n".join(subset_ids), encoding="utf-8")

        # 3 fake hosted models
        manifest = {
            f"Fake-{name}": {
                "display_name": f"Fake-{name}",
                "family": "decision",
                "deployment": "hosted",
                "adapter": "decisions",
                "model": f"mock/fake-{name}",
                "accepted_resolved_models": [f"mock/fake-{name}"],
                "provider": "MockProvider",
                "base_url": "https://localhost",
                "path": "/api/alpha/decisions",
            }
            for name in ("A", "B", "C")
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        # Mock make_request to return canned response
        def mock_request(base_url, path, payload, api_key=None, extra_headers=None, timeout_s=30.0):
            model_id = payload["model"]
            # Extract case fields and text
            canned = {
                "model": model_id,
                "answers": {
                    qid: {
                        "type": "choice",
                        "choice": "count" if "service_type" in qid else "unspecified",
                        "probabilities": {"count": 1.0},
                    }
                    for qid in payload["questions"]
                },
                "usage": {"input_tokens": 50, "output_tokens": 10, "cost": 0.0001},
                "provider": "MockProvider",
            }
            return 200, json.dumps(canned), 0.01, 1000.0, 1000.01, None, {}

        with patch("src.edgebench.interpreters.decisions.make_request", side_effect=mock_request):
            report = run_benchmark(
                cases_path=cases_path,
                rq="RQ1",
                condition="test_cond",
                model_names=["Fake-A", "Fake-B", "Fake-C"],
                out_dir=out_dir,
                repeats_subset_path=subset_path,
                workers=2,
                seed=20260924,
                spend_cap_usd=20.0,
                allow_dirty=True,
                manifest_path=manifest_path,
            )

        # Expected counts: 20 for r0, 5 for r1, 5 for r2 per model
        for name in ("Fake-A", "Fake-B", "Fake-C"):
            assert report["expected_rows_per_model_repeat"][f"{name}:r0"] == 20
            assert report["expected_rows_per_model_repeat"][f"{name}:r1"] == 5
            assert report["expected_rows_per_model_repeat"][f"{name}:r2"] == 5

            assert report["actual_rows_per_model_repeat"][f"{name}:r0"] == 20
            assert report["actual_rows_per_model_repeat"][f"{name}:r1"] == 5
            assert report["actual_rows_per_model_repeat"][f"{name}:r2"] == 5

        assert report["duplicates"] == 0
        assert report["stop_reason"] is None


def test_runner_interrupted_run_resumes_without_duplicates():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        cases_path = tmp / "cases.jsonl"
        manifest_path = tmp / "models.json"
        out_dir = tmp / "out"

        cases = [
            Case(
                case_id=f"case_{i}",
                text=f"Text {i}",
                fields=FIELD_SETS[4],
                bundle_size=1,
                truth=[{"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}],
            )
            for i in range(6)
        ]
        dump_cases_jsonl(cases, cases_path)

        manifest = {
            "Fake-M": {
                "display_name": "Fake-M",
                "family": "decision",
                "deployment": "hosted",
                "adapter": "decisions",
                "model": "mock/fake-m",
                "accepted_resolved_models": ["mock/fake-m"],
                "provider": "MockProvider",
                "base_url": "https://localhost",
                "path": "/api/alpha/decisions",
            }
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        def mock_request(base_url, path, payload, api_key=None, extra_headers=None, timeout_s=30.0):
            canned = {
                "model": payload["model"],
                "answers": {
                    qid: {"type": "choice", "choice": "count"}
                    for qid in payload["questions"]
                },
                "usage": {"cost": 0.001},
            }
            return 200, json.dumps(canned), 0.01, 1000.0, 1000.01, None, {}

        with patch("src.edgebench.interpreters.decisions.make_request", side_effect=mock_request):
            # Run 1: with tight spend cap to simulate interruption after a few cases
            rep1 = run_benchmark(
                cases_path=cases_path,
                rq="RQ1",
                condition="resume_cond",
                model_names=["Fake-M"],
                out_dir=out_dir,
                workers=1,
                seed=42,
                spend_cap_usd=0.0025,  # Stops after ~3 calls
                allow_dirty=True,
                manifest_path=manifest_path,
            )
            assert rep1["stop_reason"] is not None

            # Run 2: resume with full spend cap
            rep2 = run_benchmark(
                cases_path=cases_path,
                rq="RQ1",
                condition="resume_cond",
                model_names=["Fake-M"],
                out_dir=out_dir,
                workers=1,
                seed=42,
                spend_cap_usd=20.0,
                allow_dirty=True,
                manifest_path=manifest_path,
            )

        assert rep2["duplicates"] == 0
        assert rep2["actual_rows_per_model_repeat"]["Fake-M:r0"] == 6
        assert rep2["stop_reason"] is None
