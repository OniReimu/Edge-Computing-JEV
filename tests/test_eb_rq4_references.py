"""Unit tests for RQ4 reference models (Reranker and Service Classifier).

Tests run without requiring torch or sentence-transformers.
"""
from __future__ import annotations

import builtins
import json
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest

from src.edgebench.contract import Case
from src.edgebench.interpreters.reranker import RerankerInterpreter, calibrate_reranker
from src.edgebench.interpreters.service_classifier import (
    ServiceClassifierInterpreter,
    mask_logits,
)
from src.edgebench.manifest import build_interpreter, load_manifest
from scripts.eb_rq4_train import (
    build_label_space,
    build_training_data,
    load_catalog_data,
)


def test_import_interpreters_installs_no_trace_function():
    """Importing src.edgebench.interpreters installs no trace function (sys.gettrace() unchanged)."""
    orig_trace = sys.gettrace()
    import src.edgebench.interpreters  # noqa: F401
    assert sys.gettrace() is orig_trace


def test_manifest_build_four_reference_models():
    """load_manifest() + building each of the four reference models returns the right interpreter class."""
    manifest = load_manifest()
    m_reranker = build_interpreter("MiniLM-Reranker", manifest=manifest)
    assert isinstance(m_reranker, RerankerInterpreter)

    m_all = build_interpreter("DistilBERT-Clf-All", manifest=manifest)
    assert isinstance(m_all, ServiceClassifierInterpreter)

    m_frozen = build_interpreter("DistilBERT-Clf-Frozen", manifest=manifest)
    assert isinstance(m_frozen, ServiceClassifierInterpreter)

    m_retrained = build_interpreter("DistilBERT-Clf-Retrained", manifest=manifest)
    assert isinstance(m_retrained, ServiceClassifierInterpreter)


def test_threshold_calibration_toy_dev_set():
    """Threshold calibration on a toy dev set with a known best theta and tie-breaking."""
    # Toy cases with known observed scores: (max_cosine, best_candidate, gold_service)
    # Case 1: max_cos = 0.8, best = "svc_a", gold = "svc_a"
    # Case 2: max_cos = 0.5, best = "svc_b", gold = "svc_b"
    # Case 3: max_cos = 0.3, best = "svc_c", gold = "unsupported"
    observed = [
        (0.8, "svc_a", "svc_a"),
        (0.5, "svc_b", "svc_b"),
        (0.3, "svc_c", "unsupported"),
    ]

    # At theta = 0.3: Case 3 predicts "svc_c" (wrong), acc = 2/3
    # At theta = 0.5: Case 3 predicts "unsupported" (correct), Case 2 predicts "svc_b" (correct), Case 1 predicts "svc_a" (correct), acc = 3/3
    # At theta = 0.8: Case 2 predicts "unsupported" (wrong), acc = 2/3
    best_theta, best_acc, curve = calibrate_reranker(dev_cases=[], observed_scores=observed)

    assert best_acc == pytest.approx(1.0)
    assert best_theta == pytest.approx(0.5)

    # Test tie-breaking: ties -> smaller theta
    # Suppose we have observed scores where theta=0.4 and theta=0.6 both yield 100%
    observed_ties = [
        (0.7, "svc_a", "svc_a"),
        (0.3, "svc_b", "unsupported"),
    ]
    # For theta in (0.3, 0.7], both Case 1 and Case 2 are correct.
    # Candidate thetas around 0.3 and 0.7:
    best_theta_tie, best_acc_tie, _ = calibrate_reranker(dev_cases=[], observed_scores=observed_ties)
    assert best_acc_tie == pytest.approx(1.0)
    # Should pick the smaller theta
    assert best_theta_tie <= 0.7


