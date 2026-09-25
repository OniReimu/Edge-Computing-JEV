"""P2g: JSON-schema constrained decoding on MLX with CUDA parity; Laya token counting out of the timed path.

The outlines-core processors run for real on a small byte-level BPE tokenizer (no weights, no network).
MLX tests skip where mlx is not importable; the real-tokenizer parity check skips when the pinned
Qwen3.5-4B tokenizer is not in the local Hugging Face cache.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import random
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import jsonschema
import numpy as np
import pytest
import torch

import scripts.eb_laya_tokens as laya_tokens
import scripts.eb_serve_laya as laya_srv
import scripts.eb_serve_qwen_json as qwen_srv
from src.edgebench.contract import Case
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.manifest import load_manifest


# ---------------------------------------------------------------------------
# Fixtures: toy tokenizer, benchmark schemas, deterministic fake language model
# ---------------------------------------------------------------------------
def _schemas() -> list[dict]:
    client = ChatJsonClient(name="q", model="m", provider_slug="local", base_url="http://127.0.0.1:1",
                            deployment="self-hosted")
    cases = [
        Case(case_id="a", text="t", truth=[{}]),
        Case(case_id="b", text="t", fields=["service_type"],
             service_options={"svc_a": "service a", "svc_b": "service b", "unsupported": "none"}, truth=[{}]),
        Case(case_id="c", text="t", fields=["service_type"], bundle_size=2, truth=[{}, {}]),
    ]
    return [client.build_schema(c) for c in cases]


@pytest.fixture(scope="module")
def toy_tok():
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers
    from transformers import PreTrainedTokenizerFast

    corpus = [json.dumps({"service_type": v, "locality": "site_only", "urgency": "urgent"}) for v in
              ("ocr", "count", "detection", "unsupported", "svc_a")] * 20
    tk = Tokenizer(models.BPE())
    tk.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tk.decoder = decoders.ByteLevel()
    tk.train_from_iterator(corpus, trainers.BpeTrainer(
        vocab_size=400, special_tokens=["<|endoftext|>", "<|im_end|>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet()))
    return PreTrainedTokenizerFast(tokenizer_object=tk, eos_token="<|im_end|>", pad_token="<|endoftext|>")


def _fake_logits(seq: list[int], width: int) -> np.ndarray:
    """Deterministic pseudo-random next-token logits as a function of the whole token sequence."""
    seed = int.from_bytes(hashlib.sha256(json.dumps(seq).encode()).digest()[:4], "little")
    return np.random.default_rng(seed).standard_normal(width).astype(np.float32)


class _FakeMlxLM:
    """mlx-lm model stand-in: returns _fake_logits for the sequence fed so far (cache = its own history)."""

    def __init__(self, width: int, force: dict[int, int] | None = None):
        self.width = width
        self.force = force or {}  # generated-step -> token id to put on top
        self.seq: list[int] = []
        self.n_prompt = 0

    def make_cache(self):
        self.seq = []
        return []

    def __call__(self, inputs, cache=None):
        import mlx.core as mx

        rows = []
        for t in np.array(inputs)[0].tolist():
            self.seq.append(int(t))
            logits = _fake_logits(self.seq, self.width)
            step = len(self.seq) - self.n_prompt + 1  # 1-based index of the token these logits predict
            if step in self.force:
                logits[self.force[step]] = 100.0
            rows.append(logits)
        return mx.array(np.stack(rows)[None])


class _FakeHFLM:
    """Transformers model stand-in: greedy generate with the given logits processors and eos ids."""

    device = "cpu"

    def __init__(self, width: int, force: dict[int, int] | None = None):
        self.width = width
        self.force = force or {}

    def generate(self, input_ids, attention_mask, max_new_tokens, do_sample, eos_token_id, pad_token_id,
                 logits_processor=()):
        assert do_sample is False
        ids = input_ids.clone()
        n_prompt = ids.shape[1]
        for _ in range(max_new_tokens):
            logits = torch.from_numpy(_fake_logits(ids[0].tolist(), self.width))[None]
            step = ids.shape[1] - n_prompt + 1
            if step in self.force:
                logits[0, self.force[step]] = 100.0
            for p in logits_processor:
                logits = p(ids, logits)
            nxt = int(torch.argmax(logits[0]))
            ids = torch.cat([ids, torch.tensor([[nxt]])], dim=1)
            if nxt in eos_token_id:
                break
        self.n_new = ids.shape[1] - n_prompt
        return ids


def _allowed_torch(proc, seq, width):
    return torch.isfinite(proc(torch.tensor([seq]), torch.zeros(1, width))).numpy()[0]


def _allowed_mlx(proc, seq, width):
    import mlx.core as mx

    return np.array(mx.isfinite(proc(mx.array(seq), mx.zeros((1, width)))))[0]


def _walk_and_compare(constraints, allowed_fns, schema, width, seed, steps=80):
    """Random walk over allowed tokens; every processor must allow exactly the same set at every step."""
    procs = [c.processor(schema) for c in constraints]
    rng = random.Random(seed)
    seq = [5, 6, 7]  # arbitrary prompt
    for _ in range(steps):
        masks = [fn(p, seq, width) for p, fn in zip(procs, allowed_fns)]
        for m in masks[1:]:
            assert np.array_equal(masks[0], m)
        allowed = np.flatnonzero(masks[0]).tolist()
        assert allowed, "constraint allows no token"
        nxt = rng.choice(allowed)
        seq.append(nxt)
        if nxt == constraints[0].vocabulary.get_eos_token_id():
            return


# ---------------------------------------------------------------------------
# 1. Shared processor: CUDA route unchanged; MLX masks exactly the CUDA-allowed set
# ---------------------------------------------------------------------------
def test_stop_tokens_defined_once_and_resolved(toy_tok):
    assert qwen_srv.STOP_TOKENS == ("<|im_end|>", "<|endoftext|>")
    assert qwen_srv.stop_token_ids(toy_tok) == sorted(toy_tok.convert_tokens_to_ids(list(qwen_srv.STOP_TOKENS)))
    missing = SimpleNamespace(unk_token_id=None, convert_tokens_to_ids=lambda t: None)
    with pytest.raises(ValueError, match="not in the tokenizer vocabulary"):
        qwen_srv.stop_token_ids(missing)


def test_shared_builder_matches_outlines_transformers_route(toy_tok):
    """SchemaConstraint("torch") allows the same tokens as outlines' public Transformers route (the P2e CUDA path)."""
    import outlines
    from outlines.backends import get_json_schema_logits_processor

    class _Public:
        vocabulary = qwen_srv.build_outlines_vocabulary(toy_tok)

        def __init__(self):
            self.model = outlines.from_transformers(object(), toy_tok)

        def processor(self, schema):
            return get_json_schema_logits_processor("outlines_core", self.model, json.dumps(schema))

    width = len(toy_tok) + 13  # model logits are wider than the tokenizer vocabulary
    shared = qwen_srv.SchemaConstraint(toy_tok, "torch")
    for schema in _schemas():
        for seed in range(5):
            _walk_and_compare([shared, _Public()], [_allowed_torch, _allowed_torch], schema, width, seed)


