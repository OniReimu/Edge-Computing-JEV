"""P3h: tuple-group isolation for blind verification and re-queue of anchored ver batches."""
from __future__ import annotations

from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from src.edgebench.corpus.catalog import save_catalogs
from src.edgebench.corpus.exchange import CorpusExchange, tuple_group_key

REPO_ROOT = Path(__file__).resolve().parent.parent

RQ2 = ["clean", "colloquial", "negation", "codeswitch", "defaultbait", "revised", "keyvalue"]
RQ3 = ["F4_low", "F4_medium", "F4_high", "F8_low", "F8_medium", "F8_high"]


@pytest.fixture
def exchange_env(tmp_path: Path):
    exchange_dir = tmp_path / "exchange"
    data_dir = tmp_path / "data"
    save_catalogs(data_dir / "catalog", seed=20260924)
    exchange = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=20260924)
    return exchange, exchange_dir, data_dir


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _mark_generated(exchange: CorpusExchange) -> None:
    # Bypass the gen stage: every item gets a unique text (diversity lint never fires) and a generator.
    for it in exchange.items.values():
        it.status, it.text, it.generator = "done_gen", f"Handle order {it.item_id} for the team today.", "fake-gen@agy"
    exchange._save_state()


def _active_ver_batches(exchange: CorpusExchange) -> dict[str, list[str]]:
    return {
        f.stem: [o["item_id"] for o in _read_jsonl(f)]
        for f in sorted(exchange.ver_todo_dir.glob("*.jsonl"))
        if f.name not in exchange.ingested_ver_files
    }


def _write_ver_done(exchange: CorpusExchange, batch_ids: list[str]) -> None:
    for bid in batch_ids:
        with open(exchange.ver_done_dir / f"{bid}.jsonl", "w", encoding="utf-8") as f:
            for o in _read_jsonl(exchange.ver_todo_dir / f"{bid}.jsonl"):
                it = exchange.items[o["item_id"]]
                f.write(json.dumps({"item_id": it.item_id, "labels": dict(it.tuple_labels), "verifier": "fake-ver@opus"}) + "\n")


def _context_key(it) -> tuple[int, str]:
    from src.edgebench.corpus.tuples import is_rq4_condition
    return (len(it.tuple_labels), it.condition if is_rq4_condition(it.condition) else "standard")


def _assert_isolated(exchange: CorpusExchange, batches: dict[str, list[str]], batch_size: int) -> None:
    for bid, ids in batches.items():
        items = [exchange.items[i] for i in ids]
        assert 0 < len(items) <= batch_size, bid
        keys = [tuple_group_key(it) for it in items]
        dup = [k for k, c in Counter(keys).items() if c > 1]
        assert not dup, f"{bid} holds parallel texts of one tuple group: {dup}"
        assert len({_context_key(it) for it in items}) == 1, f"{bid} mixes verification contexts"
        assert all(it.ver_batch_id == bid and it.status == "exported_ver" for it in items)


def test_p3h_tuple_group_key_definition(exchange_env):
    exchange, _, _ = exchange_env
    exchange.init_targets(conditions=RQ2 + ["F4_low", "F4_high", "F6_low", "K15", "K64"], splits=["test", "dev"], n_test=4, n_dev=2)
    by = {(it.condition, it.split, it.tuple_id.rsplit("_", 1)[1]): it for it in exchange.items.values()}

    # RQ2: all seven conditions at one (split, index) share a key; split and index separate keys
    assert len({tuple_group_key(by[(c, "test", "0003")]) for c in RQ2}) == 1
    assert tuple_group_key(by[("clean", "test", "0003")]) == ("RQ2", "test", 3)
    assert tuple_group_key(by[("clean", "test", "0003")]) != tuple_group_key(by[("clean", "dev", "0001")])
    assert tuple_group_key(by[("clean", "test", "0003")]) != tuple_group_key(by[("clean", "test", "0002")])
    # RQ3: levels at one F share a key; different F do not
    assert tuple_group_key(by[("F4_low", "test", "0003")]) == tuple_group_key(by[("F4_high", "test", "0003")]) == ("RQ3", "F4", "test", 3)
    assert tuple_group_key(by[("F4_low", "test", "0003")]) != tuple_group_key(by[("F6_low", "test", "0003")])
    # RQ4: every item is its own group
    assert tuple_group_key(by[("K15", "test", "0003")]) != tuple_group_key(by[("K64", "test", "0003")])
    assert len({tuple_group_key(it) for it in exchange.items.values() if it.condition in ("K15", "K64")}) == 12


