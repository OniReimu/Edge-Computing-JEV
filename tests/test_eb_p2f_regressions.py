"""Regression tests for the P2f review findings on P2d/P2e (1 x P0, 4 x P1, 1 x P2)."""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import random
import socket
import subprocess
import sys
import threading
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import scripts.eb_serve_laya as laya_srv
import scripts.eb_serve_qwen_json as qwen_srv
from src.edgebench.contract import Case
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.runner import run_benchmark

REPO = Path(__file__).resolve().parent.parent
MODEL_ID = "qj-local@test"


# ---------------------------------------------------------------------------
# Mock self-hosted chat_json server: can "die" (drop every chat request) and records /warmup calls
# ---------------------------------------------------------------------------
def _answer_for(schema: dict) -> dict:
    props = schema["properties"]
    if "requests" in props:
        item = props["requests"]["items"]
        return {"requests": [_answer_for(item) for _ in range(props["requests"]["minItems"])]}
    return {f: spec["enum"][0] for f, spec in props.items()}


class _MockServer:
    def __init__(self, warmup_supported: bool = True):
        self.die_after: int | None = None
        self.n_chat = 0
        self.events: list[tuple[str, object]] = []
        self.warmup_supported = warmup_supported
        state = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _send(self, status: int, data: dict) -> None:
                body = json.dumps(data).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                if self.path == "/warmup":
                    if not state.warmup_supported:
                        self._send(404, {"error": "Endpoint not found"})
                        return
                    state.events.append(("warmup", req["schemas"]))
                    self._send(200, {"schemas": [
                        {"schema_sha256": hashlib.sha256(json.dumps(s).encode()).hexdigest(),
                         "compile_s": 0.25, "cached": False} for s in req["schemas"]]})
                    return
                if state.die_after is not None and state.n_chat >= state.die_after:
                    self.close_connection = True  # crashed server: connection dropped, no response
                    return
                state.n_chat += 1
                schema = req["response_format"]["json_schema"]["schema"]
                state.events.append(("chat", schema))
                self._send(200, {
                    "model": MODEL_ID, "provider": "local",
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": json.dumps(_answer_for(schema))}}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 5,
                              "completion_tokens_details": {"reasoning_tokens": 0}, "cost": 0.0},
                })

            def log_message(self, *a):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


def _client(port: int) -> ChatJsonClient:
    return ChatJsonClient(name="qj", model=MODEL_ID, provider_slug="local", accepted_resolved_models=[MODEL_ID],
                          base_url=f"http://127.0.0.1:{port}", deployment="self-hosted", timeout_s=5.0)


TRUTH4 = {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}


def _write(path: Path, cases: list[Case]) -> Path:
    path.write_text("".join(json.dumps(c.to_dict()) + "\n" for c in cases), encoding="utf-8")
    return path


def _run(cases_file: Path, out: Path, client):
    with patch("src.edgebench.runner.build_interpreter", return_value=client):
        return run_benchmark(cases_path=cases_file, rq="RQ1a", condition="base", model_names=["qj"],
                             out_dir=out, workers=1, allow_dirty=True)


def _rows(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "ledger.jsonl").read_text().splitlines() if line.strip()]


# ---------------------------------------------------------------------------
# Fix 1 (P0): self-hosted server crash mid-condition stops the run; resume completes the rest
# ---------------------------------------------------------------------------
def test_p2f_1_server_dies_after_k_requests_stops_and_resume_completes(tmp_path: Path):
    srv = _MockServer()
    n, k = 6, 2
    cases_file = _write(tmp_path / "cases.jsonl",
                        [Case(case_id=f"c{i}", text="t", truth=[dict(TRUTH4)]) for i in range(n)])
    out = tmp_path / "out"
    try:
        srv.die_after = k
        rep1 = _run(cases_file, out, _client(srv.port))
        rows1 = _rows(out)
        assert len(rows1) == k + 1
        assert rep1["stop_reason"] == "self_hosted_server_down"
        assert json.loads((out / "integrity.json").read_text())["stop_reason"] == "self_hosted_server_down"
        failing = rows1[-1]
        assert failing["valid"] is False and failing["http_status"] is None
        assert failing["error_type"] in ("RemoteDisconnected", "ConnectionResetError", "BrokenPipeError")
        assert all(r["valid"] for r in rows1[:-1])

        srv.die_after = None  # server restarted
        rep2 = _run(cases_file, out, _client(srv.port))
    finally:
        srv.close()

    rows = _rows(out)
    assert len(rows) == n
    assert len({r["case_id"] for r in rows}) == n
    assert rep2["stop_reason"] is None and rep2["duplicates"] == 0
    assert srv.n_chat == n - 1  # the failing case keeps its invalid row and is not re-sent
    assert rows[k]["case_id"] == failing["case_id"] and rows[k]["valid"] is False