def test_mlx_processor_masks_exactly_the_cuda_allowed_set(toy_tok):
    pytest.importorskip("mlx.core")
    width = len(toy_tok) + 13
    cuda = qwen_srv.SchemaConstraint(toy_tok, "torch")
    mlx = qwen_srv.SchemaConstraint(toy_tok, "mlx")
    for schema in _schemas():
        for seed in range(10):
            _walk_and_compare([cuda, mlx], [_allowed_torch, _allowed_mlx], schema, width, seed)


def test_mlx_cuda_parity_on_real_qwen_tokenizer():
    """Local check on the pinned Qwen3.5-4B tokenizer at the model's logits width (248320)."""
    pytest.importorskip("mlx.core")
    from transformers import AutoTokenizer

    try:
        tok = AutoTokenizer.from_pretrained(qwen_srv.MODEL_SOURCE, revision=qwen_srv.MODEL_REVISION,
                                            local_files_only=True)
    except OSError:
        pytest.skip("Qwen3.5-4B tokenizer not in the local HF cache")
    assert qwen_srv.stop_token_ids(tok) == [248044, 248046]
    cuda = qwen_srv.SchemaConstraint(tok, "torch")
    mlx = qwen_srv.SchemaConstraint(tok, "mlx")
    for schema in _schemas():
        for seed in range(3):
            _walk_and_compare([cuda, mlx], [_allowed_torch, _allowed_mlx], schema, 248320, seed)


