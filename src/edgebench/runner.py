"""Benchmark runner orchestrating cases, models, concurrency, spend cap, and integrity checks."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
from pathlib import Path
import random
import threading
import time
from typing import Any

from src.edgebench.contract import Case, load_cases_jsonl
from src.edgebench.interpreters.base import Decision, Interpreter
from src.edgebench.interpreters.chat_json import ChatJsonClient
from src.edgebench.interpreters.transport import (
    get_post_timeout_healthy,
    get_post_timeout_wait,
    get_send_marker,
    post_json_once,
    reset_send_marker,
)
from src.edgebench.ledger import LedgerWriter, completed_keys, resolve_git_provenance
from src.edgebench.manifest import build_interpreter, load_manifest
from src.edgebench.provenance import sha256_file, verify_listed_file
from src.edgebench.scoring import score_decision

# Connection-level failures (no HTTP status) that mean a self-hosted server process is gone.
SERVER_DOWN_ERRORS = frozenset(
    {"ConnectionRefusedError", "RemoteDisconnected", "ConnectionResetError", "BrokenPipeError"}
)
WARMUP_TIMEOUT_S = 3600.0
# Consecutive HTTP 5xx from a self-hosted server that stop the run (4xx are by-design outcomes, e.g. K limits).
SERVER_ERROR_STREAK_STOP = 3


def load_subset_ids(repeats_subset_path: str | Path | None) -> set[str]:
    if not repeats_subset_path:
        return set()
    p = Path(repeats_subset_path)
    if str(p).lower() == "none" or not p.exists():
        return set()

    with open(p, "r", encoding="utf-8") as f:
        content = f.read().strip()
        if not content:
            return set()
        if content.startswith("["):
            try:
                data = json.loads(content)
                return {str(x) for x in data}
            except Exception:
                pass
        return {line.strip() for line in content.splitlines() if line.strip()}


def warmup_schemas(model: ChatJsonClient, cases: list[Case]) -> dict[str, Any]:
    """POST /warmup with every distinct response schema of the condition, before any timed request.

    The server compiles and caches its constrained-decoding processors (untimed, no ledger row).
    A server without the endpoint (404) is a no-op. Returns the record stored in integrity.json.
    """
    schemas: list[dict[str, Any]] = []
    seen: set[str] = set()
    for case in cases:
        schema = model.build_schema(case)
        key = json.dumps(schema)
        if key not in seen:
            seen.add(key)
            schemas.append(schema)
    record: dict[str, Any] = {"n_schemas": len(schemas), "http_status": None, "error": None,
                              "client_s": None, "schemas": []}
    t0 = time.perf_counter()
    try:
        status, body = post_json_once(model.base_url, "/warmup", {"schemas": schemas}, timeout_s=WARMUP_TIMEOUT_S)
    except Exception as exc:
        record["error"] = type(exc).__name__
        return record
    record["client_s"] = time.perf_counter() - t0
    record["http_status"] = status
    if status == 200:
        try:
            record["schemas"] = json.loads(body).get("schemas", [])
        except Exception:
            record["error"] = "bad_warmup_response"
    elif status != 404:
        record["error"] = f"HTTP_{status}"
    return record


def run_benchmark(
    cases_path: str | Path,
    rq: str,
    condition: str,
    model_names: list[str],
    out_dir: str | Path,
    repeats_subset_path: str | Path | None = None,
    workers: int = 4,
    seed: int = 20260924,
    spend_cap_usd: float = 20.0,
    allow_dirty: bool = False,
    manifest_path: str | Path | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Run Edgebench benchmark over cases with specified models.

    `base_url` overrides the manifest URL of the (self-hosted) models, e.g. the per-job port on the cluster.
    """
    git_sha, is_dirty, git_source, provenance_tree_sha256 = resolve_git_provenance()
    if is_dirty and not allow_dirty:
        raise RuntimeError(
            "Refusing to start: git working tree has modified tracked files. Pass --allow-dirty to proceed."
        )
    # Bind the cases file: its hash goes into integrity.json and every row; without git it must be listed
    # in PROVENANCE.json with this hash.
    if git_source == "provenance":
        cases_sha256 = verify_listed_file(cases_path)
    else:
        cases_sha256 = sha256_file(Path(cases_path))

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    ledger_path = out / "ledger.jsonl"
    integrity_path = out / "integrity.json"

    # Load manifest and build interpreters
    manifest = load_manifest(manifest_path)
    interpreters: list[Interpreter] = [
        build_interpreter(name, manifest=manifest, api_key=api_key, base_url=base_url, condition=condition)
        for name in model_names
    ]
    effective_base_urls = {m.name: getattr(m, "base_url", None) for m in interpreters}

    # Validate self-hosted vs hosted
    has_self_hosted = any(m.deployment == "self-hosted" for m in interpreters)
    has_hosted = any(m.deployment == "hosted" for m in interpreters)
    if has_self_hosted and has_hosted:
        raise ValueError(
            "Refusing to mix self-hosted models with hosted models in a single invocation."
        )
    if has_self_hosted:
        workers = 1

    # Load cases
    raw_cases = load_cases_jsonl(cases_path)
    if not raw_cases:
        raise ValueError(f"No cases found in {cases_path}")

    # Shuffle with seed + stable hash(condition)
    cond_hash = int(hashlib.sha256(condition.encode("utf-8")).hexdigest()[:8], 16)
    combined_seed = (seed + cond_hash) & 0x7FFFFFFF
    rng = random.Random(combined_seed)
    cases = list(raw_cases)
    rng.shuffle(cases)

    # Load repeats subset
    subset_ids = load_subset_ids(repeats_subset_path)

    # Open the ledger first: a torn final line (crash mid-write) is dropped before resume reads the keys.
    run_id = f"{rq}_{condition}_{seed}"
    ledger_writer = LedgerWriter(
        path=ledger_path,
        run_id=run_id,
        git_sha=git_sha,
        rq=rq,
        condition=condition,
        allow_dirty=allow_dirty,
        git_source=git_source,
        provenance_tree_sha256=provenance_tree_sha256,
        cases_sha256=cases_sha256,
    )

    # Resume: completed keys
    completed = completed_keys(ledger_path)

    state_lock = threading.Lock()
    total_spend = 0.0
    stop_requested = False
    stop_reason: str | None = None
    server_error_streak: dict[str, int] = {}

    # Track pre-existing costs for completed keys within current (rq, condition) scope
    if ledger_path.exists():
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                    if str(row.get("rq")) == rq and str(row.get("condition")) == condition:
                        if row.get("cost_usd") is not None:  # null = not reported (counted in integrity)
                            total_spend += float(row["cost_usd"])
                except Exception:
                    pass

    # Compile constrained-decoding schemas outside the timed loop (every invocation, so resume re-warms).
    schema_warmup: dict[str, Any] = {
        m.name: warmup_schemas(m, cases)
        for m in interpreters
        if isinstance(m, ChatJsonClient) and m.deployment == "self-hosted"
    }

    def process_case(case: Case) -> None:
        nonlocal total_spend, stop_requested, stop_reason

        repeats_for_case = [0]
        if case.case_id in subset_ids:
            repeats_for_case.extend([1, 2])

        for repeat in repeats_for_case:
            with state_lock:
                if stop_requested:
                    return

            # Per-case seeded random order
            case_seed = f"{seed}:{condition}:{case.case_id}:{repeat}"
            case_rng = random.Random(case_seed)
            case_models = list(interpreters)
            case_rng.shuffle(case_models)

            for model in case_models:
                with state_lock:
                    if stop_requested:
                        return
                    key = (rq, condition, model.name, str(case.case_id), repeat)
                    if key in completed:
                        continue

                reset_send_marker()
                try:
                    decision = model.decide(case)
                except Exception as exc:
                    t_exc_perf = time.perf_counter()
                    t_exc_wall = time.time()
                    default_labels = [
                        {f: "unspecified" for f in case.fields}
                        for _ in range(case.bundle_size)
                    ]
                    # Latency = send -> exception when a request went out; None when nothing was sent.
                    sent = get_send_marker()
                    decision = Decision(
                        labels=default_labels,
                        valid=False,
                        error_type=type(exc).__name__,
                        latency_s=(t_exc_perf - sent[1]) if sent else None,
                        t_send_wall=sent[0] if sent else 0.0,
                        t_recv_wall=t_exc_wall if sent else 0.0,
                        provider=getattr(model, "provider_slug", getattr(model, "expected_provider", "")),
                    )

                decision.post_timeout_wait_s = get_post_timeout_wait()
                server_unhealthy_after_timeout = get_post_timeout_healthy() is False
                score_res = score_decision(decision, case)
                correct, em, unsafe_locality, spurious_count, missed_count, unspecified_truth_count, specified_truth_count = score_res[:7]
                request_em = score_res.request_em
                request_field_correct = score_res.request_field_correct

                with state_lock:
                    ledger_writer.write_row(
                        model=model.name,
                        case_id=case.case_id,
                        repeat=repeat,
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
                        platform=getattr(model, "platform", None),
                    )
                    completed.add(key)
                    if decision.cost_usd is not None:
                        total_spend += decision.cost_usd
                    if decision.http_status is not None and 500 <= decision.http_status < 600:
                        server_error_streak[model.name] = server_error_streak.get(model.name, 0) + 1
                    else:
                        server_error_streak[model.name] = 0

                    # Check spend cap
                    if total_spend >= spend_cap_usd and not stop_requested:
                        stop_requested = True
                        stop_reason = f"spend_cap_exceeded (${total_spend:.4f} >= ${spend_cap_usd})"

                    # Check stop conditions
                    if not stop_requested:
                        if decision.http_status in (401, 403):
                            stop_requested = True
                            stop_reason = f"HTTP_{decision.http_status}"
                        elif decision.error_type == "model_mismatch":
                            stop_requested = True
                            stop_reason = "model_mismatch"
                        elif decision.error_type == "reasoning_tokens_nonzero":
                            stop_requested = True
                            stop_reason = "reasoning_tokens_nonzero"
                        elif (
                            model.deployment == "self-hosted"
                            and decision.http_status is None
                            and decision.error_type in SERVER_DOWN_ERRORS
                        ):
                            # Keep this row (a real invalid outcome); send nothing more. Resume re-sends the rest.
                            stop_requested = True
                            stop_reason = "self_hosted_server_down"
                        elif model.deployment == "self-hosted" and server_unhealthy_after_timeout:
                            # Hung server: /health not 200 within the post-timeout wait. Keep the timed-out row,
                            # send nothing more (PBS restarts the server once and resumes).
                            stop_requested = True
                            stop_reason = "self_hosted_server_down"
                        elif (
                            model.deployment == "self-hosted"
                            and server_error_streak[model.name] >= SERVER_ERROR_STREAK_STOP
                        ):
                            # Persistent server errors: keep these rows, send nothing more (resume re-sends the rest).
                            stop_requested = True
                            stop_reason = "self_hosted_server_error"

    # Execute with worker pool
    if workers > 1:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [executor.submit(process_case, case) for case in cases]
            for f in as_completed(futures):
                try:
                    f.result()
                except Exception as exc:
                    with state_lock:
                        stop_requested = True
                        stop_reason = stop_reason or f"exception_{type(exc).__name__}"
    else:
        for case in cases:
            process_case(case)
            if stop_requested:
                break

    ledger_writer.close()

    # Integrity calculation
    actual_rows: list[dict[str, Any]] = []
    if ledger_path.exists():
        with open(ledger_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        actual_rows.append(json.loads(line))
                    except Exception:
                        pass

    # Filter to this rq and condition
    relevant_rows = [
        r for r in actual_rows if r.get("rq") == rq and r.get("condition") == condition
    ]

    expected_rows_per_model_repeat: dict[str, int] = {}
    actual_rows_per_model_repeat: dict[str, int] = {}

    subset_cases_count = len([c for c in cases if c.case_id in subset_ids])
    for m in model_names:
        expected_rows_per_model_repeat[f"{m}:r0"] = len(cases)
        expected_rows_per_model_repeat[f"{m}:r1"] = subset_cases_count
        expected_rows_per_model_repeat[f"{m}:r2"] = subset_cases_count

        for r_num in (0, 1, 2):
            key_str = f"{m}:r{r_num}"
            count = len(
                [
                    r
                    for r in relevant_rows
                    if r.get("model") == m and r.get("repeat") == r_num
                ]
            )
            actual_rows_per_model_repeat[key_str] = count

    # Duplicates check
    seen_row_keys: set[tuple[str, str, str, str, int]] = set()
    duplicate_count = 0
    for r in relevant_rows:
        row_key = (
            str(r["rq"]),
            str(r["condition"]),
            str(r["model"]),
            str(r["case_id"]),
            int(r["repeat"]),
        )
        if row_key in seen_row_keys:
            duplicate_count += 1
        seen_row_keys.add(row_key)

    # Error counts by type
    error_counts: dict[str, int] = {}
    resolved_models: dict[str, set[str]] = {m: set() for m in model_names}
    cost_per_model: dict[str, float | None] = {m: None for m in model_names}

    for r in relevant_rows:
        m = r.get("model", "")
        if r.get("error_type"):
            err = str(r["error_type"])
            error_counts[err] = error_counts.get(err, 0) + 1
        if m in resolved_models and r.get("resolved_model"):
            resolved_models[m].add(str(r["resolved_model"]))
        if m in cost_per_model and r.get("cost_usd") is not None:
            cost_per_model[m] = (cost_per_model[m] or 0.0) + float(r["cost_usd"])

    integrity_report: dict[str, Any] = {
        "run_id": run_id,
        "git_sha": git_sha,
        "git_source": git_source,
        "provenance_tree_sha256": provenance_tree_sha256,
        "cases_path": str(cases_path),
        "cases_sha256": cases_sha256,
        "effective_base_urls": effective_base_urls,
        "rq": rq,
        "condition": condition,
        "stop_reason": stop_reason,
        "torn_line_dropped": ledger_writer.torn_line_dropped,
        "total_spend_usd": total_spend,
        "expected_rows_per_model_repeat": expected_rows_per_model_repeat,
        "actual_rows_per_model_repeat": actual_rows_per_model_repeat,
        "duplicates": duplicate_count,
        "error_counts_by_type": error_counts,
        "resolved_model_ids_seen": {
            m: sorted(list(resolved_models[m])) for m in model_names
        },
        "total_cost_per_model": cost_per_model,
        # null usage / cost = not reported; reasoning disabled but reasoning_tokens absent = not verifiable
        "cost_unknown_rows": sum(r.get("cost_usd") is None for r in relevant_rows),
        "usage_unreported_rows": sum(r.get("usage_reported") is False for r in relevant_rows),
        "reasoning_tokens_missing_rows": sum(bool(r.get("reasoning_tokens_missing")) for r in relevant_rows),
        "schema_warmup": schema_warmup,
    }

    with open(integrity_path, "w", encoding="utf-8") as f:
        json.dump(integrity_report, f, indent=2)

    return integrity_report
