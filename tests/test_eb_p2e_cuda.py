"""Offline tests for the P2e CUDA backends, git-less runner, and manifest entries.

No GPU, no model weights, no network: loaders, outlines and generation are mocked.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import torch

import scripts.eb_serve_laya as laya_srv
import scripts.eb_serve_qwen_json as qwen_srv
import scripts.eb_serve_semif as semif_srv
from scripts.eb_align_check import compare_runs
from src.edgebench.contract import Case
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.manifest import PLATFORMS, build_interpreter, load_manifest
from src.edgebench.runner import run_benchmark

REPO = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Backend flag selection (mocked loaders)
# ---------------------------------------------------------------------------
def test_semif_cuda_backend_uses_torch_reference_path_bf16():
    with patch("semif_phase1.core.load_causal_model", return_value=("m", "t", {"device": "cuda:0"})) as load:
        assert semif_srv.load_backend_model("cuda") == ("m", "t", {"device": "cuda:0"})
    load.assert_called_once_with(
        semif_srv.MODEL_SOURCE, revision=semif_srv.MODEL_REVISION, device="cuda", dtype="bfloat16"
    )
    assert semif_srv.resolved_model_id("cuda") == "semif-qwen3.5-4b@23cf1f39+cuda"
    assert semif_srv.resolved_model_id("mlx") == semif_srv.resolved_model_id("mps") == "semif-qwen3.5-4b@23cf1f39"
    with pytest.raises(ValueError):
        semif_srv.load_backend_model("rocm")

    with patch.object(sys, "argv", ["eb_serve_semif.py", "--backend", "cuda", "--port", "8611"]), \
            patch.object(semif_srv, "run_server") as run:
        semif_srv.main()
    run.assert_called_once_with(port=8611, backend="cuda", mode="shared", max_tokens=32768)


def test_semif_response_shape_identical_across_backends():
    def score_fn(rows, max_tokens):
        return ([{"id": r["id"], "option_ids": [o["id"] for o in r["options"]], "probabilities": [0.7, 0.3]}
                 for r in rows], {"prefix_tokens": 10, "true_suffix_tokens": 5})

    req = {"state": "s", "questions": {
        "a": {"type": "choice", "instructions": "x", "criteria": {"p": "P", "q": "Q"}},
        "b": {"type": "choice", "instructions": "y", "criteria": {"p": "P", "q": "Q"}},
    }}
    mlx = semif_srv.process_decisions_request(req, score_fn, model_id=semif_srv.resolved_model_id("mlx"))
    cuda = semif_srv.process_decisions_request(req, score_fn, model_id=semif_srv.resolved_model_id("cuda"))
    assert cuda["model"].endswith("+cuda")
    assert {k: v for k, v in mlx.items() if k != "model"} == {k: v for k, v in cuda.items() if k != "model"}


def test_laya_cuda_device_pins_revision_and_requires_cuda():
    agent = SimpleNamespace(device="cuda:0")
    with patch("huggingface_hub.snapshot_download", return_value="/snap/bc76") as snap, \
            patch("laya.load", return_value=agent) as load:
        assert laya_srv.load_agent("cuda") is agent
    snap.assert_called_once_with(
        laya_srv.MODEL_ID_OR_PATH, revision=laya_srv.MODEL_REVISION, allow_patterns=laya_srv.LAYA_ALLOW_PATTERNS
    )
    load.assert_called_once_with("/snap/bc76", device="cuda")
    assert laya_srv.resolved_model_id("cuda") == "laya-typed-decisions@bc76315b+cuda"
    assert laya_srv.resolved_model_id("mps") == "laya-typed-decisions@bc76315b"

    # laya silently falls back to CPU when CUDA is missing; the server must refuse that.
    with patch("huggingface_hub.snapshot_download", return_value="/snap"), \
            patch("laya.load", return_value=SimpleNamespace(device="cpu")):
        with pytest.raises(RuntimeError, match="did not load on CUDA"):
            laya_srv.load_agent("cuda")

    with patch.object(sys, "argv", ["eb_serve_laya.py", "--device", "cuda", "--port", "8612"]), \
            patch.object(laya_srv, "run_server") as run:
        laya_srv.main()
    run.assert_called_once_with(port=8612, device="cuda")


def test_qwen_json_backend_selection():
    with patch.object(qwen_srv, "load_hf_model", return_value=("hf", "tok")) as load, \
            patch.object(qwen_srv, "SchemaConstraint") as constraint:
        model, tok, mid = qwen_srv.load_backend("cuda", "constrained")
        assert isinstance(model, qwen_srv.CudaQwenJson) and model.constrained and tok == "tok"
        assert mid == "qwen3.5-4b-json@851bf6e8+constrained-cuda"
        constraint.assert_called_once_with("tok", "torch")

        constraint.reset_mock()
        model, _, mid = qwen_srv.load_backend("cuda", "free")
        assert not model.constrained and mid == "qwen3.5-4b-json@851bf6e8+free-cuda"
        constraint.assert_not_called()
    load.assert_called_with(qwen_srv.MODEL_SOURCE, qwen_srv.MODEL_REVISION, device="cuda")
    with pytest.raises(ValueError):
        qwen_srv.load_backend("rocm", "constrained")

    with patch.object(sys, "argv", ["eb_serve_qwen_json.py", "--backend", "cuda", "--port", "8613"]), \
            patch.object(qwen_srv, "run_server") as run:
        qwen_srv.main()
    run.assert_called_once_with(port=8613, backend="cuda", decoding=None)


# ---------------------------------------------------------------------------
# qwen_json: CUDA renders the same prompt as MLX; outlines schema wiring
# ---------------------------------------------------------------------------
TEMPLATE_OUT = "<|im_start|>user\nx<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n"


def _chat_body() -> dict:
    case = Case(case_id="c", text="Read the label on site, urgent.", truth=[{
        "service_type": "ocr", "locality": "site_only", "quality_floor": "unspecified", "urgency": "urgent"}])
    client = ChatJsonClient(name="q", model="m", provider_slug="local", base_url="http://127.0.0.1:1",
                            deployment="self-hosted")
    return client.build_request(case)


def test_qwen_json_cuda_renders_same_prompt_as_mlx():
    tok = MagicMock()
    tok.apply_chat_template.return_value = TEMPLATE_OUT
    tok.encode.side_effect = lambda text, add_special_tokens=False: [1] * len(text)
    body = _chat_body()
    content = '{"service_type": "ocr"}'

    mlx_model = MagicMock()
    mlx_model.generate.return_value = content
    mlx_resp = qwen_srv.process_chat_completion(mlx_model, tok, body)
    cuda_model = MagicMock()
    cuda_model.generate.return_value = content
    cuda_resp = qwen_srv.process_chat_completion(
        cuda_model, tok, body, model_id="qwen3.5-4b-json@851bf6e8+constrained-cuda"
    )

    assert mlx_model.generate.call_args.args == cuda_model.generate.call_args.args
    cuda_prompt, cuda_max, cuda_schema = cuda_model.generate.call_args.args
    assert cuda_prompt == TEMPLATE_OUT
    assert cuda_max == body["max_tokens"]
    assert cuda_schema == body["response_format"]["json_schema"]["schema"]
    assert set(cuda_resp) == set(mlx_resp)
    assert cuda_resp["choices"] == mlx_resp["choices"] and cuda_resp["usage"] == mlx_resp["usage"]
    assert cuda_resp["model"] == "qwen3.5-4b-json@851bf6e8+constrained-cuda"


class _FakeTok:
    eos_token_id = 248046  # <|im_end|>
    pad_token_id = 248044  # <|endoftext|>
    unk_token_id = None

    def convert_tokens_to_ids(self, token):
        return {"<|im_end|>": 248046, "<|endoftext|>": 248044}.get(token)

    def __call__(self, prompt, return_tensors="pt", add_special_tokens=False):
        assert add_special_tokens is False
        ids = torch.tensor([[7, 8, 9]])
        return {"input_ids": ids, "attention_mask": torch.ones_like(ids)}

    def decode(self, ids, skip_special_tokens=False):
        assert skip_special_tokens is False
        return "|".join(str(i) for i in ids)


class _FakeHF:
    device = "cpu"
    generation_config = SimpleNamespace(eos_token_id=248044)

    def __init__(self):
        self.calls = []

    def generate(self, input_ids, attention_mask, **kwargs):
        self.calls.append(kwargs)
        return torch.tensor([[7, 8, 9, 11, 12, 248046, 248046]])


def test_qwen_json_outlines_schema_wiring():
    processor = MagicMock()
    factory = MagicMock(return_value=processor)

    hf = _FakeHF()
    tok = _FakeTok()
    schema = _chat_body()["response_format"]["json_schema"]["schema"]
    with patch.object(qwen_srv, "build_outlines_vocabulary", return_value="vocab") as vocab, \
            patch.object(qwen_srv, "build_json_schema_processor", factory):
        gen = qwen_srv.CudaQwenJson(hf, tok, constrained=True)
        out1 = gen.generate("prompt", 40, schema)
        out2 = gen.generate("prompt", 40, schema)

    # Processor built once per schema, from the schema in request order, and reset per request.
    vocab.assert_called_once_with(tok)
    factory.assert_called_once_with("vocab", json.dumps(schema), "torch")
    assert list(json.loads(factory.call_args.args[1])["properties"]) == list(schema["properties"])
    assert processor.reset.call_count == 2
    kw = hf.calls[0]
    assert list(kw["logits_processor"]) == [processor]
    assert kw["do_sample"] is False and kw["max_new_tokens"] == 40
    assert kw["eos_token_id"] == [248044, 248046]  # STOP_TOKENS: <|endoftext|>, <|im_end|>
    assert out1 == out2 == "11|12"  # prompt and trailing stop tokens removed

    free = qwen_srv.CudaQwenJson(_FakeHF(), _FakeTok(), constrained=False)
    free.generate("prompt", 40, schema)
    assert "logits_processor" not in free.model.calls[0]


def test_response_schema_extraction():
    body = _chat_body()
    assert qwen_srv.response_schema(body) == body["response_format"]["json_schema"]["schema"]
    assert qwen_srv.response_schema({"messages": []}) is None
    assert qwen_srv.response_schema({"response_format": {"type": "json_object"}}) is None


# ---------------------------------------------------------------------------
# Manifest: CUDA entries, platform on every entry, ids match the servers
# ---------------------------------------------------------------------------
def test_manifest_cuda_entries_and_platforms():
    manifest = load_manifest()
    for name, entry in manifest.items():
        assert entry.get("platform") in PLATFORMS, name
        if entry["deployment"] == "hosted":
            assert entry["platform"] == "hosted"
    expected = {
        "SemIf-Qwen3.5-4B@cuda": (8700, semif_srv.resolved_model_id("cuda")),
        "Laya@cuda": (8800, laya_srv.resolved_model_id("cuda")),
        "Qwen3.5-4B-JSON@cuda": (8900, qwen_srv.RESOLVED_MODEL_IDS[("cuda", "constrained")]),
    }
    for name, (port, server_id) in expected.items():
        e = manifest[name]
        assert e["deployment"] == "self-hosted" and e["platform"] == "H100-NVL"
        assert e["base_url"] == f"http://127.0.0.1:{port}"
        assert e["model"] == server_id and e["accepted_resolved_models"] == [server_id]
    for name in ("SemIf-Qwen3.5-4B", "Laya", "Qwen3.5-4B-JSON"):
        assert manifest[name]["platform"] == "M4-Max"
    assert build_interpreter("Laya@cuda", manifest=manifest).platform == "H100-NVL"

    bad = {"X": dict(manifest["Laya"], platform="A100")}
    with pytest.raises(ValueError, match="unknown platform"):
        build_interpreter("X", manifest=bad)


# ---------------------------------------------------------------------------
# Git-less runner
# ---------------------------------------------------------------------------
class _OkInterp(Interpreter):
    def decide(self, case: Case) -> Decision:
        return Decision(labels=[dict(case.truth[0])], valid=True, latency_s=0.01)


def _cases(tmp_path: Path) -> Path:
    p = tmp_path / "cases.jsonl"
    truth = {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}
    p.write_text(json.dumps(Case(case_id="c1", text="t", truth=[truth]).to_dict()) + "\n", encoding="utf-8")
    return p


def _run(tmp_path: Path, out: str):
    interp = _OkInterp("m", "self-hosted")
    interp.platform = "H100-NVL"
    with patch("src.edgebench.runner.build_interpreter", return_value=interp):
        return run_benchmark(cases_path=_cases(tmp_path), rq="RQ1", condition="base", model_names=["m"],
                             out_dir=tmp_path / out, workers=1)


SHA = "0123456789abcdef0123456789abcdef01234567"


def test_gitless_runner_accepts_attested_provenance(tmp_path: Path, monkeypatch):
    # P2f: git-less provenance comes from a verified PROVENANCE.json (EB_TREE_CLEAN alone is not trusted).
    from src.edgebench.provenance import tree_sha256

    from src.edgebench.provenance import sha256_file

    root = tmp_path  # P2h: the --cases file must be listed in PROVENANCE.json too
    (root / "a.txt").write_text("a\n")
    files = {"a.txt": "87428fc522803d31065e7bce3cf03fe475096631e5e07bbd7a0fde60c4cf25c7",
             "cases.jsonl": sha256_file(_cases(tmp_path))}
    (root / "PROVENANCE.json").write_text(json.dumps(
        {"head_sha": SHA, "files": files, "tree_sha256": tree_sha256(files)}))
    monkeypatch.setattr("src.edgebench.provenance.REPO_ROOT", root)
    monkeypatch.setattr("src.edgebench.ledger.shutil.which", lambda name: None)
    monkeypatch.setenv("EB_GIT_SHA", SHA)
    report = _run(tmp_path, "ok")
    assert report["git_sha"] == SHA and report["git_source"] == "provenance"
    row = json.loads((tmp_path / "ok" / "ledger.jsonl").read_text().splitlines()[0])
    assert row["git_sha"] == SHA and row["git_source"] == "provenance" and row["platform"] == "H100-NVL"


@pytest.mark.parametrize("sha,clean", [(None, "1"), (SHA, None), (SHA, "0"), ("abc123", "1"), (SHA[:-1] + "g", "1")])
def test_gitless_runner_refuses_without_attestation(tmp_path: Path, monkeypatch, sha, clean):
    monkeypatch.setattr("src.edgebench.ledger.shutil.which", lambda name: None)
    for key, val in (("EB_GIT_SHA", sha), ("EB_TREE_CLEAN", clean)):
        if val is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, val)
    with pytest.raises(RuntimeError, match="PROVENANCE.json"):
        _run(tmp_path, "refused")
    assert not (tmp_path / "refused" / "ledger.jsonl").exists()


def test_runner_with_git_ignores_env_attestation(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("src.edgebench.ledger._git_available", lambda: True)
    monkeypatch.setattr("src.edgebench.ledger.get_git_status", lambda: ("f" * 40, True))
    monkeypatch.setenv("EB_GIT_SHA", SHA)
    monkeypatch.setenv("EB_TREE_CLEAN", "1")
    with pytest.raises(RuntimeError, match="modified tracked files"):
        _run(tmp_path, "dirty")


# ---------------------------------------------------------------------------
# Alignment check compare mode
# ---------------------------------------------------------------------------
def test_align_compare_reports_agreement_and_probability_gap():
    def run(model, labels2, p):
        return {"model": model, "platform": None, "resolved_models": [model], "cases": [
            {"case_id": "a", "valid": True, "labels": [{"f": "x"}], "probabilities": [{"f": {"x": p, "y": 1 - p}}]},
            {"case_id": "b", "valid": True, "labels": [labels2], "probabilities": None},
        ]}

    rep = compare_runs(run("mlx", {"f": "x"}, 0.9), run("cuda", {"f": "y"}, 0.8))
    assert rep["n_common"] == 2
    assert rep["case_agreement"] == pytest.approx(0.5)
    assert rep["field_agreement"] == pytest.approx(0.5)
    assert rep["prob_abs_diff_max"] == pytest.approx(0.1)
    assert [d["case_id"] for d in rep["disagreements"]] == ["b"]




