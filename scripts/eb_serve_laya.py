#!/usr/bin/env python3
"""Laya localhost HTTP server exposing POST /api/alpha/decisions.

Exposes the same request/response JSON shape as OpenRouter's Jev endpoint.
Model: convaiinnovations/laya-typed-decisions at revision bc76315b568af04bc19f133c8bca9a2b3a2d9905.
Model ID in responses: laya-typed-decisions@bc76315b (MPS / CPU) or laya-typed-decisions@bc76315b+cuda.
Device: MPS (Apple Silicon GPU), CPU, or CUDA; every device loads the checkpoint snapshot pinned to MODEL_REVISION.
Handles 1024-token context natively via Laya library without manual truncation.
The response carries only the answers: usage.input_tokens and truncated are null, so no token counting
sits in the timed path. scripts/eb_laya_tokens.py recomputes both offline with
compute_untruncated_token_count (derived from Laya's own sequence builder, laya.common.build_sequence,
and its max_len/head_max_len budget).
"""
from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

# One accelerator: accept every connection (thread per connection) but run one inference at a time.
# A single-threaded HTTPServer served only the first keep-alive client and starved concurrent ones (RQ5 pilot).
INFERENCE_LOCK = threading.Lock()
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

# Ensure repository root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

MODEL_ID_OR_PATH = "convaiinnovations/laya-typed-decisions"
MODEL_REVISION = "bc76315b568af04bc19f133c8bca9a2b3a2d9905"
RESOLVED_MODEL_ID = "laya-typed-decisions@bc76315b"
DEFAULT_PORT = 8602
DEVICES = ("mps", "cpu", "cuda")
# Files laya.Agent itself downloads for a root checkpoint.
LAYA_ALLOW_PATTERNS = ["rl_agent_config.json", "model.safetensors", "tokenizer/*", "encoder/*"]


def resolved_model_id(device: str) -> str:
    """Model id reported by the server for a device."""
    return RESOLVED_MODEL_ID + "+cuda" if device == "cuda" else RESOLVED_MODEL_ID


def load_agent(device: str) -> Any:
    """Load Laya through laya.load from a snapshot pinned to MODEL_REVISION (any device).

    On CUDA a silent CPU fallback is refused.
    """
    import laya
    from huggingface_hub import snapshot_download

    path = snapshot_download(MODEL_ID_OR_PATH, revision=MODEL_REVISION, allow_patterns=LAYA_ALLOW_PATTERNS)
    agent = laya.load(path, device=device)
    if device == "cuda" and str(agent.device).split(":")[0] != "cuda":
        raise RuntimeError(f"Laya did not load on CUDA (got device {agent.device})")
    return agent


