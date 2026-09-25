#!/usr/bin/env python3
"""Qwen-JSON localhost HTTP server exposing POST /api/v1/chat/completions.

Generative reference using Qwen/Qwen3.5-4B rev 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a in BF16.
Backends (decoding constrained to the request's response_format JSON schema by default):
  mlx  (default): mlx-lm.                                     Model ID qwen3.5-4b-json@851bf6e8+constrained
        (--decoding free: unconstrained,                      Model ID qwen3.5-4b-json@851bf6e8+free)
  cuda: Transformers AutoModelForCausalLM.                    Model ID qwen3.5-4b-json@851bf6e8+constrained-cuda
        (--decoding free: unconstrained,                      Model ID qwen3.5-4b-json@851bf6e8+free-cuda)
Both backends render the same prompt, tokenize it the same way, build the same outlines-core
JSON-schema processor (SchemaConstraint; only the mask kernel's tensor library differs), decode
greedily, stop at the same STOP_TOKENS and return the same response shape.
Thinking is disabled: the chat template is rendered exactly as
apply_chat_template(..., add_generation_prompt=True, enable_thinking=False) produces it, including
the empty <think>...</think> block that is the template's thinking-off signal. No token is banned;
if the generated text still contains <think> or </think>, the response carries reasoning_leak: true
and the client scores it invalid.
Greedy decoding (temperature 0).
POST /warmup {"schemas": [...]} compiles and caches the constraint processors ahead of the timed requests.
"""
from __future__ import annotations

import argparse
import hashlib
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

MODEL_SOURCE = "Qwen/Qwen3.5-4B"
MODEL_REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"
RESOLVED_MODEL_IDS = {
    ("mlx", "constrained"): "qwen3.5-4b-json@851bf6e8+constrained",
    ("mlx", "free"): "qwen3.5-4b-json@851bf6e8+free",
    ("cuda", "constrained"): "qwen3.5-4b-json@851bf6e8+constrained-cuda",
    ("cuda", "free"): "qwen3.5-4b-json@851bf6e8+free-cuda",
}
RESOLVED_MODEL_ID = RESOLVED_MODEL_IDS[("mlx", "constrained")]
DEFAULT_PORT = 8603
# Generation stops at the first of these tokens, on both backends (Qwen3.5: 248046 and 248044).
STOP_TOKENS = ("<|im_end|>", "<|endoftext|>")


def stop_token_ids(tokenizer: Any) -> list[int]:
    """Ids of STOP_TOKENS in a Transformers tokenizer; every stop token must be in the vocabulary."""
    ids = []
    for token in STOP_TOKENS:
        token_id = tokenizer.convert_tokens_to_ids(token)
        if token_id is None or token_id == tokenizer.unk_token_id:
            raise ValueError(f"Stop token {token!r} is not in the tokenizer vocabulary")
        ids.append(int(token_id))
    return sorted(ids)


def build_outlines_vocabulary(hf_tokenizer: Any) -> Any:
    """outlines-core Vocabulary for a Transformers tokenizer, built as outlines' Transformers integration builds it."""
    from outlines.backends.outlines_core import OutlinesCoreBackend
    from outlines.models.transformers import TransformerTokenizer

    tok = TransformerTokenizer(hf_tokenizer)
    return OutlinesCoreBackend.create_outlines_core_vocabulary(
        tok.get_vocab(), tok.eos_token_id, tok.eos_token, tok.convert_token_to_string
    )


def build_json_schema_processor(vocabulary: Any, schema_json: str, tensor_library_name: str) -> Any:
    """outlines-core logits processor for a JSON schema: schema -> regex -> Index over the vocabulary.

    Same construction as outlines' get_json_schema_logits_processor("outlines_core", ...) with the
    default whitespace pattern. Each step it sets the logits of disallowed token ids to -inf and,
    from the second step on, advances its guide with the last sampled token.
    """
    from outlines.backends.outlines_core import OutlinesCoreLogitsProcessor
    from outlines_core import Index
    from outlines_core.json_schema import build_regex_from_schema

    index = Index(build_regex_from_schema(schema_json), vocabulary)
    return OutlinesCoreLogitsProcessor(index, tensor_library_name)


