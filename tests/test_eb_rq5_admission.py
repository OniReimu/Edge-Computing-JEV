"""Tests for live admission queue semantics, timeout, cache, and slot concurrency."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import time
from typing import Any

import pytest

from src.edgebench.contract import Case
from src.edgebench.e2e.admission import run_admission
from src.edgebench.interpreters.base import Decision, Interpreter
from src.intent_cache import IntentCache


class FakeInterpreter(Interpreter):
    def __init__(self, delay_s: float = 0.05, valid: bool = True) -> None:
        super().__init__(name="fake", deployment="hosted")
        self.delay_s = delay_s
        self.valid = valid
        self.calls = 0

    def decide(self, case: Case) -> Decision:
        self.calls += 1
        if self.delay_s > 0:
            time.sleep(self.delay_s)
        if not self.valid:
            return Decision(valid=False, error_type="SimulatedFailure", latency_s=self.delay_s)
        return Decision(
            labels=[{"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"}],
            valid=True,
            latency_s=self.delay_s,
            cost_usd=0.0001,
        )


def _make_arrival(
    idx: int,
    arrival_s: float,
    deadline_s: float = 2.0,
    text: str | None = None,
) -> dict[str, Any]:
    return {
        "id": idx,
        "arrival": arrival_s,
        "deadline": round(arrival_s + deadline_s, 6),
        "origin": 0,
        "size_mb": 0.5,
        "text": text or f"request text {idx}",
        "truth": [
            {
                "service_type": "count",
                "locality": "site_only",
                "quality_floor": "standard",
                "urgency": "normal",
            }
        ],
    }


def test_admission_queue_overflow() -> None:
    """When slots are saturated and queue limit is reached, excess arrivals get queue_overflow."""
    # 4 slots, queue limit 2 -> capacity is 6 in-flight/waiting.
    # 7 arrivals simultaneously at t=2.0. Fake interpreter takes 0.15s.
    # Arrival 7 should get queue_overflow.
    interp = FakeInterpreter(delay_s=0.15)
    arrivals = [_make_arrival(i, 2.0, deadline_s=2.0) for i in range(7)]
    start = time.monotonic() - 2.0

    traces = asyncio.run(
        run_admission(
            arrivals,
            interp,
            concurrency=4,
            queue_limit=2,
            deadline=2.0,
            cache_enabled=None,
            start_time=start,
        )
    )

    statuses = [traces[i]["status"] for i in range(7)]
    overflow_count = statuses.count("queue_overflow")
    recorded_count = statuses.count("decision_recorded")

    assert overflow_count >= 1, f"Expected at least 1 queue_overflow, got {statuses}"
    assert recorded_count == 6, f"Expected 6 recorded decisions, got {statuses}"
    assert statuses[6] == "queue_overflow"


def test_admission_deadline_expiry_while_waiting() -> None:
    """Arrival at 5.0 s with absolute deadline 5.08 s behind a busy slot -> queue_expired with terminal 5.08."""
    interp = FakeInterpreter(delay_s=0.25)
    # 1 slot, 1 arrival holds it for 0.25s.
    # Arrival at 5.0 s with absolute deadline 5.08 s behind a busy slot
    arrivals = [
        _make_arrival(0, 5.0, deadline_s=1.0),
        _make_arrival(1, 5.0, deadline_s=0.08),
    ]

    start = time.monotonic() - 5.0
    traces = asyncio.run(
        run_admission(
            arrivals,
            interp,
            concurrency=1,
            queue_limit=5,
            deadline=2.0,  # fallback deadline; row['deadline'] is used if present
            cache_enabled=None,
            start_time=start,
        )
    )

    assert traces[0]["status"] == "decision_recorded"
    assert traces[1]["status"] == "queue_expired"
    assert traces[1]["terminal"] == pytest.approx(5.08, abs=1e-4)


def test_admission_deadline_expiry_on_arrival() -> None:
    """Arrival that arrives past its target deadline immediately gets queue_expired."""
    interp = FakeInterpreter(delay_s=0.01)
    # Schedule an arrival at 5.0s with deadline_s=0.1 (absolute deadline 5.1), but run starting at 5.5s
    arrivals = [
        _make_arrival(0, 5.0, deadline_s=0.1),
    ]
    start = time.monotonic() - 5.5
    traces = asyncio.run(
        run_admission(
            arrivals,
            interp,
            concurrency=4,
            queue_limit=10,
            deadline=0.1,
            cache_enabled=None,
            start_time=start,
        )
    )

    assert traces[0]["status"] == "queue_expired"
    assert traces[0]["terminal"] == pytest.approx(5.1, abs=1e-4)


def test_admission_cache_hit_before_slot() -> None:
    """Arrival matching cached item returns immediately without taking an interpreter slot."""
    interp = FakeInterpreter(delay_s=0.1)
    cache = IntentCache()
    # Pre-populate cache
    cache.store(
        "cached text query",
        {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
        ready_at=0.0,
    )

    arrivals = [_make_arrival(0, 2.0, deadline_s=2.0, text="cached text query")]
    start = time.monotonic() - 2.0
    traces = asyncio.run(
        run_admission(
            arrivals,
            interp,
            concurrency=1,
            queue_limit=2,
            deadline=2.0,
            cache_enabled=cache,
            start_time=start,
        )
    )

    assert traces[0]["status"] == "decision_recorded"
    assert traces[0]["decision_metadata"]["cache_hit"] is True
    assert interp.calls == 0  # Interpreter was never called


def test_admission_cache_hit_after_slot() -> None:
    """Second identical arrival waiting in queue benefits from first arrival's cached result."""
    interp = FakeInterpreter(delay_s=0.15)
    cache = IntentCache()

    arrivals = [
        _make_arrival(0, 2.0, deadline_s=2.0, text="shared query text"),
        _make_arrival(1, 2.02, deadline_s=2.0, text="shared query text"),
    ]
    start = time.monotonic() - 2.0
    traces = asyncio.run(
        run_admission(
            arrivals,
            interp,
            concurrency=1,  # Only 1 slot forces arrival 1 to wait
            queue_limit=5,
            deadline=2.0,
            cache_enabled=cache,
            start_time=start,
        )
    )

    assert traces[0]["status"] == "decision_recorded"
    assert traces[0]["decision_metadata"]["cache_hit"] is False

    assert traces[1]["status"] == "decision_recorded"
    assert traces[1]["decision_metadata"]["cache_hit"] is True
    # Interpreter should only have been called once across both arrivals
    assert interp.calls == 1