def compute_untruncated_token_count(agent: Any, state: Any, questions: dict[str, dict[str, Any]]) -> tuple[int, bool]:
    """Untruncated input tokens (summed over question rows) and whether Laya truncates any row.

    The state is tokenized once (it is question-independent). Per question, the head and each
    option are tokenized untruncated, and the lengths laya.common.build_sequence would feed are
    derived with its budget formula (48-token option cap, head_max_len option/head budget, max_len
    state room and final cut). Every cut in build_sequence keeps a slice of its part, so a row is
    truncated exactly when its fed length is shorter than its untruncated length.
    """
    from laya.agent import Agent
    from laya.common import render_options, serialize_state

    tok = agent.tok
    mask_tok = tok.mask_token
    max_len = agent.cfg.get("max_len", 512)
    head_max_len = agent.cfg.get("head_max_len", 192)
    n_state = len(tok(serialize_state(state).replace(mask_tok, " "), add_special_tokens=False)["input_ids"])

    total_tokens = 0
    is_truncated = False
    for qid, q_data in questions.items():
        Agent._check_question(qid, q_data)
        q = Agent._to_internal(q_data)
        ins = str(q["ins"]).replace(mask_tok, " ")
        n_head = len(tok("%s question: %s" % (q["t"], ins), add_special_tokens=False)["input_ids"])
        opt_full = [
            1 + len(tok(" " + opt.replace(mask_tok, " "), add_special_tokens=False)["input_ids"])
            for opt in render_options(q)
        ]
        # build_sequence budget, on lengths
        opt_fed = [min(n, 1 + 48) for n in opt_full]
        opt_budget = head_max_len - sum(opt_fed)
        if opt_budget < 16:
            per = max(4, (head_max_len - 16) // max(1, len(opt_fed)))
            opt_fed = [min(n, per) for n in opt_fed]
            opt_budget = head_max_len - sum(opt_fed)
        head_fed = min(n_head, max(8, opt_budget))
        prefix = 1 + head_fed + 1 + sum(opt_fed) + 1
        room = max(0, max_len - prefix - 1)
        fed = min(prefix + min(n_state, room) + 1, max_len)

        full = 1 + n_head + 1 + sum(opt_full) + 1 + n_state + 1
        total_tokens += full
        if fed != full:
            is_truncated = True

    return total_tokens, is_truncated


def process_laya_request(
    agent: Any,
    body: dict[str, Any],
    model_id: str = RESOLVED_MODEL_ID,
) -> dict[str, Any]:
    """Process decisions request using Laya agent. Answers only: no tokenizer call on this path."""
    state = body.get("state")
    if not state or not isinstance(state, str):
        raise ValueError("Field 'state' must be a nonempty string")
    questions = body.get("questions")
    if not isinstance(questions, dict) or not questions:
        raise ValueError("Field 'questions' must be a nonempty object")

    # Call agent.system_one natively with state and questions
    raw_result = agent.system_one(state=state, questions=questions)

    # Format answers
    answers: dict[str, dict[str, Any]] = {}
    for qid, ans in raw_result.get("answers", {}).items():
        probs = ans.get("probabilities", {})
        choice = ans.get("choice", "")
        confidence = ans.get("confidence")
        if confidence is None and probs:
            p_vals = sorted(probs.values(), reverse=True)
            confidence = float(p_vals[0] - (p_vals[1] if len(p_vals) > 1 else 0.0))
        answers[qid] = {
            "type": ans.get("type", "choice"),
            "choice": choice,
            "probabilities": {k: float(v) for k, v in probs.items()},
            "confidence": float(confidence if confidence is not None else 0.0),
        }

    return {
        "model": model_id,
        "provider": "local",
        "answers": answers,
        # Token counts are recomputed offline (scripts/eb_laya_tokens.py), outside the timed path.
        "usage": {
            "input_tokens": None,
            "output_tokens": 0,
            "cost": 0.0,
            "truncated": None,
        },
        "truncated": None,
    }


class LayaRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    agent: Any = None
    device_name: str = "mps"
    model_id: str = RESOLVED_MODEL_ID

    def _send_json(self, status: int, data: dict[str, Any], compute_ms: float = 0.0) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("x-compute-ms", f"{compute_ms:.2f}")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send_json(
                200,
                {
                    "status": "ok",
                    "pid": os.getpid(),  # eb_selfhosted.pbs checks it equals SERVER_PID
                    "model": self.model_id,
                    "backend": self.device_name,
                },
            )
        else:
            self._send_json(404, {"error": f"Endpoint not found: {self.path}"})

    def do_POST(self) -> None:
        with INFERENCE_LOCK:
            self._do_post()

    def _do_post(self) -> None:
        if self.path != "/api/alpha/decisions":
            self._send_json(404, {"error": f"Endpoint not found: {self.path}"})
            return

        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length)

        try:
            req_data = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            self._send_json(400, {"error": f"Invalid JSON payload: {exc}"})
            return

        t0 = time.perf_counter()
        try:
            resp_data = process_laya_request(self.agent, req_data, model_id=self.model_id)
            compute_ms = (time.perf_counter() - t0) * 1000.0
            self._send_json(200, resp_data, compute_ms=compute_ms)
        except ValueError as val_err:
            compute_ms = (time.perf_counter() - t0) * 1000.0
            self._send_json(400, {"error": str(val_err), "model": self.model_id}, compute_ms=compute_ms)
        except Exception as exc:
            compute_ms = (time.perf_counter() - t0) * 1000.0
            self._send_json(500, {"error": f"Internal error: {exc}", "model": self.model_id}, compute_ms=compute_ms)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def warmup(agent: Any, count: int = 5) -> None:
    """Run 5 dummy inference calls to warm up."""
    print(f"Warming up Laya ({agent.device}) with {count} dummy calls...")
    dummy_questions = {
        "q1": {
            "type": "choice",
            "instructions": "Is the system healthy?",
            "criteria": {"yes": "The system is healthy", "no": "The system is unhealthy"},
        }
    }
    dummy_state = "The system health check passed at 08:00 UTC."
    for _ in range(count):
        agent.system_one(state=dummy_state, questions=dummy_questions)
    print("Warmup complete.")


def run_server(port: int = DEFAULT_PORT, device: str = "mps") -> None:
    print(f"Loading Laya model ({MODEL_ID_OR_PATH} @ {MODEL_REVISION[:8]}, device={device})...")
    try:
        agent = load_agent(device)
    except Exception as exc:
        if device == "mps":
            print(f"MPS load failed ({exc}), falling back to CPU...")
            agent = load_agent("cpu")
            device = "cpu"
        else:
            raise

    warmup(agent, count=5)

    LayaRequestHandler.agent = agent
    LayaRequestHandler.device_name = str(agent.device)
    LayaRequestHandler.model_id = resolved_model_id(device)

    server = ThreadingHTTPServer(("127.0.0.1", port), LayaRequestHandler)
    print(f"Laya server listening on http://127.0.0.1:{port} (device={agent.device}, model={resolved_model_id(device)}, single worker thread)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Laya server.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Laya localhost HTTP server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 8602)")
    parser.add_argument("--device", choices=list(DEVICES), default="mps", help="Device (default: mps)")
    args = parser.parse_args()
    run_server(port=args.port, device=args.device)


if __name__ == "__main__":
    main()
