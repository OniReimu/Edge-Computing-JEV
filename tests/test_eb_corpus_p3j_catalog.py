"""P3j: RQ4 catalog label validity (catalog audit E1-E16 + catalog-aware unsupported pool) and the
operations that repair existing items (retarget, requeue-gen, item-level requeue-ver)."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from src.edgebench.corpus.catalog import (
    build_nested_and_churn_catalogs,
    get_services_catalog,
    is_valid_unsupported_target,
    save_catalogs,
    verify_catalog_invariants,
)
from src.edgebench.corpus.catalog_data import RAW_NOVEL_SERVICES, RAW_SERVICES
from src.edgebench.corpus.exchange import CorpusExchange

REPO_ROOT = Path(__file__).resolve().parent.parent
CATALOG_DIR = REPO_ROOT / "data" / "edgebench" / "v1" / "catalog"
SEED = 20260924
SVC = {s["id"]: s for s in RAW_SERVICES + RAW_NOVEL_SERVICES}

# Catalog audit section 5, "Required (P1)"
AUDIT_E: dict[str, str] = {
    "meter_reading_ocr": "read cumulative consumption digits from household electricity, gas and water utility meter registers",
    "instrument_gauge_ocr": "read needle positions and units from pressure, temperature and flow gauges on industrial process equipment",
    "drone_detector": "localize small drones with bounding boxes in sky-facing camera video to feed a tracking system",
    "drone_perimeter_alert": "detect drones crossing a site's boundary in camera video and raise a trespass alert to security staff",
    "es_to_en_speech_translator": "translate one-way Spanish audio such as broadcasts or voicemail into natural English speech",
    "en_to_es_speech_translator": "translate one-way English broadcasts and announcements into spoken and transcribed Spanish",
    "tailgating_detector": "detect a second vehicle following an authorized car through a raised parking gate barrier",
    "fire_detector": "detect visible flames and smoke in camera views of buildings, vehicles and industrial yards",
    "handwritten_form_ocr": "transcribe handwritten field entries from scanned patient intake and registration forms",
    "ambient_noise_level_meter": "compute workers' cumulative noise dose against occupational exposure limits in workshops",
    "customer_dwell_time_meter": "measure how long shoppers stand in front of promotional endcap displays, from overhead cameras",
    "speeding_vehicle_detector": "measure each individual vehicle's speed from calibrated road footage for speed enforcement",
    "traffic_congestion_analyzer": "rate freeway congestion level of service from lane occupancy and mean segment speed",
    "queue_length_analyzer": "estimate expected customer wait time at retail checkouts from observed cashier service rates",
    "ship_ballast_water_invasive_algae_cytometer": "dose ultraviolet treatment lamps in cargo ship ballast water systems to meet discharge standards",
    "sewage_network_h2s_corrosion_modeler": "model crown concrete acid corrosion rates along municipal trunk sewers from flow and temperature records",
}
# is_valid_unsupported_target (catalog-free) of each edited service before the edit (f831cce)
STATUS_BEFORE: dict[str, bool] = {
    "meter_reading_ocr": False, "instrument_gauge_ocr": False, "drone_detector": False, "drone_perimeter_alert": False,
    "es_to_en_speech_translator": True, "en_to_es_speech_translator": True, "tailgating_detector": False,
    "fire_detector": False, "handwritten_form_ocr": False, "ambient_noise_level_meter": True,
    "customer_dwell_time_meter": True, "speeding_vehicle_detector": True, "traffic_congestion_analyzer": True,
    "queue_length_analyzer": True, "ship_ballast_water_invasive_algae_cytometer": True,
    "sewage_network_h2s_corrosion_modeler": True,
}
COND_CATALOG = {"K4": "C_4", "K15": "C_15", "K64": "C_64", "K128": "C_128", "churn25": "v25", "churn50": "v50"}
# Catalog audit appendix: the P1 B items (condition, unsupported target)
AUDIT_P1_B: list[tuple[str, str]] = [
    ("K128", "academic_transcript_parser"), ("K128", "bank_statement_table_parser"),
    ("churn25", "bank_statement_table_parser"), ("K4", "customs_declaration_parser"),
    ("K15", "handwritten_survey_digitizer"), ("K4", "handwritten_survey_digitizer"),
    ("K64", "handwritten_survey_digitizer"), ("churn25", "identity_card_extractor"),
    ("churn25", "invoice_data_extractor"), ("K4", "medical_prescription_parser"),
    ("K4", "shipping_manifest_digitizer"), ("K4", "tax_form_w2_parser"), ("churn25", "tax_form_w2_parser"),
    ("K15", "utility_bill_parser"), ("K64", "utility_bill_parser"), ("K4", "queue_length_analyzer"),
    ("churn50", "queue_length_analyzer"), ("K15", "package_xray_contraband_screener"),
    ("K4", "under_vehicle_inspection_scanner"), ("K64", "drone_acoustic_classifier"),
]


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _snapshot(root: Path) -> dict[str, bytes | None]:
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None) for p in sorted(root.rglob("*"))}


# ---------------------------------------------------------------------------
# Item 1: descriptions E1-E16
# ---------------------------------------------------------------------------
def test_p3j_1_audit_descriptions_and_regenerated_catalog(tmp_path: Path):
    for sid, desc in AUDIT_E.items():
        assert SVC[sid]["description"] == desc, sid
        assert len(desc.split()) <= 20, sid
        assert is_valid_unsupported_target(SVC[sid]) is STATUS_BEFORE[sid], sid
    assert SVC["ship_ballast_water_invasive_algae_cytometer"]["name"] == "Cargo Ship Ballast Water Ultraviolet Dose Controller"
    # Name Jaccard (< 0.8 over all 294 names) and every other invariant
    verify_catalog_invariants(get_services_catalog(), build_nested_and_churn_catalogs(seed=SEED))

    # The committed catalog files are what save_catalogs writes from the current data; catalogs.json is unchanged
    services_file, catalogs_file = save_catalogs(tmp_path, seed=SEED)
    assert services_file.read_bytes() == (CATALOG_DIR / "services.json").read_bytes()
    assert catalogs_file.read_bytes() == (CATALOG_DIR / "catalogs.json").read_bytes()


# ---------------------------------------------------------------------------
# Item 2: catalog-aware unsupported pool
# ---------------------------------------------------------------------------
def test_p3j_2_catalog_aware_unsupported_target():
    cats = build_nested_and_churn_catalogs(seed=SEED)
    doc_ids = [s["id"] for s in RAW_SERVICES if s["family"] == "document_processing"]
    assert len(doc_ids) == 16
    for cat in ("C_4", "C_15", "C_64", "C_128", "v25"):  # ocr active
        for sid in doc_ids:
            assert not is_valid_unsupported_target(SVC[sid], cats[cat]), (cat, sid)
    # churn50 has no ocr: its document parsers keep their catalog-free status, except the ID-card extractor
    # (passport_mrz_ocr active)
    assert "ocr" not in cats["v50"] and "passport_mrz_ocr" in cats["v50"]
    for sid in doc_ids:
        expected = is_valid_unsupported_target(SVC[sid]) and sid != "identity_card_extractor"
        assert is_valid_unsupported_target(SVC[sid], cats["v50"]) is expected, sid
    assert is_valid_unsupported_target(SVC["invoice_data_extractor"], cats["v50"])

    # Object screeners: covered by detection (absent only in churn25)
    for sid in ("under_vehicle_inspection_scanner", "package_xray_contraband_screener"):
        for cat in ("C_4", "C_15", "C_64"):
            assert not is_valid_unsupported_target(SVC[sid], cats[cat]), (cat, sid)
        assert is_valid_unsupported_target(SVC[sid], cats["v25"]), sid

    # Near-duplicates
    assert not is_valid_unsupported_target(SVC["loitering_at_atm_detector"], cats["C_128"])
    assert is_valid_unsupported_target(SVC["loitering_at_atm_detector"], cats["C_15"])
    assert not is_valid_unsupported_target(SVC["drone_acoustic_classifier"], cats["C_64"])
    assert not is_valid_unsupported_target(SVC["drone_acoustic_classifier"], cats["v25"])
    assert is_valid_unsupported_target(SVC["drone_acoustic_classifier"], cats["v50"])
    assert not is_valid_unsupported_target(SVC["handwritten_survey_digitizer"], ["handwritten_form_ocr"])
    assert not is_valid_unsupported_target(SVC["identity_card_extractor"], ["visitor_id_scanner"])

    # Without a catalog the check is the catalog-free one (statuses unchanged for existing callers)
    for sid in ("invoice_data_extractor", "identity_card_extractor", "handwritten_survey_digitizer",
                "under_vehicle_inspection_scanner", "loitering_at_atm_detector", "drone_acoustic_classifier"):
        assert is_valid_unsupported_target(SVC[sid]), sid

    # Every audit P1 B item's target is out of its condition's pool now; queue_length_analyzer (B3, covered by
    # count) is fixed by its E14 description instead and stays in the pool
    from src.edgebench.corpus.tuples import rq4_active_catalog_and_unsupported_pool

    novel_ids = [s["id"] for s in RAW_NOVEL_SERVICES]
    for cond, target in AUDIT_P1_B:
        _, pool = rq4_active_catalog_and_unsupported_pool(cond, cats, novel_ids)
        assert (target in pool) is (target == "queue_length_analyzer"), (cond, target)
    # K254 draws from the 40 novel services, none of which the new rules touch
    assert rq4_active_catalog_and_unsupported_pool("K254", cats, novel_ids)[1] == novel_ids

    # Fresh sampling only draws from the catalog-aware pool
    from src.edgebench.corpus.tuples import sample_tuples_for_condition
    for cond, cat in COND_CATALOG.items():
        for t in sample_tuples_for_condition(cond, "test", 300, SEED, catalogs=cats, novel_service_ids=novel_ids):
            if t.meta["is_unsupported"]:
                assert is_valid_unsupported_target(SVC[t.meta["target_service"]], cats[cat]), (cond, t.meta)


# ---------------------------------------------------------------------------
# Item 3: operations (retarget, requeue-gen, item-level requeue-ver)
# ---------------------------------------------------------------------------
def _load_build_script():
    spec = importlib.util.spec_from_file_location("eb_build_corpus_p3j", REPO_ROOT / "scripts" / "eb_build_corpus.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _cli(monkeypatch, data_dir: Path, exchange_dir: Path, *argv: str) -> None:
    mod = _load_build_script()
    monkeypatch.setattr(sys, "argv", ["eb_build_corpus.py", "--data-dir", str(data_dir),
                                      "--exchange-dir", str(exchange_dir), *argv])
    mod.main()


def _generate(ex: CorpusExchange, items) -> None:
    for it in items:
        it.status, it.text, it.generator = "done_gen", f"Handle order {it.item_id} for the team today.", "fake-gen"
    ex._save_state()


def _verify_all_exported(ex: CorpusExchange) -> None:
    for vf in sorted(ex.ver_todo_dir.glob("*.jsonl")):
        if vf.name in ex.ingested_ver_files or (ex.ver_done_dir / vf.name).exists():
            continue
        with open(ex.ver_done_dir / vf.name, "w", encoding="utf-8") as f:
            for o in _read_jsonl(vf):
                it = ex.items[o["item_id"]]
                f.write(json.dumps({"item_id": it.item_id, "labels": dict(it.tuple_labels), "verifier": "fake-ver"}) + "\n")


def _accept(ex: CorpusExchange, items) -> None:
    _generate(ex, items)
    ex.export_ver()
    _verify_all_exported(ex)
    ex.ingest_ver()
    assert all(it.status == "accepted" for it in items)


def _unsupported(ex: CorpusExchange, cond: str = "K4", split: str = "test") -> list:
    return sorted((it for it in ex.items.values() if it.condition == cond and it.split == split
                   and it.tuple_labels["service_type"] == "unsupported"), key=lambda it: it.tuple_id)


@pytest.fixture
def k4(tmp_path: Path):
    """K4 test (30 items, 3 unsupported) and dev (10 items, 1 unsupported), nothing generated yet."""
    exchange_dir, data_dir = tmp_path / "ex", tmp_path / "data"
    save_catalogs(data_dir / "catalog", seed=SEED)
    ex = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    ex.init_targets(conditions=["K4"], splits=["test", "dev"], n_test=30, n_dev=10)
    assert len(_unsupported(ex)) == 3
    return ex, exchange_dir, data_dir


def test_p3j_3a_retarget_picks_a_fresh_pool_target_and_resets(k4):
    from src.edgebench.corpus.tuples import rq4_active_catalog_and_unsupported_pool

    ex, exchange_dir, data_dir = k4
    u1, u2, u3 = _unsupported(ex)
    _accept(ex, [u1])
    u2.status = "done_gen"
    u2.text, u2.generator = "some text", "g"
    ex._save_state()
    others = {u3.meta["target_service"]}
    old = {u1.item_id: u1.meta["target_service"], u2.item_id: u2.meta["target_service"]}

    res = ex.retarget([u2.item_id, u1.item_id], allow_accepted=True, reason="audit B1")
    cats = build_nested_and_churn_catalogs(seed=SEED)
    _, pool = rq4_active_catalog_and_unsupported_pool("K4", cats, [s["id"] for s in RAW_NOVEL_SERVICES])
    new = {i: c["new"] for i, c in res["retargeted"].items()}
    assert set(new) == {u1.item_id, u2.item_id}
    assert len(set(new.values())) == 2 and not set(new.values()) & (others | set(old.values()))
    assert set(new.values()) <= set(pool)

    reloaded = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    for it, prior in ((reloaded.items[u1.item_id], "accepted"), (reloaded.items[u2.item_id], "done_gen")):
        assert it.meta["target_service"] == new[it.item_id] and it.tuple_labels["service_type"] == "unsupported"
        assert (it.status, it.text, it.generator, it.verifier_labels, it.verifier, it.gen_batch_id, it.ver_batch_id) == \
            ("pending_gen", None, None, None, None, None, None)
        rec = it.requeues[-1]
        assert (rec["op"], rec["retargeted_from"], rec["retargeted_to"], rec["prior_status"], rec["reason"]) == \
            ("retarget", old[it.item_id], new[it.item_id], prior, "audit B1")
        assert rec["time"]

    # Deterministic in (seed, item_id): an identical exchange picks the same targets
    twin_dir = exchange_dir.parent / "twin"
    twin = CorpusExchange(exchange_dir=twin_dir, data_dir=data_dir, seed=SEED)
    twin.init_targets(conditions=["K4"], splits=["test", "dev"], n_test=30, n_dev=10)
    assert {i: c["new"] for i, c in twin.retarget([u1.item_id, u2.item_id])["retargeted"].items()} == new

    # The next gen export asks for the new target
    files = ex.export_gen(conditions=["K4"], splits=["test"], n_test=30, n_dev=10)
    prompts = {o["item_id"]: o["prompt"] for f in files for o in _read_jsonl(f)}
    for i, sid in new.items():
        assert f"Needed service capability: {SVC[sid]['description']}" in prompts[i]


def test_p3j_3a_retarget_falls_back_to_a_used_target_when_the_pool_has_no_other(k4, monkeypatch):
    import src.edgebench.corpus.exchange as exchange_mod

    ex, _, _ = k4
    u1, u2, _ = _unsupported(ex)
    pool = [u1.meta["target_service"], u2.meta["target_service"]]
    monkeypatch.setattr(exchange_mod, "rq4_active_catalog_and_unsupported_pool", lambda *a: ([], pool))
    assert ex.retarget([u1.item_id])["retargeted"][u1.item_id]["new"] == u2.meta["target_service"]


def test_p3j_3a_retarget_refusals_change_nothing(k4):
    ex, exchange_dir, data_dir = k4
    u1, u2, u3 = _unsupported(ex)
    supported = next(it for it in ex.items.values() if it.tuple_labels["service_type"] != "unsupported")
    _accept(ex, [u1])
    u3.status = "rejected"
    ex._save_state()
    ex.export_gen(conditions=["K4"], splits=["test"], n_test=30, n_dev=10)  # u2 now in an active gen todo batch
    before = _snapshot(exchange_dir)

    for ids, kw, pattern in (
        ([u1.item_id], {}, "accepted \\(pass allow_accepted"),
        ([supported.item_id], {}, "not an unsupported item"),
        ([u3.item_id], {}, "rejected"),
        ([u2.item_id], {}, "active batch file"),
        (["it_unknown"], {}, "unknown item IDs"),
        ([u1.item_id, u2.item_id], {"allow_accepted": True}, "active batch file"),
        ([], {}, "no item IDs"),
    ):
        with pytest.raises(ValueError, match=pattern):
            ex.retarget(ids, **kw)
        assert _snapshot(exchange_dir) == before

    # Non-RQ4 items are refused
    ex.init_targets(conditions=["clean"], splits=["dev"], n_test=30, n_dev=10)
    clean_item = next(it for it in ex.items.values() if it.condition == "clean")
    with pytest.raises(ValueError, match="not an RQ4 item"):
        ex.retarget([clean_item.item_id])

    # Frozen groups are refused (P3i guard)
    (data_dir / "_frozen.json").write_text(json.dumps({"RQ4/K4/test": {"sha256": "x", "n": 30}}), encoding="utf-8")
    state = ex._state_file().read_bytes()
    with pytest.raises(ValueError, match=r"retarget: refusing to change 1 item\(s\) of frozen group\(s\) \['RQ4/K4/test'\]"):
        ex.retarget([u1.item_id], allow_accepted=True)
    assert ex._state_file().read_bytes() == state


def test_p3j_3b_requeue_gen_archives_supersedes_and_rebuilds_prompts(k4):
    ex, exchange_dir, data_dir = k4
    files = ex.export_gen(conditions=["K4"], splits=["test"], n_test=30, n_dev=10)
    assert [f.stem for f in files] == ["gen_K4_test_001"]
    bid = "gen_K4_test_001"
    ids = [o["item_id"] for o in _read_jsonl(files[0])]
    old_prompts = {o["item_id"]: o["prompt"] for o in _read_jsonl(files[0])}

    # The catalog changes after export: the requeued items get prompts from the new description
    target = ex.items[ids[0]].meta["target_service"]
    services = json.loads((data_dir / "catalog" / "services.json").read_text(encoding="utf-8"))
    for s in services["services"] + services["novel_services"]:
        if s["id"] == target:
            s["description"] = "a brand new description of the needed capability"
    (data_dir / "catalog" / "services.json").write_text(json.dumps(services, indent=2), encoding="utf-8")

    res = ex.requeue_gen([bid], reason="catalog E1-E16")
    assert sorted(res["requeued"]) == sorted(ids) and res["skipped"] == []
    archive = Path(res["archive_dir"])
    assert archive.parent == exchange_dir / "gen" / "_superseded"
    assert (archive / "todo" / f"{bid}.jsonl").exists() and not (ex.gen_todo_dir / f"{bid}.jsonl").exists()
    reloaded = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    assert bid in reloaded.superseded_gen_batches
    for i in ids:
        it = reloaded.items[i]
        assert (it.status, it.gen_batch_id) == ("pending_gen", None)
        assert (it.requeues[-1]["op"], it.requeues[-1]["requeued_from"], it.requeues[-1]["reason"]) == \
            ("requeue_gen", bid, "catalog E1-E16")

    # Re-export: a new batch ID (the superseded one is never reused), same items, current catalog text
    new_files = reloaded.export_gen(conditions=["K4"], splits=["test"], n_test=30, n_dev=10)
    assert [f.stem for f in new_files] == ["gen_K4_test_002"]
    new_prompts = {o["item_id"]: o["prompt"] for o in _read_jsonl(new_files[0])}
    assert set(new_prompts) == set(ids)
    assert "a brand new description of the needed capability" in new_prompts[ids[0]]
    assert new_prompts[ids[0]] != old_prompts[ids[0]]

    # A late done file for the superseded batch is never ingested and does not block the live batch
    (reloaded.gen_done_dir / f"{bid}.jsonl").write_text(
        "".join(json.dumps({"item_id": i, "text": "stale text from the old prompt", "generator": "g"}) + "\n" for i in ids),
        encoding="utf-8")
    out = reloaded.ingest_gen()
    assert out["superseded_skipped"] == [f"{bid}.jsonl"]
    assert all(reloaded.items[i].status == "exported_gen" and reloaded.items[i].text is None for i in ids)


def test_p3j_3b_requeue_gen_refusals_change_nothing(k4):
    ex, exchange_dir, data_dir = k4
    ex.export_gen(conditions=["K4"], n_test=30, n_dev=10)
    done_bid, bid = "gen_K4_dev_001", "gen_K4_test_001"
    (ex.gen_done_dir / f"{done_bid}.jsonl").write_text("{}\n", encoding="utf-8")
    before = _snapshot(exchange_dir)
    for ids, pattern in (([done_bid], "has a done file"), ([bid, done_bid], "has a done file"),
                         (["gen_K4_test_009"], "no gen todo batch"), ([], "no batch IDs")):
        with pytest.raises(ValueError, match=pattern):
            ex.requeue_gen(ids)
        assert _snapshot(exchange_dir) == before

    ex.requeue_gen([bid])
    with pytest.raises(ValueError, match="already superseded"):
        ex.requeue_gen([bid])

    # Frozen groups are refused
    ex.export_gen(conditions=["K4"], splits=["test"], n_test=30, n_dev=10)
    (data_dir / "_frozen.json").write_text(json.dumps({"RQ4/K4/test": {"sha256": "x", "n": 30}}), encoding="utf-8")
    before = _snapshot(exchange_dir)
    with pytest.raises(ValueError, match=r"requeue_gen: refusing to change 30 item\(s\) of frozen group"):
        ex.requeue_gen(["gen_K4_test_002"])
    assert _snapshot(exchange_dir) == before


def test_p3j_3c_requeue_ver_items(k4):
    ex, exchange_dir, data_dir = k4
    test_items = sorted((it for it in ex.items.values() if it.condition == "K4" and it.split == "test"),
                        key=lambda it: it.tuple_id)
    acc, pend = test_items[:6], test_items[6:]
    _accept(ex, acc)
    acc_bid = acc[0].ver_batch_id
    assert {it.ver_batch_id for it in acc} == {acc_bid}
    _generate(ex, pend[:4])
    ex.export_ver()  # pend[:4] exported_ver in a live batch without a done file
    live_bid = pend[0].ver_batch_id
    assert live_bid != acc_bid

    res = ex.requeue_ver_items([acc[0].item_id, acc[1].item_id, pend[0].item_id, pend[5].item_id], reason="E-edit")
    assert sorted(res["requeued"]) == sorted([acc[0].item_id, acc[1].item_id, pend[0].item_id])
    assert res["skipped"] == [pend[5].item_id]  # pending_gen: nothing to re-verify
    archive = Path(res["archive_dir"])
    for bid in (acc_bid, live_bid):
        assert (archive / "todo" / f"{bid}.jsonl").exists() and (archive / "todo" / f"{bid}.context.md").exists()
        assert not (ex.ver_todo_dir / f"{bid}.jsonl").exists()
    assert (archive / "done" / f"{acc_bid}.jsonl").exists()

    reloaded = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    assert {acc_bid, live_bid} <= reloaded.superseded_ver_batches
    for i in (acc[0].item_id, acc[1].item_id, pend[0].item_id):
        it = reloaded.items[i]
        assert (it.status, it.ver_batch_id, it.verifier_labels, it.verifier) == ("done_gen", None, None, None)
        assert it.text and it.requeues[-1]["reason"] == "E-edit"
    assert all(reloaded.items[it.item_id].status == "accepted" for it in acc[2:])

    # An accepted item whose batch an earlier requeue already superseded: reset, nothing left to move
    res2 = reloaded.requeue_ver_items([acc[2].item_id])
    assert res2["requeued"] == [acc[2].item_id] and res2["archive_dir"] is None
    assert reloaded.items[acc[2].item_id].status == "done_gen"
    assert reloaded.items[acc[2].item_id].requeues[-1] == {"requeued_from": acc_bid, "reason": "requeue-ver", "archive": ""}

    # Re-export: the requeued items and the unselected items of the superseded live batch go to a fresh batch
    files = reloaded.export_ver()
    exported = {o["item_id"] for f in files if f.suffix == ".jsonl" for o in _read_jsonl(f)}
    assert exported == {acc[0].item_id, acc[1].item_id, acc[2].item_id, *(it.item_id for it in pend[:4])}

    # Refusals
    before = _snapshot(exchange_dir)
    with pytest.raises(ValueError, match="unknown item IDs"):
        reloaded.requeue_ver_items(["it_unknown"])
    (data_dir / "_frozen.json").write_text(json.dumps({"RQ4/K4/test": {"sha256": "x", "n": 30}}), encoding="utf-8")
    with pytest.raises(ValueError, match="requeue_ver_items: refusing to change"):
        reloaded.requeue_ver_items([acc[3].item_id])
    assert _snapshot(exchange_dir) == before


def test_p3j_3_cli(k4, monkeypatch, capsys):
    ex, exchange_dir, data_dir = k4
    u1, u2, u3 = _unsupported(ex)
    other = next(it for it in ex.items.values() if it.split == "test" and it.tuple_labels["service_type"] != "unsupported")
    _accept(ex, [u1, other])
    ex.export_gen(conditions=["K4"], splits=["test"], n_test=30, n_dev=10)
    capsys.readouterr()

    _cli(monkeypatch, data_dir, exchange_dir, "requeue-gen", "--batches", "gen_K4_test_001", "--reason", "cli")
    assert "to pending_gen" in capsys.readouterr().out
    ids_file = exchange_dir.parent / "ids.txt"
    ids_file.write_text(f"{u1.item_id}\n{u2.item_id}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="accepted \\(pass allow_accepted"):
        _cli(monkeypatch, data_dir, exchange_dir, "retarget", "--items", f"@{ids_file}")
    _cli(monkeypatch, data_dir, exchange_dir, "retarget", "--items", f"@{ids_file}", "--allow-accepted")
    assert "Retargeted 2 item(s)" in capsys.readouterr().out
    state = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    assert all(state.items[i].status == "pending_gen" for i in (u1.item_id, u2.item_id))

    for argv in (("requeue-ver",), ("requeue-ver", "--batches", "vbatch_0001", "--items", other.item_id)):
        with pytest.raises(ValueError, match="exactly one of --batches or --items"):
            _cli(monkeypatch, data_dir, exchange_dir, *argv)
    _cli(monkeypatch, data_dir, exchange_dir, "requeue-ver", "--items", other.item_id, "--reason", "cli")
    assert "Requeued 1 item(s) to done_gen" in capsys.readouterr().out
    state = CorpusExchange(exchange_dir=exchange_dir, data_dir=data_dir, seed=SEED)
    assert state.items[other.item_id].status == "done_gen"