def test_masking_never_returns_outside_service_options():
    """Masking never returns an id outside service_options ∪ {unsupported}."""
    id2label = {
        0: "svc_allowed_1",
        1: "svc_allowed_2",
        2: "svc_forbidden_high_logit",
        3: "unsupported",
    }
    # svc_forbidden_high_logit has highest raw logit (10.0)
    logits = [2.0, 1.0, 10.0, 0.5]
    service_options = {
        "svc_allowed_1": "Description 1",
        "svc_allowed_2": "Description 2",
        "unsupported": "unsupported",
    }

    best_idx, best_label, masked = mask_logits(logits, id2label, service_options)

    # svc_forbidden_high_logit must be masked to -inf
    assert masked[2] == -float("inf")
    # Must predict svc_allowed_1, NOT svc_forbidden_high_logit
    assert best_label == "svc_allowed_1"
    assert best_label in service_options

    # Test when all allowed options have lower logit than unsupported
    logits_unsupp = [-5.0, -10.0, 10.0, 2.0]
    _, best_label_unsupp, _ = mask_logits(logits_unsupp, id2label, service_options)
    assert best_label_unsupp == "unsupported"
    assert best_label_unsupp in service_options

    # Test decision method with fake model
    mock_model = MagicMock()
    mock_logits = MagicMock()
    mock_logits.detach().cpu().numpy().copy.return_value = [2.0, 1.0, 10.0, 0.5]
    mock_outputs = MagicMock(logits=[mock_logits])
    mock_model.return_value = mock_outputs

    mock_tokenizer = MagicMock()
    mock_inputs = {"input_ids": MagicMock()}
    mock_tokenizer.return_value = mock_inputs

    interp = ServiceClassifierInterpreter(
        name="DistilBERT-Clf-All",
        model=mock_model,
        tokenizer=mock_tokenizer,
        id2label=id2label,
        device="cpu",
    )

    case = Case(
        case_id="K4_test_0001",
        text="Sample request",
        fields=["service_type", "locality"],
        service_options=service_options,
        truth=[{"service_type": "unsupported", "locality": "unspecified"}],
    )
    decision = interp.decide(case)
    pred_service = decision.labels[0]["service_type"]
    assert pred_service in service_options
    assert pred_service != "svc_forbidden_high_logit"


def test_retrained_head_selection_by_condition():
    """Retrained model selects head only from explicit per-condition mapping and condition.

    churn25 -> _25, churn50 -> _50, K64 -> error.
    Removes every inference from case_id or service_options.
    """
    manifest = load_manifest()
    interp = build_interpreter("DistilBERT-Clf-Retrained", manifest=manifest)

    # 1. churn25 -> _25
    assert interp.resolve_head("churn25") == "_25"
    interp_25 = build_interpreter("DistilBERT-Clf-Retrained", manifest=manifest, condition="churn25")
    assert interp_25.resolve_head() == "_25"
    case_meta_25 = Case(
        case_id="case_001",
        text="Text",
        truth=[{"service_type": "unsupported"}],
        meta={"condition": "churn25"},
        service_options={"unsupported": "unsupported"},
    )
    assert interp.resolve_head_for_case(case_meta_25) == "_25"
    assert interp_25.resolve_head_for_case(case_meta_25) == "_25"

    # 2. churn50 -> _50
    assert interp.resolve_head("churn50") == "_50"
    interp_50 = build_interpreter("DistilBERT-Clf-Retrained", manifest=manifest, condition="churn50")
    assert interp_50.resolve_head() == "_50"
    case_meta_50 = Case(
        case_id="case_002",
        text="Text",
        truth=[{"service_type": "unsupported"}],
        meta={"condition": "churn50"},
        service_options={"unsupported": "unsupported"},
    )
    assert interp.resolve_head_for_case(case_meta_50) == "_50"
    assert interp_50.resolve_head_for_case(case_meta_50) == "_50"

    # 3. K64 -> error
    with pytest.raises(ValueError, match="K64"):
        interp.resolve_head("K64")

    interp_k64 = build_interpreter("DistilBERT-Clf-Retrained", manifest=manifest, condition="K64")
    with pytest.raises(ValueError, match="K64"):
        interp_k64.resolve_head()

    case_meta_k64 = Case(
        case_id="case_003",
        text="Text",
        truth=[{"service_type": "unsupported"}],
        meta={"condition": "K64"},
        service_options={"unsupported": "unsupported"},
    )
    with pytest.raises(ValueError, match="K64"):
        interp.resolve_head_for_case(case_meta_k64)

    # 4. Remove every inference from case_id or service_options:
    # A case with churn25 in its case_id or service_options must NOT be inferred
    case_id_bait = Case(
        case_id="churn25_test_0042",
        text="Text",
        truth=[{"service_type": "unsupported"}],
        service_options={"unsupported": "unsupported", "work_zone_merge_compliance_monitor": "desc"},
    )
    with pytest.raises(ValueError):
        interp.resolve_head_for_case(case_id_bait)

    case_options_bait = Case(
        case_id="arbitrary_id",
        text="Text",
        truth=[{"service_type": "unsupported"}],
        service_options={"unsupported": "unsupported", "novel_service_50": "desc"},
    )
    with pytest.raises(ValueError):
        interp.resolve_head_for_case(case_options_bait)


