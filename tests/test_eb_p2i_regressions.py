"""Regression tests for the three P1s left open by the final P2h review (P2i)."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import sys
import threading
import time
from unittest.mock import patch

import pytest

import scripts.eb_align_check as align
import scripts.eb_run as eb_run
from src.edgebench.contract import Case
from src.edgebench.interpreters import transport
from src.edgebench.interpreters.base import Decision
from src.edgebench.interpreters.decisions import DecisionsClient
from src.edgebench.interpreters.transport import close_thread_connections, wait_for_health

REPO = Path(__file__).resolve().parent.parent
MID = "dec-local@test"
TRUTH4 = {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}


# ---------------------------------------------------------------------------
# Fix A: a server that stays unhealthy after a client timeout stops the run (exit 3, resumable)
# ---------------------------------------------------------------------------
class _HangingServer:
    """Single-threaded mock decisions server. POST number `hang_at` sleeps past the client timeout; while
    `broken` is set, GET /health never reports healthy ("503": answers 503; "silent": stalls past the wait)."""

    def __init__(self, hang_at: int, hang_s: float, health_mode: str):
        self.broken = True
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
                if state.broken:
                    if health_mode == "silent":
                        time.sleep(1.2)  # longer than the (patched) post-timeout wait
                    self._send(503, {"status": "stuck"})
                    return
                self._send(200, {"status": "ok", "pid": os.getpid()})

            def do_POST(self):
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                i = state.n_post
                state.n_post += 1
                if state.broken and i == hang_at:
                    time.sleep(hang_s)
                answers = {qid: {"type": "choice", "choice": next(iter(q["criteria"]))}
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
        close_thread_connections()
        self.httpd.shutdown()
        self.httpd.server_close()


def _dec_client(url: str, timeout_s: float) -> DecisionsClient:
    return DecisionsClient(name="dec", model=MID, accepted_resolved_models=[MID], expected_provider="local",
                           base_url=url, deployment="self-hosted", timeout_s=timeout_s)


def _write_cases(path: Path, n: int) -> Path:
    cases = [Case(case_id=f"c{i}", text="t", truth=[dict(TRUTH4)]) for i in range(n)]
    path.write_text("".join(json.dumps(c.to_dict()) + "\n" for c in cases), encoding="utf-8")
    return path


def _rows(out: Path) -> list[dict]:
    return [json.loads(line) for line in (out / "ledger.jsonl").read_text().splitlines() if line.strip()]


def _eb_run(monkeypatch, cases_file: Path, out: Path, client) -> int:
    argv = ["eb_run.py", "--cases", str(cases_file), "--rq", "RQ1a", "--condition", "base", "--models", client.name,
            "--out", str(out), "--workers", "1", "--allow-dirty"]
    monkeypatch.setattr(sys, "argv", argv)
    with patch("src.edgebench.runner.build_interpreter", return_value=client):
        try:
            eb_run.main()
        except SystemExit as exc:
            return int(exc.code or 0)
    return 0


@pytest.mark.parametrize("health_mode", ["503", "silent"])
def test_p2i_a_unhealthy_after_timeout_stops_exit_3_and_resume_completes(tmp_path: Path, monkeypatch,
                                                                         health_mode: str):
    n, k = 6, 2
    monkeypatch.setattr(transport, "POST_TIMEOUT_HEALTH_WAIT_S", 1.0)
    srv = _HangingServer(hang_at=k, hang_s=1.0, health_mode=health_mode)
    cases_file = _write_cases(tmp_path / "cases.jsonl", n)
    out = tmp_path / "out"
    try:
        rc = _eb_run(monkeypatch, cases_file, out, _dec_client(srv.url, timeout_s=0.4))
        rows = _rows(out)
        assert rc == eb_run.EXIT_SELF_HOSTED_SERVER_DOWN == 3
        assert len(rows) == k + 1  # the timed-out row is kept
        assert rows[-1]["error_type"] == "TimeoutError" and rows[-1]["post_timeout_wait_s"] is not None
        assert srv.n_post == k + 1  # nothing sent after the server stayed unhealthy
        assert json.loads((out / "integrity.json").read_text())["stop_reason"] == "self_hosted_server_down"

        srv.broken = False  # server recovered (PBS restart-once)
        rc2 = _eb_run(monkeypatch, cases_file, out, _dec_client(srv.url, timeout_s=5.0))
    finally:
        srv.close()
    rows = _rows(out)
    assert rc2 == 0
    assert len(rows) == n and len({r["case_id"] for r in rows}) == n
    integrity = json.loads((out / "integrity.json").read_text())
    assert integrity["stop_reason"] is None and integrity["duplicates"] == 0
    assert srv.n_post == n  # resume sent exactly the rest


def test_p2i_a_wait_for_health_reports_healthy(tmp_path: Path):
    srv = _HangingServer(hang_at=-1, hang_s=0.0, health_mode="503")
    try:
        srv.broken = False
        waited, healthy = wait_for_health(srv.url, max_wait_s=2.0, poll_s=0.1)
        assert healthy is True and waited < 1.0
        srv.broken = True
        waited, healthy = wait_for_health(srv.url, max_wait_s=0.5, poll_s=0.1)
        assert healthy is False and waited >= 0.5
    finally:
        srv.close()
    waited, healthy = wait_for_health(srv.url, max_wait_s=2.0, poll_s=0.1)  # refused: server gone
    assert healthy is False


# ---------------------------------------------------------------------------
# Fix B: per-model port ranges never overlap across jobs
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Fix C: the alignment gate refuses a reference built from different requests
# ---------------------------------------------------------------------------
class _OfflineDecisions(DecisionsClient):
    """Real request builder; decide() answers the truth without a server."""

    def decide(self, case: Case) -> Decision:
        self.build_request(case)
        return Decision(labels=[dict(t) for t in case.truth], valid=True, latency_s=0.01,
                        resolved_model=self.model)


def _align_run(tmp_path: Path, name: str, model_id: str, base_url: str, cases: Path) -> Path:
    client = _OfflineDecisions(name="dec", model=model_id, accepted_resolved_models=[model_id],
                               base_url=base_url, deployment="self-hosted")
    out = tmp_path / f"{name}.json"
    with patch.object(align, "build_interpreter", return_value=client):
        assert align.main(["run", "--model", "dec", "--out", str(out), "--cases", str(cases)]) == 0
    return out


def _cases20(tmp_path: Path) -> Path:
    return _write_cases(tmp_path / "fx.jsonl", 20)


def test_p2i_c_run_records_request_hashes_excluding_platform_fields(tmp_path: Path):
    cases = _cases20(tmp_path)
    a = json.loads(_align_run(tmp_path, "mlx", "m@mlx", "http://127.0.0.1:8601", cases).read_text())
    b = json.loads(_align_run(tmp_path, "cuda", "m@cuda", "http://127.0.0.1:8700", cases).read_text())
    hashes_a = [r["request_sha256"] for r in a["cases"]]
    assert all(isinstance(h, str) and len(h) == 64 for h in hashes_a)
    assert hashes_a == [r["request_sha256"] for r in b["cases"]]  # model id / base URL excluded
    import hashlib
    assert a["contract_sha256"] == hashlib.sha256("".join(hashes_a).encode("utf-8")).hexdigest()
    assert a["contract_sha256"] == b["contract_sha256"]


def test_p2i_c_gate_fails_when_reference_requests_differ(tmp_path: Path, capsys):
    cases = _cases20(tmp_path)
    ref = _align_run(tmp_path, "mlx", "m@mlx", "http://127.0.0.1:8601", cases)
    from src.edgebench.interpreters import decisions as dec_mod

    real = dec_mod.get_field_instruction

    def changed(field, **kw):
        text = real(field, **kw)
        return text + " (revised)" if field == "urgency" else text

    with patch.object(dec_mod, "get_field_instruction", side_effect=changed):
        cuda = _align_run(tmp_path, "cuda", "m@cuda", "http://127.0.0.1:8700", cases)
    out = tmp_path / "cmp.json"
    capsys.readouterr()
    rc = align.main(["compare", str(ref), str(cuda), "--out", str(out), "--gate"])
    assert rc != 0
    assert "reference stale: request hashes differ" in capsys.readouterr().err
    report = json.loads(out.read_text())
    assert report["gate"]["passed"] is False
    assert report["gate"]["reasons"] == ["reference stale: request hashes differ"]
    assert report["a"]["contract_sha256"] != report["b"]["contract_sha256"]
    assert report["a"]["contract_sha256"] and report["b"]["contract_sha256"]
    assert report["request_hash_mismatches"] == 20
    assert report["field_agreement"] == 1.0  # same responses: only the requests differ


def test_p2i_c_gate_fails_when_reference_has_no_request_hashes(tmp_path: Path, capsys):
    # A reference written before request hashes existed cannot be shown to match: stale.
    cases = _cases20(tmp_path)
    ref = _align_run(tmp_path, "mlx", "m@mlx", "http://127.0.0.1:8601", cases)
    legacy = json.loads(ref.read_text())
    legacy.pop("contract_sha256")
    for r in legacy["cases"]:
        r.pop("request_sha256")
    ref.write_text(json.dumps(legacy))
    cuda = _align_run(tmp_path, "cuda", "m@cuda", "http://127.0.0.1:8700", cases)
    rc = align.main(["compare", str(ref), str(cuda), "--out", str(tmp_path / "cmp.json"), "--gate"])
    assert rc != 0 and "reference stale: request hashes differ" in capsys.readouterr().err


def test_p2i_c_identical_requests_gate_evaluates_agreement(tmp_path: Path):
    cases = _cases20(tmp_path)
    ref = _align_run(tmp_path, "mlx", "m@mlx", "http://127.0.0.1:8601", cases)
    cuda = _align_run(tmp_path, "cuda", "m@cuda", "http://127.0.0.1:8700", cases)
    out = tmp_path / "cmp.json"
    assert align.main(["compare", str(ref), str(cuda), "--out", str(out), "--gate"]) == 0
    report = json.loads(out.read_text())
    assert report["gate"]["passed"] is True and report["request_hash_mismatches"] == 0
    assert report["a"]["contract_sha256"] == report["b"]["contract_sha256"]

    # same requests, 5/20 cases disagree on one field: 75/80 < 0.95, the agreement gate still applies
    data = json.loads(cuda.read_text())
    for r in data["cases"][:5]:
        r["labels"] = [dict(r["labels"][0], urgency="urgent")]
    cuda.write_text(json.dumps(data))
    assert align.main(["compare", str(ref), str(cuda), "--out", str(out), "--gate"]) != 0
    reasons = json.loads(out.read_text())["gate"]["reasons"]
    assert reasons and all("stale" not in r for r in reasons) and "field_agreement" in reasons[0]
