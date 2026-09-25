"""Tests for Oracle and Fixed-Latency control interpreters."""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.edgebench.e2e.admission import run_admission
from src.edgebench.e2e.sim import simulate, summarize
from src.edgebench.interpreters.fixed_latency import FixedLatencyInterpreter
from src.edgebench.manifest import build_interpreter, load_manifest


def _make_workload(n: int = 15, arrival_interval: float = 0.05, deadline: float = 0.8) -> list[dict[str, Any]]:
    return [
        {
            "id": i,
            "arrival": i * arrival_interval,
            "deadline": deadline,
            "origin": i % 4,
            "size_mb": 0.25,
            "text": f"request {i} count query",
            "truth": [
                {
                    "service_type": "count",
                    "locality": "remote_allowed",
                    "quality_floor": "standard",
                    "urgency": "normal",
                }
            ],
        }
        for i in range(n)
    ]


def test_oracle_interpreter_controls() -> None:
    """Oracle interpreter achieves maximum completion ceiling on a feasible trace."""
    oracle = build_interpreter("oracle")
    trace = _make_workload(n=10, arrival_interval=0.05, deadline=2.0)

    # Run admission
    ctrace = asyncio.run(
        run_admission(
            trace,
            oracle,
            concurrency=4,
            deadline=2.0,
            cache_enabled=False,
        )
    )

    # Replay in simulator
    outcomes = simulate(trace, controller_trace=ctrace, deadline=2.0, n_edges=4)
    summary = summarize(outcomes)

    # Oracle should have 100% completion on feasible arrivals with ample deadline
    assert summary["n"] == 10
    assert summary["counts"].get("success", 0) == 10
    assert summary["success_rate"] == 1.0
    for r in outcomes:
        assert r["status"] == "success"
        assert r["locality_violation"] is False


def test_fixed_latency_monotonicity() -> None:
    """Completion rate must be non-increasing as fixed interpreter latency increases."""
    # Test latencies: low, medium, high
    delays = [0.02, 0.20, 0.90]
    trace = _make_workload(n=8, arrival_interval=0.02, deadline=0.6)

    completions = []
    for d in delays:
        interp = FixedLatencyInterpreter(delay_s=d)
        ctrace = asyncio.run(
            run_admission(
                trace,
                interp,
                concurrency=2,
                deadline=0.6,
                cache_enabled=False,
            )
        )
        outcomes = simulate(trace, controller_trace=ctrace, deadline=0.6, n_edges=4)
        summary = summarize(outcomes)
        completions.append(summary["success_rate"])

    # Monotonicity check: completion(low) >= completion(medium) >= completion(high)
    assert completions[0] >= completions[1], f"Expected {completions[0]} >= {completions[1]}"
    assert completions[1] >= completions[2], f"Expected {completions[1]} >= {completions[2]}"
    # High latency (> deadline) should fail to complete requests within deadline
    assert completions[2] == 0.0

    # Also verify building from manifest works
    m_interp = build_interpreter("fixed-latency-0.3")
    assert isinstance(m_interp, FixedLatencyInterpreter)
    assert m_interp.delay_s == 0.3