def test_reranker_decision_path_threshold_filtering():
    """Reranker decision path: max cosine above theta -> predicted service; below theta -> unsupported.

    Flipping `if max_cosine < theta` to `>` causes this test to fail.
    """
    import numpy as np

    class FakeEncoder:
        def __init__(self, mapping: dict[str, list[float]]):
            self.mapping = {k: np.array(v, dtype=float) for k, v in mapping.items()}

        def encode(self, texts: list[str], normalize_embeddings: bool = True):
            return np.array([self.mapping[t] for t in texts], dtype=float)

    service_options = {
        "traffic_monitor": "desc_traffic",
        "weather_station": "desc_weather",
        "unsupported": "unsupported",
    }
    vectors = {
        "desc_traffic": [1.0, 0.0],
        "desc_weather": [0.0, 1.0],
        "query_traffic": [1.0, 0.0],
        "query_music": [0.2, 0.2],
    }
    fake_enc = FakeEncoder(vectors)
    reranker = RerankerInterpreter(
        name="MiniLM-Reranker",
        threshold=0.5,
        encoder=fake_enc,
    )

    # Case 1: max_cosine = 1.0 >= 0.5 (above theta) -> predicts "traffic_monitor"
    case_above = Case(
        case_id="case_above_theta",
        text="query_traffic",
        fields=["service_type", "locality"],
        service_options=service_options,
        truth=[{"service_type": "traffic_monitor", "locality": "unspecified"}],
    )
    decision_above = reranker.decide(case_above)
    assert decision_above.labels[0]["service_type"] == "traffic_monitor"

    # Case 2: max_cosine = 0.2 < 0.5 (below theta) -> predicts "unsupported"
    case_below = Case(
        case_id="case_below_theta",
        text="query_music",
        fields=["service_type", "locality"],
        service_options=service_options,
        truth=[{"service_type": "unsupported", "locality": "unspecified"}],
    )
    decision_below = reranker.decide(case_below)
    assert decision_below.labels[0]["service_type"] == "unsupported"


def test_label_space_construction():
    """Label space construction: frozen excludes v25/v50 new services; retrained includes them."""
    catalogs, _ = load_catalog_data()

    v0_services = set(catalogs["v0"])
    v25_services = set(catalogs["v25"])
    v50_services = set(catalogs["v50"])

    new_v25 = v25_services - v0_services
    new_v50 = v50_services - v0_services

    assert len(new_v25) == 16
    assert len(new_v50) == 32

    # clf_frozen
    frozen_labels = set(build_label_space("clf_frozen", catalogs))
    assert "unsupported" in frozen_labels
    assert len(frozen_labels) == 65
    # Must exclude all new services from v25 and v50
    assert frozen_labels.isdisjoint(new_v25)
    assert frozen_labels.isdisjoint(new_v50)

    # clf_retrained_25
    r25_labels = set(build_label_space("clf_retrained_25", catalogs))
    assert "unsupported" in r25_labels
    assert len(r25_labels) == 65
    # Must include the 16 new services
    assert new_v25.issubset(r25_labels)

    # clf_retrained_50
    r50_labels = set(build_label_space("clf_retrained_50", catalogs))
    assert "unsupported" in r50_labels
    assert len(r50_labels) == 65
    # Must include the 32 new services
    assert new_v50.issubset(r50_labels)


def test_training_data_builder_never_reads_test_jsonl():
    """Training data builder never reads a test.jsonl file."""
    opened_paths: list[str] = []
    real_open = builtins.open

    def recording_open(*args, **kwargs):
        path_str = str(args[0])
        opened_paths.append(path_str)
        return real_open(*args, **kwargs)

    # Patch open during data building
    orig_open = builtins.open
    builtins.open = recording_open
    try:
        for m_type in ["clf_all", "clf_frozen", "clf_retrained_25", "clf_retrained_50"]:
            examples, label_space, stats = build_training_data(m_type)
            assert len(examples) > 0
            assert len(label_space) > 0
    finally:
        builtins.open = orig_open

    # Check all recorded paths
    test_paths_opened = [p for p in opened_paths if "test.jsonl" in p]
    assert len(test_paths_opened) == 0, f"Violated protocol: opened test files: {test_paths_opened}"

    # Verify that dev.jsonl was indeed opened
    dev_paths_opened = [p for p in opened_paths if "dev.jsonl" in p]
    assert len(dev_paths_opened) > 0