def test_p3h_export_ver_batches_never_hold_two_items_of_one_tuple_group(exchange_env):
    exchange, _, _ = exchange_env
    exchange.init_targets(conditions=RQ2 + RQ3 + ["K15"], splits=["test", "dev"], n_test=12, n_dev=4)
    _mark_generated(exchange)
    pending = set(exchange.items)

    files = exchange.export_ver(ver_batch_size=20)
    batches = _active_ver_batches(exchange)
    assert {f.stem for f in files if f.name.endswith(".jsonl")} == set(batches)
    assert all((exchange.ver_todo_dir / f"{bid}.context.md").exists() for bid in batches)
    _assert_isolated(exchange, batches, batch_size=20)

    # The union covers every pending item exactly once
    exported = [i for ids in batches.values() for i in ids]
    assert Counter(exported) == Counter(pending)

    # Idempotent: nothing is left to export
    assert exchange.export_ver(ver_batch_size=20) == []


def test_p3h_export_ver_is_deterministic_under_the_corpus_seed(tmp_path: Path):
    layouts = []
    for run in ("a", "b"):
        data_dir = tmp_path / run / "data"
        save_catalogs(data_dir / "catalog", seed=20260924)
        ex = CorpusExchange(exchange_dir=tmp_path / run / "ex", data_dir=data_dir, seed=20260924)
        ex.init_targets(conditions=RQ2, splits=["test"], n_test=6, n_dev=0)
        _mark_generated(ex)
        ex.export_ver(ver_batch_size=7)
        layouts.append(_active_ver_batches(ex))
    assert layouts[0] == layouts[1]


def test_p3h_requeue_accepted_batch_archives_files_and_reexports_isolated(exchange_env):
    exchange, exchange_dir, _ = exchange_env
    exchange.init_targets(conditions=RQ2 + ["F4_low", "F4_medium", "F4_high"], splits=["test"], n_test=6, n_dev=0)
    _mark_generated(exchange)
    exchange.export_ver(ver_batch_size=8)
    first = _active_ver_batches(exchange)
    _write_ver_done(exchange, list(first))
    res = exchange.ingest_ver()
    assert res["items_accepted"] == len(exchange.items)

    victim_bid = sorted(first)[0]
    victims = set(first[victim_bid])
    before = {i: (exchange.items[i].text, exchange.items[i].generator, exchange.items[i].attempt) for i in victims}

    out = exchange.requeue_ver([victim_bid], reason="anchored: parallel texts in one batch")
    assert set(out["requeued"]) == victims and out["skipped"] == []

    # Items back to done_gen; text, generator, attempt unchanged; verifier labels cleared; requeue recorded
    for i in victims:
        it = exchange.items[i]
        assert it.status == "done_gen"
        assert (it.text, it.generator, it.attempt) == before[i]
        assert it.verifier_labels is None and it.verifier is None and it.ver_batch_id is None
        assert it.requeues[-1]["requeued_from"] == victim_bid
        assert it.requeues[-1]["reason"] == "anchored: parallel texts in one batch"
    others = set(exchange.items) - victims
    assert all(exchange.items[i].status == "accepted" for i in others)

    # Files archived under ver/_superseded/<timestamp>/, never deleted
    for p in (exchange.ver_todo_dir / f"{victim_bid}.jsonl", exchange.ver_todo_dir / f"{victim_bid}.context.md",
              exchange.ver_done_dir / f"{victim_bid}.jsonl"):
        assert not p.exists()
    archive = Path(out["archive_dir"])
    assert archive.parent == exchange_dir / "ver" / "_superseded"
    assert (archive / "todo" / f"{victim_bid}.jsonl").exists()
    assert (archive / "todo" / f"{victim_bid}.context.md").exists()
    assert (archive / "done" / f"{victim_bid}.jsonl").exists()

    # State survives a reload
    reloaded = CorpusExchange(exchange_dir=exchange_dir, data_dir=exchange.data_dir, seed=20260924)
    assert victim_bid in reloaded.superseded_ver_batches
    assert all(reloaded.items[i].status == "done_gen" and reloaded.items[i].requeues for i in victims)

    # Re-export: only the requeued items, in new isolated batches that never reuse the superseded id
    files = exchange.export_ver(ver_batch_size=8)
    second = {f.stem: [o["item_id"] for o in _read_jsonl(f)] for f in files if f.name.endswith(".jsonl")}
    assert victim_bid not in second
    assert Counter(i for ids in second.values() for i in ids) == Counter(victims)
    _assert_isolated(exchange, second, batch_size=8)

    # A late done file for the superseded batch (a verifier still holding it) is ignored, not ingested
    (exchange.ver_done_dir / f"{victim_bid}.jsonl").write_text(
        (archive / "done" / f"{victim_bid}.jsonl").read_text(encoding="utf-8"), encoding="utf-8")

    _write_ver_done(exchange, list(second))
    res = exchange.ingest_ver()
    assert res["items_accepted"] == len(victims)
    assert res["superseded_skipped"] == [f"{victim_bid}.jsonl"]
    assert f"{victim_bid}.jsonl" in exchange.ingested_ver_files  # the original, pre-requeue ingestion

    # Accepted exactly once per (condition, split, tuple_id), no duplicates
    accepted = Counter((it.condition, it.split, it.tuple_id) for it in exchange.items.values() if it.status == "accepted")
    assert len(accepted) == len(exchange.items) and set(accepted.values()) == {1}
    assert exchange.ingest_ver()["items_accepted"] == 0
    exchange.assemble(n_test=6, n_dev=0)