def test_constraint_key_order_is_request_order(toy_tok):
    schema = {"type": "object", "properties": {"b": {"type": "string", "enum": ["yes"]},
                                               "a": {"type": "string", "enum": ["no"]}},
              "required": ["b", "a"], "additionalProperties": False}
    proc = qwen_srv.SchemaConstraint(toy_tok, "torch").processor(schema)
    width = len(toy_tok)
    seq = [5]
    text = ""
    while True:  # follow the lowest allowed id: the only freedom is optional whitespace
        allowed = np.flatnonzero(_allowed_torch(proc, seq, width))
        nxt = int(allowed[0])
        if nxt == toy_tok.eos_token_id:
            break
        seq.append(nxt)
        text += toy_tok.decode([nxt])
    assert list(json.loads(text)) == ["b", "a"]


# ---------------------------------------------------------------------------
# 2. Constrained generation: outputs parse against the schema; MLX == CUDA token for token
# ---------------------------------------------------------------------------
def _mlx_backend(toy_tok, constrained, force=None):
    from mlx_lm.tokenizer_utils import TokenizerWrapper

    gen = qwen_srv.MlxQwenJson(None, TokenizerWrapper(toy_tok), constrained=constrained)
    gen.model = _FakeMlxLM(len(toy_tok) + 13, force)
    return gen


def _mlx_generate(gen, prompt, max_tokens, schema):
    gen.model.n_prompt = len(gen.hf_tokenizer.encode(prompt, add_special_tokens=False))
    return gen.generate(prompt, max_tokens, schema)


def test_cuda_constrained_outputs_parse_against_schema(toy_tok):
    gen = qwen_srv.CudaQwenJson(_FakeHFLM(len(toy_tok) + 13), toy_tok, constrained=True)
    free = qwen_srv.CudaQwenJson(_FakeHFLM(len(toy_tok) + 13), toy_tok, constrained=False)
    n_free_invalid = 0
    for schema in _schemas():
        for i in range(4):
            prompt = f"case {i}: return JSON"
            out = gen.generate(prompt, 200, schema)
            jsonschema.validate(json.loads(out), schema)
            assert list(json.loads(out)) == list(schema["properties"])
            try:
                jsonschema.validate(json.loads(free.generate(prompt, 60, schema)), schema)
            except (ValueError, jsonschema.ValidationError):
                n_free_invalid += 1
    assert n_free_invalid == 12  # the fake model alone never emits schema-valid JSON


def test_mlx_constrained_outputs_parse_and_match_cuda(toy_tok):
    pytest.importorskip("mlx.core")
    cuda = qwen_srv.CudaQwenJson(_FakeHFLM(len(toy_tok) + 13), toy_tok, constrained=True)
    mlx = _mlx_backend(toy_tok, constrained=True)
    for schema in _schemas():
        for i in range(4):
            prompt = f"case {i}: return JSON"
            out = _mlx_generate(mlx, prompt, 200, schema)
            jsonschema.validate(json.loads(out), schema)
            assert out == cuda.generate(prompt, 200, schema)


def test_mlx_and_cuda_stop_at_the_same_explicit_stop_set(toy_tok):
    """Free decoding: <|endoftext|> stops generation on both backends, like <|im_end|>."""
    pytest.importorskip("mlx.core")
    width = len(toy_tok) + 13
    prompt = "stop test"
    unforced = qwen_srv.CudaQwenJson(_FakeHFLM(width), toy_tok, constrained=False)
    unforced.generate(prompt, 30, None)
    assert unforced.model.n_new > 4  # without forcing, no stop token within the first 4 tokens
    for stop in qwen_srv.STOP_TOKENS:
        force = {4: toy_tok.convert_tokens_to_ids(stop)}
        cuda = qwen_srv.CudaQwenJson(_FakeHFLM(width, force), toy_tok, constrained=False)
        mlx = _mlx_backend(toy_tok, constrained=False, force=force)
        out_cuda = cuda.generate(prompt, 30, None)
        out_mlx = _mlx_generate(mlx, prompt, 30, None)
        assert out_mlx == out_cuda and stop not in out_mlx
        # Both stopped at the forced 4th token (MLX feeds the stop token once more, pipelined).
        assert cuda.model.n_new == 4 and len(mlx.model.seq) - mlx.model.n_prompt == 4