def test_admission_slot_held_past_deadline() -> None:
    """Slow interpreter holds slot even if arrival deadline passes, blocking subsequent arrivals."""
    # Arrival 0 has deadline 2.05s, but interpreter runs for 0.25s.
    # Arrival 1 arrives at t=2.01 with deadline 3.0s, waiting on the 1 available slot.
    interp = FakeInterpreter(delay_s=0.25)

    arrivals = [
        _make_arrival(0, 2.0, deadline_s=0.05),
        _make_arrival(1, 2.01, deadline_s=1.0),
    ]
    start = time.monotonic() - 2.0
    traces = asyncio.run(
        run_admission(
            arrivals,
            interp,
            concurrency=1,
            queue_limit=5,
            deadline=2.0,
            cache_enabled=None,
            start_time=start,
        )
    )

    # Arrival 1 couldn't start decision until Arrival 0 finished at ~2.25s
    arr1_start = traces[1]["decision_start"]
    assert arr1_start >= 2.20, f"Slot was prematurely released; arrival 1 started at {arr1_start}"


def test_admission_deadline_check_mutation() -> None:
    """Mutation check: flipping admission deadline comparison must fail this test."""
    interp = FakeInterpreter(delay_s=0.02)

    # Test case 1: arrival is legitimately expired: observed (2.5) >= target_arrival (2.0) + deadline (0.01)
    expired_arrival = [_make_arrival(0, 2.0, deadline_s=0.01)]
    start_exp = time.monotonic() - 2.5
    trace_exp = asyncio.run(run_admission(expired_arrival, interp, concurrency=1, queue_limit=5, deadline=0.01, start_time=start_exp))
    assert trace_exp[0]["status"] == "queue_expired", "Expired arrival must get queue_expired"

    # Test case 2: arrival is well within deadline: observed ~ 2.0 < target_arrival (2.0) + deadline (2.0)
    valid_arrival = [_make_arrival(1, 2.0, deadline_s=2.0)]
    start_val = time.monotonic() - 2.0
    trace_val = asyncio.run(run_admission(valid_arrival, interp, concurrency=1, queue_limit=5, deadline=2.0, start_time=start_val))
    assert trace_val[1]["status"] == "decision_recorded", "Valid arrival must NOT get queue_expired"


def test_admission_last_row_expiry_matches_deadline() -> None:
    """Real last row of traces/load_4/1.jsonl expires at exactly its absolute deadline field."""
    trace_path = Path("traces/load_4/1.jsonl")
    with open(trace_path, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]
        last_row = json.loads(lines[-1])

    interp = FakeInterpreter(delay_s=0.01)
    # Force it to arrive past deadline so it expires on arrival
    start = time.monotonic() - (last_row["deadline"] + 1.0)
    traces = asyncio.run(
        run_admission(
            [last_row],
            interp,
            concurrency=1,
            queue_limit=5,
            deadline=2.0,
            cache_enabled=None,
            start_time=start,
        )
    )

    r = traces[last_row["id"]]
    assert r["status"] == "queue_expired"
    assert r["terminal"] == pytest.approx(last_row["deadline"], abs=1e-5)