def test_p2f_1_connection_refused_stops_after_first_row(tmp_path: Path):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()  # nothing listens on this port
    cases_file = _write(tmp_path / "cases.jsonl",
                        [Case(case_id=f"c{i}", text="t", truth=[dict(TRUTH4)]) for i in range(4)])
    rep = _run(cases_file, tmp_path / "out", _client(port))
    rows = _rows(tmp_path / "out")
    assert len(rows) == 1 and rows[0]["error_type"] == "ConnectionRefusedError"
    assert rep["stop_reason"] == "self_hosted_server_down"


def test_p2f_1_eb_run_exits_nonzero_on_server_down(monkeypatch):
    import scripts.eb_run as eb_run

    argv = ["eb_run.py", "--cases", "x", "--rq", "RQ1a", "--condition", "c", "--models", "m", "--out", "o"]
    monkeypatch.setattr(sys, "argv", argv)
    report = {"stop_reason": "self_hosted_server_down", "total_spend_usd": 0.0,
              "expected_rows_per_model_repeat": {"m:r0": 1}, "actual_rows_per_model_repeat": {"m:r0": 1},
              "duplicates": 0}
    with patch.object(eb_run, "run_benchmark", return_value=report):
        with pytest.raises(SystemExit) as exc:
            eb_run.main()
    assert exc.value.code == eb_run.EXIT_SELF_HOSTED_SERVER_DOWN != 0

    with patch.object(eb_run, "run_benchmark", return_value=dict(report, stop_reason=None)):
        eb_run.main()  # a completed run exits 0


# ---------------------------------------------------------------------------
# Fix 2 (P1): Laya counting runs after inference; state tokenized once per request
# ---------------------------------------------------------------------------
class _CountingTok:
    mask_token = "[MASK]"
    mask_token_id = 1
    cls_token_id = 2
    sep_token_id = 3

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text, add_special_tokens=False):
        self.calls.append(text)
        return {"input_ids": [100 + len(w) for w in text.split()]}


def _q(criteria, ins="Pick service"):
    return {"type": "choice", "instructions": ins, "criteria": criteria}


def test_p2f_2_state_tokenized_once():
    # Counting left the server in P2g (scripts/eb_laya_tokens.py); the count itself still tokenizes
    # the question-independent state once per request.
    tok = _CountingTok()
    agent = SimpleNamespace(tok=tok, cfg={"max_len": 1024, "head_max_len": 192})
    state = "read the parcel label at the dock"
    questions = {f"q{i}": _q({"ocr": "OCR text", "count": "Count items"}) for i in range(3)}
    total, truncated = laya_srv.compute_untruncated_token_count(agent, state, questions)
    assert tok.calls.count(state) == 1
    assert total > 0 and truncated is False


def _reference_count(agent, state, questions):
    """The P2d implementation: full build_sequence per question vs the untruncated rendering."""
    from laya.agent import Agent
    from laya.common import build_sequence, render_options, serialize_state

    tok = agent.tok
    total, trunc = 0, False
    for qid, qd in questions.items():
        q = Agent._to_internal(qd)
        ins = str(q["ins"]).replace(tok.mask_token, " ")
        full = [tok.cls_token_id] + tok("%s question: %s" % (q["t"], ins))["input_ids"] + [tok.sep_token_id]
        for opt in render_options(q):
            full += [tok.mask_token_id] + tok(" " + opt)["input_ids"]
        full += [tok.sep_token_id] + tok(serialize_state(state))["input_ids"] + [tok.sep_token_id]
        fed, _ = build_sequence(tok, state, q, agent.cfg.get("max_len", 512), agent.cfg.get("head_max_len", 192),
                                truncate_left=isinstance(state, list))
        total += len(full)
        trunc = trunc or list(fed) != full
    return total, trunc


def test_p2f_2_budget_formula_matches_build_sequence_randomized():
    rng = random.Random(7)
    for _ in range(300):
        agent = SimpleNamespace(tok=_CountingTok(), cfg={"max_len": rng.choice([16, 40, 80, 200, 1024]),
                                                         "head_max_len": rng.choice([12, 20, 32, 64, 192])})
        state = " ".join(["s"] * rng.randint(1, 120))
        qs = {}
        for qi in range(rng.randint(1, 3)):
            crit = {f"o{j}": " ".join(["w"] * rng.randint(0, 70)) for j in range(rng.randint(2, 6))}
            qs[f"q{qi}"] = _q(crit, ins=" ".join(["i"] * rng.randint(1, 40)))
        assert laya_srv.compute_untruncated_token_count(agent, state, qs) == _reference_count(agent, state, qs)


