"""P3i: per-condition freeze so experiments can start on a condition while generation continues."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

import pytest

from src.edgebench.contract import Case, dump_cases_jsonl
from src.edgebench.corpus.assemble import compute_sha256
from src.edgebench.corpus.bundle import BUNDLE_SIZES
from src.edgebench.corpus.catalog import save_catalogs
from src.edgebench.corpus.exchange import CorpusExchange
from src.edgebench.corpus.pad import TARGET_LENGTHS

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED = 20260924
N_TEST, N_DEV = 8, 2  # 8 clean test cases: bundle k=8 needs at least k sources


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load_build_script():
    spec = importlib.util.spec_from_file_location("eb_build_corpus_p3i", REPO_ROOT / "scripts" / "eb_build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cli(monkeypatch, data_dir: Path, exchange_dir: Path, *argv: str) -> None:
    mod = _load_build_script()
    monkeypatch.setattr(sys, "argv", ["eb_build_corpus.py", "--data-dir", str(data_dir),
                                      "--exchange-dir", str(exchange_dir), *argv])
    mod.main()


def _generate(exchange: CorpusExchange, items) -> None:
    # Bypass the gen stage: a unique text per item, so the diversity lint never fires.
    for it in items:
        it.status, it.text, it.generator = "done_gen", f"Handle order {it.item_id} for the team today.", "fake-gen@agy"
    exchange._save_state()


def _verify_all_exported(exchange: CorpusExchange) -> None:
    for vf in sorted(exchange.ver_todo_dir.glob("*.jsonl")):
        if vf.name in exchange.ingested_ver_files or (exchange.ver_done_dir / vf.name).exists():
            continue
        with open(exchange.ver_done_dir / vf.name, "w", encoding="utf-8") as f:
            for o in _read_jsonl(vf):
                it = exchange.items[o["item_id"]]
                f.write(json.dumps({"item_id": it.item_id, "labels": dict(it.tuple_labels), "verifier": "fake-ver@opus"}) + "\n")


def _items(exchange: CorpusExchange, cond: str, split: str) -> list:
    return sorted((it for it in exchange.items.values() if it.condition == cond and it.split == split),
                  key=lambda it: it.tuple_id)


def _accept(exchange: CorpusExchange, items) -> None:
    _generate(exchange, items)
    exchange.export_ver()
    _verify_all_exported(exchange)
    exchange.ingest_ver()
    assert all(it.status == "accepted" for it in items)


@pytest.fixture
def env(tmp_path: Path):
    """clean test complete (8 accepted); clean dev and negation test still in progress."""
    exchange_dir, data_dir = tmp_path / "exchange", tmp_path / "data"
    save_catalogs(data_dir / "catalog", seed=SEED)
    exchange = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    exchange.init_targets(conditions=["clean", "negation"], splits=["test", "dev"], n_test=N_TEST, n_dev=N_DEV)
    _accept(exchange, _items(exchange, "clean", "test") + _items(exchange, "clean", "dev")[:1])
    return exchange, exchange_dir, data_dir


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None) for p in sorted(root.rglob("*"))}


# ---------------------------------------------------------------------------
# Item 1: split filter
# ---------------------------------------------------------------------------
def test_p3i_1_assemble_split_filter_writes_only_selected_groups(env):
    exchange, _, data_dir = env
    sentinel = b'{"sentinel": true}\n'
    for rel in ("RQ2/clean/dev.jsonl", "RQ2/negation/test.jsonl", "_accepted/clean_dev.jsonl"):
        (data_dir / rel).parent.mkdir(parents=True, exist_ok=True)
        (data_dir / rel).write_bytes(sentinel)
    old_yields = {"negation": {"target_n": 10, "sentinel": 1}, "K4": {"target_n": 3, "sentinel": 2}}
    (data_dir / "_yields.json").write_text(json.dumps(old_yields), encoding="utf-8")

    # clean dev (1/2 accepted) and negation (0 accepted) are incomplete: only clean/test is selected and asserted
    res = exchange.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)
    assert sorted(str(p.relative_to(data_dir)) for p in res["files"]) == ["RQ2/clean/test.jsonl", "_accepted/clean_test.jsonl"]
    assert [c["case_id"] for c in _read_jsonl(data_dir / "RQ2" / "clean" / "test.jsonl")] == \
        [it.tuple_id for it in _items(exchange, "clean", "test")]
    for rel in ("RQ2/clean/dev.jsonl", "RQ2/negation/test.jsonl", "_accepted/clean_dev.jsonl"):
        assert (data_dir / rel).read_bytes() == sentinel, rel

    # _yields.json: the selected condition is updated, unselected entries are kept
    yields = json.loads((data_dir / "_yields.json").read_text(encoding="utf-8"))
    assert yields["negation"] == old_yields["negation"] and yields["K4"] == old_yields["K4"]
    assert yields["clean"] == exchange.compute_yields()["clean"]

    # A selected group is asserted even when state has nothing for it
    with pytest.raises(ValueError, match="K4/test: 0 accepted items, expected 8"):
        exchange.assemble(conditions=["K4"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)
    # The unfiltered call keeps asserting every group in state
    with pytest.raises(ValueError, match="accepted items, expected"):
        exchange.assemble(n_test=N_TEST, n_dev=N_DEV)


def test_p3i_1_assemble_cli_conditions_and_splits(env, monkeypatch):
    exchange, exchange_dir, data_dir = env
    _cli(monkeypatch, data_dir, exchange_dir, "assemble", "--conditions", "clean", "--splits", "test",
         "--n-test", str(N_TEST), "--n-dev", str(N_DEV))
    assert (data_dir / "RQ2" / "clean" / "test.jsonl").exists()
    assert not (data_dir / "RQ2" / "clean" / "dev.jsonl").exists()
    assert not (data_dir / "RQ2" / "negation").exists()


# ---------------------------------------------------------------------------
# Item 2: freeze record; a frozen group must come out byte-identical, else nothing is written
# ---------------------------------------------------------------------------
def test_p3i_2_selective_assemble_records_freeze_and_blocks_changes(env):
    exchange, exchange_dir, data_dir = env
    clean_test = data_dir / "RQ2" / "clean" / "test.jsonl"
    exchange.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)

    frozen = json.loads((data_dir / "_frozen.json").read_text(encoding="utf-8"))
    assert list(frozen) == ["RQ2/clean/test"]
    rec = frozen["RQ2/clean/test"]
    head = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True, cwd=REPO_ROOT).stdout.strip()
    assert rec["sha256"] == compute_sha256(clean_test)
    assert rec["n"] == N_TEST and rec["git_head"] == head and rec["frozen_at"]

    # Byte-identical re-assemble passes and keeps the original record
    exchange.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)
    assert json.loads((data_dir / "_frozen.json").read_text(encoding="utf-8")) == frozen

    # State changed behind the guards: any assemble writing the frozen group raises and writes nothing
    (data_dir / "_yields.json").write_text('{"sentinel": 1}', encoding="utf-8")
    before = _snapshot(data_dir)
    _items(exchange, "clean", "test")[0].text = "A different accepted text."
    with pytest.raises(ValueError, match=r"frozen group\(s\) would change: \['RQ2/clean/test'\]"):
        exchange.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)
    _accept(exchange, _items(exchange, "clean", "dev")[1:])  # clean dev complete: an unfiltered call gets past n
    with pytest.raises(ValueError, match="would change"):
        exchange.assemble(conditions=["clean"], n_test=N_TEST, n_dev=N_DEV)
    assert _snapshot(data_dir) == before


def test_p3i_2_unfiltered_assemble_does_not_freeze(tmp_path: Path):
    data_dir = tmp_path / "data"
    save_catalogs(data_dir / "catalog", seed=SEED)
    exchange = CorpusExchange(exchange_dir=tmp_path / "ex", data_dir=data_dir, seed=SEED)
    exchange.init_targets(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=0)
    _accept(exchange, _items(exchange, "clean", "test"))
    exchange.assemble(n_test=N_TEST, n_dev=0)
    assert (data_dir / "RQ2" / "clean" / "test.jsonl").exists()
    assert not (data_dir / "_frozen.json").exists()


# ---------------------------------------------------------------------------
# Item 3: frozen groups are immutable in the exchange
# ---------------------------------------------------------------------------
def test_p3i_3_frozen_group_refuses_requeue_ingest_and_export(tmp_path: Path):
    exchange_dir, data_dir = tmp_path / "ex", tmp_path / "data"
    save_catalogs(data_dir / "catalog", seed=SEED)
    ex = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    ex.init_targets(conditions=["clean"], splits=["test", "dev"], n_test=N_TEST + 4, n_dev=N_DEV)
    test_items, dev_items = _items(ex, "clean", "test"), _items(ex, "clean", "dev")
    done, a, b, c, d = test_items[:N_TEST], *test_items[N_TEST:]
    _accept(ex, done)
    accepted_batch = done[0].ver_batch_id

    # a: exported for verification with an uningested done file; b: exported for generation with an uningested
    # done file; c: generated, never exported for verification; d: pending generation
    _generate(ex, [a])
    ex.export_ver(conditions=["clean"], splits=["test"])
    _verify_all_exported(ex)
    b.status, b.gen_batch_id = "exported_gen", "gen_clean_test_001"
    (ex.gen_todo_dir / "gen_clean_test_001.jsonl").write_text(json.dumps({"item_id": b.item_id}) + "\n", encoding="utf-8")
    (ex.gen_done_dir / "gen_clean_test_001.jsonl").write_text(
        json.dumps({"item_id": b.item_id, "text": "Please sort the invoices by date.", "generator": "g"}) + "\n", encoding="utf-8")
    _generate(ex, [c])

    ex.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)  # freezes RQ2/clean/test
    state = ex._state_file().read_bytes()
    exchange_before = _snapshot(exchange_dir)

    with pytest.raises(ValueError, match=r"ingest_ver: refusing to change 1 item\(s\) of frozen group\(s\) \['RQ2/clean/test'\]"):
        ex.ingest_ver()
    with pytest.raises(ValueError, match=r"ingest_gen: refusing to change .*RQ2/clean/test"):
        ex.ingest_gen()
    with pytest.raises(ValueError, match=r"requeue_ver: refusing to change .*RQ2/clean/test"):
        ex.requeue_ver([accepted_batch], reason="x")
    assert ex._state_file().read_bytes() == state and _snapshot(exchange_dir) == exchange_before
    reloaded = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    assert (reloaded.items[a.item_id].status, reloaded.items[b.item_id].status) == ("exported_ver", "exported_gen")
    assert all(reloaded.items[x.item_id].status == "accepted" for x in done)
    assert accepted_batch not in reloaded.superseded_ver_batches

    # Export skips the frozen group (c, d) and still exports the unfrozen clean dev items
    _generate(ex, dev_items[:1])
    ver_files = ex.export_ver()
    assert {o["item_id"] for f in ver_files if f.suffix == ".jsonl" for o in _read_jsonl(f)} == {dev_items[0].item_id}
    gen_files = ex.export_gen(conditions=["clean"], n_test=N_TEST + 4, n_dev=N_DEV)
    assert {o["item_id"] for f in gen_files for o in _read_jsonl(f)} == {dev_items[1].item_id}
    assert (c.status, d.status) == ("done_gen", "pending_gen")


# ---------------------------------------------------------------------------
# Item 4: noise / pad / bundle per split, from the frozen clean file only; outputs frozen
# ---------------------------------------------------------------------------
def test_p3i_4_derived_conditions_need_frozen_clean_and_are_frozen(env, monkeypatch):
    exchange, exchange_dir, data_dir = env
    for cmd in ("noise", "pad", "bundle"):
        with pytest.raises(ValueError, match="RQ2/clean/test is not frozen"):
            _cli(monkeypatch, data_dir, exchange_dir, cmd, "--splits", "test")
    exchange.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)

    for cmd in ("noise", "pad", "bundle"):
        _cli(monkeypatch, data_dir, exchange_dir, cmd, "--splits", "test")
    expected = {"RQ2/noise/test": N_TEST, "RQ1a/base/test": N_TEST,
                **{f"RQ1a/pad_{T}/test": N_TEST for T in TARGET_LENGTHS},
                **{f"RQ1b/k{k}/test": 300 for k in BUNDLE_SIZES}}
    frozen = json.loads((data_dir / "_frozen.json").read_text(encoding="utf-8"))
    assert set(frozen) == {"RQ2/clean/test", *expected}
    for key, n in expected.items():
        assert frozen[key]["n"] == n and frozen[key]["sha256"] == compute_sha256(data_dir / f"{key}.jsonl"), key
    assert not list(data_dir.glob("*/*/dev.jsonl"))

    # Default splits include dev, whose clean file is not frozen: refuse, nothing written
    before = _snapshot(data_dir)
    for cmd in ("noise", "pad", "bundle"):
        with pytest.raises(ValueError, match="RQ2/clean/dev is not frozen"):
            _cli(monkeypatch, data_dir, exchange_dir, cmd)
    # A frozen derived group must come out byte-identical (another seed changes the noise)
    _cli(monkeypatch, data_dir, exchange_dir, "noise", "--splits", "test")
    with pytest.raises(ValueError, match=r"would change: \['RQ2/noise/test'\]"):
        _cli(monkeypatch, data_dir, exchange_dir, "--seed", "7", "noise", "--splits", "test")
    # The clean file on disk must match its frozen record
    clean_test = data_dir / "RQ2" / "clean" / "test.jsonl"
    clean_test.write_bytes(clean_test.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="does not match its frozen record"):
        _cli(monkeypatch, data_dir, exchange_dir, "bundle", "--splits", "test")
    clean_test.write_bytes(before["RQ2/clean/test.jsonl"])
    assert _snapshot(data_dir) == before


# ---------------------------------------------------------------------------
# Item 5: a filtered assemble writes timing subsets only for the test files it wrote; manifest/stats stay global
# ---------------------------------------------------------------------------
def test_p3i_5_filtered_assemble_timing_subset_and_partial_manifest(env, monkeypatch):
    _, exchange_dir, data_dir = env
    other = data_dir / "RQ2" / "negation" / "test.jsonl"
    other.parent.mkdir(parents=True)
    dump_cases_jsonl([Case(case_id="RQ2_negation_test_0000", text="x", truth=[{"urgency": "urgent"}])], other)
    _cli(monkeypatch, data_dir, exchange_dir, "assemble", "--conditions", "clean", "--splits", "test",
         "--n-test", str(N_TEST), "--n-dev", str(N_DEV))

    assert sorted(p.parent.name for p in data_dir.rglob("timing_subset.txt")) == ["clean"]
    subset = (data_dir / "RQ2" / "clean" / "timing_subset.txt").read_text(encoding="utf-8").split()
    assert len(subset) == N_TEST
    manifest = json.loads((data_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "RQ2/clean/test.jsonl" in manifest["files"] and "_frozen.json" in manifest["files"]
    assert "| RQ2/clean | test | 8 |" in (data_dir / "stats.md").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Item 6: freeze-status (read-only)
# ---------------------------------------------------------------------------
def test_p3i_6_freeze_status_cli_is_read_only(env, monkeypatch, capsys):
    exchange, exchange_dir, data_dir = env
    exchange.assemble(conditions=["clean"], splits=["test"], n_test=N_TEST, n_dev=N_DEV)
    _cli(monkeypatch, data_dir, exchange_dir, "noise", "--splits", "test")
    capsys.readouterr()
    sha = json.loads((data_dir / "_frozen.json").read_text(encoding="utf-8"))["RQ2/clean/test"]["sha256"]

    before = _snapshot(data_dir.parent)
    _cli(monkeypatch, data_dir, exchange_dir, "freeze-status")
    out = capsys.readouterr().out
    rows = {cells[0]: cells[1:] for line in out.splitlines()
            if (cells := [c.strip() for c in line.strip("|").split("|")]) and "/" in cells[0]}
    assert rows["RQ2/clean/test"] == ["8/8", f"yes {sha[:12]} n=8"]
    assert rows["RQ2/clean/dev"] == ["1/2", "no"]
    assert rows["RQ2/negation/test"] == ["0/8", "no"]
    assert rows["RQ4/K4/test"] == ["0/0", "no"]
    assert rows["RQ2/noise/test"][0] == "derived" and rows["RQ2/noise/test"][1].startswith("yes ")

    # Pointing at an exchange dir that does not exist creates nothing
    _cli(monkeypatch, data_dir, data_dir.parent / "no_exchange", "freeze-status")
    assert _snapshot(data_dir.parent) == before
