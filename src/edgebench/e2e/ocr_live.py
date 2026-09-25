"""Dispatch real OCR across 3 Dockerised testbed nodes as each admission finishes.

Supports 3 nodes (local, edge2, cloud) and the Interpreter interface.
"""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
import time
from typing import Any, Callable

from src.edgebench.e2e.admission import run_admission
from src.edgebench.e2e.traces import absolute_deadline
from src.edgebench.interpreters.base import Interpreter
from src.edgebench.ledger import LedgerWriter
from src.ocr_client import character_error_rate, normalize, recognize
from src.schema import FIELDS


def score_ocr(row: dict[str, Any], result: dict[str, Any], deadline: float = 2.0) -> dict[str, Any]:
    """Score a single OCR testbed result against ground truth."""
    truth = row["truth"]
    truth_dict = truth[0] if isinstance(truth, list) else truth
    predicted = result.get("predicted")
    ocr = result.get("ocr", {})

    supported = (truth_dict.get("service_type") == "ocr")
    actual_ocr = result.get("dispatched", False)
    valid_output = (result.get("status") == "ocr_returned") and (ocr.get("status") == "ok")

    output_ok = (
        valid_output
        and normalize(ocr.get("text", "")) == normalize(row.get("ground_truth", ""))
    )
    locality_ok = actual_ocr and (
        truth_dict.get("locality") == "remote_allowed" or result.get("node") == "local"
    )
    tier_ok = actual_ocr and (
        truth_dict.get("quality_floor") != "high" or result.get("tier") == "high"
    )
    expected_priority = 0 if truth_dict.get("urgency") == "urgent" else 1
    priority_ok = actual_ocr and (result.get("priority") == expected_priority)
    timely = result.get("terminal", float("inf")) <= absolute_deadline(row, deadline)

    correct_completion = bool(
        supported and actual_ocr and output_ok and locality_ok and tier_ok and priority_ok and timely
    )
    false_accept = bool(not supported and actual_ocr)
    correct_rejection = bool(not supported and result.get("status") in ("unsupported", "undeployed"))

    # Offsite violation: payload sent to non-local node without remote_allowed
    is_remote = result.get("node") is not None and result.get("node") != "local"
    is_locality_violation = is_remote and (truth_dict.get("locality") != "remote_allowed")
    offsite_bytes = result.get("sent_bytes", 0) if is_locality_violation else 0

    return dict(
        supported=supported,
        strict_semantic=(predicted == truth_dict),
        output_exact=output_ok,
        output_case_insensitive=(
            valid_output
            and normalize(ocr.get("text", "")).casefold() == normalize(row.get("ground_truth", "")).casefold()
        ),
        cer=character_error_rate(ocr.get("text", ""), row.get("ground_truth", "")) if valid_output else None,
        locality_ok=locality_ok,
        tier_ok=tier_ok,
        priority_ok=priority_ok,
        timely=timely,
        correct_completion=correct_completion,
        false_accept=false_accept,
        correct_rejection=correct_rejection,
        offsite_violation_bytes=offsite_bytes,
        locality_violation=bool(is_locality_violation),
    )


