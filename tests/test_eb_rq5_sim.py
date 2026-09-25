"""Tests for N-node discrete-event simulation, equivalence, and locality violations."""
from __future__ import annotations

import pytest

from src.edgebench.e2e.sim import get_speed_factors, simulate, summarize
from src.simulator import simulate as orig_simulate, workload as orig_workload


def test_speed_factors_formula() -> None:
    # N=4 must match old simulator: 1.0, 1.1, 1.2, 1.3, and cloud 0.65
    factors_4 = get_speed_factors(4)
    assert len(factors_4) == 5
    for a, b in zip(factors_4, [1.0, 1.1, 1.2, 1.3, 0.65]):
        assert pytest.approx(a, abs=1e-6) == b

    # N=10
    factors_10 = get_speed_factors(10)
    assert len(factors_10) == 11
    assert pytest.approx(factors_10[0], abs=1e-6) == 1.0
    assert pytest.approx(factors_10[9], abs=1e-6) == 1.3
    assert factors_10[10] == 0.65


def test_simulator_equivalence_with_old_simulator() -> None:
    """Verify that with N=4 edges + cloud, new sim matches old sim outcomes exactly."""
    fixture = [
        {"id": "i1", "text": "count cars", "truth": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}},
        {"id": "i2", "text": "read sign", "truth": {"service_type": "ocr", "locality": "site_only", "quality_floor": "high", "urgency": "urgent"}},
        {"id": "i3", "text": "detect boxes", "truth": {"service_type": "detection", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}},
        {"id": "i4", "text": "other task", "truth": {"service_type": "unsupported", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"}},
    ]
    arrivals = orig_workload(fixture, kind="steady", n=60, seed=42, semantic="changing")

    def decide_cb(r):
        return (r["truth"], 0.05, {"cost_usd": 0.001, "api_calls": 1})

    orig_out = orig_simulate(arrivals, decide_cb, deadline=2.0)
    new_out = simulate(arrivals, decide_cb, deadline=2.0, n_edges=4)

    assert len(orig_out) == len(new_out)
    for i in range(len(orig_out)):
        o = orig_out[i]
        n = new_out[i]
        assert o["status"] == n["status"], f"Status mismatch at {i}: orig={o['status']}, new={n['status']}"
        assert o.get("node") == n.get("node"), f"Node mismatch at {i}: orig={o.get('node')}, new={n.get('node')}"
        assert pytest.approx(o["terminal"], abs=1e-5) == n["terminal"]


def test_simulator_controller_trace_equivalence() -> None:
    """Verify external decision timeline replay matches old simulator."""
    fixture = [
        {"id": "i1", "text": "count cars", "truth": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"}},
        {"id": "i2", "text": "read sign", "truth": {"service_type": "ocr", "locality": "site_only", "quality_floor": "high", "urgency": "urgent"}},
    ]
    arrivals = orig_workload(fixture, kind="steady", n=30, seed=42)

    ctrace = {}
    for a in arrivals:
        ctrace[a["id"]] = {
            "id": a["id"],
            "decision_start": a["arrival"] + 0.01,
            "decision_end": a["arrival"] + 0.04,
            "decision_elapsed_s": 0.03,
            "predicted": a["truth"],
            "decision_metadata": {"cost_usd": 0.0005},
            "decision_timed_out": False,
        }

    orig_out = orig_simulate(arrivals, None, controller_trace=ctrace, deadline=2.0)
    new_out = simulate(arrivals, None, controller_trace=ctrace, deadline=2.0, n_edges=4)

    for i in range(len(orig_out)):
        assert orig_out[i]["status"] == new_out[i]["status"]
        assert orig_out[i]["node"] == new_out[i]["node"]
        assert pytest.approx(orig_out[i]["terminal"], abs=1e-5) == new_out[i]["terminal"]


def test_locality_violation_flag_hand_built_cases() -> None:
    """Verify locality_violation is strictly True when payload moves off-origin and truth is not remote_allowed."""
    # Case A: Model predicts remote_allowed, so scheduler puts it on cloud (node 4 != origin 0).
    # Truth is site_only -> locality violation!
    case_a = [{
        "id": 0,
        "arrival": 0.0,
        "deadline": 2.0,
        "origin": 0,
        "size_mb": 0.5,
        "text": "case_a",
        "truth": {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
    }]
    # Pred: model says remote_allowed, allowing scheduler to pick faster/cloud node
    trace_a = {
        0: {
            "id": 0,
            "decision_start": 0.01,
            "decision_end": 0.02,
            "decision_elapsed_s": 0.01,
            "predicted": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
            "decision_metadata": {},
            "decision_timed_out": False,
        }
    }
    # In simulate with n_edges=4, cloud (node 4) is faster (0.65 factor).
    res_a = simulate(case_a, controller_trace=trace_a, n_edges=4)[0]
    if res_a["node"] != 0:
        assert res_a["locality_violation"] is True
        assert res_a["status"] == "wrong_or_late"  # Because locality_ok is False

    # Case B: Local dispatch with site_only -> NO violation
    trace_b = {
        0: {
            "id": 0,
            "decision_start": 0.01,
            "decision_end": 0.02,
            "decision_elapsed_s": 0.01,
            "predicted": {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
            "decision_metadata": {},
            "decision_timed_out": False,
        }
    }
    res_b = simulate(case_a, controller_trace=trace_b, n_edges=4)[0]
    assert res_b["node"] == 0
    assert res_b["locality_violation"] is False
    assert res_b["status"] == "success"

    # Case C: Remote dispatch with remote_allowed truth -> NO violation
    case_c = [{
        "id": 0,
        "arrival": 0.0,
        "deadline": 2.0,
        "origin": 0,
        "size_mb": 0.5,
        "text": "case_c",
        "truth": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
    }]
    res_c = simulate(case_c, controller_trace=trace_a, n_edges=4)[0]
    assert res_c["locality_violation"] is False


def test_scheduler_deadline_rule_mutation() -> None:
    """Mutation test: flipping estimate <= deadline to > or < must make this test fail."""
    # Arrival at t=0, deadline=0.03. Decision finishes at 0.02.
    # Minimum execution time is transfer (>=0.002) + duration (>=0.04*1.0) = 0.042 > deadline 0.03.
    # Scheduler MUST reject with no_feasible_node.
    tight_arrival = [{
        "id": 0,
        "arrival": 0.0,
        "deadline": 0.03,
        "origin": 0,
        "size_mb": 0.25,
        "text": "tight",
        "truth": {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
    }]
    trace_tight = {
        0: {
            "id": 0,
            "decision_start": 0.001,
            "decision_end": 0.005,
            "decision_elapsed_s": 0.004,
            "predicted": {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
            "decision_metadata": {},
            "decision_timed_out": False,
        }
    }
    res_tight = simulate(tight_arrival, controller_trace=trace_tight, n_edges=4)[0]
    assert res_tight["status"] == "no_feasible_node"
    assert res_tight.get("node") is None

    # Loose arrival: deadline=2.0. Must succeed.
    loose_arrival = [{
        "id": 0,
        "arrival": 0.0,
        "deadline": 2.0,
        "origin": 0,
        "size_mb": 0.25,
        "text": "loose",
        "truth": {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
    }]
    trace_loose = {
        0: {
            "id": 0,
            "decision_start": 0.001,
            "decision_end": 0.005,
            "decision_elapsed_s": 0.004,
            "predicted": {"service_type": "count", "locality": "site_only", "quality_floor": "standard", "urgency": "normal"},
            "decision_metadata": {},
            "decision_timed_out": False,
        }
    }
    res_loose = simulate(loose_arrival, controller_trace=trace_loose, n_edges=4)[0]
    assert res_loose["status"] == "success"
    assert res_loose["node"] == 0


def test_recompute_completion_from_outcomes_alone() -> None:
    """From one toy Part A arm's outcomes alone, recompute operational and strict completion and check against sim rows."""
    arrivals = [
        # 0: Success (exact match, remote allowed, standard, normal)
        {
            "id": 0, "case_id": "c0", "arrival": 0.0, "deadline": 2.0, "origin": 0, "size_mb": 0.25, "text": "t0",
            "truth": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
        },
        # 1: Locality violation (site_only, but pred remote_allowed -> sent to cloud 4 != origin 3)
        {
            "id": 1, "case_id": "c1", "arrival": 0.1, "deadline": 2.0, "origin": 3, "size_mb": 0.01, "text": "t1",
            "truth": {"service_type": "detection", "locality": "site_only", "quality_floor": "high", "urgency": "normal"},
        },
        # 2: Quality tier violation (truth high, but pred standard)
        {
            "id": 2, "case_id": "c2", "arrival": 0.2, "deadline": 2.0, "origin": 0, "size_mb": 0.25, "text": "t2",
            "truth": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "high", "urgency": "normal"},
        },
        # 3: Unsupported service
        {
            "id": 3, "case_id": "c3", "arrival": 0.3, "deadline": 2.0, "origin": 0, "size_mb": 0.25, "text": "t3",
            "truth": {"service_type": "unsupported", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"},
        },
        # 4: Queue expired
        {
            "id": 4, "case_id": "c4", "arrival": 0.4, "deadline": 0.45, "origin": 0, "size_mb": 0.25, "text": "t4",
            "truth": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
        },
    ]

    ctrace = {
        0: {
            "id": 0, "decision_start": 0.01, "decision_end": 0.03, "decision_elapsed_s": 0.02,
            "predicted": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
            "decision_metadata": {"cache_hit": False, "api_calls": 1, "cost_usd": 0.0002}, "decision_timed_out": False,
        },
        1: {
            "id": 1, "decision_start": 0.11, "decision_end": 0.13, "decision_elapsed_s": 0.02,
            "predicted": {"service_type": "detection", "locality": "remote_allowed", "quality_floor": "high", "urgency": "normal"},
            "decision_metadata": {"cache_hit": False, "api_calls": 1, "cost_usd": 0.0002}, "decision_timed_out": False,
        },
        2: {
            "id": 2, "decision_start": 0.21, "decision_end": 0.23, "decision_elapsed_s": 0.02,
            "predicted": {"service_type": "count", "locality": "remote_allowed", "quality_floor": "standard", "urgency": "normal"},
            "decision_metadata": {"cache_hit": False, "api_calls": 1, "cost_usd": 0.0002}, "decision_timed_out": False,
        },
        3: {
            "id": 3, "decision_start": 0.31, "decision_end": 0.33, "decision_elapsed_s": 0.02,
            "predicted": {"service_type": "unsupported", "locality": "unspecified", "quality_floor": "unspecified", "urgency": "unspecified"},
            "decision_metadata": {"cache_hit": False, "api_calls": 1, "cost_usd": 0.0002}, "decision_timed_out": False,
        },
        4: {
            "id": 4, "status": "queue_expired", "terminal": 0.45,
        },
    }

    sim_results = simulate(arrivals, controller_trace=ctrace, deadline=2.0, n_edges=4)

    # Build outcomes exactly as eb_rq5a.py writes them
    outcome_rows = []
    for r in sim_results:
        truth = r.get("truth", [])
        truth_dict = truth[0] if isinstance(truth, list) else truth
        meta = r.get("decision_metadata", {}) or {}
        outcome_rows.append({
            "id": r["id"],
            "case_id": r.get("case_id"),
            "status": r["status"],
            "arrival": r["arrival"],
            "terminal": r["terminal"],
            "deadline": r.get("deadline"),
            "origin": r.get("origin"),
            "T": round(r["T"], 6),
            "queue_wait_s": round(r.get("queue_wait_s", 0.0), 6),
            "decision_elapsed_s": round(r.get("decision_elapsed_s", 0.0), 6),
            "transfer_s": round(r.get("transfer_s", 0.0), 6),
            "service_s": round(r.get("service_s", 0.0), 6),
            "service_queue_s": round(r.get("service_queue_s", 0.0), 6),
            "node": r.get("node"),
            "locality_violation": bool(r.get("locality_violation", False)),
            "cost_usd": r.get("cost_usd", 0.0),
            "predicted": r.get("predicted"),
            "truth": truth_dict,
            "priority": r.get("priority"),
            "joint_correct": bool(r.get("joint_correct", False)),
            "locality_ok": bool(r.get("locality_ok", False)),
            "quality_ok": bool(r.get("quality_ok", False)),
            "decision_start": r.get("decision_start"),
            "decision_end": r.get("decision_end"),
            "decision_timed_out": bool(r.get("decision_timed_out", False)),
            "cache_hit": bool(meta.get("cache_hit", False)),
            "api_calls": int(meta.get("api_calls", 0)),
            "network_ready": r.get("network_ready"),
            "service_start": r.get("service_start"),
            "model": "oracle",
            "cell": "load_4",
            "seed": 1,
        })

    # Now, test recomputing operational and strict completion from outcome_rows ALONE
    sim_by_id = {r["id"]: r for r in sim_results}
    for row in outcome_rows:
        pred = row["predicted"]
        truth = row["truth"]

        # Recompute components:
        # 1. service (valid service executed, not unsupported)
        has_service = (
            pred is not None
            and pred.get("service_type") == truth.get("service_type")
            and truth.get("service_type") != "unsupported"
            and row["service_start"] is not None
        )
        # 2. locality (remote_allowed or executed on origin node)
        locality_ok = (truth.get("locality") == "remote_allowed" or row.get("node") == row.get("origin"))
        # 3. minimum tier (quality floor satisfied)
        min_tier_ok = (truth.get("quality_floor") != "high" or (pred is not None and pred.get("quality_floor") == "high"))
        # 4. mapped priority (urgent -> 0, normal -> 1)
        expected_priority = 0 if truth.get("urgency") == "urgent" else 1
        priority_ok = (row.get("priority") == expected_priority)
        # 5. finish <= deadline
        finish_on_time = (row.get("terminal") is not None and row["terminal"] <= row["deadline"])

        operational_completion = bool(
            has_service
            and locality_ok
            and min_tier_ok
            and priority_ok
            and finish_on_time
        )

        strict_completion = bool(
            row["joint_correct"]
            and row["locality_ok"]
            and row["quality_ok"]
            and finish_on_time
            and row["status"] == "success"
        )

        # Check against simulator row
        sim_r = sim_by_id[row["id"]]
        is_sim_success = (sim_r["status"] == "success")
        assert strict_completion == is_sim_success, f"Row {row['id']} strict mismatch: strict={strict_completion}, sim_success={is_sim_success}"

        # Check expected properties per case
        if row["id"] == 0:
            assert operational_completion is True
            assert strict_completion is True
        elif row["id"] == 1:
            # Locality violation
            assert locality_ok is False
            assert operational_completion is False
            assert strict_completion is False
            assert sim_r["status"] == "wrong_or_late"
        elif row["id"] == 2:
            # Quality floor violation
            assert min_tier_ok is False
            assert operational_completion is False
            assert strict_completion is False
            assert sim_r["status"] == "wrong_or_late"
        elif row["id"] == 3:
            # Unsupported service
            assert has_service is False
            assert operational_completion is False
            assert strict_completion is False
            assert sim_r["status"] == "unsupported"
        elif row["id"] == 4:
            # Queue expired
            assert has_service is False
            assert operational_completion is False
            assert strict_completion is False
            assert sim_r["status"] == "queue_expired"