class SchemaConstraint:
    """JSON-schema logits processors over one tokenizer, cached per schema and reset per request.

    Both backends build their processors here, so the vocabulary, the schema regex and the index are
    identical; only the tensor library of the mask kernel differs ("torch" on CUDA, "mlx" on MLX).
    """

    def __init__(self, hf_tokenizer: Any, tensor_library_name: str) -> None:
        self.tensor_library_name = tensor_library_name
        self.vocabulary = build_outlines_vocabulary(hf_tokenizer)
        self._processors: dict[str, Any] = {}

    def compile_schema(self, schema: dict[str, Any]) -> tuple[Any, float, bool]:
        """Build (or fetch) the cached processor for a schema: (processor, compile_s, was_cached)."""
        # Schema kept in request order: property order fixes the key order the constraint allows.
        key = json.dumps(schema)
        processor = self._processors.get(key)
        if processor is not None:
            return processor, 0.0, True
        t0 = time.perf_counter()
        processor = build_json_schema_processor(self.vocabulary, key, self.tensor_library_name)
        compile_s = time.perf_counter() - t0
        self._processors[key] = processor
        return processor, compile_s, False

    def processor(self, schema: dict[str, Any]) -> Any:
        """The schema's processor, reset for a new request."""
        processor, _, _ = self.compile_schema(schema)
        processor.reset()
        return processor


def render_prompt_no_think(tokenizer: Any, messages: list[dict[str, str]]) -> str:
    """Render the chat prompt with thinking disabled, exactly as the template produces it.

    The empty <think> block emitted by the Qwen3.5 template with enable_thinking=False is kept:
    it is the template's thinking-off signal.
    """
    return tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
    )


def has_reasoning_leak(text: str) -> bool:
    """True if generated text contains a think tag despite thinking being disabled."""
    return "<think>" in text or "</think>" in text


def response_schema(body: dict[str, Any]) -> dict[str, Any] | None:
    """JSON schema from an OpenAI-style response_format of type json_schema, else None."""
    response_format = body.get("response_format")
    if not isinstance(response_format, dict) or response_format.get("type") != "json_schema":
        return None
    schema = (response_format.get("json_schema") or {}).get("schema")
    return schema if isinstance(schema, dict) else None


def load_hf_model(source: str = MODEL_SOURCE, revision: str = MODEL_REVISION, device: str = "cuda") -> tuple[Any, Any]:
    """Load the pinned causal LM (BF16) and tokenizer with Transformers.

    Qwen3.5 checkpoints carry a composite config; like SemIf's loader, the text config is passed
    to AutoModelForCausalLM so the same language-model weights load, and incomplete loads fail.
    """
    import torch
    import transformers

    common = {"revision": revision, "trust_remote_code": False}
    config = transformers.AutoConfig.from_pretrained(source, **common)
    if config.model_type in {"qwen3_5", "qwen3_5_text"}:
        config = config.get_text_config()
    tokenizer = transformers.AutoTokenizer.from_pretrained(source, **common)
    model, loading = transformers.AutoModelForCausalLM.from_pretrained(
        source,
        config=config,
        dtype=torch.bfloat16,
        device_map={"": device},
        output_loading_info=True,
        **common,
    )
    if any(loading.get(key) for key in ("missing_keys", "mismatched_keys", "error_msgs")):
        raise RuntimeError(f"Checkpoint did not load completely: {loading}")
    model.eval()
    return model, tokenizer


class CudaQwenJson:
    """Greedy Transformers generation on the exact rendered prompt, optionally JSON-schema constrained.

    Constraint: the SchemaConstraint processor (torch tensors) for the request schema is passed to
    model.generate. The prompt is tokenized here rather than through outlines' model wrapper, which
    would re-apply the chat template to a string prompt.
    """

    def __init__(self, model: Any, tokenizer: Any, constrained: bool = True) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.constrained = constrained
        self.constraint = SchemaConstraint(tokenizer, "torch") if constrained else None

    def compile_schema(self, schema: dict[str, Any]) -> tuple[Any, float, bool]:
        return self.constraint.compile_schema(schema)

    def generate(self, prompt: str, max_tokens: int, schema: dict[str, Any] | None) -> str:
        import torch
        from transformers import LogitsProcessorList

        enc = self.tokenizer(prompt, return_tensors="pt", add_special_tokens=False)
        input_ids = enc["input_ids"].to(self.model.device)
        attention_mask = enc["attention_mask"].to(self.model.device)
        stop_ids = stop_token_ids(self.tokenizer)
        kwargs: dict[str, Any] = {
            "max_new_tokens": max_tokens,
            "do_sample": False,
            "eos_token_id": stop_ids,
            "pad_token_id": self.tokenizer.pad_token_id if self.tokenizer.pad_token_id is not None else stop_ids[0],
        }
        if self.constrained and schema is not None:
            kwargs["logits_processor"] = LogitsProcessorList([self.constraint.processor(schema)])
        with torch.inference_mode():
            out = self.model.generate(input_ids=input_ids, attention_mask=attention_mask, **kwargs)
        new_ids = out[0, input_ids.shape[1]:].tolist()
        stop_set = set(stop_ids)
        if self.tokenizer.pad_token_id is not None:
            stop_set.add(self.tokenizer.pad_token_id)
        while new_ids and new_ids[-1] in stop_set:
            new_ids.pop()
        # Keep special tokens so a <think> leak stays visible to has_reasoning_leak.
        return self.tokenizer.decode(new_ids, skip_special_tokens=False)


