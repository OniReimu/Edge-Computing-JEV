"""Tests for RQ5 trace generation, determinism, and SHA-256 manifests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.edgebench.e2e.traces import (
    CELLS_A,
    CONDITIONS_B,
    DEFAULT_POOL_PATH,
    compute_sha256,
    generate_all_traces_a,
    generate_trace_a,
    generate_trace_b,
    load_pool,
    select_repeated_8,
)


def test_pool_loading() -> None:
    pool = load_pool(DEFAULT_POOL_PATH)
    assert len(pool) == 300
    services = {r["truth"][0]["service_type"] for r in pool}
    assert services == {"count", "detection", "ocr"}


def test_select_repeated_8() -> None:
    pool = load_pool(DEFAULT_POOL_PATH)
    rep1 = select_repeated_8(pool, seed=20260924)
    rep2 = select_repeated_8(pool, seed=20260924)
    assert len(rep1) == 8
    # Exact determinism
    assert [r["case_id"] for r in rep1] == [r["case_id"] for r in rep2]

    # Verify 6 OCR (supported) and 2 non-OCR
    ocr_count = sum(r["truth"][0]["service_type"] == "ocr" for r in rep1)
    non_ocr_count = sum(r["truth"][0]["service_type"] != "ocr" for r in rep1)
    assert ocr_count == 6
    assert non_ocr_count == 2


def test_trace_determinism() -> None:
    pool = load_pool(DEFAULT_POOL_PATH)
    trace_a1 = generate_trace_a("load_4", seed=1, pool=pool, n=300)
    trace_a2 = generate_trace_a("load_4", seed=1, pool=pool, n=300)
    assert len(trace_a1) == 300
    assert len(trace_a2) == 300
    for r1, r2 in zip(trace_a1, trace_a2):
        assert r1 == r2


def test_trace_manifest_verification(tmp_path: Path) -> None:
    manifest = generate_all_traces_a(out_dir=tmp_path / "traces", seeds=(1,))
    assert len(manifest) == 15

    for key, rec in manifest.items():
        file_path = tmp_path / "traces" / rec["file"]
        assert file_path.exists()
        actual_sha = compute_sha256(file_path)
        assert actual_sha == rec["sha256"], f"SHA mismatch on {key}"
        assert rec["arrivals"] == 300


def test_changing_vs_repeated_texts() -> None:
    pool = load_pool(DEFAULT_POOL_PATH)
    changing_trace = generate_trace_a("load_4", seed=1, pool=pool, n=300)
    repeated_trace = generate_trace_a("reuse_repeated_off", seed=1, pool=pool, n=300)

    # Changing has 300 unique texts
    unique_changing = len({r["case_id"] for r in changing_trace})
    assert unique_changing == 300

    # Repeated has at most 8 unique texts
    unique_repeated = len({r["case_id"] for r in repeated_trace})
    assert unique_repeated <= 8


def test_bursty_alternation() -> None:
    pool = load_pool(DEFAULT_POOL_PATH)
    trace = generate_trace_a("bursty", seed=1, pool=pool, n=300)
    # Check that arrivals span multiple 20s segments
    times = [r["arrival"] for r in trace]
    assert times[-1] > 40.0  # At least 2 full 20s segments
    assert all(times[i] <= times[i + 1] for i in range(len(times) - 1))


def test_part_b_changing_distinct_texts() -> None:
    """Assert 180 distinct OCR texts and 60 distinct other texts for every changing condition."""
    changing_conditions = [
        cond for cond, cfg in CONDITIONS_B.items() if cfg["text"] == "changing"
    ]
    assert len(changing_conditions) == 4

    for cond in changing_conditions:
        trace = generate_trace_b(cond, seed=1)
        ocr_rows = [r for r in trace if r["is_ocr"]]
        other_rows = [r for r in trace if not r["is_ocr"]]

        assert len(ocr_rows) == 180
        assert len(other_rows) == 60

        unique_ocr_texts = {r["text"] for r in ocr_rows}
        unique_other_texts = {r["text"] for r in other_rows}

        assert len(unique_ocr_texts) == 180, f"Condition {cond} has {len(unique_ocr_texts)} distinct OCR texts, expected 180"
        assert len(unique_other_texts) == 60, f"Condition {cond} has {len(unique_other_texts)} distinct other texts, expected 60"


def test_part_b_repeated_texts_preserved() -> None:
    """Repeated conditions in Part B cycle the fixed 8 texts."""
    repeated_conditions = [
        cond for cond, cfg in CONDITIONS_B.items() if cfg["text"] == "repeated"
    ]
    assert len(repeated_conditions) == 4

    for cond in repeated_conditions:
        trace = generate_trace_b(cond, seed=1)
        ocr_rows = [r for r in trace if r["is_ocr"]]
        other_rows = [r for r in trace if not r["is_ocr"]]

        assert len(ocr_rows) == 180
        assert len(other_rows) == 60

        unique_ocr_texts = {r["text"] for r in ocr_rows}
        unique_other_texts = {r["text"] for r in other_rows}

        assert len(unique_ocr_texts) <= 6
        assert len(unique_other_texts) <= 2


def test_part_a_changing_300_distinct_texts() -> None:
    """Part A changing cells have exactly 300 distinct texts."""
    pool = load_pool(DEFAULT_POOL_PATH)
    changing_cells = [
        cell for cell, cfg in CELLS_A.items() if cfg["text"] == "changing"
    ]
    assert len(changing_cells) >= 12

    for cell in changing_cells:
        trace = generate_trace_a(cell, seed=1, pool=pool, n=300)
        assert len(trace) == 300
        unique_texts = {r["text"] for r in trace}
        assert len(unique_texts) == 300, f"Cell {cell} has {len(unique_texts)} distinct texts, expected 300"