# ---------------------------------------------------------------------------
# Fix 3 (P1): outlines schema compile happens in /warmup, before the timed loop
# ---------------------------------------------------------------------------
def _schema_cases() -> list[Case]:
    opts = {"svc_a": "service a", "svc_b": "service b", "unsupported": "none"}
    cases = []
    for i in range(3):
        cases.append(Case(case_id=f"a{i}", text="t", truth=[dict(TRUTH4)]))
        cases.append(Case(case_id=f"b{i}", text="t", fields=["service_type"], service_options=opts,
                          truth=[{"service_type": "svc_a"}]))
        cases.append(Case(case_id=f"c{i}", text="t", fields=["service_type"], bundle_size=2,
                          truth=[{"service_type": "ocr"}, {"service_type": "count"}]))
    return cases


def test_p2f_3_warmup_each_distinct_schema_once_before_first_timed_request(tmp_path: Path):
    srv = _MockServer()
    cases = _schema_cases()
    cases_file = _write(tmp_path / "cases.jsonl", cases)
    client = _client(srv.port)
    expected = {json.dumps(client.build_schema(c)) for c in cases}
    assert len(expected) == 3
    try:
        rep = _run(cases_file, tmp_path / "out", client)
        first_run_events = list(srv.events)
        # Resume in a new invocation warms up again.
        _run(cases_file, tmp_path / "out", client)
    finally:
        srv.close()

    kinds = [e[0] for e in first_run_events]
    assert kinds[0] == "warmup" and kinds.count("warmup") == 1
    sent = [json.dumps(s) for s in first_run_events[0][1]]
    assert len(sent) == len(set(sent)) and set(sent) == expected
    assert kinds.count("chat") == len(cases)

    warm = json.loads((tmp_path / "out" / "integrity.json").read_text())["schema_warmup"]["qj"]
    assert rep["schema_warmup"]["qj"]["http_status"] == 200
    assert [s["compile_s"] for s in warm["schemas"]] == [0.25, 0.25, 0.25]
    assert [e[0] for e in srv.events].count("warmup") == 2


def test_p2f_3_server_without_warmup_endpoint_is_a_noop(tmp_path: Path):
    srv = _MockServer(warmup_supported=False)
    cases_file = _write(tmp_path / "cases.jsonl", _schema_cases())
    try:
        rep = _run(cases_file, tmp_path / "out", _client(srv.port))
    finally:
        srv.close()
    assert rep["stop_reason"] is None and len(_rows(tmp_path / "out")) == 9
    assert rep["schema_warmup"]["qj"]["http_status"] == 404
    assert rep["schema_warmup"]["qj"]["schemas"] == []


@pytest.mark.parametrize("backend_cls", [qwen_srv.CudaQwenJson, qwen_srv.MlxQwenJson])
def test_p2f_3_server_warmup_compiles_and_caches_processors(backend_cls):
    processor = MagicMock()
    factory = MagicMock(return_value=processor)
    client = _client(1)
    s1, s2 = (client.build_schema(c) for c in _schema_cases()[:2])

    with patch.object(qwen_srv, "build_outlines_vocabulary", return_value="vocab"), \
            patch.object(qwen_srv, "build_json_schema_processor", factory):
        gen = backend_cls(MagicMock(), MagicMock(), constrained=True)
        resp = qwen_srv.process_warmup(gen, {"schemas": [s1, s2]})
        assert factory.call_count == 2
        assert [s["cached"] for s in resp["schemas"]] == [False, False]
        assert all(s["compile_s"] >= 0 for s in resp["schemas"])
        assert resp["schemas"][0]["schema_sha256"] == hashlib.sha256(json.dumps(s1).encode()).hexdigest()
        # A timed request with a warmed schema reuses the cached processor.
        gen.constraint.processor(json.loads(json.dumps(s1)))
        assert factory.call_count == 2

    free = qwen_srv.process_warmup(backend_cls(MagicMock(), MagicMock(), constrained=False), {"schemas": [s1]})
    assert free["schemas"][0]["compile_s"] == 0.0 and free["schemas"][0]["compiled"] is False
    with pytest.raises(ValueError):
        qwen_srv.process_warmup(gen, {"schemas": "nope"})


# ---------------------------------------------------------------------------
# Fix 4 (P1): RQ names; an explicitly requested missing RQ directory is fatal
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fix 5 (P1): git-less provenance via PROVENANCE.json
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def _tree(tmp_path: Path) -> Path:
    root = tmp_path / "tree"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("alpha\n")
    (root / "sub" / "b.py").write_text("print('b')\n")
    _git(root, "init", "-q")
    _git(root, "add", "a.txt", "sub/b.py")
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-q", "-m", "init")
    return root


def _provenance_cli(root: Path):
    return subprocess.run([sys.executable, str(REPO / "scripts" / "eb_provenance.py"), "--repo", str(root)],
                          capture_output=True, text=True)


