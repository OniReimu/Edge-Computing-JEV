"""Regression tests for the corpus gate-review findings (P3f / P3f2: 1 x P0, 10 x P1, P2-3, codeswitch; P3g)."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from src.edgebench.contract import (
    Case,
    DEFAULT_CRITERIA,
    FIELD_SETS,
    get_field_instruction,
)
from src.edgebench.corpus.assemble import (
    compute_sha256,
    generate_manifest,
    generate_stats_markdown,
)
from src.edgebench.corpus.bundle import create_bundle_messages
from src.edgebench.corpus.catalog import load_catalogs, load_services, save_catalogs
from src.edgebench.corpus.client import CorpusLLMClient
from src.edgebench.corpus.exchange import CorpusExchange
from src.edgebench.corpus.lints import (
    check_codeswitch_monolingual_lint,
    check_copy_4gram_lint,
    check_enum_leak_lint,
)
from src.edgebench.corpus.noise import derive_noise_cases
from src.edgebench.corpus.pad import (
    assert_padding_clean,
    create_padded_dataset,
    get_tokenizer,
)
from src.edgebench.corpus.pipeline import CorpusPipeline
from src.edgebench.corpus.prompts import (
    build_generator_batch_prompt,
    build_single_item_generator_prompt,
    build_verifier_batch_prompt,
    build_verifier_context_markdown,
)
from src.edgebench.corpus.tuples import (
    TupleItem,
    sample_tuples_for_condition,
)
from src.edgebench.interpreters.decisions import DecisionsClient

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def exchange_env(tmp_path: Path):
    exchange_dir = tmp_path / "exchange"
    data_dir = tmp_path / "data"
    cat_dir = data_dir / "catalog"
    save_catalogs(cat_dir, seed=20260924)

    exchange = CorpusExchange(
        exchange_dir=exchange_dir,
        data_dir=data_dir,
        seed=20260924,
    )
    return exchange, exchange_dir, data_dir


def _unique_text(it) -> str:
    # Every opening 4-gram and word 5-gram contains the item id, so the diversity lint never fires.
    return f"Handle order {it.item_id} for the team today."


def _write_gen_done(exchange: CorpusExchange, text_for=_unique_text, generator: str = "fake-gen@agy") -> None:
    for gf in sorted(exchange.gen_todo_dir.glob("*.jsonl")):
        if gf.name in exchange.ingested_gen_files:
            continue
        with open(gf, encoding="utf-8") as f_in, open(exchange.gen_done_dir / gf.name, "w", encoding="utf-8") as f_out:
            for line in f_in:
                iid = json.loads(line)["item_id"]
                f_out.write(json.dumps({"item_id": iid, "text": text_for(exchange.items[iid]), "generator": generator}) + "\n")


def _write_ver_done(exchange: CorpusExchange, labels_for=None, verifier: str = "fake-ver@opus") -> None:
    for vf in sorted(exchange.ver_todo_dir.glob("*.jsonl")):
        if vf.name in exchange.ingested_ver_files:
            continue
        with open(vf, encoding="utf-8") as f_in, open(exchange.ver_done_dir / vf.name, "w", encoding="utf-8") as f_out:
            for line in f_in:
                it = exchange.items[json.loads(line)["item_id"]]
                labels = labels_for(it) if labels_for else dict(it.tuple_labels)
                f_out.write(json.dumps({"item_id": it.item_id, "labels": labels, "verifier": verifier}) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# Item 1: P0 — ingest never writes the formal corpus files; assemble rewrites them from state
# ---------------------------------------------------------------------------
def test_p3f_1_p0_ingest_ver_does_not_write_formal_files_and_assemble_rewrites(exchange_env):
    exchange, exchange_dir, data_dir = exchange_env
    exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=10, n_test=10, n_dev=0)
    _write_gen_done(exchange)
    exchange.ingest_gen()

    ver_files = exchange.export_ver(conditions=["clean"], splits=["test"], ver_batch_size=5)
    b1_file, b2_file = sorted(f for f in ver_files if f.name.endswith(".jsonl"))
    done_v1 = exchange.ver_done_dir / b1_file.name
    done_v2 = exchange.ver_done_dir / b2_file.name
    _write_ver_done(exchange)
    good_v2 = done_v2.read_text(encoding="utf-8")
    done_v2.write_text(good_v2[: len(good_v2) // 2], encoding="utf-8")  # truncated second done file

    with pytest.raises(ValueError):
        exchange.ingest_ver()

    # State was saved after the first done file: a fresh load sees it ingested and its 5 items accepted
    reloaded = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=20260924)
    assert done_v1.name in reloaded.ingested_ver_files
    assert done_v2.name not in reloaded.ingested_ver_files
    assert sum(1 for it in reloaded.items.values() if it.status == "accepted") == 5

    canonical_file = data_dir / "RQ2" / "clean" / "test.jsonl"
    accepted_file = data_dir / "_accepted" / "clean_test.jsonl"
    assert not canonical_file.exists()
    assert not accepted_file.exists()

    # Fix the second file and re-ingest: each item is accepted exactly once, still no formal files
    done_v2.write_text(good_v2, encoding="utf-8")
    res = reloaded.ingest_ver()
    assert res["items_accepted"] == 5
    assert len(reloaded.items) == 10
    assert sum(1 for it in reloaded.items.values() if it.status == "accepted") == 10
    assert not canonical_file.exists()

    # Assemble writes exactly n unique rows sorted by case_id, and rewrites (never appends)
    reloaded.assemble(n_test=10, n_dev=0)
    cases = _read_jsonl(canonical_file)
    case_ids = [c["case_id"] for c in cases]
    assert len(cases) == 10 and len(set(case_ids)) == 10 and case_ids == sorted(case_ids)
    assert [r["tuple_id"] for r in _read_jsonl(accepted_file)] == case_ids
    first_bytes = canonical_file.read_bytes()
    reloaded.assemble(n_test=10, n_dev=0)
    assert canonical_file.read_bytes() == first_bytes

    # Assemble asserts n
    with pytest.raises(ValueError, match="expected 11"):
        reloaded.assemble(n_test=11, n_dev=0)

    # Assemble asserts unique case_ids (a second accepted item for an existing tuple)
    dup = next(it for it in reloaded.items.values() if it.status == "accepted")
    extra = type(dup).from_dict({**dup.to_dict(), "item_id": "it_duplicate"})
    reloaded.items[extra.item_id] = extra
    with pytest.raises(ValueError, match="duplicate accepted case_ids"):
        reloaded.assemble(n_test=11, n_dev=0)


# ---------------------------------------------------------------------------
# Item 2: P1-1 — RQ2 conditions must share tuples
# ---------------------------------------------------------------------------
def test_p3f_2_p1_1_rq2_conditions_share_tuples():
    rq2_conditions = ["clean", "colloquial", "negation", "codeswitch", "defaultbait", "revised", "keyvalue"]
    sampled = {
        cond: sample_tuples_for_condition(cond, split="test", n=60, base_seed=20260924)
        for cond in rq2_conditions
    }

    clean_tuples = sampled["clean"]
    for cond in rq2_conditions[1:]:
        other_tuples = sampled[cond]
        assert len(other_tuples) == len(clean_tuples)
        for i in range(len(clean_tuples)):
            t_clean = clean_tuples[i]
            t_other = other_tuples[i]
            assert t_clean.tuple_labels == t_other.tuple_labels, f"Mismatch labels at {i} for {cond}"
            assert t_clean.meta["scenario"] == t_other.meta["scenario"], f"Mismatch scenario at {i} for {cond}"
            assert t_other.tuple_id == f"{cond}_test_{i:04d}"


# ---------------------------------------------------------------------------
# Item 3: P1-2 — defaultbait needs an unspecified field
# ---------------------------------------------------------------------------
def test_p3f_3_p1_2_defaultbait_unspecified_field_and_zero_all_specified():
    tuples = sample_tuples_for_condition("defaultbait", split="test", n=300, base_seed=20260924)
    assert len(tuples) == 300

    non_service_fields = ["locality", "quality_floor", "urgency"]
    all_specified_count = sum(
        1 for t in tuples if all(t.tuple_labels[f] != "unspecified" for f in non_service_fields)
    )
    assert all_specified_count == 0

    for f in non_service_fields:
        counts = Counter(t.tuple_labels[f] for t in tuples)
        assert counts["unspecified"] >= 120
        opts = [k for k in counts if k != "unspecified"]
        assert len(opts) == 2
        assert abs(counts[opts[0]] - counts[opts[1]]) <= 5


# ---------------------------------------------------------------------------
# Item 4: P1-3 — unsupported is neither seen nor unseen
# ---------------------------------------------------------------------------
def test_p3f_4_p1_3_unsupported_seen_is_none(tmp_path: Path):
    cat_dir = tmp_path / "catalog"
    save_catalogs(cat_dir, seed=20260924)
    catalogs = load_catalogs(cat_dir)
    novel_ids = [s["id"] for s in load_services(cat_dir)["novel_services"]]

    for cond in ("K254", "churn25"):
        tuples = sample_tuples_for_condition(
            cond, split="test", n=100, base_seed=20260924, catalogs=catalogs, novel_service_ids=novel_ids,
        )
        unsupp = [t for t in tuples if t.meta.get("is_unsupported")]
        assert len(unsupp) > 0
        for t in unsupp:
            assert t.meta.get("seen") is None, f"Expected seen=None for unsupported, got {t.meta.get('seen')}"
        assert all(isinstance(t.meta["seen"], bool) for t in tuples if not t.meta.get("is_unsupported"))


# ---------------------------------------------------------------------------
# Item 5: P1-4 — RQ4 copy lint must not vary with K (exchange and API pipeline)
# ---------------------------------------------------------------------------
def _k_invariance_fixture(data_dir: Path) -> tuple[dict[str, list[str]], dict[str, Any], str]:
    cat_dir = data_dir / "catalog"
    catalogs = load_catalogs(cat_dir)
    services = load_services(cat_dir)
    all_svcs = {s["id"]: s for s in services["services"] + services["novel_services"]}
    # A 4-gram from a service that is active under K254 but not under K4
    other_id = next(s for s in catalogs["C_254"] if s not in catalogs["C_4"] and len(all_svcs[s]["description"].split()) >= 4)
    span = " ".join(all_svcs[other_id]["description"].lower().split()[:4])
    return catalogs, all_svcs, span


def test_p3f_5_p1_4_rq4_copy_lint_invariant_to_k_exchange(exchange_env):
    exchange, _, data_dir = exchange_env
    catalogs, all_svcs, span = _k_invariance_fixture(data_dir)
    exchange.export_gen(conditions=["K4", "K254"], splits=["test"], gen_batch_size=20, n_test=10, n_dev=0)
    items = list(exchange.items.values())
    # The span must not come from any item's own target description (else the lint is right to fire)
    assert all(check_copy_4gram_lint(f"x {span} y", [], all_svcs[it.meta["target_service"]]["description"])[0] for it in items)

    _write_gen_done(exchange, text_for=lambda it: f"Order {it.item_id} needs us to {span} before noon.")
    res = exchange.ingest_gen()
    assert res["rejections"].get("lint_copy_4gram", 0) == 0
    verdicts = {cond: {it.status for it in items if it.condition == cond} for cond in ("K4", "K254")}
    assert verdicts == {"K4": {"done_gen"}, "K254": {"done_gen"}}


def test_p3f_5_p1_4_rq4_copy_lint_still_rejects_target_description(exchange_env):
    # Positive control: copying the target's own description is rejected under every K
    exchange, _, data_dir = exchange_env
    _, all_svcs, _ = _k_invariance_fixture(data_dir)
    exchange.export_gen(conditions=["K4", "K254"], splits=["test"], gen_batch_size=20, n_test=10, n_dev=0)

    def copy_target(it) -> str:
        span = " ".join(all_svcs[it.meta["target_service"]]["description"].lower().split()[-4:])
        return f"Order {it.item_id} needs us to {span} before noon."

    _write_gen_done(exchange, text_for=copy_target)
    res = exchange.ingest_gen()
    assert res["rejections"]["lint_copy_4gram"] == 20


def test_p3f_5_p1_4_rq4_copy_lint_invariant_to_k_pipeline(tmp_path: Path):
    data_dir = tmp_path / "data"
    save_catalogs(data_dir / "catalog", seed=20260924)
    catalogs, all_svcs, span = _k_invariance_fixture(data_dir)
    labels = {"service_type": "count", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}
    gen_calls = 0

    def transport(payload: dict[str, Any]):
        nonlocal gen_calls
        user_msg = payload["messages"][1]["content"]
        if "specifications:\n\n" in user_msg:
            gen_calls += 1
            specs = json.loads(user_msg.split("specifications:\n\n")[1])
            text = f"We need to {span} at the gate." if gen_calls == 1 else "Tally the crates at the gate."
            body = {"items": [{"id": sp["id"], "text": text} for sp in specs]}
        else:
            batch = json.loads(user_msg.split("the batch:\n\n")[1])
            body = {"items": [{"id": b["id"], "labels": dict(labels)} for b in batch]}
        resp = {"model": payload["model"], "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
                "choices": [{"message": {"content": json.dumps(body)}}]}
        return 200, json.dumps(resp), 0.01, None

    copy_rejections = {}
    for cond, cat_key in (("K4", "C_4"), ("K254", "C_254")):
        gen_calls = 0
        opts = {sid: all_svcs[sid]["description"] for sid in catalogs[cat_key]}
        opts["unsupported"] = "unsupported service"
        pipeline = CorpusPipeline(
            client=CorpusLLMClient(log_dir=tmp_path / f"runs_{cond}", transport_override=transport),
            service_catalog=all_svcs,
            catalogs=catalogs,
            accepted_dir=tmp_path / f"accepted_{cond}",
        )
        item = TupleItem(condition=cond, split="test", tuple_id=f"{cond}_test_0000", tuple_labels=dict(labels),
                         meta={"target_service": "count", "wording_family": "email"})
        pipeline.run_condition_split(cond, "test", [item], active_service_options=opts)
        copy_rejections[cond] = pipeline.get_rejections(cond).get("lint_copy_4gram", 0)
    assert copy_rejections == {"K4": 0, "K254": 0}


# ---------------------------------------------------------------------------
# Item 6: P1-6 — enum / field-name leak lint (decided scope), wired into ingest_gen
# ---------------------------------------------------------------------------
def test_p3f_6_p1_6_enum_and_field_name_leak_lint():
    pass_texts = [
        "save energy where possible",
        "Normal urgency is fine, batch it if necessary.",
        "Please keep it on site only for privacy reasons.",
        "We need high quality analysis with standard turnaround.",
        "Ensure single instance execution in interactive mode.",
        "Retention and redundancy do not matter; locality is up to you.",
        "Which service type fits this?",
        "Eco mode, performance mode, realtime or replicated are all fine words.",
    ]
    for txt in pass_texts:
        ok, msg = check_enum_leak_lint(txt)
        assert ok is True, f"Unexpected failure on '{txt}': {msg}"

    fail_texts = [
        "Process this with site_only handling.",
        "Using remote_allowed setting.",
        "Please discard_after_use immediately.",
        "Mark it retain_allowed.",
        "Check the quality_floor carefully.",
        "Check the quality floor setting.",
        "Specify the latency_class here.",
        "Specify the Latency  Class here.",
        "Set service_type to detection.",
    ]
    for txt in fail_texts:
        ok, msg = check_enum_leak_lint(txt)
        assert ok is False, f"Expected failure on '{txt}'"
        assert "Enum/field leak detected" in msg

    target = {"target_service_id": "sawmill_timber_log_inspection", "target_service_name": "Sawmill Timber Log Inspection"}
    assert check_enum_leak_lint("Detect defects on the timber logs", **target)[0] is True
    assert check_enum_leak_lint("Run sawmill_timber_log_inspection now", **target)[0] is False
    assert check_enum_leak_lint("Please launch sawmill timber log inspection today", **target)[0] is False
    # Single-word service ids are plain English, never rejected as an id
    assert check_enum_leak_lint("Count the crates", target_service_id="count")[0] is True


def test_p3f_6_enum_leak_lint_through_ingest_gen(exchange_env):
    exchange, _, data_dir = exchange_env
    exchange.export_gen(conditions=["clean", "K254"], splits=["test"], gen_batch_size=20, n_test=10, n_dev=0)
    services = load_services(data_dir / "catalog")
    names = {s["id"]: s["name"] for s in services["services"] + services["novel_services"]}
    clean = sorted((it for it in exchange.items.values() if it.condition == "clean"), key=lambda it: it.tuple_id)
    rq4 = sorted((it for it in exchange.items.values() if it.condition == "K254"), key=lambda it: it.tuple_id)
    rq4_named = next(it for it in rq4 if "_" in it.meta["target_service"])

    texts = {
        clean[0].item_id: f"Order {clean[0].item_id}: keep it site_only please.",
        clean[1].item_id: f"Order {clean[1].item_id}: mind the quality floor here.",
        clean[2].item_id: f"Order {clean[2].item_id}: save energy where possible.",
        clean[3].item_id: f"Order {clean[3].item_id}: Normal urgency is fine.",
        rq4_named.item_id: f"Order {rq4_named.item_id}: start {names[rq4_named.meta['target_service']].upper()} now.",
    }
    _write_gen_done(exchange, text_for=lambda it: texts.get(it.item_id, _unique_text(it)))
    res = exchange.ingest_gen()

    assert res["rejections"]["lint_enum_leak"] == 3
    for it in (clean[0], clean[1], rq4_named):
        assert it.reject_reasons == ["lint_enum_leak"] and it.status == "pending_gen"
    assert clean[2].status == "done_gen" and clean[3].status == "done_gen"


# ---------------------------------------------------------------------------
# Item 7 (E): one reading-rules sentence for interpreters and verifier
# ---------------------------------------------------------------------------
def test_p3f_7_reading_rules_instruction_strings():
    from src.edgebench.contract import READING_RULES, SERVICE_PRECEDENCE_RULE

    rules = (
        "Count a requirement if it is stated directly, indirectly or through negation; if it is revised, use the "
        "final value. Ignore requirements for something else or explicitly not wanted. Never infer from the setting "
        "or fill in defaults."
    )
    assert READING_RULES == rules
    assert get_field_instruction("locality") == f"Extract locality from the requirements stated in the text. {rules}"
    assert get_field_instruction("urgency", request_index=1, bundle_size=3) == (
        f"Extract urgency from the requirements stated for request number 1 in the text. {rules}"
    )
    assert get_field_instruction("service_type", is_catalog=True) == (
        f"Extract service_type from the requirements stated in the text. {rules} {SERVICE_PRECEDENCE_RULE}"
    )
    req = DecisionsClient(name="Jev-1.13.0").build_request(
        Case(case_id="b", text="1. a\n2. b", bundle_size=2, truth=[{}, {}])
    )
    assert "for request number 1 in the text" in req["questions"]["r1__locality"]["instructions"]


@pytest.mark.parametrize("catalog", [None, {"svc_a": "service a", "unsupported": "unsupported service"}])
def test_p3f_7_verifier_instructions_equal_field_instruction_byte_for_byte(catalog):
    fields = FIELD_SETS[8]
    expected = [get_field_instruction(f, is_catalog=(f == "service_type" and catalog is not None)) for f in fields]

    context_md = build_verifier_context_markdown(fields, catalog)
    ctx_instr = [l[len("Instruction: "):] for l in context_md.splitlines() if l.startswith("Instruction: ")]
    assert ctx_instr == expected

    api_sys, _, _ = build_verifier_batch_prompt([("c1", "text")], fields, catalog)
    api_instr = [l[len("Instruction: "):] for l in api_sys.splitlines() if l.startswith("Instruction: ")]
    assert api_instr == expected

    for doc in (context_md, api_sys):
        assert "Respect negation" not in doc
        assert "Do not infer missing requirements" not in doc
        assert "Label each text; for each field choose one allowed option following the instruction." in doc


# ---------------------------------------------------------------------------
# Item 8: P1-5 — partial done files and stuck exported_* items
# ---------------------------------------------------------------------------
def test_p3f_8_partial_gen_done_file_raises_and_is_not_ingested(exchange_env):
    exchange, _, _ = exchange_env
    gf = exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=5, n_test=5, n_dev=0)[0]
    todo = _read_jsonl(gf)
    done_f = exchange.gen_done_dir / gf.name
    done_f.write_text("".join(
        json.dumps({"item_id": o["item_id"], "text": "Valid text", "generator": "g"}) + "\n" for o in todo[:4]
    ), encoding="utf-8")

    with pytest.raises(ValueError, match="do not match todo batch"):
        exchange.ingest_gen()
    assert done_f.name not in exchange.ingested_gen_files
    assert all(it.status == "exported_gen" for it in exchange.items.values())

    # A done file without its todo batch is rejected too
    (exchange.gen_done_dir / "gen_orphan.jsonl").write_text(done_f.read_text(), encoding="utf-8")
    done_f.unlink()
    with pytest.raises(ValueError, match="no matching todo batch"):
        exchange.ingest_gen()


def test_p3f_8_partial_ver_done_file_raises_and_is_not_ingested(exchange_env):
    exchange, _, _ = exchange_env
    exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=5, n_test=5, n_dev=0)
    _write_gen_done(exchange)
    exchange.ingest_gen()
    vf = next(f for f in exchange.export_ver(conditions=["clean"], splits=["test"]) if f.name.endswith(".jsonl"))
    todo = _read_jsonl(vf)
    done_f = exchange.ver_done_dir / vf.name
    done_f.write_text("".join(
        json.dumps({"item_id": o["item_id"], "labels": exchange.items[o["item_id"]].tuple_labels, "verifier": "v"}) + "\n"
        for o in todo[:4]
    ), encoding="utf-8")

    with pytest.raises(ValueError, match="do not match todo batch"):
        exchange.ingest_ver()
    assert done_f.name not in exchange.ingested_ver_files
    assert all(it.status == "exported_ver" for it in exchange.items.values())


def test_p3f_8_stuck_exported_items_are_requeued(exchange_env):
    exchange, _, _ = exchange_env
    gf = exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=5, n_test=5, n_dev=0)[0]
    # A batch recorded as ingested while one item stayed exported_gen (legacy state)
    exchange.ingested_gen_files.add(gf.name)
    stuck = next(iter(exchange.items.values()))
    assert stuck.status == "exported_gen"
    retry = exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=5, n_test=5, n_dev=0)
    assert stuck.item_id in {o["item_id"] for f in retry for o in _read_jsonl(f)}

    # Same for the ver stage
    for it in exchange.items.values():
        it.status, it.text = "done_gen", _unique_text(it)
    vf = next(f for f in exchange.export_ver(conditions=["clean"], splits=["test"]) if f.name.endswith(".jsonl"))
    exchange.ingested_ver_files.add(vf.name)
    assert stuck.status == "exported_ver"
    retry_ver = exchange.export_ver(conditions=["clean"], splits=["test"])
    assert stuck.item_id in {o["item_id"] for f in retry_ver if f.name.endswith(".jsonl") for o in _read_jsonl(f)}


def test_p3f_8_replaced_original_is_never_reexported(exchange_env):
    # A "rejected" original is terminal: its replacement carries the tuple; re-exporting both would
    # produce two accepted items for one case_id.
    exchange, _, _ = exchange_env
    exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=5, n_test=5, n_dev=0)
    victim = sorted(exchange.items.values(), key=lambda it: it.tuple_id)[0]
    for _ in range(3):
        _write_gen_done(exchange, text_for=lambda it: "Run the generic fallback." if it is victim else _unique_text(it))
        exchange.ingest_gen()
        exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=5, n_test=5, n_dev=0)
    assert victim.status == "rejected"
    replacement = next(it for it in exchange.items.values() if it.replaced_from == victim.item_id)
    active = {o["item_id"] for f in exchange.gen_todo_dir.glob("*.jsonl")
              if f.name not in exchange.ingested_gen_files for o in _read_jsonl(f)}
    assert replacement.item_id in active
    assert victim.item_id not in active


# ---------------------------------------------------------------------------
# Item 9: P1-9 — manifest provenance and yields
# ---------------------------------------------------------------------------
def test_p3f_9_yields_from_state_and_stats(exchange_env):
    exchange, _, data_dir = exchange_env
    exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=10, n_test=10, n_dev=0)
    _write_gen_done(exchange)
    exchange.ingest_gen()
    exchange.export_ver(conditions=["clean"], splits=["test"])
    victim = sorted(exchange.items.values(), key=lambda it: it.tuple_id)[0]
    _write_ver_done(exchange, labels_for=lambda it: {k: "bogus" for k in it.tuple_labels} if it is victim else dict(it.tuple_labels))
    exchange.ingest_ver()
    exchange.export_gen(conditions=["clean"], splits=["test"], n_test=10, n_dev=0)
    _write_gen_done(exchange)
    exchange.ingest_gen()
    exchange.export_ver(conditions=["clean"], splits=["test"])
    _write_ver_done(exchange)
    exchange.ingest_ver()

    exchange.assemble(n_test=10, n_dev=0)
    yields = json.loads((data_dir / "_yields.json").read_text(encoding="utf-8"))
    assert yields == exchange.compute_yields()
    assert yields["clean"] == {"target_n": 10, "first_pass_accepted": 9, "accepted": 10, "first_pass": 0.9, "final": 1.0}

    stats = generate_stats_markdown(data_dir, yields=yields)
    assert "| RQ2/clean | test | 10 |" in stats
    assert "| 90.0% | 100.0% |" in stats


def test_p3f_9_manifest_provenance(exchange_env):
    exchange, _, data_dir = exchange_env
    gen_files = exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=10, n_test=10, n_dev=0)
    prompt_sha = {o["item_id"]: hashlib.sha256(o["prompt"].encode("utf-8")).hexdigest()
                  for f in gen_files for o in _read_jsonl(f)}
    _write_gen_done(exchange, generator="gemini-3.8-flash-high@agy")
    exchange.ingest_gen()
    exchange.export_ver(conditions=["clean"], splits=["test"])
    _write_ver_done(exchange, verifier="claude-opus-5.5@subagent")
    exchange.ingest_ver()
    exchange.assemble(n_test=10, n_dev=0)

    clean_cases = [Case.from_dict(d) for d in _read_jsonl(data_dir / "RQ2" / "clean" / "test.jsonl")]
    from src.edgebench.contract import dump_cases_jsonl
    dump_cases_jsonl(derive_noise_cases(clean_cases), data_dir / "RQ2" / "noise" / "test.jsonl")
    dump_cases_jsonl(create_padded_dataset(clean_cases, target_length=512), data_dir / "RQ1a" / "pad_512" / "test.jsonl")
    dump_cases_jsonl(create_bundle_messages(clean_cases, k=2, n_messages=3), data_dir / "RQ1b" / "k2" / "test.jsonl")
    bare = Case(case_id="no_provenance", text="x", truth=[{}])
    dump_cases_jsonl([bare], data_dir / "RQ2" / "bare" / "test.jsonl")

    manifest = generate_manifest(data_dir, yields=exchange.compute_yields(), total_cost_usd=0.0, seed=20260924)

    assert manifest["seed"] == 20260924
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    assert manifest["git_head"] == head
    assert isinstance(manifest["tree_dirty"], bool)
    assert manifest["catalog_file_hashes"] == {
        f"catalog/{n}": compute_sha256(data_dir / "catalog" / n) for n in ("catalogs.json", "services.json")
    }
    assert manifest["generators"] == ["gemini-3.8-flash-high@agy"]
    assert manifest["verifiers"] == ["claude-opus-5.5@subagent"]
    assert manifest["models"]["generator"] == "gemini-3.8-flash-high@agy"

    items = manifest["items"]
    by_tuple = {it.tuple_id: it.item_id for it in exchange.items.values()}
    for c in clean_cases:
        assert items[c.case_id]["prompt_sha256"] == prompt_sha[by_tuple[c.case_id]]
        assert items[c.case_id]["generator"] == "gemini-3.8-flash-high@agy"
        noise_id = c.case_id.replace("clean", "noise")
        assert items[noise_id]["derivation"] == "noise"
        assert items[noise_id]["prompt_sha256"] == prompt_sha[by_tuple[c.case_id]]
        assert items[f"{c.case_id}_pad_512"]["verifier"] == "claude-opus-5.5@subagent"
    bundle = items["RQ1b_k2_test_0000"]
    assert bundle["derivation"] == "bundle_k2"
    assert bundle["generator"] == ["gemini-3.8-flash-high@agy"] * 2
    assert isinstance(bundle["prompt_sha256"], list) and len(bundle["prompt_sha256"]) == 2
    # No fallback to a default model name for an item without provenance
    assert items["no_provenance"]["generator"] is None and items["no_provenance"]["verifier"] is None
    assert "claude-sonnet-5" not in json.dumps(manifest) and "gpt-5.6-sol" not in json.dumps(manifest)


def _load_build_script():
    spec = importlib.util.spec_from_file_location("eb_build_corpus_p3f", REPO_ROOT / "scripts" / "eb_build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_p3f_9_file_transport_assemble_cost_zero_and_rewrites_from_state(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    exchange = CorpusExchange(exchange_dir="ex", data_dir="data", seed=20260924)
    exchange.export_gen(conditions=["clean"], splits=["test"], gen_batch_size=4, n_test=4, n_dev=0)
    _write_gen_done(exchange)
    exchange.ingest_gen()
    exchange.export_ver(conditions=["clean"], splits=["test"])
    _write_ver_done(exchange)
    exchange.ingest_ver()
    calls = tmp_path / "runs" / "_corpus" / "calls.jsonl"
    calls.parent.mkdir(parents=True)
    calls.write_text(json.dumps({"cost_usd": 5.0}) + "\n", encoding="utf-8")

    mod = _load_build_script()
    monkeypatch.setattr(sys, "argv", ["eb_build_corpus.py", "--data-dir", "data", "--exchange-dir", "ex",
                                      "assemble", "--n-test", "4", "--n-dev", "0"])
    mod.main()

    manifest = json.loads((tmp_path / "data" / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["total_cost_usd"] == 0.0
    assert manifest["seed"] == 20260924
    assert len(_read_jsonl(tmp_path / "data" / "RQ2" / "clean" / "test.jsonl")) == 4
    assert "| 100.0% | 100.0% |" in (tmp_path / "data" / "stats.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Item 10: P1-10 — shared padding prefixes
# ---------------------------------------------------------------------------
def test_p3f_10_p1_10_shared_padding_prefixes():
    enc = get_tokenizer()
    clean_cases = [
        Case(
            case_id=f"clean_test_{i:04d}",
            text=f"Clean edge request text number {i} needing immediate processing.",
            truth=[{"service_type": "ocr"}],
        )
        for i in range(20)
    ]

    padded_cases = create_padded_dataset(clean_cases, target_length=512, seed=20260924)
    assert len(padded_cases) == len(clean_cases)

    for src, pc in zip(sorted(clean_cases, key=lambda c: c.case_id), padded_cases):
        actual_tokens = len(enc.encode(pc.text))
        assert abs(actual_tokens - 512) / 512 <= 0.03
        # The stop list applies to the padding only; the request itself may contain cue words
        segments = pc.text.split(src.text)
        assert len(segments) == 2
        for seg in segments:
            assert_padding_clean(seg)

    all_tokens = [enc.encode(pc.text) for pc in padded_cases]
    max_prefix = 0
    for i in range(len(all_tokens)):
        for j in range(i + 1, len(all_tokens)):
            t1, t2 = all_tokens[i], all_tokens[j]
            cp = 0
            while cp < len(t1) and cp < len(t2) and t1[cp] == t2[cp]:
                cp += 1
            max_prefix = max(max_prefix, cp)
    assert max_prefix < 64, f"Max pairwise common prefix was {max_prefix} >= 64 tokens"


# ---------------------------------------------------------------------------
# Item 11: P1-11 — state corruption must fail closed
# ---------------------------------------------------------------------------
def test_p3f_11_p1_11_state_corruption_fails_closed(exchange_env):
    exchange, exchange_dir, data_dir = exchange_env
    exchange._state_file().write_text("{ corrupt json data ::: [", encoding="utf-8")

    with pytest.raises(ValueError, match="Corrupt exchange state"):
        CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=20260924)


# ---------------------------------------------------------------------------
# Item 12: P2-3 — noise/pad/bundle sort clean cases by case_id
# ---------------------------------------------------------------------------
def test_p3f_12_p2_3_clean_cases_sorted_before_derivation():
    c1 = Case(case_id="case_0001", text="Text 1", truth=[{"service_type": "ocr"}])
    c2 = Case(case_id="case_0002", text="Text 2", truth=[{"service_type": "detection"}])

    n_fwd = derive_noise_cases([c1, c2], seed=42)
    n_rev = derive_noise_cases([c2, c1], seed=42)
    assert [c.case_id for c in n_fwd] == [c.case_id for c in n_rev]
    assert [c.text for c in n_fwd] == [c.text for c in n_rev]

    p_fwd = create_padded_dataset([c1, c2], target_length=512, seed=42)
    p_rev = create_padded_dataset([c2, c1], target_length=512, seed=42)
    assert [c.case_id for c in p_fwd] == [c.case_id for c in p_rev]
    assert [c.text for c in p_fwd] == [c.text for c in p_rev]

    b_fwd = create_bundle_messages([c1, c2], k=2, n_messages=2, seed=42)
    b_rev = create_bundle_messages([c2, c1], k=2, n_messages=2, seed=42)
    assert [c.case_id for c in b_fwd] == [c.case_id for c in b_rev]
    assert [c.text for c in b_fwd] == [c.text for c in b_rev]


# ---------------------------------------------------------------------------
# Item 13: code-switching compliance (prompt, lint, and ingest_gen wiring)
# ---------------------------------------------------------------------------
def test_p3f_13_codeswitch_compliance_prompt_and_lint():
    t_item = TupleItem(
        condition="codeswitch",
        split="test",
        tuple_id="codeswitch_test_0001",
        tuple_labels={"service_type": "count"},
        meta={"language": "de", "scenario": "farm drone"},
    )
    prompt = build_single_item_generator_prompt(t_item, {})
    assert (
        "Mix English and de within the text: it must contain at least one full clause in English and at least one "
        "full clause in de. Do not write the whole text in one language. State each requirement once, in either "
        "language; never repeat a requirement as a translation."
    ) in prompt

    all_de = "Bitte führen Sie die Objekterkennung durch und speichern Sie das Ergebnis auf dem Server nicht."
    ok_de, msg_de = check_codeswitch_monolingual_lint(all_de, target_lang="de")
    assert ok_de is False
    assert "Insufficient code-switching" in msg_de

    mixed_de = "Please process this incoming data and bitte nicht auf dem Server speichern for this task."
    assert check_codeswitch_monolingual_lint(mixed_de, target_lang="de")[0] is True

    mixed_zh = "Please process this request with high urgency and 請檢測車輛 using edge detection."
    assert check_codeswitch_monolingual_lint(mixed_zh, target_lang="zh")[0] is True


CODESWITCH_MIXED = {
    "de": "Please count the pallets on this dock, bitte nicht auf dem Server speichern ({id}).",
    "fr": "Please count the pallets on this dock, et nous voulons les résultats avec la note ({id}).",
    "es": "Please count the pallets on this dock, y los resultados para el equipo con calma ({id}).",
    "zh": "Please count the pallets on this dock and 请尽快处理这个任务 ({id}).",
}


def test_p3f_13b_codeswitch_lint_through_ingest_gen(exchange_env):
    exchange, _, _ = exchange_env
    exchange.export_gen(conditions=["codeswitch", "clean"], splits=["test"], gen_batch_size=20, n_test=8, n_dev=0)
    cs = sorted((it for it in exchange.items.values() if it.condition == "codeswitch"), key=lambda it: it.tuple_id)
    victim = next(it for it in cs if it.meta["language"] == "de")
    all_german = "Bitte zählen Sie die Paletten auf dem Dock und das Ergebnis ist wichtig ({id})."
    clean_german = next(it for it in exchange.items.values() if it.condition == "clean")

    def text_for(it) -> str:
        if it is victim or it is clean_german:
            return all_german.format(id=it.item_id)
        if it.condition == "codeswitch":
            return CODESWITCH_MIXED[it.meta["language"]].format(id=it.item_id)
        return _unique_text(it)

    _write_gen_done(exchange, text_for=text_for)
    res = exchange.ingest_gen()

    assert res["rejections"]["lint_codeswitch_monolingual"] == 1
    assert victim.reject_reasons == ["lint_codeswitch_monolingual"]
    assert {it.meta["language"] for it in cs if it.status == "done_gen"} == {"zh", "es", "fr", "de"}
    assert clean_german.status == "done_gen"  # the lint applies to the codeswitch condition only


# Genuinely code-switched texts the short stopword lists (threshold 3) used to reject.
CODESWITCH_REAL_POSITIVES = [
    ("es", "Hi Marta, attached are the sight-glass photos from fermentation tanks 2 through 6. ¿Podrías marcar con un recuadro cada acumulación de espuma o sedimento que aparezca, indicando dónde está en la imagen? Thanks, Jonas"),
    ("fr", "Reefer van 22, rear compartment: the temperature logger label photo needs its printed text transcribed, including batch codes and the timestamp. Il faut une reconnaissance très fiable, sans aucune erreur de caractère, car ces valeurs servent à la traçabilité."),
    ("es", "FlareWatch alert: flare stack imaging on Platform Sierra shows several active flames. Cuenta cuántas antorchas encendidas hay y devuelve solo la cifra, sin otro texto. Offloading to the onshore cloud is permitted."),
    ("de", "AGV-Hub: Fahrzeug 12 hat ein Foto des beschädigten Regaletiketts hochgeladen. Please extract the printed location code and SKU from the image as text. Keine Eile, das kann ganz regulär in der Warteschlange mitlaufen."),
    ("fr", "Salle d'opération 4: the air quality sensor's LCD was photographed during the audit, please transcribe the particle and humidity values shown. Les images ne doivent pas quitter l'hôpital. Basic recognition accuracy will do."),
    ("de", "Wachturm Nord meldet mehrere Hotspots im Wärmebild. Count the distinct heat sources in the frame and reply with the figure alone. Die Bilddaten bleiben auf dem Turm-Rechner, and there's no rush, the regular queue is fine."),
    ("es", "SkiPass Gate: a guest's pass couldn't be validated at the Cumbre chairlift. Please extract the printed pass number and expiry date from the attached photo. Luego envía el texto a recepción para revisarlo."),
    ("es", "oye, te paso los escaneos del tramo de vía de ayer. can you box every crack, missing clip or loose bolt and mark where it is? con precisión básica alcanza, nada fancy."),
    ("fr", "Onduleur 3B, ferme solaire Est: the thermal photos of the inverter cabinet need each hot component boxed with its position in the frame. Le technicien a signalé une surchauffe hier soir."),
    ("de", "moin, I've got photos of the engine room log sheets, can you turn the handwritten and printed entries into text? Kannst du ruhig über die Cloud jagen, muss nicht an Bord bleiben. Einfache Genauigkeit reicht völlig."),
    ("es", "HarvestTrack: la cosechadora 3 registró una nueva pila de troncos. Count the logs in the stack and reply with the number only. Cloud processing is fine for this, pero el conteo debe ser lo más exacto posible."),
    # Terse English clause or short target clause: rejected by the old ">= 2 on each side" rule
    ("de", "hey, can you read what's printed on the temp logger label in this pic? Ich brauch's echt dringend."),
    ("zh", "AGV route blocked near dock doors. 请数一下通道上有几个纸箱，只报数字。 Images stay inside the warehouse network."),
    ("de", "AGV status: shelf scan complete. Bitte die Kartons im Regalfach zählen und nur die Anzahl melden, die Verarbeitung darf extern erfolgen. Everyday accuracy is fine."),
    ("es", "Checkpoint alert: vehicle cargo X-ray ready. Hay que contar los bultos visibles y devolver solo el total, sin margen de error. Scans never leave the border post."),
    ("de", "Regalscanner Gang 5 meldet: neues Bild vom Kühlregal erfasst. How many yogurt cups are on the second shelf? Reply with a number only; no need for anything beyond everyday accuracy."),
    ("es", "Engine room telemetry, MV Pacífico: a new gauge panel image is available. ¿Cuántos indicadores están encendidos? Solo el número, y con una lectura ordinaria es suficiente."),
]

CODESWITCH_MONOLINGUAL_NEGATIVES = [
    ("de", "Guten Tag Logistik-Team, bitte zählen Sie die gelagerten Paletten im aktuellen Gabelstapler-Sichtfeld und geben Sie lediglich den reinen Zahlenwert zurück. Bitte stellen Sie sicher, dass alle Berechnungen vollständig auf dem Fahrzeugrechner im Lager verbleiben."),
    ("fr", "Please count the pallets on the loading dock and report only the number. The images must stay on the local server, and there is no rush for this one."),
    ("es", "Hola equipo, por favor cuenten los palés de la zona de carga y devuelvan solo el número. Las imágenes no deben salir del almacén y no hay prisa con esto."),
    ("zh", "Please count the pallets on the loading dock and report only the number, the images must stay on the local server."),
    ("zh", "请统计装卸区的托盘数量，只返回数字。图像必须保留在本地服务器上，不要上传到云端。"),
    # All German apart from an acronym and a product code: zero English function words
    ("de", "AGV 7 meldet: die Palette mit Artikel KX-4410 steht im Gang, bitte die Kartons zählen und nur die Anzahl melden."),
    # One function word per side: neither side reaches 2, so the relaxed rule still rejects it
    ("de", "Bitte scan label, please."),
]


@pytest.mark.parametrize("lang,text", CODESWITCH_REAL_POSITIVES)
def test_codeswitch_lint_accepts_real_mixed_texts(lang, text):
    ok, msg = check_codeswitch_monolingual_lint(text, target_lang=lang)
    assert ok is True, msg


@pytest.mark.parametrize("lang,text", CODESWITCH_MONOLINGUAL_NEGATIVES)
def test_codeswitch_lint_rejects_monolingual_texts(lang, text):
    ok, msg = check_codeswitch_monolingual_lint(text, target_lang=lang)
    assert ok is False
    assert "Insufficient code-switching" in msg


def test_codeswitch_real_texts_through_ingest_gen(exchange_env):
    exchange, _, _ = exchange_env
    exchange.export_gen(conditions=["codeswitch"], splits=["test"], gen_batch_size=40, n_test=40, n_dev=0)
    pool = {lang: sorted((it for it in exchange.items.values() if it.meta["language"] == lang), key=lambda it: it.tuple_id)
            for lang in ("zh", "es", "fr", "de")}
    assigned: dict[str, tuple[str, bool]] = {}
    for texts, expect_ok in ((CODESWITCH_REAL_POSITIVES, True), (CODESWITCH_MONOLINGUAL_NEGATIVES, False)):
        for lang, text in texts:
            assigned[pool[lang].pop(0).item_id] = (text, expect_ok)

    def text_for(it) -> str:
        if it.item_id in assigned:
            return assigned[it.item_id][0]
        # Filler that is mixed for every target language, so the rejection count isolates the negatives
        return f"Handle order {it.item_id} for the team today, bitte y et 请尽快处理这个任务 le der el."

    _write_gen_done(exchange, text_for=text_for)
    res = exchange.ingest_gen()

    assert res["rejections"]["lint_codeswitch_monolingual"] == len(CODESWITCH_MONOLINGUAL_NEGATIVES)
    for iid, (_, expect_ok) in assigned.items():
        it = exchange.items[iid]
        if expect_ok:
            assert it.status == "done_gen", (it.meta["language"], it.reject_reasons)
        else:
            assert it.reject_reasons == ["lint_codeswitch_monolingual"]


# ---------------------------------------------------------------------------
# P3g: distractor definition in every medium/high instruction
# ---------------------------------------------------------------------------
DISTRACTOR_TEXT = (
    "plus one distractor: a requirement value or service that the text explicitly marks as NOT wanted for this job, "
    "or that belongs to a different team, device or job (e.g. another crew's request, a setting used last month). "
    "The distractor must concern a field listed under \"Specified requirements\", must not change the requested value "
    "of that field, and must never mention a field listed under \"Fields to leave unmentioned\". Do not use ambient "
    "sensor readings or weather as the distractor."
)


@pytest.mark.parametrize("f", [4, 6, 8])
def test_p3g_distractor_definition_in_medium_and_high_only(f):
    for level in ("low", "medium", "high"):
        cond = f"F{f}_{level}"
        tuples = sample_tuples_for_condition(cond, "test", 30, base_seed=20260924)
        _, user_p, _ = build_generator_batch_prompt(tuples, {})
        batch_insts = [sp["condition_instructions"] for sp in json.loads(user_p.split("specifications:\n\n")[1])]
        single_prompts = [build_single_item_generator_prompt(t, {}) for t in tuples]
        for doc in single_prompts + batch_insts:
            if level == "low":
                assert "distractor" not in doc
            else:
                assert DISTRACTOR_TEXT in doc
