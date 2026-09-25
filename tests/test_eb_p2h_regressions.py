"""Regression tests for the P2h gate-review findings on the self-hosted stack (1 x P0, 8 x P1)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch
import urllib.request
import warnings

import pytest

import scripts.eb_align_check as align
import scripts.eb_run as eb_run
from src.edgebench import provenance
from src.edgebench.contract import Case
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.interpreters.decisions import DecisionsClient
from src.edgebench.interpreters.transport import close_thread_connections
from src.edgebench.ledger import LedgerWriter
from src.edgebench.manifest import build_interpreter, load_manifest
from src.edgebench.runner import run_benchmark
from src.edgebench import scoring
from src.edgebench.scoring import aggregate_metrics

REPO = Path(__file__).resolve().parent.parent
ALIGN_DIR = REPO / "configs" / "edgebench" / "align"
MID = "dec-local@test"
TRUTH4 = {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}


# ---------------------------------------------------------------------------
# Helpers: a single-threaded mock decisions server (like the real servers) with a per-request script
# ---------------------------------------------------------------------------
class _DecisionsServer:
    """HTTPServer (one request at a time, as the real servers). `script(i)` picks the i-th POST's outcome:
    "ok", an int HTTP status, or ("sleep", seconds) before answering "ok"."""

    def __init__(self, script):
        self.script = script
        self.n_post = 0
        self.n_health = 0
        state = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, status: int, data: dict) -> None:
                body = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def do_GET(self):
                state.n_health += 1
                self._send(200, {"status": "ok", "pid": os.getpid()})

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                i = state.n_post
                state.n_post += 1
                action = state.script(i)
                if isinstance(action, tuple) and action[0] == "sleep":
                    time.sleep(action[1])
                    action = "ok"
                if action != "ok":
                    self._send(int(action), {"error": f"scripted {action}", "model": MID})
                    return
                answers = {qid: {"type": "choice", "choice": next(iter(q["criteria"])),
                                 "probabilities": {next(iter(q["criteria"])): 1.0}}
                           for qid, q in req["questions"].items()}
                self._send(200, {"model": MID, "provider": "local", "answers": answers,
                                 "usage": {"input_tokens": 7, "output_tokens": 0, "cost": 0.0}})

            def log_message(self, *a):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        close_thread_connections()  # a held keep-alive connection would block a one-request-at-a-time server
        self.httpd.shutdown()
        self.httpd.server_close()


def _dec_client(url: str, timeout_s: float = 5.0) -> DecisionsClient:
    return DecisionsClient(name="dec", model=MID, accepted_resolved_models=[MID], expected_provider="local",
                           base_url=url, deployment="self-hosted", timeout_s=timeout_s)


def _write_cases(path: Path, n: int) -> Path:
    cases = [Case(case_id=f"c{i}", text="t", truth=[dict(TRUTH4)]) for i in range(n)]
    path.write_text("".join(json.dumps(c.to_dict()) + "\n" for c in cases), encoding="utf-8")
    return path


def _run(cases_file: Path, out: Path, client, **kw):
    with patch("src.edgebench.runner.build_interpreter", return_value=client):
        return run_benchmark(cases_path=cases_file, rq="RQ1a", condition="base", model_names=[client.name],
                             out_dir=out, workers=1, allow_dirty=True, **kw)


def _rows(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "ledger.jsonl").read_text().splitlines() if line.strip()]


class _Fixed(Interpreter):
    """Always-valid reference-like interpreter with configurable usage/cost."""

    def __init__(self, name="m", deployment="self-hosted", cost=0.0, tokens=3):
        super().__init__(name, deployment)
        self.cost, self.tokens = cost, tokens

    def decide(self, case: Case) -> Decision:
        return Decision(labels=[dict(t) for t in case.truth], valid=True, latency_s=0.01,
                        input_tokens=self.tokens, output_tokens=self.tokens, reasoning_tokens=self.tokens,
                        cost_usd=self.cost)


# ---------------------------------------------------------------------------
# Fix 1 (P0-1): 3 consecutive self-hosted 5xx stop the run like the server-down path
# ---------------------------------------------------------------------------
def test_p2h_1_persistent_5xx_stops_after_three_and_resume_sends_rest(tmp_path: Path):
    n, k = 9, 2
    broken = {"on": True}
    srv = _DecisionsServer(lambda i: 500 if broken["on"] and i >= k else "ok")
    cases_file = _write_cases(tmp_path / "cases.jsonl", n)
    out = tmp_path / "out"
    try:
        rep = _run(cases_file, out, _dec_client(srv.url))
        rows = _rows(out)
        assert len(rows) == k + 3
        assert [r["http_status"] for r in rows] == [200] * k + [500] * 3
        assert rep["stop_reason"] == "self_hosted_server_error"
        assert json.loads((out / "integrity.json").read_text())["stop_reason"] == "self_hosted_server_error"
        assert srv.n_post == k + 3  # nothing sent after the third 5xx

        broken["on"] = False  # server restarted
        rep2 = _run(cases_file, out, _dec_client(srv.url))
    finally:
        srv.close()
    rows = _rows(out)
    assert len(rows) == n and len({r["case_id"] for r in rows}) == n
    assert rep2["stop_reason"] is None and rep2["duplicates"] == 0
    assert srv.n_post == n  # resume sent exactly the rest; the 5xx rows are kept


def test_p2h_1_4xx_and_nonconsecutive_5xx_do_not_stop(tmp_path: Path):
    # SemIf 400 at K>=64 / Laya 400 at K=254 are by design; a 5xx streak broken by a success resets.
    pattern = [400, 400, 400, 400, 500, 500, "ok", 500, 500, "ok"]
    srv = _DecisionsServer(lambda i: pattern[i])
    cases_file = _write_cases(tmp_path / "cases.jsonl", len(pattern))
    try:
        rep = _run(cases_file, tmp_path / "out", _dec_client(srv.url))
    finally:
        srv.close()
    assert rep["stop_reason"] is None
    assert len(_rows(tmp_path / "out")) == len(pattern)


def test_p2h_1_eb_run_exits_3_on_server_error(monkeypatch):
    argv = ["eb_run.py", "--cases", "x", "--rq", "RQ1a", "--condition", "c", "--models", "m", "--out", "o"]
    monkeypatch.setattr(sys, "argv", argv)
    report = {"stop_reason": "self_hosted_server_error", "total_spend_usd": 0.0,
              "expected_rows_per_model_repeat": {"m:r0": 5}, "actual_rows_per_model_repeat": {"m:r0": 3},
              "duplicates": 0}
    with patch.object(eb_run, "run_benchmark", return_value=report):
        with pytest.raises(SystemExit) as exc:
            eb_run.main()
    assert exc.value.code == 3


def test_p2h_1_align_run_exits_nonzero_when_not_all_valid(tmp_path: Path):
    fixture = _write_cases(tmp_path / "fx.jsonl", 3)

    class Half(_Fixed):
        def decide(self, case):
            d = super().decide(case)
            d.valid = case.case_id != "c1"
            return d

    with patch.object(align, "build_interpreter", return_value=Half()):
        assert align.main(["run", "--model", "m", "--out", str(tmp_path / "a.json"), "--cases", str(fixture)]) != 0
    assert json.loads((tmp_path / "a.json").read_text())["valid"] == 2  # written before the non-zero exit
    with patch.object(align, "build_interpreter", return_value=_Fixed()):
        assert align.main(["run", "--model", "m", "--out", str(tmp_path / "b.json"), "--cases", str(fixture)]) == 0


# ---------------------------------------------------------------------------
# Fix 2 (P1-1): after a client timeout on a self-hosted server, wait for /health before the next request
# ---------------------------------------------------------------------------
def test_p2h_2_timeout_waits_for_server_backlog_before_next_request(tmp_path: Path):
    srv = _DecisionsServer(lambda i: ("sleep", 1.6) if i == 0 else "ok")
    cases_file = _write_cases(tmp_path / "cases.jsonl", 3)
    try:
        rep = _run(cases_file, tmp_path / "out", _dec_client(srv.url, timeout_s=0.6))
    finally:
        srv.close()
    rows = _rows(tmp_path / "out")
    assert rep["stop_reason"] is None and len(rows) == 3
    timed_out = rows[0]
    assert timed_out["error_type"] == "TimeoutError" and timed_out["http_status"] is None
    assert timed_out["post_timeout_wait_s"] is not None and timed_out["post_timeout_wait_s"] >= 0.5
    assert srv.n_health >= 1
    for r in rows[1:]:
        assert r["valid"] is True
        assert r["latency_s"] < 0.4  # the next case does not absorb the abandoned request's backlog
        assert r["post_timeout_wait_s"] is None


# ---------------------------------------------------------------------------
# Fix 3 (P1-2): torn final ledger line is truncated on open; row-count mismatch exits 4
# ---------------------------------------------------------------------------
def test_p2h_3_torn_tail_is_dropped_and_resume_yields_n_unique_rows(tmp_path: Path):
    n = 5
    cases_file = _write_cases(tmp_path / "cases.jsonl", n)
    out = tmp_path / "out"
    _run(cases_file, out, _Fixed())
    ledger = out / "ledger.jsonl"
    data = ledger.read_bytes()
    ledger.write_bytes(data[:-25])  # crash mid-write of the last row: no trailing newline
    rep = _run(cases_file, out, _Fixed())
    lines = ledger.read_text().splitlines()
    rows = [json.loads(line) for line in lines]  # every line parses
    assert len(rows) == n and len({r["case_id"] for r in rows}) == n
    assert rep["torn_line_dropped"] is True and rep["duplicates"] == 0
    assert json.loads((out / "integrity.json").read_text())["torn_line_dropped"] is True
    rep2 = _run(cases_file, out, _Fixed())
    assert rep2["torn_line_dropped"] is False


def test_p2h_3_torn_complete_json_without_newline_is_rerun(tmp_path: Path):
    # A row whose JSON is complete but whose newline never landed is torn too: it is dropped and re-run.
    n = 3
    cases_file = _write_cases(tmp_path / "cases.jsonl", n)
    out = tmp_path / "out"
    _run(cases_file, out, _Fixed())
    ledger = out / "ledger.jsonl"
    ledger.write_bytes(ledger.read_bytes()[:-1])
    rep = _run(cases_file, out, _Fixed())
    rows = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert len(rows) == n and rep["torn_line_dropped"] is True and ledger.read_bytes().endswith(b"\n")


@pytest.mark.parametrize("actual,dups,code", [({"m:r0": 4}, 0, 4), ({"m:r0": 5}, 1, 4), ({"m:r0": 5}, 0, None)])
def test_p2h_3_eb_run_exits_4_on_row_count_or_duplicates(monkeypatch, actual, dups, code):
    argv = ["eb_run.py", "--cases", "x", "--rq", "RQ1a", "--condition", "c", "--models", "m", "--out", "o"]
    monkeypatch.setattr(sys, "argv", argv)
    report = {"stop_reason": None, "total_spend_usd": 0.0, "expected_rows_per_model_repeat": {"m:r0": 5},
              "actual_rows_per_model_repeat": actual, "duplicates": dups}
    with patch.object(eb_run, "run_benchmark", return_value=report):
        if code is None:
            eb_run.main()
        else:
            with pytest.raises(SystemExit) as exc:
                eb_run.main()
            assert exc.value.code == code == eb_run.EXIT_INTEGRITY


# ---------------------------------------------------------------------------
# Fix 4 (P1-3): missing usage / cost stays None ("unknown"), never 0
# ---------------------------------------------------------------------------
def _case1() -> Case:
    return Case(case_id="c", text="t", truth=[dict(TRUTH4)])


def _ok_answers(case: Case) -> dict:
    client = DecisionsClient(name="d", model=MID, accepted_resolved_models=[MID])
    return {qid: {"type": "choice", "choice": next(iter(q["criteria"]))}
            for qid, q in client.build_request(case)["questions"].items()}


def _decide_decisions(body: dict, accepted=(MID,)) -> Decision:
    client = DecisionsClient(name="d", model=MID, accepted_resolved_models=list(accepted))
    ret = (200, json.dumps(body), 0.1, 1.0, 1.1, None, {})
    with patch("src.edgebench.interpreters.decisions.make_request", return_value=ret):
        return client.decide(_case1())


def test_p2h_4_decision_defaults_are_unknown():
    d = Decision()
    assert d.input_tokens is None and d.output_tokens is None and d.reasoning_tokens is None
    assert d.completion_tokens_raw is None and d.cost_usd is None
    assert Decision(output_tokens=4).completion_tokens_raw == 4


def test_p2h_4_decisions_missing_usage_is_none():
    d = _decide_decisions({"model": MID, "answers": _ok_answers(_case1())})
    assert d.valid is True
    assert (d.input_tokens, d.output_tokens, d.reasoning_tokens, d.cost_usd) == (None, None, None, None)
    d0 = _decide_decisions({"model": MID, "answers": _ok_answers(_case1()),
                            "usage": {"input_tokens": 0, "output_tokens": 0, "cost": 0.0}})
    assert (d0.input_tokens, d0.output_tokens, d0.cost_usd) == (0, 0, 0.0)  # reported zero stays zero


def test_p2h_4_decisions_mismatch_and_missing_answers_keep_usage():
    usage = {"input_tokens": 42, "output_tokens": 3, "cost": 0.5}
    mm = _decide_decisions({"model": "other", "answers": {}, "usage": usage})
    assert mm.error_type == "model_mismatch"
    assert (mm.input_tokens, mm.output_tokens, mm.cost_usd) == (42, 3, 0.5)
    ma = _decide_decisions({"model": MID, "answers": "nope", "usage": usage})
    assert ma.error_type == "missing_answers"
    assert (ma.input_tokens, ma.output_tokens, ma.cost_usd) == (42, 3, 0.5)


def _decide_chat(usage: dict | None, deployment="hosted") -> Decision:
    client = ChatJsonClient(name="q", model="q/m", provider_slug="p", deployment=deployment,
                            base_url="https://openrouter.ai" if deployment == "hosted" else "http://127.0.0.1:1")
    case = _case1()
    body = {"model": "q/m", "choices": [{"finish_reason": "stop",
                                         "message": {"content": json.dumps(TRUTH4)}}]}
    if usage is not None:
        body["usage"] = usage
    ret = (200, json.dumps(body), 0.1, 1.0, 1.1, None, {})
    with patch("src.edgebench.interpreters.chat_json.make_request", return_value=ret):
        return client.decide(case)


def test_p2h_4_chat_json_missing_usage_is_none_and_reasoning_unverifiable_is_flagged():
    d = _decide_chat(None)
    assert d.valid is True  # still scored
    assert (d.input_tokens, d.output_tokens, d.reasoning_tokens, d.cost_usd) == (None, None, None, None)
    assert d.reasoning_tokens_missing is True
    d2 = _decide_chat({"prompt_tokens": 5, "completion_tokens": 2, "cost": 0.01})
    assert d2.reasoning_tokens is None and d2.reasoning_tokens_missing is True and d2.valid is True
    d3 = _decide_chat({"prompt_tokens": 5, "completion_tokens": 2,
                       "completion_tokens_details": {"reasoning_tokens": 0}, "cost": 0.01})
    assert d3.reasoning_tokens == 0 and d3.reasoning_tokens_missing is False
    d4 = _decide_chat({"prompt_tokens": 5, "completion_tokens": 2,
                       "completion_tokens_details": {"reasoning_tokens": 7}})
    assert d4.valid is False and d4.error_type == "reasoning_tokens_nonzero" and d4.cost_usd is None


def test_p2h_4_ledger_writes_null_and_usage_reported(tmp_path: Path):
    w = LedgerWriter(tmp_path / "l.jsonl", run_id="r", git_sha="s", rq="RQ1a", condition="c")
    unknown = w.write_row("m", "c1", 0, Decision(labels=[]), correct={}, em=False)
    known = w.write_row("m", "c2", 0, Decision(labels=[], input_tokens=5, output_tokens=0, cost_usd=0.0),
                        correct={}, em=False)
    w.close()
    rows = [json.loads(x) for x in (tmp_path / "l.jsonl").read_text().splitlines()]
    assert rows[0]["input_tokens"] is None and rows[0]["cost_usd"] is None and rows[0]["usage_reported"] is False
    assert rows[1]["input_tokens"] == 5 and rows[1]["usage_reported"] is True
    assert unknown["reasoning_tokens_missing"] is False and known["usage_reported"] is True


def test_p2h_4_runner_counts_unknown_cost_and_reasoning_missing(tmp_path: Path):
    cases_file = _write_cases(tmp_path / "cases.jsonl", 3)
    out = tmp_path / "out"
    rep = _run(cases_file, out, _Fixed(cost=None, tokens=None))
    assert rep["stop_reason"] is None and len(_rows(out)) == 3
    assert rep["total_spend_usd"] == 0.0
    assert rep["total_cost_per_model"]["m"] is None
    assert rep["cost_unknown_rows"] == 3 and rep["usage_unreported_rows"] == 3
    assert rep["reasoning_tokens_missing_rows"] == 0
    # resume over null-cost rows reads them as unknown (no crash, no silent zero-cost row)
    rep2 = _run(cases_file, out, _Fixed(cost=None, tokens=None))
    assert rep2["duplicates"] == 0 and rep2["cost_unknown_rows"] == 3


def _score_row(case_id: str, **kw) -> dict:
    row = {"case_id": case_id, "repeat": 0, "em": True, "valid": True, "correct": {"urgency": True},
           "unsafe_locality": False, "spurious_count": 0, "missed_count": 0, "unspecified_truth_count": 0,
           "specified_truth_count": 1, "latency_s": 0.1}
    row.update(kw)
    return row


def test_p2h_4_scoring_means_over_known_only_with_counts():
    rows = [_score_row("a", input_tokens=10, output_tokens=None, reasoning_tokens=None, cost_usd=1.0),
            _score_row("b", input_tokens=None, output_tokens=None, reasoning_tokens=None, cost_usd=None),
            _score_row("c", input_tokens=20, output_tokens=None, reasoning_tokens=None, cost_usd=3.0)]
    agg = aggregate_metrics(rows)
    assert agg["n_input_tokens"] == 2 and agg["mean_input_tokens"] == 15.0 and agg["total_input_tokens"] == 30
    assert agg["n_output_tokens"] == 0 and agg["mean_output_tokens"] is None and agg["total_output_tokens"] is None
    assert agg["n_cost"] == 2 and agg["total_cost_usd"] == 4.0
    assert agg["cost_per_1000_correct"] == pytest.approx(4.0 / 2 * 1000.0)


def _laya_rows(n: int) -> list[dict]:
    return [dict(_score_row(f"c{i}", input_tokens=None, output_tokens=0, reasoning_tokens=None, cost_usd=0.0),
                 rq="RQ1a", condition="base", model="Laya@cuda") for i in range(n)]


def test_p2h_4_laya_sidecar_join_and_missing_sidecar_is_none(tmp_path: Path):
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in _laya_rows(2)), encoding="utf-8")
    with pytest.warns(UserWarning, match="laya_tokens"):
        rows = scoring.load_ledger_rows(ledger)
    assert all(r["input_tokens"] is None for r in rows)
    assert aggregate_metrics(rows)["mean_input_tokens"] is None  # never 0

    sidecar = Path(f"{ledger}.laya_tokens.jsonl")
    sidecar.write_text("".join(json.dumps({"condition": "base", "case_id": f"c{i}", "input_tokens": 100 + i,
                                           "truncated": i == 1, "model_revision": "x"}) + "\n" for i in range(2)))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        rows = scoring.load_ledger_rows(ledger)
    assert [r["input_tokens"] for r in rows] == [100, 101] and [r["truncated"] for r in rows] == [False, True]
    agg = aggregate_metrics(rows)
    assert agg["mean_input_tokens"] == 100.5 and agg["n_input_tokens"] == 2


# ---------------------------------------------------------------------------
# Fix 5 (P1-4): the cases file is provenance-bound
# ---------------------------------------------------------------------------
def test_p2h_5_cases_sha256_in_integrity_and_rows(tmp_path: Path):
    import hashlib

    cases_file = _write_cases(tmp_path / "cases.jsonl", 3)
    rep = _run(cases_file, tmp_path / "out", _Fixed())
    digest = hashlib.sha256(cases_file.read_bytes()).hexdigest()
    assert rep["cases_sha256"] == digest
    assert json.loads((tmp_path / "out" / "integrity.json").read_text())["cases_sha256"] == digest
    assert {r["cases_sha256"] for r in _rows(tmp_path / "out")} == {digest}


def _provenance_root(tmp_path: Path, listed: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "PROVENANCE.json").write_text(json.dumps({"head_sha": "a" * 40, "files": listed}))
    return root


def _run_gitless(root: Path, cases_file: Path, out: Path):
    with patch("src.edgebench.runner.resolve_git_provenance",
               return_value=("a" * 40, False, "provenance", "t" * 64)), \
         patch.object(provenance, "REPO_ROOT", root):
        return _run(cases_file, out, _Fixed())


def test_p2h_5_gitless_mode_requires_cases_listed_with_matching_hash(tmp_path: Path):
    root = _provenance_root(tmp_path, {})
    rel = "data/edgebench/v1/RQ1a/base/test.jsonl"
    cases_file = root / rel
    cases_file.parent.mkdir(parents=True)
    _write_cases(cases_file, 2)

    with pytest.raises(RuntimeError, match="not listed"):
        _run_gitless(root, cases_file, tmp_path / "o1")
    assert not (tmp_path / "o1" / "ledger.jsonl").exists()

    (root / "PROVENANCE.json").write_text(json.dumps({"head_sha": "a" * 40, "files": {rel: "0" * 64}}))
    with pytest.raises(RuntimeError, match="does not match"):
        _run_gitless(root, cases_file, tmp_path / "o2")

    outside = _write_cases(tmp_path / "elsewhere.jsonl", 2)
    with pytest.raises(RuntimeError):
        _run_gitless(root, outside, tmp_path / "o3")

    (root / "PROVENANCE.json").write_text(json.dumps(
        {"head_sha": "a" * 40, "files": {rel: provenance.sha256_file(cases_file)}}))
    rep = _run_gitless(root, cases_file, tmp_path / "o4")
    assert rep["stop_reason"] is None and len(_rows(tmp_path / "o4")) == 2


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


@pytest.mark.parametrize("ignored", [False, True])
def test_p2h_5_build_provenance_lists_corpus_data_tracked_or_not(tmp_path: Path, ignored: bool):
    root = tmp_path / "r"
    root.mkdir()
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    (root / "code.py").write_text("x = 1\n")
    if ignored:
        (root / ".gitignore").write_text("data/\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-qm", "init")
    data = root / "data" / "edgebench" / "v1" / "RQ1a" / "base" / "test.jsonl"
    data.parent.mkdir(parents=True)
    data.write_text('{"case_id": "c0"}\n')
    built = provenance.build_provenance(root)
    rel = "data/edgebench/v1/RQ1a/base/test.jsonl"
    assert built["files"][rel] == provenance.sha256_file(data)
    assert "code.py" in built["files"]
    assert provenance.verify_provenance(root)[0] == built["head_sha"]
    # other untracked files still refuse the build
    (root / "stray.txt").write_text("x")
    if not ignored:
        with pytest.raises(RuntimeError, match="not clean"):
            provenance.build_provenance(root)


# ---------------------------------------------------------------------------
# Fix 6 (P1-5): /health reports the server pid; per-job port offset; --base-url override
# ---------------------------------------------------------------------------
def _health_of(handler_cls) -> dict:
    httpd = HTTPServer(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{httpd.server_address[1]}/health", timeout=5) as r:
            return json.loads(r.read())
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_p2h_6_servers_health_reports_pid():
    import scripts.eb_serve_laya as laya_srv
    import scripts.eb_serve_qwen_json as qwen_srv
    import scripts.eb_serve_semif as semif_srv

    for cls in (laya_srv.LayaRequestHandler, qwen_srv.QwenJsonRequestHandler, semif_srv.SemIfRequestHandler):
        body = _health_of(cls)
        assert body["pid"] == os.getpid() and body["status"] == "ok"


def _bash(script: str, env_extra: dict[str, str], tmp_path: Path) -> subprocess.CompletedProcess:
    path = tmp_path / "blk.sh"
    path.write_text("set -euo pipefail\n" + script)
    env = {"PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin", **env_extra}
    return subprocess.run(["bash", str(path)], env=env, capture_output=True, text=True, timeout=60)


def test_p2h_6_base_url_override_for_self_hosted_only(tmp_path: Path):
    m = build_interpreter("Laya@cuda", manifest=load_manifest(), base_url="http://127.0.0.1:8655")
    assert m.base_url == "http://127.0.0.1:8655"
    with pytest.raises(ValueError):
        build_interpreter("Jev-1.13.0", manifest=load_manifest(), base_url="http://127.0.0.1:8655", api_key="x")

    srv = _DecisionsServer(lambda i: "ok")
    manifest = {"dec": {"adapter": "decisions", "deployment": "self-hosted", "platform": "H100-NVL", "model": MID,
                        "accepted_resolved_models": [MID], "base_url": "http://127.0.0.1:1"}}
    mpath = tmp_path / "models.json"
    mpath.write_text(json.dumps(manifest))
    cases_file = _write_cases(tmp_path / "cases.jsonl", 2)
    try:
        rep = run_benchmark(cases_path=cases_file, rq="RQ1a", condition="base", model_names=["dec"],
                            out_dir=tmp_path / "out", workers=1, allow_dirty=True, manifest_path=mpath,
                            base_url=srv.url)
    finally:
        srv.close()
    assert rep["stop_reason"] is None and len(_rows(tmp_path / "out")) == 2
    assert rep["effective_base_urls"] == {"dec": srv.url}


def test_p2h_6_eb_run_and_align_accept_base_url(monkeypatch, tmp_path: Path):
    argv = ["eb_run.py", "--cases", "x", "--rq", "RQ1a", "--condition", "c", "--models", "m", "--out", "o",
            "--base-url", "http://127.0.0.1:8650"]
    monkeypatch.setattr(sys, "argv", argv)
    report = {"stop_reason": None, "total_spend_usd": 0.0, "expected_rows_per_model_repeat": {},
              "actual_rows_per_model_repeat": {}, "duplicates": 0}
    with patch.object(eb_run, "run_benchmark", return_value=report) as rb:
        eb_run.main()
    assert rb.call_args.kwargs["base_url"] == "http://127.0.0.1:8650"

    fixture = _write_cases(tmp_path / "fx.jsonl", 1)
    with patch.object(align, "build_interpreter", return_value=_Fixed()) as bi:
        align.main(["run", "--model", "m", "--out", str(tmp_path / "a.json"), "--cases", str(fixture),
                    "--base-url", "http://127.0.0.1:8650"])
    assert bi.call_args.kwargs["base_url"] == "http://127.0.0.1:8650"
    assert "base_url" in json.loads((tmp_path / "a.json").read_text())  # effective URL recorded


# ---------------------------------------------------------------------------
# Fix 7 (P1-6): GPU bind is mandatory
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fix 8 (P1-7): uv-managed Python and user caches live under $OUTROOT
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fix 9 (P1-8): MLX alignment references + CUDA compare gate
# ---------------------------------------------------------------------------
def _align_file(labels_per_case: list[dict], valid: list[bool]) -> dict:
    cases = [{"case_id": f"c{i:02d}", "valid": v, "labels": [lab], "probabilities": None,
              "request_sha256": f"{i:064x}"}  # same requests on both sides (P2i gate)
             for i, (lab, v) in enumerate(zip(labels_per_case, valid))]
    return {"model": "m", "platform": "x", "resolved_models": ["r"], "n": len(cases),
            "valid": sum(valid), "em": 0, "cases": cases}


def test_p2h_9_compare_gate(tmp_path: Path):
    base = [dict(TRUTH4) for _ in range(20)]
    a = tmp_path / "a.json"
    a.write_text(json.dumps(_align_file(base, [True] * 20)))

    def gate(b_labels, b_valid) -> int:
        b = tmp_path / "b.json"
        b.write_text(json.dumps(_align_file(b_labels, b_valid)))
        out = tmp_path / "cmp.json"
        out.unlink(missing_ok=True)
        rc = align.main(["compare", str(a), str(b), "--out", str(out), "--gate"])
        assert out.exists()  # the compare JSON is written whether or not the gate passes
        return rc

    assert gate(base, [True] * 20) == 0
    assert gate(base, [True] * 19 + [False]) != 0  # valid < 20
    four_off = [dict(TRUTH4, urgency="urgent") if i < 5 else dict(TRUTH4) for i in range(20)]
    assert gate(four_off, [True] * 20) != 0  # 75/80 = 0.9375 < 0.95
    three_off = [dict(TRUTH4, urgency="urgent") if i < 4 else dict(TRUTH4) for i in range(20)]
    assert gate(three_off, [True] * 20) == 0  # 76/80 = 0.95
    assert gate(base[:19], [True] * 19) != 0  # fewer than 20 cases
    report = json.loads((tmp_path / "cmp.json").read_text())
    assert report["gate"]["passed"] is False


@pytest.mark.parametrize("name,model", [("semif", "SemIf-Qwen3.5-4B"), ("laya", "Laya"),
                                        ("qwen_json", "Qwen3.5-4B-JSON")])
def test_p2h_9_mlx_alignment_references_are_tracked(name: str, model: str):
    path = ALIGN_DIR / f"mlx_{name}.json"
    ref = json.loads(path.read_text())
    assert ref["model"] == model and ref["platform"] == "M4-Max"
    assert ref["resolved_models"] == [load_manifest()[model]["model"]]
    assert ref["n"] == 20 and ref["valid"] == 20
    assert "code_sha" in ref and "date_utc" in ref


# ---------------------------------------------------------------------------
# Fix 10 (corpus-review P1, scoring side): seen/unseen buckets exclude unsupported targets and seen=None
# ---------------------------------------------------------------------------
def test_p2h_10_seen_unseen_buckets_exclude_unsupported_and_unknown():
    from src.edgebench.scoring import compute_catalog_metrics

    opts = {"svc_a": "a", "svc_b": "b", "unsupported": "none of the catalog"}

    def case(cid: str, seen, truth_svc: str) -> Case:
        return Case(case_id=cid, text="t", fields=["service_type"], service_options=opts,
                    truth=[{"service_type": truth_svc}], meta={"seen": seen})

    def row(cid: str, pred: str, truth_svc: str) -> dict:
        return {"case_id": cid, "labels": [{"service_type": pred}], "correct": {"service_type": pred == truth_svc}}

    spec = [  # (case_id, seen, truth, prediction)
        ("s1", True, "svc_a", "svc_a"), ("s2", True, "svc_b", "svc_a"),
        ("u1", False, "svc_a", "svc_b"), ("u2", False, "svc_b", "svc_a"), ("u3", False, "svc_a", "svc_a"),
        ("x1", False, "unsupported", "unsupported"), ("x2", False, "unsupported", "unsupported"),  # legacy seen=False
        ("x3", None, "unsupported", "unsupported"), ("x4", None, "unsupported", "svc_a"),  # new corpus: seen=None
    ]
    cases_map = {cid: case(cid, seen, t) for cid, seen, t, _ in spec}
    rows = [row(cid, p, t) for cid, _, t, p in spec]
    m = compute_catalog_metrics(rows, cases_map=cases_map, n_resamples=200)
    assert m["seen_n"] == 2 and m["seen_accuracy"] == 0.5
    # the unsupported targets no longer inflate the unseen bucket (was 3/5 with x1, x2 counted as unseen)
    assert m["unseen_n"] == 3 and m["unseen_accuracy"] == pytest.approx(1 / 3)
    assert m["seen_unseen_gap"] == pytest.approx(0.5 - 1 / 3)
    # unsupported cases are still scored in the unsupported bucket
    assert (m["unsupported_tp"], m["unsupported_fn"], m["unsupported_fp"]) == (3, 1, 0)
