"""Offline unit tests for request/response translation of local servers.

No model loading; scorers are mocked.
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from scripts.eb_serve_semif import (
    compute_confidence,
    process_decisions_request,
    translate_request_to_semif_rows,
)
from scripts.eb_serve_laya import (
    compute_untruncated_token_count,
    process_laya_request,
)
from scripts.eb_serve_qwen_json import (
    process_chat_completion,
    render_prompt_no_think,
)


# ==============================================================================
# SemIf Translation Tests
# ==============================================================================

def test_semif_confidence():
    assert compute_confidence([0.8, 0.2]) == pytest.approx(0.6)
    assert compute_confidence([0.5, 0.3, 0.2]) == pytest.approx(0.2)
    assert compute_confidence([0.9]) == pytest.approx(0.9)
    assert compute_confidence([]) == 0.0


def test_semif_translate_rows():
    state = "Test state description"
    questions = {
        "q1": {
            "type": "choice",
            "instructions": "Select service",
            "criteria": {"ocr": "Optical recognition", "count": "Count items"},
        }
    }
    rows = translate_request_to_semif_rows(state, questions)
    assert len(rows) == 1
    assert rows[0]["id"] == "q1"
    assert rows[0]["state"] == state
    assert rows[0]["question"] == "Select service"
    assert len(rows[0]["options"]) == 2
    assert rows[0]["options"][0]["id"] == "ocr"


def test_semif_translate_rows_exceeds_16_options():
    state = "Test state"
    opts = {f"opt_{i}": f"desc {i}" for i in range(17)}
    questions = {
        "q1": {
            "type": "choice",
            "instructions": "Pick one",
            "criteria": opts,
        }
    }
    with pytest.raises(ValueError, match="supports 2-16 options"):
        translate_request_to_semif_rows(state, questions)


def test_semif_process_decisions_request_shared():
    mock_score_fn = MagicMock()
    mock_score_fn.return_value = (
        [
            {
                "id": "r1__service_type",
                "option_ids": ["ocr", "count"],
                "probabilities": [0.85, 0.15],
            },
            {
                "id": "r1__locality",
                "option_ids": ["site_only", "remote_allowed"],
                "probabilities": [0.90, 0.10],
            },
        ],
        {"prefix_tokens": 50, "true_suffix_tokens": 30},
    )

    req = {
        "model": "semif-qwen3.5-4b@23cf1f39",
        "state": "Read parcel on site",
        "questions": {
            "r1__service_type": {
                "type": "choice",
                "instructions": "Pick service",
                "criteria": {"ocr": "OCR", "count": "Count"},
            },
            "r1__locality": {
                "type": "choice",
                "instructions": "Pick locality",
                "criteria": {"site_only": "Site only", "remote_allowed": "Remote allowed"},
            },
        },
    }

    resp = process_decisions_request(req, mock_score_fn, mode="shared")
    assert resp["model"] == "semif-qwen3.5-4b@23cf1f39"
    assert resp["provider"] == "local"
    assert "r1__service_type" in resp["answers"]
    assert resp["answers"]["r1__service_type"]["choice"] == "ocr"
    assert resp["answers"]["r1__service_type"]["confidence"] == pytest.approx(0.70)
    assert resp["answers"]["r1__locality"]["choice"] == "site_only"
    assert resp["answers"]["r1__locality"]["confidence"] == pytest.approx(0.80)
    assert resp["usage"]["input_tokens"] == 80
    assert resp["usage"]["output_tokens"] == 0
    assert resp["usage"]["cost"] == 0.0


# ==============================================================================
# Laya Translation Tests
# ==============================================================================

def test_laya_compute_untruncated_tokens():
    mock_tok = MagicMock()
    mock_tok.mask_token = "[MASK]"
    # Return mock token list of length 10
    mock_tok.side_effect = lambda text, add_special_tokens=False: {"input_ids": [1] * 10}

    mock_agent = MagicMock()
    mock_agent.tok = mock_tok
    mock_agent.cfg = {"max_len": 50}

    questions = {
        "q1": {
            "type": "choice",
            "instructions": "Pick service",
            "criteria": {"ocr": "OCR", "count": "Count"},
        }
    }
    # With max_len=50 and lengths, let's see if it calculates without errors
    total, is_trunc = compute_untruncated_token_count(mock_agent, "sample state", questions)
    assert total > 0
    assert isinstance(is_trunc, bool)


def test_laya_process_request():
    mock_agent = MagicMock()
    mock_tok = MagicMock()
    mock_tok.mask_token = "[MASK]"
    mock_tok.side_effect = lambda text, add_special_tokens=False: {"input_ids": [1] * 5}
    mock_agent.tok = mock_tok
    mock_agent.cfg = {"max_len": 1024}

    mock_agent.system_one.return_value = {
        "model": "laya-rl-agent",
        "answers": {
            "q1": {
                "type": "choice",
                "choice": "ocr",
                "probabilities": {"ocr": 0.9, "count": 0.1},
                "confidence": 0.8,
            }
        },
        "usage": {"input_tokens": 25, "output_tokens": 0},
    }

    req = {
        "model": "laya-typed-decisions@bc76315b",
        "state": "Read parcel",
        "questions": {
            "q1": {
                "type": "choice",
                "instructions": "Pick service",
                "criteria": {"ocr": "OCR", "count": "Count"},
            }
        },
    }

    resp = process_laya_request(mock_agent, req)
    assert resp["model"] == "laya-typed-decisions@bc76315b"
    assert resp["provider"] == "local"
    assert resp["answers"]["q1"]["choice"] == "ocr"
    assert resp["answers"]["q1"]["confidence"] == pytest.approx(0.8)
    # Token accounting is done offline (scripts/eb_laya_tokens.py), not in the response path.
    assert resp["truncated"] is None
    assert resp["usage"]["truncated"] is None
    assert resp["usage"]["input_tokens"] is None


# ==============================================================================
# Qwen-JSON Translation Tests
# ==============================================================================

def test_qwen_json_render_prompt_no_think():
    mock_tokenizer = MagicMock()
    # Mock template returning template with empty think tags
    mock_tokenizer.apply_chat_template.return_value = (
        "<|im_start|>system\nReturn JSON.<|im_end|>\n<|im_start|>user\nHi<|im_end|>\n"
        "<|im_start|>assistant\n<think>\n\n</think>\n\n"
    )
    prompt = render_prompt_no_think(mock_tokenizer, [{"role": "user", "content": "Hi"}])
    # The empty think block is the template's thinking-off signal and is kept verbatim.
    assert prompt == mock_tokenizer.apply_chat_template.return_value
    assert prompt.endswith("<|im_start|>assistant\n<think>\n\n</think>\n\n")


def test_qwen_json_process_chat_completion():
    mock_model = MagicMock()
    mock_tokenizer = MagicMock()
    mock_tokenizer.apply_chat_template.return_value = "<|im_start|>assistant\n"
    mock_tokenizer.encode.side_effect = lambda text, add_special_tokens=False: [1] * len(text)

    body = {
        "messages": [
            {"role": "system", "content": "Return JSON."},
            {"role": "user", "content": "Extract fields."},
        ],
        "max_tokens": 128,
        "temperature": 0,
    }

    mock_model.generate.return_value = '{"service_type": "ocr"}'
    resp = process_chat_completion(mock_model, mock_tokenizer, body)

    assert resp["model"] == "qwen3.5-4b-json@851bf6e8+constrained"
    assert resp["provider"] == "local"
    assert resp["choices"][0]["finish_reason"] == "stop"
    assert resp["choices"][0]["message"]["content"] == '{"service_type": "ocr"}'
    assert resp["usage"]["completion_tokens_details"]["reasoning_tokens"] == 0