async def run_online_ocr(
    arrivals: list[dict[str, Any]],
    interpreter: Interpreter,
    urls: dict[str, str],
    estimates: dict[str, dict[str, float]],
    *,
    cache_enabled: bool = False,
    deadline: float = 2.0,
    concurrency: int = 4,
    queue_limit: int = 32,
    service_limit: int = 16,
    ledger_writer: LedgerWriter | None = None,
    seed: int = 1,
    condition: str = "default",
    stopped: Callable[[], bool] = lambda: False,
    event_sink: Callable[[dict[str, Any]], None] = lambda r: None,
    transport: Callable[..., dict[str, Any]] = recognize,
    executor: ThreadPoolExecutor | None = None,
) -> list[dict[str, Any]]:
    """Run real OCR testbed with live admission and 3 priority queues."""
    start = time.monotonic()
    now = lambda: time.monotonic() - start

    queues = {n: asyncio.PriorityQueue(maxsize=service_limit) for n in urls}
    state = {n: dict(active_end=0.0, pending={}) for n in urls}
    results: dict[int, dict[str, Any]] = {}
    rows = {r["id"]: r for r in arrivals}
    sequence = 0
    broken = False

    def finish(result: dict[str, Any]) -> None:
        result["score"] = score_ocr(rows[result["id"]], result, deadline)
        results[result["id"]]= result
        event_sink(dict(event="task_finished", **result))

    async def worker(node: str) -> None:
        nonlocal broken
        while True:
            priority, order, result = await queues[node].get()
            state[node]["pending"].pop(order, None)
            row = rows[result["id"]]
            try:
                begin = now()
                if broken or begin >= absolute_deadline(row, deadline):
                    result.update(
                        status="service_queue_expired" if not broken else "service_aborted",
                        terminal=begin,
                    )
                    finish(result)
                    continue

                tier = result["tier"]
                state[node]["active_end"] = begin + estimates[node][tier]

                image_path = Path(row["image_path"])
                data = image_path.read_bytes()
                if hashlib.sha256(data).hexdigest() != row["image_sha256"]:
                    raise ValueError(f"Image identity mismatch for {row['id']}")

                result.update(dispatched=True, service_dispatch=begin, sent_bytes=len(data))
                event_sink(dict(event="ocr_dispatch", id=row["id"], node=node, at=begin, sent_bytes=len(data)))

                answer = await asyncio.to_thread(transport, urls[node], data, str(row["id"]), tier, priority)
                end = now()
                result.update(
                    ocr=answer,
                    terminal=end,
                    origin_service_s=end - begin,
                    status="ocr_returned" if answer.get("status") == "ok" else "ocr_error",
                )

                if (
                    answer.get("node") != node
                    or answer.get("tier") != tier
                    or answer.get("priority") != priority
                    or answer.get("image_sha256") != row["image_sha256"]
                ):
                    raise ValueError("Unexpected OCR response identity")
                finish(result)

            except Exception as exc:
                broken = True
                result.update(
                    status="service_transport_or_integrity_error",
                    terminal=now(),
                    error_type=type(exc).__name__,
                )
                finish(result)
            finally:
                state[node]["active_end"] = 0.0
                queues[node].task_done()

    def admitted(trace: dict[str, Any]) -> None:
        nonlocal sequence
        row = rows[trace["id"]]
        result = dict(trace)
        result["is_ocr"] = row.get("is_ocr", True)
        truth = row.get("truth", [])
        result["truth"] = truth[0] if isinstance(truth, list) else truth
        labels = trace.get("predicted")

        if broken or stopped():
            result.update(status="aborted", terminal=now())
            finish(result)
            return

        if trace.get("status") != "decision_recorded" or labels is None:
            result.update(terminal=now())
            finish(result)
            return

        end = trace["decision_end"]
        if end >= absolute_deadline(row, deadline):
            result.update(status="decision_late", terminal=now())
            finish(result)
            return

        if set(labels) != set(FIELDS) or any(labels[f] not in vals for f, vals in FIELDS.items()):
            result.update(status="invalid_labels", terminal=now())
            finish(result)
            return

        if labels["service_type"] != "ocr":
            result.update(
                status="unsupported" if labels["service_type"] == "unsupported" else "undeployed",
                terminal=now(),
            )
            finish(result)
            return

        tier = "high" if labels["quality_floor"] == "high" else "standard"
        priority = 0 if labels["urgency"] == "urgent" else 1

        candidates = []
        current = now()
        for node in urls:
            if node != "local" and labels["locality"] != "remote_allowed":
                continue
            if queues[node].full():
                continue
            wait = max(0.0, state[node]["active_end"] - current)
            wait += sum(estimates[node][t] for p, t in state[node]["pending"].values() if p <= priority)
            estimated = current + wait + estimates[node][tier]
            if estimated <= absolute_deadline(row, deadline):
                # Ties broken by local preference (node != 'local' is 0 for local, 1 for remote)
                candidates.append((estimated, int(node != "local"), node))

        if not candidates:
            result.update(status="no_feasible_node", terminal=current)
            finish(result)
            return

        estimated, _, node = min(candidates)
        result.update(
            node=node,
            tier=tier,
            priority=priority,
            service_enqueued=current,
            estimated_finish=estimated,
        )
        sequence += 1
        state[node]["pending"][sequence] = (priority, tier)
        queues[node].put_nowait((priority, sequence, result))

    workers = [asyncio.create_task(worker(n)) for n in urls]
    try:
        with (ThreadPoolExecutor(max_workers=concurrency) if executor is None else nullcontext(executor)) as pool:
            await run_admission(
                arrivals=arrivals,
                interpreter=interpreter,
                cache_enabled=cache_enabled,
                concurrency=concurrency,
                deadline=deadline,
                queue_limit=queue_limit,
                executor=pool,
                ledger_writer=ledger_writer,
                seed=seed,
                condition=condition,
                stopped=lambda: broken or stopped(),
                event_sink=admitted,
                start_time=start,
            )
        await asyncio.gather(*(q.join() for q in queues.values()))
    finally:
        for task in workers:
            task.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    if len(results) != len(arrivals):
        raise RuntimeError(f"Missing terminal records: got {len(results)}/{len(arrivals)}")
    return [results[r["id"]] for r in arrivals]