def test_p2f_5b_provenance_script_refuses_dirty_and_hashes_ls_files(tmp_path: Path):
    root = _tree(tmp_path)
    (root / "a.txt").write_text("changed\n")
    dirty = _provenance_cli(root)
    assert dirty.returncode != 0 and not (root / "PROVENANCE.json").exists()
    _git(root, "checkout", "--", "a.txt")
    (root / "stray.txt").write_text("x")
    untracked = _provenance_cli(root)
    assert untracked.returncode != 0 and not (root / "PROVENANCE.json").exists()
    (root / "stray.txt").unlink()

    ok = _provenance_cli(root)
    assert ok.returncode == 0, ok.stderr
    data = json.loads((root / "PROVENANCE.json").read_text())
    assert data["head_sha"] == _git(root, "rev-parse", "HEAD")
    assert data["files"] == {
        "a.txt": hashlib.sha256(b"alpha\n").hexdigest(),
        "sub/b.py": hashlib.sha256(b"print('b')\n").hexdigest(),
    }
    listing = "".join(f"{data['files'][p]}  {p}\n" for p in sorted(data["files"]))
    assert data["tree_sha256"] == hashlib.sha256(listing.encode()).hexdigest()


class _OkInterp(Interpreter):
    def decide(self, case: Case) -> Decision:
        return Decision(labels=[dict(case.truth[0])], valid=True, latency_s=0.01)


def _tree_cases(root: Path) -> Path:
    # P2h: in git-less mode the --cases file must be listed in PROVENANCE.json (corpus tree, tracked or not)
    path = root / "data" / "edgebench" / "v1" / "RQ1a" / "base" / "test.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return _write(path, [Case(case_id="c1", text="t", truth=[dict(TRUTH4)])])


def _gitless_run(tmp_path: Path, root: Path, monkeypatch, out: str):
    monkeypatch.setattr("src.edgebench.ledger._git_available", lambda: False)
    monkeypatch.setattr("src.edgebench.provenance.REPO_ROOT", root)
    cases_file = _tree_cases(root)
    with patch("src.edgebench.runner.build_interpreter", return_value=_OkInterp("m", "self-hosted")):
        return run_benchmark(cases_path=cases_file, rq="RQ1a", condition="base", model_names=["m"],
                             out_dir=tmp_path / out, workers=1)


def test_p2f_5c_gitless_runner_verifies_provenance_tree(tmp_path: Path, monkeypatch):
    root = _tree(tmp_path)
    _tree_cases(root)
    assert _provenance_cli(root).returncode == 0
    data = json.loads((root / "PROVENANCE.json").read_text())
    monkeypatch.setenv("EB_GIT_SHA", data["head_sha"])

    rep = _gitless_run(tmp_path, root, monkeypatch, "ok")
    row = _rows(tmp_path / "ok")[0]
    assert row["provenance_tree_sha256"] == data["tree_sha256"] == rep["provenance_tree_sha256"]
    assert row["git_sha"] == data["head_sha"] and row["git_source"] == "provenance"

    # EB_GIT_SHA that disagrees with PROVENANCE.json is refused.
    monkeypatch.setenv("EB_GIT_SHA", "f" * 40)
    with pytest.raises(RuntimeError, match="EB_GIT_SHA"):
        _gitless_run(tmp_path, root, monkeypatch, "sha_mismatch")
    monkeypatch.delenv("EB_GIT_SHA")

    (root / "sub" / "b.py").write_text("print('tampered')\n")
    with pytest.raises(RuntimeError, match="sub/b.py"):
        _gitless_run(tmp_path, root, monkeypatch, "tampered")
    (root / "sub" / "b.py").unlink()
    with pytest.raises(RuntimeError, match="sub/b.py"):
        _gitless_run(tmp_path, root, monkeypatch, "missing")
    for out in ("sha_mismatch", "tampered", "missing"):
        assert not (tmp_path / out / "ledger.jsonl").exists()


def test_p2f_5c_env_attestation_alone_is_not_trusted(tmp_path: Path, monkeypatch):
    root = _tree(tmp_path)  # no PROVENANCE.json
    monkeypatch.setenv("EB_GIT_SHA", _git(root, "rev-parse", "HEAD"))
    monkeypatch.setenv("EB_TREE_CLEAN", "1")
    with pytest.raises(RuntimeError, match="PROVENANCE.json"):
        _gitless_run(tmp_path, root, monkeypatch, "env_only")
    assert not (tmp_path / "env_only" / "ledger.jsonl").exists()


# ---------------------------------------------------------------------------
# Fix 6 (P2): CUDA / Triton / Inductor caches on the project volume
# ---------------------------------------------------------------------------