class MlxQwenJson:
    """Greedy mlx-lm generation on the exact rendered prompt, optionally JSON-schema constrained.

    Same semantics as CudaQwenJson: the prompt is tokenized without added special tokens, the
    SchemaConstraint processor (mlx arrays) for the request schema is passed to mlx-lm's
    generate_step as a logits processor, the argmax token is taken, generation stops at the first
    STOP_TOKENS id, and the new tokens are decoded keeping special tokens.
    """

    def __init__(self, model: Any, tokenizer: Any, constrained: bool = True) -> None:
        self.model = model
        # mlx-lm's TokenizerWrapper wraps the Transformers tokenizer the CUDA backend uses directly.
        self.hf_tokenizer = getattr(tokenizer, "_tokenizer", tokenizer)
        self.constrained = constrained
        self.constraint = SchemaConstraint(self.hf_tokenizer, "mlx") if constrained else None

    def compile_schema(self, schema: dict[str, Any]) -> tuple[Any, float, bool]:
        return self.constraint.compile_schema(schema)

    def generate(self, prompt: str, max_tokens: int, schema: dict[str, Any] | None) -> str:
        import mlx.core as mx
        from mlx_lm.generate import generate_step
        from mlx_lm.sample_utils import make_sampler

        prompt_ids = mx.array(self.hf_tokenizer.encode(prompt, add_special_tokens=False))
        processors = [self.constraint.processor(schema)] if self.constrained and schema is not None else None
        stop_ids = set(stop_token_ids(self.hf_tokenizer))
        new_ids: list[int] = []
        for token, _ in generate_step(
            prompt_ids, self.model, max_tokens=max_tokens, sampler=make_sampler(temp=0.0), logits_processors=processors
        ):
            if token in stop_ids:
                break
            new_ids.append(token)
        # Keep special tokens so a <think> leak stays visible to has_reasoning_leak.
        return self.hf_tokenizer.decode(new_ids, skip_special_tokens=False)


def process_chat_completion(
    model: Any,
    tokenizer: Any,
    body: dict[str, Any],
    model_id: str = RESOLVED_MODEL_ID,
) -> dict[str, Any]:
    """Execute chat completion and produce OpenAI-compatible response.

    `model` is an MlxQwenJson or CudaQwenJson instance.
    """
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Field 'messages' must be a nonempty array")

    max_tokens = int(body.get("max_tokens", 256))

    prompt = render_prompt_no_think(tokenizer, messages)
    prompt_tokens = len(tokenizer.encode(prompt, add_special_tokens=False))

    generated_content = model.generate(prompt, max_tokens, response_schema(body))

    completion_tokens = len(tokenizer.encode(generated_content, add_special_tokens=False))

    resp: dict[str, Any] = {
        "id": f"chatcmpl-local-{int(time.time() * 1000)}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_id,
        "provider": "local",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": generated_content.strip(),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "completion_tokens_details": {
                "reasoning_tokens": 0,
            },
            "cost": 0.0,
        },
    }
    if has_reasoning_leak(generated_content):
        resp["reasoning_leak"] = True
    return resp