# ---------------------------------------------------------------------------
# 3. MLX backend wiring: model ids, /warmup, default decoding
# ---------------------------------------------------------------------------
def test_mlx_backend_selection_and_ids():
    with patch("huggingface_hub.snapshot_download", return_value="/snap") as snap, \
            patch("mlx_lm.load", return_value=("m", "tok")), \
            patch.object(qwen_srv, "SchemaConstraint") as constraint:
        model, tok, mid = qwen_srv.load_backend("mlx", "constrained")
        assert isinstance(model, qwen_srv.MlxQwenJson) and model.constrained and tok == "tok"
        assert mid == qwen_srv.RESOLVED_MODEL_ID == "qwen3.5-4b-json@851bf6e8+constrained"
        constraint.assert_called_once_with("tok", "mlx")
        constraint.reset_mock()
        model, _, mid = qwen_srv.load_backend("mlx", "free")
        assert not model.constrained and mid == "qwen3.5-4b-json@851bf6e8+free"
        constraint.assert_not_called()
    snap.assert_called_with(qwen_srv.MODEL_SOURCE, revision=qwen_srv.MODEL_REVISION)

    manifest = load_manifest()
    assert manifest["Qwen3.5-4B-JSON"]["model"] == qwen_srv.RESOLVED_MODEL_ID
    assert manifest["Qwen3.5-4B-JSON"]["accepted_resolved_models"] == [qwen_srv.RESOLVED_MODEL_ID]

    with patch.object(qwen_srv, "load_backend", side_effect=RuntimeError("stop")) as load:
        with pytest.raises(RuntimeError):
            qwen_srv.run_server(backend="mlx")
    load.assert_called_once_with("mlx", "constrained")


def test_mlx_warmup_compiles_real_processors(toy_tok):
    pytest.importorskip("mlx.core")
    gen = _mlx_backend(toy_tok, constrained=True)
    schemas = _schemas()
    resp = qwen_srv.process_warmup(gen, {"schemas": schemas})
    assert [s["compiled"] for s in resp["schemas"]] == [True] * 3
    assert [s["cached"] for s in resp["schemas"]] == [False] * 3
    again = qwen_srv.process_warmup(gen, {"schemas": schemas})
    assert [s["cached"] for s in again["schemas"]] == [True] * 3


# ---------------------------------------------------------------------------
# 4. Laya: no tokenizer call in the response path; offline sidecar; pinned revision on every device
# ---------------------------------------------------------------------------
class _WordTok:
    """The P2d fixture tokenizer: one token per word, BERT-style special ids."""

    mask_token = "[MASK]"
    mask_token_id = 1
    cls_token_id = 2
    sep_token_id = 3

    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, text, add_special_tokens=False):
        self.calls.append(text)
        return {"input_ids": [100 + len(w) for w in text.split()]}


def test_laya_response_path_has_no_tokenizer_call():
    order: list[str] = []
    tok = _WordTok()
    agent = SimpleNamespace(tok=tok, cfg={"max_len": 1024, "head_max_len": 192})

    def system_one(state, questions):
        order.append("system_one")
        return {"answers": {q: {"choice": "ocr", "probabilities": {"ocr": 0.9, "count": 0.1}} for q in questions}}

    agent.system_one = system_one
    questions = {f"q{i}": {"type": "choice", "instructions": "Pick", "criteria": {"ocr": "OCR", "count": "C"}}
                 for i in range(3)}
    with patch.object(laya_srv, "compute_untruncated_token_count",
                      side_effect=lambda *a, **k: order.append("count")) as count:
        resp = laya_srv.process_laya_request(agent, {"state": "read the label", "questions": questions})
    assert order == ["system_one"] and tok.calls == []
    count.assert_not_called()
    assert resp["usage"]["input_tokens"] is None and resp["usage"]["truncated"] is None
    assert resp["truncated"] is None
    assert set(resp["answers"]) == set(questions)