def test_p3h_requeue_exported_uningested_batch_and_items_file_subset(exchange_env, tmp_path: Path):
    exchange, _, _ = exchange_env
    exchange.init_targets(conditions=RQ2, splits=["test"], n_test=4, n_dev=0)
    _mark_generated(exchange)
    exchange.export_ver(ver_batch_size=7)
    batches = _active_ver_batches(exchange)
    bid = sorted(batches)[0]
    _write_ver_done(exchange, [bid])  # done but not yet ingested

    keep, requeue = batches[bid][:2], batches[bid][2:]
    items_file = tmp_path / "items.txt"
    items_file.write_text("\n".join(requeue) + "\n", encoding="utf-8")
    out = exchange.requeue_ver([bid], item_ids=requeue, reason="subset")
    assert set(out["requeued"]) == set(requeue)
    assert all(exchange.items[i].status == "done_gen" for i in requeue)
    # Items of an archived batch left out of the item list are orphaned exported_ver and re-export with the rest
    assert all(exchange.items[i].status == "exported_ver" for i in keep)
    files = exchange.export_ver(ver_batch_size=7)
    reexported = {o["item_id"] for f in files if f.name.endswith(".jsonl") for o in _read_jsonl(f)}
    assert reexported == set(batches[bid])

    # Item ids outside the named batches, unknown batches and already-superseded batches fail closed
    other = sorted(batches)[1]
    with pytest.raises(ValueError, match="not in the named batches"):
        exchange.requeue_ver([other], item_ids=[requeue[0]], reason="x")
    with pytest.raises(ValueError, match="no ver todo batch"):
        exchange.requeue_ver(["vbatch_9999"], reason="x")
    with pytest.raises(ValueError, match="already superseded"):
        exchange.requeue_ver([bid], reason="x")


def _load_build_script():
    spec = importlib.util.spec_from_file_location("eb_build_corpus_p3h", REPO_ROOT / "scripts" / "eb_build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_p3h_requeue_ver_cli(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    save_catalogs(Path("data") / "catalog", seed=20260924)
    exchange = CorpusExchange(exchange_dir="ex", data_dir="data", seed=20260924)
    exchange.init_targets(conditions=RQ2, splits=["test"], n_test=4, n_dev=0)
    _mark_generated(exchange)
    exchange.export_ver(ver_batch_size=7)
    b1, b2 = sorted(_active_ver_batches(exchange))[:2]
    requeue = [o["item_id"] for o in _read_jsonl(exchange.ver_todo_dir / f"{b2}.jsonl")][:3]
    Path("items.jsonl").write_text("".join(json.dumps({"item_id": i}) + "\n" for i in requeue), encoding="utf-8")

    mod = _load_build_script()
    monkeypatch.setattr(sys, "argv", ["eb_build_corpus.py", "--data-dir", "data", "--exchange-dir", "ex",
                                      "requeue-ver", "--batches", f"{b1},{b2}", "--items-file", "items.jsonl",
                                      "--reason", "anchored"])
    mod.main()
    assert "Requeued 3 item(s)" in capsys.readouterr().out

    state = CorpusExchange(exchange_dir="ex", data_dir="data", seed=20260924)
    assert {i for i, it in state.items.items() if it.requeues} == set(requeue)
    assert state.superseded_ver_batches >= {b1, b2}