def process_warmup(model: Any, body: dict[str, Any]) -> dict[str, Any]:
    """Compile and cache the constraint processors for the given schemas (untimed; no generation).

    Only constrained decoding compiles anything; free decoding answers with compile_s 0.
    """
    schemas = body.get("schemas")
    if not isinstance(schemas, list) or not all(isinstance(x, dict) for x in schemas):
        raise ValueError("Field 'schemas' must be an array of JSON schema objects")
    constrained = model.constrained is True
    out = []
    for schema in schemas:
        entry: dict[str, Any] = {"schema_sha256": hashlib.sha256(json.dumps(schema).encode("utf-8")).hexdigest()}
        if constrained:
            _, compile_s, cached = model.compile_schema(schema)
            entry.update(compiled=True, compile_s=compile_s, cached=cached)
        else:
            entry.update(compiled=False, compile_s=0.0, cached=False)
        out.append(entry)
    return {"schemas": out}


class QwenJsonRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    model: Any = None
    tokenizer: Any = None
    backend: str = "mlx"
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
                    "backend": self.backend,
                },
            )
        else:
            self._send_json(404, {"error": f"Endpoint not found: {self.path}"})

    def do_POST(self) -> None:
        with INFERENCE_LOCK:
            self._do_post()

    def _do_post(self) -> None:
        if self.path not in ("/api/v1/chat/completions", "/warmup"):
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
            if self.path == "/warmup":
                resp_data = process_warmup(self.model, req_data)
            else:
                resp_data = process_chat_completion(self.model, self.tokenizer, req_data, model_id=self.model_id)
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


def warmup(model: Any, tokenizer: Any, count: int = 5, model_id: str = RESOLVED_MODEL_ID) -> None:
    """Run 5 dummy inference calls to warm up kernels and cache (and the schema constraint)."""
    print(f"Warming up Qwen-JSON ({model_id}) with {count} dummy calls...")
    dummy_body = {
        "messages": [
            {"role": "system", "content": "Return JSON only."},
            {"role": "user", "content": "Ping test."},
        ],
        "max_tokens": 16,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "warmup",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"ok": {"type": "string", "enum": ["yes", "no"]}},
                    "required": ["ok"],
                    "additionalProperties": False,
                },
            },
        },
    }
    for _ in range(count):
        process_chat_completion(model, tokenizer, dummy_body, model_id=model_id)
    print("Warmup complete.")


def load_backend(backend: str, decoding: str) -> tuple[Any, Any, str]:
    """Return (model, tokenizer, model_id) for a backend / decoding mode."""
    key = (backend, decoding)
    if key not in RESOLVED_MODEL_IDS:
        raise ValueError(f"Unsupported backend/decoding combination: {backend}/{decoding}")
    if backend == "mlx":
        import mlx_lm
        from huggingface_hub import snapshot_download

        path = snapshot_download(MODEL_SOURCE, revision=MODEL_REVISION)
        model, tokenizer = mlx_lm.load(path, tokenizer_config={"trust_remote_code": False})
        return MlxQwenJson(model, tokenizer, constrained=decoding == "constrained"), tokenizer, RESOLVED_MODEL_IDS[key]
    hf_model, tokenizer = load_hf_model(MODEL_SOURCE, MODEL_REVISION, device="cuda")
    return CudaQwenJson(hf_model, tokenizer, constrained=decoding == "constrained"), tokenizer, RESOLVED_MODEL_IDS[key]


def run_server(port: int = DEFAULT_PORT, backend: str = "mlx", decoding: str | None = None) -> None:
    decoding = decoding or "constrained"
    print(f"Loading Qwen-JSON model ({MODEL_SOURCE} @ {MODEL_REVISION[:8]}, backend={backend}, decoding={decoding})...")
    model, tokenizer, model_id = load_backend(backend, decoding)

    warmup(model, tokenizer, count=5, model_id=model_id)

    QwenJsonRequestHandler.model = model
    QwenJsonRequestHandler.tokenizer = tokenizer
    QwenJsonRequestHandler.backend = backend
    QwenJsonRequestHandler.model_id = model_id

    server = ThreadingHTTPServer(("127.0.0.1", port), QwenJsonRequestHandler)
    print(f"Qwen-JSON server listening on http://127.0.0.1:{port} (model={model_id}, single worker thread)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Qwen-JSON server.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Qwen-JSON localhost HTTP server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Port to bind (default: 8603)")
    parser.add_argument("--backend", choices=["mlx", "cuda"], default="mlx", help="Backend (default: mlx)")
    parser.add_argument(
        "--decoding",
        choices=["constrained", "free"],
        default=None,
        help="JSON-schema constrained (default) or free decoding",
    )
    args = parser.parse_args()
    run_server(port=args.port, backend=args.backend, decoding=args.decoding)


if __name__ == "__main__":
    main()