def _laya_cases() -> list[Case]:
    return [
        Case(case_id="c1", text="Read the parcel label at the dock, urgent.", truth=[{}]),
        Case(case_id="c2", text=" ".join(["pallet"] * 30) + " count them on site.", fields=["service_type"],
             service_options={"svc_a": "service a", "svc_b": "service b", "unsupported": "none"}, truth=[{}]),
        Case(case_id="c3", text="First read the meter, then count the boxes.", bundle_size=2, truth=[{}, {}]),
    ]


# (input_tokens, truncated) for these cases and agent configs. The pre-P2g server returned
# c1/c2/c3 = 215/104/486 under the old field instruction; the pin follows the D-6 contract text
# (READING_RULES in get_field_instruction, EXP-2026-001 deviations.md), which lengthens every question.
PREVIOUS_SERVER_COUNTS = {
    (1024, 192): {"c1": (335, False), "c2": (134, False), "c3": (702, False)},
    (40, 32): {"c1": (335, True), "c2": (134, True), "c3": (702, True)},
}


@pytest.mark.parametrize("cfg", sorted(PREVIOUS_SERVER_COUNTS))
def test_laya_offline_sidecar_reproduces_previous_server_counts(tmp_path: Path, cfg):
    cases = _laya_cases()
    cases_file = tmp_path / "cases.jsonl"
    cases_file.write_text("".join(json.dumps(c.to_dict()) + "\n" for c in cases), encoding="utf-8")
    rows = [{"condition": cond, "model": model, "case_id": c.case_id, "repeat": rep}
            for cond in ("cond_b", "cond_a") for c in cases for model in ("Laya", "Laya@cuda") for rep in (0, 1)]
    rows.append({"condition": "cond_x", "model": "SemIf-Qwen3.5-4B", "case_id": "c1", "repeat": 0})
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    agent = SimpleNamespace(tok=_WordTok(), cfg={"max_len": cfg[0], "head_max_len": cfg[1]})
    with patch.object(laya_tokens, "load_agent", return_value=agent) as load:
        assert laya_tokens.main(["--ledger", str(ledger), "--cases", str(cases_file)]) == 0
    load.assert_called_once_with("cpu")

    out = tmp_path / "ledger.jsonl.laya_tokens.jsonl"
    assert laya_tokens.sidecar_path(ledger) == out
    records = [json.loads(line) for line in out.read_text().splitlines()]
    assert [(r["condition"], r["case_id"]) for r in records] == [
        (cond, cid) for cond in ("cond_a", "cond_b") for cid in ("c1", "c2", "c3")]
    for r in records:
        assert (r["input_tokens"], r["truncated"]) == PREVIOUS_SERVER_COUNTS[cfg][r["case_id"]]
        assert r["model_revision"] == laya_srv.MODEL_REVISION
    first = out.read_bytes()
    with patch.object(laya_tokens, "load_agent", return_value=agent):
        laya_tokens.main(["--ledger", str(ledger), "--cases", str(cases_file)])
    assert out.read_bytes() == first  # deterministic

    with pytest.raises(KeyError, match="not in the cases file"):
        laya_tokens.compute_sidecar(rows, cases[:2], agent, load_manifest())


@pytest.mark.parametrize("device", ["mps", "cpu", "cuda"])
def test_laya_every_device_loads_the_pinned_revision(device):
    agent = SimpleNamespace(device=device)
    with patch("huggingface_hub.snapshot_download", return_value="/snap/bc76") as snap, \
            patch("laya.load", return_value=agent) as load:
        assert laya_srv.load_agent(device) is agent
    snap.assert_called_once_with(
        laya_srv.MODEL_ID_OR_PATH, revision=laya_srv.MODEL_REVISION, allow_patterns=laya_srv.LAYA_ALLOW_PATTERNS
    )
    load.assert_called_once_with("/snap/bc76", device=device)


def test_laya_mps_server_and_cpu_fallback_use_pinned_loader():
    agent = SimpleNamespace(device="cpu")
    with patch.object(laya_srv, "load_agent", side_effect=[RuntimeError("no mps"), agent]) as load, \
            patch.object(laya_srv, "warmup"), patch.object(laya_srv, "ThreadingHTTPServer") as server:
        server.return_value.serve_forever.side_effect = KeyboardInterrupt
        laya_srv.run_server(device="mps")
    assert load.call_args_list == [call("mps"), call("cpu")]
    assert laya_srv.LayaRequestHandler.model_id == laya_srv.RESOLVED_MODEL_ID
