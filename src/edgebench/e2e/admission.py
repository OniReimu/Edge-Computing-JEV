"""Live wall-clock admission with bounded slots, queue limit, and edgebench ledger integration."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
from pathlib import Path
import time
from typing import Any, Callable

from src.edgebench.contract import Case
from src.edgebench.e2e.traces import absolute_deadline
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.ledger import LedgerWriter
from src.edgebench.scoring import score_decision
from src.intent_cache import IntentCache


class RunStopped(RuntimeError):
    """Raised when admission run is aborted prematurely."""
    pass


def make_case_from_row(row: dict[str, Any]) -> Case:
    """Convert an arrival trace row to an Edgebench Case."""
    truth = row.get("truth", [])
    if isinstance(truth, dict):
        truth_list = [truth]
    elif isinstance(truth, list):
        truth_list = truth
    else:
        truth_list = []
    
    case_id = str(row.get("case_id", row.get("id", "0")))
    text = row.get("text", "")
    fields = row.get("fields", ["service_type", "locality", "quality_floor", "urgency"])
    return Case(case_id=case_id, text=text, fields=fields, truth=truth_list)


async def run_admission(
    arrivals: list[dict[str, Any]],
    interpreter: Interpreter,
    cache_enabled: bool = False,
    concurrency: int = 4,
    deadline: float = 2.0,
    queue_limit: int = 32,
    executor: ThreadPoolExecutor | None = None,
    ledger_writer: LedgerWriter | None = None,
    seed: int = 1,
    condition: str = "default",
    stopped: Callable[[], bool] = lambda: False,
    event_sink: Callable[[dict[str, Any]], None] = lambda r: None,
    start_time: float | None = None,
) -> dict[int, dict[str, Any]]:
    """Run live wall-clock admission using an Interpreter.

    Semantics:
    - Exactly `concurrency` parallel slots held while calling `interpreter.decide(case)`.
    - Waiting queue limited to `queue_limit` pending arrivals.
    - Deadline-bounded queueing (arrivals that expire while waiting or upon arrival receive queue_expired).
    - Cache checked on arrival and after slot acquisition.
    - An in-flight slot is held until the thread call returns, even if the service deadline has passed.
    - Every interpreter call is recorded to the edgebench ledger.
    """
    start = time.monotonic() if start_time is None else start_time
    loop = asyncio.get_running_loop()
    semaphore = asyncio.Semaphore(concurrency)
    cache = cache_enabled if isinstance(cache_enabled, IntentCache) else (IntentCache() if cache_enabled else None)
    traces: dict[int, dict[str, Any]] = {}
    waiting = 0
    request_counter = itertools.count(1)

    def now() -> float:
        return time.monotonic() - start

    def save(r: dict[str, Any]) -> None:
        traces[r["id"]] = r
        event_sink(r)

    def cached(row: dict[str, Any], r: dict[str, Any]) -> bool:
        begin = now()
        labels = cache.lookup(row["text"], begin) if cache else None
        if labels is None:
            return False
        end = now()
        r.update(
            queue_wait_s=begin - row["arrival"],
            decision_start=begin,
            decision_end=end,
            decision_elapsed_s=end - begin,
            predicted=labels,
            decision_timed_out=False,
            status="decision_recorded",
            decision_metadata={"cache_hit": True, "api_calls": 0, "cost_usd": 0.0},
        )
        save(r)
        return True

    def call_interpreter(row: dict[str, Any]) -> dict[str, Any]:
        req_idx = next(request_counter)
        case = make_case_from_row(row)
        t0 = time.monotonic()
        try:
            decision = interpreter.decide(case)
        except Exception as exc:
            decision = Decision(
                valid=False,
                error_type=type(exc).__name__,
                latency_s=time.monotonic() - t0,
            )
        elapsed = time.monotonic() - t0

        # Score decision against ground truth
        try:
            score = score_decision(decision, case)
        except Exception:
            score = None

        # Write to ledger
        if ledger_writer is not None:
            correct = score.correct if score else {}
            em = score.em if score else False
            unsafe_locality = score.unsafe_locality if score else False
            spurious_count = score.spurious_count if score else 0
            missed_count = score.missed_count if score else 0
            unspecified_truth_count = score.unspecified_truth_count if score else 0
            specified_truth_count = score.specified_truth_count if score else 0
            request_em = score.request_em if score else [False]
            request_field_correct = score.request_field_correct if score else [{}]

            ledger_writer.write_row(
                model=interpreter.name,
                case_id=case.case_id,
                repeat=seed,
                decision=decision,
                correct=correct,
                em=em,
                unsafe_locality=unsafe_locality,
                spurious_count=spurious_count,
                missed_count=missed_count,
                unspecified_truth_count=unspecified_truth_count,
                specified_truth_count=specified_truth_count,
                request_em=request_em,
                request_field_correct=request_field_correct,
                platform=getattr(interpreter, "platform", None),
            )

        labels = decision.labels[0] if (decision.valid and decision.labels) else None
        status = "ok" if (decision.valid and labels is not None) else "error"
        return {
            "status": status,
            "labels": labels,
            "decision": decision,
            "cost_usd": decision.cost_usd,
            "request_index": req_idx,
            "decision_elapsed_s": elapsed,
            "error_type": decision.error_type,
        }

    async def arrive(row: dict[str, Any]) -> None:
        nonlocal waiting
        # Schedule arrival at row['arrival']
        target_arrival = row["arrival"]
        await asyncio.sleep(max(0.0, target_arrival - now()))
        observed = now()
        r: dict[str, Any] = {
            "id": row["id"],
            "arrival": target_arrival,
            "observed_arrival": observed,
            "arrival_lag_s": observed - target_arrival,
        }

        if stopped():
            r.update(status="aborted_before_dispatch", terminal=observed)
            save(r)
            return

        expires = absolute_deadline(row, deadline)
        # Admission deadline check: if already expired upon arrival
        if observed >= expires:
            r.update(status="queue_expired", terminal=expires)
            save(r)
            return

        # Check cache upon arrival
        if cached(row, r):
            return

        # Queue limit check when all slots are busy
        if semaphore.locked() and waiting >= queue_limit:
            r.update(status="queue_overflow", terminal=observed)
            save(r)
            return

        waiting += 1
        acquired = False
        try:
            time_left = max(0.0, expires - now())
            try:
                await asyncio.wait_for(semaphore.acquire(), timeout=time_left)
                acquired = True
            except asyncio.TimeoutError:
                r.update(status="queue_expired", terminal=expires)
                save(r)
                return
            finally:
                waiting -= 1

            if stopped():
                r.update(status="aborted_before_dispatch", terminal=now())
                save(r)
                return

            # Check deadline expiry after acquiring slot
            if now() >= expires:
                r.update(status="queue_expired", terminal=expires)
                save(r)
                return

            # Check cache again after waiting for a slot
            if cached(row, r):
                return

            begin = now()
            try:
                response = await loop.run_in_executor(executor, call_interpreter, row)
            except RunStopped:
                r.update(status="aborted_before_dispatch", terminal=now())
                save(r)
                return

            end = now()
            labels = response.get("labels") if response.get("status") == "ok" else None
            if cache and labels is not None:
                cache.store(row["text"], labels, end)

            is_timeout = response.get("error_type") in ("TimeoutError", "timeout", "ReadTimeout")
            r.update(
                queue_wait_s=begin - target_arrival,
                decision_start=begin,
                decision_end=end,
                decision_elapsed_s=end - begin,
                predicted=labels,
                decision_timed_out=is_timeout,
                error_type=response.get("error_type"),
                status="decision_recorded",
                decision_metadata={
                    "cache_hit": False,
                    "api_calls": 1,
                    "cost_usd": response.get("cost_usd"),
                    "api_request_index": response.get("request_index"),
                    "api_status": response.get("status"),
                },
            )
            save(r)
        finally:
            if acquired:
                semaphore.release()

    await asyncio.gather(*[arrive(row) for row in arrivals])
    return traces


def run_live_admission_arm(
    arrivals: list[dict[str, Any]],
    interpreter: Interpreter,
    cache_enabled: bool,
    concurrency: int,
    deadline: float,
    queue_limit: int,
    ledger_writer: LedgerWriter | None,
    out_dir: Path,
    seed: int = 1,
    cell: str = "default",
    stopped: Callable[[], bool] = lambda: False,
) -> dict[int, dict[str, Any]]:
    """Execute live admission arm synchronously, writing admission.jsonl."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    admission_path = out_dir / "admission.jsonl"
    
    with open(admission_path, "w", encoding="utf-8") as stream:
        def sink(row: dict[str, Any]) -> None:
            stream.write(json.dumps(row) + "\n")
            stream.flush()

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            return asyncio.run(
                run_admission(
                    arrivals=arrivals,
                    interpreter=interpreter,
                    cache_enabled=cache_enabled,
                    concurrency=concurrency,
                    deadline=deadline,
                    queue_limit=queue_limit,
                    executor=executor,
                    ledger_writer=ledger_writer,
                    seed=seed,
                    condition=cell,
                    stopped=stopped,
                    event_sink=sink,
                )
            )
