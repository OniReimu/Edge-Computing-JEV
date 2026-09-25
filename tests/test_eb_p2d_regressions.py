"""Regression tests for Edgebench P2d code-review findings (6 x P1)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

import scripts.eb_serve_qwen_json as qwen_srv
from scripts.eb_serve_laya import compute_untruncated_token_count
from src.edgebench.contract import Case, FIELD_SETS
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.interpreters.transport import make_request
from src.edgebench.runner import run_benchmark
from src.edgebench import scoring


TRUTH4 = {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}


# ---------------------------------------------------------------------------
# Finding 1: Qwen3.5 thinking-off block is kept; leaks are flagged, not banned
# ---------------------------------------------------------------------------
QWEN_TEMPLATE_OUT = (
    "<|im_start|>system\nReturn JSON.<|im_end|>\n<|im_start|>user\nHi<|im_end|>\n"
    "<|im_start|>assistant\n<think>\n\n</think>\n\n"
)


def test_p2d_1_rendered_prompt_is_template_output_byte_for_byte():
    tok = MagicMock()
    tok.apply_chat_template.return_value = QWEN_TEMPLATE_OUT
    messages = [{"role": "system", "content": "Return JSON."}, {"role": "user", "content": "Hi"}]
    prompt = qwen_srv.render_prompt_no_think(tok, messages)
    assert prompt.encode("utf-8") == QWEN_TEMPLATE_OUT.encode("utf-8")
    tok.apply_chat_template.assert_called_once_with(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )


def test_p2d_1_no_logits_processor_and_leak_flagged():
    assert not hasattr(qwen_srv, "ban_think_and_tools_processor")
    tok = MagicMock()
    tok.apply_chat_template.return_value = QWEN_TEMPLATE_OUT
    tok.encode.side_effect = lambda text, add_special_tokens=False: [1] * len(text)
    body = {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 32}

    model = MagicMock()
    model.generate.return_value = '{"service_type": "ocr"}'
    clean = qwen_srv.process_chat_completion(model, tok, body)
    # No response schema -> no constraint processor; the prompt is the template output.
    model.generate.assert_called_once_with(QWEN_TEMPLATE_OUT, 32, None)
    assert "reasoning_leak" not in clean

    model.generate.return_value = '<think>hmm</think>{"service_type": "ocr"}'
    leaked = qwen_srv.process_chat_completion(model, tok, body)
    assert leaked["reasoning_leak"] is True
    assert leaked["choices"][0]["finish_reason"] == "stop"


def test_p2d_1_client_treats_reasoning_leak_as_invalid():
    case = Case(case_id="c", text="t", fields=["service_type"], truth=[{"service_type": "ocr"}])
    client = ChatJsonClient(
        name="q", model="qwen3.5-4b-json@851bf6e8+free", provider_slug="local",
        base_url="http://127.0.0.1:8603", deployment="self-hosted",
    )
    body = {
        "model": "qwen3.5-4b-json@851bf6e8+free",
        "provider": "local",
        "reasoning_leak": True,
        "choices": [{"index": 0, "message": {"role": "assistant", "content": '{"service_type": "ocr"}'},
                     "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 5,
                  "completion_tokens_details": {"reasoning_tokens": 0}},
    }
    ret = (200, json.dumps(body), 0.01, 1.0, 1.01, None, {})
    with patch("src.edgebench.interpreters.chat_json.make_request", return_value=ret):
        dec = client.decide(case)
    assert dec.valid is False
    assert dec.error_type == "reasoning_leak"


# ---------------------------------------------------------------------------
# Finding 2: Laya input_tokens / truncated come from Laya's own sequence builder
# ---------------------------------------------------------------------------
class _WordTok:
    """Whitespace tokenizer with BERT-style special ids (one token per word)."""

    mask_token = "[MASK]"
    mask_token_id = 1
    cls_token_id = 2
    sep_token_id = 3

    def __call__(self, text, add_special_tokens=False):
        return {"input_ids": [100 + len(w) for w in text.split()]}


def _laya_agent(max_len: int, head_max_len: int):
    return SimpleNamespace(tok=_WordTok(), cfg={"max_len": max_len, "head_max_len": head_max_len})


def _q(criteria, ins="Pick service"):
    return {"type": "choice", "instructions": ins, "criteria": criteria}


def test_p2d_2_laya_counts_rendered_options_untruncated():
    # [CLS] + "choice question: Pick service"(4) + [SEP] + [MASK]" ocr: OCR text"(3)
    # + [MASK]" count: Count items"(3) + [SEP] + "a b c"(3) + [SEP] = 19
    agent = _laya_agent(max_len=1024, head_max_len=192)
    q = {"q1": _q({"ocr": "OCR text", "count": "Count items"})}
    total, truncated = compute_untruncated_token_count(agent, "a b c", q)
    assert total == 19
    assert truncated is False

    from laya.agent import Agent
    from laya.common import build_sequence
    fed, _ = build_sequence(agent.tok, "a b c", Agent._to_internal(q["q1"]), 1024, 192)
    assert len(fed) == total


def test_p2d_2_laya_option_budget_truncation_is_reported():
    # Options fit max_len but exceed head_max_len -> Laya cuts them; must be reported.
    long_desc = " ".join(["word"] * 40)
    agent = _laya_agent(max_len=1024, head_max_len=32)
    q = {"q1": _q({"ocr": long_desc, "count": long_desc})}
    total, truncated = compute_untruncated_token_count(agent, "a b c", q)
    # 1 + 4 + 1 + 2*(1 + 41) + 1 + 3 + 1
    assert total == 95
    assert truncated is True


def test_p2d_2_laya_state_truncation_and_multi_question_sum():
    agent = _laya_agent(max_len=20, head_max_len=192)
    state = " ".join(["s"] * 30)
    q = {"q1": _q({"ocr": "OCR", "count": "Count"}), "q2": _q({"yes": "Y", "no": "N"}, ins="Ok?")}
    total, truncated = compute_untruncated_token_count(agent, state, q)
    # q1: 1+4+1+(1+2)+(1+2)+1+30+1 = 44 ; q2: 1+3+1+(1+2)+(1+2)+1+30+1 = 43
    assert total == 87
    assert truncated is True


# ---------------------------------------------------------------------------
# Finding 3: exception fallback keeps measured latency, or None when nothing was sent
# ---------------------------------------------------------------------------
def _write_cases(path: Path, ids: list[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for cid in ids:
            f.write(json.dumps(Case(case_id=cid, text="t", truth=[dict(TRUTH4)]).to_dict()) + "\n")


class _SlowHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", 0)))
        time.sleep(0.15)
        body = b'{"ok": true}'
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


def test_p2d_3_exception_latency_measured_or_none(tmp_path: Path):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _SlowHandler)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class SendThenCrash(Interpreter):
        def decide(self, case: Case) -> Decision:
            if case.case_id == "sent":
                make_request(f"http://127.0.0.1:{port}", "/x", {"a": 1}, timeout_s=5.0)
            raise RuntimeError("parse failure")

    cases_file = tmp_path / "cases.jsonl"
    _write_cases(cases_file, ["sent", "unsent"])
    try:
        with patch("src.edgebench.runner.build_interpreter", return_value=SendThenCrash("m", "self-hosted")):
            run_benchmark(cases_path=cases_file, rq="RQ1a", condition="base", model_names=["m"],
                          out_dir=tmp_path / "out", workers=1, allow_dirty=True)
    finally:
        server.shutdown()
        server.server_close()

    rows = {r["case_id"]: r for r in map(json.loads, open(tmp_path / "out" / "ledger.jsonl"))}
    assert rows["sent"]["valid"] is False and rows["unsent"]["valid"] is False
    assert rows["sent"]["latency_s"] is not None and rows["sent"]["latency_s"] >= 0.15
    assert rows["sent"]["t_send_wall"] > 0
    assert rows["unsent"]["latency_s"] is None


def test_p2d_3_none_latency_excluded_from_latency_stats_but_counted_invalid():
    def row(cid, em, lat):
        return {"case_id": cid, "repeat": 0, "em": em, "valid": lat is not None, "latency_s": lat,
                "unsafe_locality": False, "spurious_count": 0, "missed_count": 0,
                "unspecified_truth_count": 0, "specified_truth_count": 4, "correct": {"service_type": em}}

    model_rows = [row("a", True, 0.2), row("b", False, None), row("c", True, 0.4)]
    ref_rows = [row("a", True, 0.1), row("b", True, 0.1), row("c", True, 0.1)]
    out = scoring.aggregate_metrics(model_rows, reference_rows=ref_rows)
    assert out["n"] == 3
    assert out["valid_rate"] == pytest.approx(2 / 3)
    assert out["em"] == pytest.approx(2 / 3)
    assert out["latency_p50"] == pytest.approx(0.3)
    paired = out["paired_vs_ref"]
    assert paired["paired_n"] == 3
    assert paired["em_diff"] == pytest.approx(-1 / 3)
    assert paired["paired_latency_n"] == 2
    assert paired["latency_diff_median"] == pytest.approx(0.2)


# ---------------------------------------------------------------------------
# Finding 4: H4 ratio-of-ratios bootstrap stratified by D, case-paired
# ---------------------------------------------------------------------------
def test_p2d_4_ratio_of_ratios_stratified_by_d():
    # Within each D stratum all values are constant, so a stratified bootstrap
    # reproduces the original composition in every replicate: CI collapses to the point.
    n1, n2 = 6, 5
    a1 = [2.0] * n1 + [20.0] * n2
    a0 = [1.0] * n1 + [4.0] * n2
    b1 = [3.0] * n1 + [9.0] * n2
    b0 = [1.0] * n1 + [2.0] * n2
    strata = ["D1"] * n1 + ["D2"] * n2

    pt_u, ci_u = scoring.compute_ratio_of_ratios(a1, a0, b1, b0, n_resamples=2000)
    assert ci_u[1] - ci_u[0] > 0  # unstratified: composition varies

    pt, ci = scoring.compute_ratio_of_ratios(a1, a0, b1, b0, n_resamples=2000, strata=strata)
    assert pt == pytest.approx(pt_u)  # pooled point estimate unchanged
    assert ci[0] == pytest.approx(pt) and ci[1] == pytest.approx(pt)

    # Case-paired: identical models give ratio-of-ratios exactly 1 in every replicate.
    rng = np.random.default_rng(1)
    x1 = rng.uniform(1, 5, 11).tolist()
    x0 = rng.uniform(1, 5, 11).tolist()
    pt_same, ci_same = scoring.compute_ratio_of_ratios(x1, x0, x1, x0, n_resamples=500, strata=strata)
    assert pt_same == pytest.approx(1.0) and ci_same == (pytest.approx(1.0), pytest.approx(1.0))


# ---------------------------------------------------------------------------
# Finding 5: Cochran's Q across k interpreters
# ---------------------------------------------------------------------------
HAND_MATRIX = [  # 10 cases x 3 interpreters
    [1, 1, 0], [1, 0, 0], [1, 1, 1], [1, 1, 0], [1, 0, 0],
    [1, 1, 0], [0, 0, 0], [1, 1, 1], [1, 0, 0], [1, 1, 0],
]


def test_p2d_5_cochrans_q_hand_computed():
    # C = (9, 6, 2), N = 17, sum R^2 = 37, k = 3
    # Q = (k-1)(k*sum C^2 - N^2) / (k*N - sum R^2) = 2*(3*121 - 289)/(51 - 37) = 148/14
    res = scoring.cochrans_q(HAND_MATRIX)
    assert res["q"] == pytest.approx(148 / 14)
    assert res["df"] == 2
    assert res["p"] == pytest.approx(math.exp(-(148 / 14) / 2))  # chi2 sf, df=2
    assert res["n"] == 10 and res["k"] == 3


def test_p2d_5_cochrans_q_degenerate_and_per_condition_helper():
    res = scoring.cochrans_q([[1, 1, 1], [0, 0, 0]])
    assert res["q"] == 0.0 and res["p"] == 1.0

    def rows_for(col, order):
        return [
            {"case_id": f"c{i}", "repeat": 0, "em": bool(HAND_MATRIX[i][col]),
             "unsafe_locality": bool(HAND_MATRIX[i][col])}
            for i in order
        ]

    fwd, rev = list(range(10)), list(reversed(range(10)))
    by_cond = {
        "base": {"A": rows_for(0, fwd), "B": rows_for(1, rev), "C": rows_for(2, fwd)},
        # model C lacks case c9 -> case-aligned matrix drops it
        "trim": {"A": rows_for(0, fwd), "B": rows_for(1, fwd), "C": rows_for(2, range(9))},
    }
    pvals = scoring.cochrans_q_pvalues_by_condition(by_cond, metric="em")
    assert pvals["base"] == pytest.approx(math.exp(-(148 / 14) / 2))
    trimmed = scoring.cochrans_q(HAND_MATRIX[:9])
    assert pvals["trim"] == pytest.approx(trimmed["p"])
    assert set(scoring.holm_adjust(pvals)) == {"base", "trim"}
    assert scoring.cochrans_q_pvalues_by_condition(by_cond, metric="unsafe_locality") == pvals


# ---------------------------------------------------------------------------
# Finding 6: RQ4 catalog metrics carry case-bootstrap CIs incl. seen-unseen gap
# ---------------------------------------------------------------------------
def _catalog_fixture(n_seen=12, n_unseen=12, seen_ok=None, unseen_ok=None):
    rows, cases = [], {}
    opts = {"svc_a": "a", "svc_b": "b", "unsupported": "none"}
    for i in range(n_seen + n_unseen):
        seen = i < n_seen
        ok = (seen_ok or (lambda j: True))(i) if seen else (unseen_ok or (lambda j: False))(i)
        truth_svc = "unsupported" if i % 4 == 0 else "svc_a"
        pred_svc = truth_svc if ok else ("svc_b" if truth_svc != "unsupported" else "svc_a")
        cid = f"k{i}"
        cases[cid] = Case(case_id=cid, text="t", fields=["service_type"], service_options=opts,
                          truth=[{"service_type": truth_svc}], meta={"seen": seen})
        rows.append({"case_id": cid, "repeat": 0, "correct": {"service_type": ok},
                     "labels": [{"service_type": pred_svc}]})
    return rows, cases


def test_p2d_6_catalog_bootstrap_cis_and_gap_upper_bound():
    rows, cases = _catalog_fixture()  # seen all correct, unseen all wrong
    m = scoring.compute_catalog_metrics(rows, cases_map=cases)
    assert m["seen_unseen_gap"] == pytest.approx(1.0)
    assert m["seen_unseen_gap_ci95"] == (pytest.approx(1.0), pytest.approx(1.0))
    assert m["seen_unseen_gap_ci_upper"] == pytest.approx(1.0)
    assert m["bootstrap"] == {"seed": 20260924, "n_resamples": 10000, "unit": "case"}
    for key in ("seen_accuracy", "unseen_accuracy", "unsupported_precision",
                "unsupported_recall", "unsupported_f1", "seen_unseen_gap"):
        lo, hi = m[f"{key}_ci95"]
        assert lo <= m[key] <= hi


def test_p2d_6_gap_recomputed_per_replicate_with_joint_case_resampling():
    rows, cases = _catalog_fixture(seen_ok=lambda j: j % 3 != 0, unseen_ok=lambda j: j % 2 == 0)
    m = scoring.compute_catalog_metrics(rows, cases_map=cases, n_resamples=400)

    n = len(rows)
    seen = np.array([cases[r["case_id"]].meta["seen"] for r in rows])
    # P2h: unsupported targets belong to neither the seen nor the unseen bucket
    sup = np.array([cases[r["case_id"]].truth[0]["service_type"] != "unsupported" for r in rows])
    ok = np.array([r["correct"]["service_type"] for r in rows], dtype=float)
    idx = np.random.default_rng(20260924).integers(0, n, size=(400, n))
    gaps = []
    for rep in idx:
        s, u = seen[rep] & sup[rep], ~seen[rep] & sup[rep]
        gaps.append(ok[rep][s].mean() - ok[rep][u].mean())
    ref = (float(np.percentile(gaps, 2.5)), float(np.percentile(gaps, 97.5)))
    assert m["seen_unseen_gap_ci95"][0] == pytest.approx(min(ref[0], m["seen_unseen_gap"]))
    assert m["seen_unseen_gap_ci95"][1] == pytest.approx(max(ref[1], m["seen_unseen_gap"]))
    assert m["seen_unseen_gap_ci_upper"] == m["seen_unseen_gap_ci95"][1]

    agg = scoring.aggregate_metrics(
        [dict(r, em=True, valid=True, latency_s=0.1, unsafe_locality=False, spurious_count=0,
              missed_count=0, unspecified_truth_count=0, specified_truth_count=1) for r in rows],
        cases_map=cases,
    )
    assert "seen_unseen_gap_ci_upper" in agg["catalog"]
