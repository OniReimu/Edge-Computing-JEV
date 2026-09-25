#!/usr/bin/env python3
"""EdgeIntent v1 Corpus Builder CLI.

Subcommands:
  catalog   - build services.json (254 edge services in 16 families + 40 novel services) and catalogs.json
  tuples    - sample label tuples per condition with balanced marginals and disjoint seeds
  generate  - exchange generation batches of 10 through the file exchange and ingest the returned texts
              (EdgeIntent v1 texts were written by Gemini-3.8-Flash and Claude-Opus-5.5)
  verify    - exchange blind-verification batches of 10 (EdgeIntent v1 verifier: Claude-Opus-5.5)
  noise     - derive noise from RQ2 clean programmatically
  pad       - produce padded lengths {512, 2048, 8192, 16384} for RQ1a
  bundle    - produce multi-request bundles {1, 2, 4, 8} for RQ1b
  assemble  - assemble final Case jsonl files, timing subsets, and manifest.json
  stats     - compute token percentiles, marginals, yields, and write stats.md
  pilot     - execute pilot build (20 tuples for RQ2/clean, RQ3/F8_high, RQ4/K254)
  requeue-ver - send items of anchored ver batches (or listed items) back to done_gen and archive the batch files
  requeue-gen - withdraw gen todo batches without a done file; their items are exported again from the current catalog
  retarget  - give RQ4 unsupported items a new unsupported target from the condition's pool and regenerate them
  freeze-status - per (condition, split): accepted/target and frozen yes/no (read-only)
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.edgebench.contract import Case, load_cases_jsonl
from src.edgebench.corpus.assemble import (
    check_frozen_outputs,
    compute_sha256,
    generate_manifest,
    generate_stats_markdown,
    load_frozen,
    select_stratified_timing_subset,
    write_frozen_outputs,
    write_timing_subset_file,
)
from src.edgebench.corpus.bundle import BUNDLE_SIZES, create_bundle_messages
from src.edgebench.corpus.catalog import (
    build_nested_and_churn_catalogs,
    get_services_catalog,
    load_catalogs,
    load_services,
    save_catalogs,
)
from src.edgebench.corpus.client import CorpusLLMClient, GENERATOR_MODEL, VERIFIER_MODEL
from src.edgebench.corpus.exchange import CorpusExchange, ALL_CONDITIONS, freeze_status
from src.edgebench.corpus.noise import derive_noise_cases
from src.edgebench.corpus.pad import TARGET_LENGTHS, create_padded_dataset
from src.edgebench.corpus.pipeline import CorpusPipeline, VerifiedCase
from src.edgebench.corpus.tuples import TupleItem, is_rq4_condition, sample_tuples_for_condition

DEFAULT_DATA_DIR = "data/edgebench/v1"
DEFAULT_EXCHANGE_DIR = "runs/_corpus_exchange"


def cmd_catalog(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    cat_dir = data_dir / "catalog"
    print(f"Building catalog in {cat_dir}...")
    services_file, catalogs_file = save_catalogs(cat_dir, seed=args.seed)
    print(f"Catalog successfully built:\n  {services_file}\n  {catalogs_file}")


def cmd_tuples(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    cat_dir = data_dir / "catalog"
    if not (cat_dir / "catalogs.json").exists():
        save_catalogs(cat_dir, seed=args.seed)

    catalogs = load_catalogs(cat_dir)
    services_data = load_services(cat_dir)
    novel_ids = [s["id"] for s in services_data["novel_services"]]

    out_tuples_dir = data_dir / "_tuples"
    out_tuples_dir.mkdir(parents=True, exist_ok=True)

    conditions = [args.condition] if args.condition else [
        "clean", "colloquial", "negation", "codeswitch", "defaultbait", "revised", "keyvalue",
        "F4_low", "F4_medium", "F4_high",
        "F6_low", "F6_medium", "F6_high",
        "F8_low", "F8_medium", "F8_high",
        "K4", "K15", "K64", "K128", "K254", "churn25", "churn50",
    ]

    for cond in conditions:
        for split, n in [("test", args.n_test), ("dev", args.n_dev)]:
            items = sample_tuples_for_condition(
                condition=cond,
                split=split,
                n=n,
                base_seed=args.seed,
                catalogs=catalogs,
                novel_service_ids=novel_ids,
            )
            out_file = out_tuples_dir / f"{cond}_{split}.jsonl"
            with open(out_file, "w", encoding="utf-8") as f:
                for it in items:
                    f.write(json.dumps(it.to_dict()) + "\n")
            print(f"Sampled {len(items)} tuples for {cond} ({split}) -> {out_file}")


def _parse_csv(value: str | None) -> list[str] | None:
    return [v.strip() for v in value.split(",") if v.strip()] if value is not None else None


def _parse_splits(value: str | None) -> list[str] | None:
    splits = _parse_csv(value)
    bad = sorted(set(splits or []) - {"test", "dev"})
    if bad or splits == []:
        raise ValueError(f"--splits must name test and/or dev, got {value!r}")
    return splits


def _frozen_clean_cases(data_dir: Path, splits: list[str]) -> dict[str, list[Case]]:
    """The frozen RQ2/clean file of each split; refuse if a split is not frozen or its file differs from the record."""
    frozen = load_frozen(data_dir)
    out: dict[str, list[Case]] = {}
    for split in splits:
        key = f"RQ2/clean/{split}"
        clean_file = data_dir / "RQ2" / "clean" / f"{split}.jsonl"
        if key not in frozen:
            raise ValueError(f"{key} is not frozen; run: assemble --conditions clean --splits {split}")
        if not clean_file.exists() or compute_sha256(clean_file) != frozen[key]["sha256"]:
            raise ValueError(f"{clean_file} does not match its frozen record in _frozen.json")
        out[split] = load_cases_jsonl(clean_file)
    return out


def _write_derived(data_dir: Path, outputs: dict[Path, list[Case]]) -> None:
    # Derived groups are frozen on write; a frozen one must come out byte-identical or nothing is written
    blobs = check_frozen_outputs(data_dir, outputs)
    write_frozen_outputs(data_dir, blobs, freeze=True)
    for path, cases in outputs.items():
        print(f"Wrote {len(cases)} cases -> {path} (frozen)")


def cmd_noise(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    noise_dir = data_dir / "RQ2" / "noise"
    outputs: dict[Path, list[Case]] = {}
    for split, clean_cases in _frozen_clean_cases(data_dir, _parse_splits(args.splits)).items():
        outputs[noise_dir / f"{split}.jsonl"] = derive_noise_cases(clean_cases, seed=args.seed)
    _write_derived(data_dir, outputs)


def cmd_pad(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    outputs: dict[Path, list[Case]] = {}
    for split, clean_cases in _frozen_clean_cases(data_dir, _parse_splits(args.splits)).items():
        # Level base: clean cases themselves
        outputs[data_dir / "RQ1a" / "base" / f"{split}.jsonl"] = clean_cases
        for T in TARGET_LENGTHS:
            pad_dir = data_dir / "RQ1a" / f"pad_{T}"
            outputs[pad_dir / f"{split}.jsonl"] = create_padded_dataset(clean_cases, target_length=T, seed=args.seed)
    _write_derived(data_dir, outputs)


def cmd_bundle(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    outputs: dict[Path, list[Case]] = {}
    for split, clean_cases in _frozen_clean_cases(data_dir, _parse_splits(args.splits)).items():
        n_msgs = 300 if split == "test" else 60
        for k in BUNDLE_SIZES:
            bundle_dir = data_dir / "RQ1b" / f"k{k}"
            outputs[bundle_dir / f"{split}.jsonl"] = create_bundle_messages(clean_cases, k=k, n_messages=n_msgs, seed=args.seed)
    _write_derived(data_dir, outputs)


def cmd_assemble(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    conditions, splits = _parse_csv(args.conditions), _parse_splits(args.splits)
    selective = conditions is not None or splits is not None
    if selective and args.transport != "file":
        raise ValueError("assemble --conditions/--splits needs --transport file")
    written: list[Path] = []
    if args.transport == "file":
        # Rewrite the generated conditions' formal files from exchange state (also writes _yields.json);
        # a selective assemble freezes the groups it writes
        exchange = CorpusExchange(exchange_dir=args.exchange_dir, data_dir=data_dir, seed=args.seed)
        res = exchange.assemble(conditions=conditions, splits=splits, n_test=args.n_test, n_dev=args.n_dev)
        print(f"Rewrote {len(res['files'])} corpus file(s) from exchange state")
        written = res["files"]

    yields: dict[str, dict[str, Any]] = {}
    yields_file = data_dir / "_yields.json"
    if yields_file.exists():
        with open(yields_file, "r", encoding="utf-8") as f:
            yields = json.load(f)

    # Stratified timing subsets for test splits (a selective assemble: only the test files it wrote)
    test_files = [p for p in written if p.name == "test.jsonl"] if selective else data_dir.glob("*/*/test.jsonl")
    for test_file in test_files:
        cases = load_cases_jsonl(test_file)
        subset_ids = select_stratified_timing_subset(cases, n_subset=100, seed=args.seed)
        write_timing_subset_file(test_file.parent / "timing_subset.txt", subset_ids)

    # Manifest and Stats. File transport (CLI-based generation and verification) has no API spend.
    total_cost = 0.0
    if args.transport == "api":
        calls_file = Path("runs/_corpus/calls.jsonl")
        if calls_file.exists():
            with open(calls_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            total_cost += float(json.loads(line).get("cost_usd", 0.0))
                        except Exception:
                            pass

    generate_manifest(data_dir, yields=yields, total_cost_usd=total_cost, seed=args.seed)
    generate_stats_markdown(data_dir, yields=yields)
    print(f"Assembled corpus manifest and stats in {data_dir}")


def cmd_stats(args: argparse.Namespace) -> None:
    data_dir = Path(args.data_dir)
    yields: dict[str, float] = {}
    yields_file = data_dir / "_yields.json"
    if yields_file.exists():
        with open(yields_file, "r", encoding="utf-8") as f:
            yields = json.load(f)
    stats_md = generate_stats_markdown(data_dir, yields=yields)
    print("Stats written to stats.md. Preview:\n")
    print(stats_md[:1500])


def cmd_pilot(args: argparse.Namespace) -> None:
    """Execute pilot build of 20 tuples for 9 conditions across RQ2, RQ3, RQ4."""
    import subprocess
    from src.edgebench.corpus.lints import get_top_repeated_5grams

    data_dir = Path(args.data_dir)
    cat_dir = data_dir / "catalog"
    save_catalogs(cat_dir, seed=args.seed)

    catalogs = load_catalogs(cat_dir)
    services_data = load_services(cat_dir)
    all_svcs = {s["id"]: s for s in services_data["services"] + services_data["novel_services"]}
    novel_ids = [s["id"] for s in services_data["novel_services"]]

    client = CorpusLLMClient()
    pipeline = CorpusPipeline(
        client=client,
        service_catalog=all_svcs,
        catalogs=catalogs,
        accepted_dir=data_dir / "_accepted",
        batch_size=10,
    )

    pilot_conditions = [
        ("RQ2/clean", "clean"),
        ("RQ2/negation", "negation"),
        ("RQ2/codeswitch", "codeswitch"),
        ("RQ2/defaultbait", "defaultbait"),
        ("RQ3/F6_medium", "F6_medium"),
        ("RQ3/F8_high", "F8_high"),
        ("RQ4/K15", "K15"),
        ("RQ4/K254", "K254"),
        ("RQ4/churn50", "churn50"),
    ]
    pilot_results: dict[str, Any] = {}

    for label, cond in pilot_conditions:
        print(f"\n--- Running Pilot for {label} (20 tuples) ---")
        tuples = sample_tuples_for_condition(
            condition=cond,
            split="test",
            n=20,
            base_seed=args.seed,
            catalogs=catalogs,
            novel_service_ids=novel_ids,
        )

        active_options = None
        if cond == "K15":
            active_options = {sid: all_svcs[sid]["description"] for sid in catalogs["C_15"]}
            active_options["unsupported"] = "unsupported service"
        elif cond == "K254":
            active_options = {sid: all_svcs[sid]["description"] for sid in catalogs["C_254"]}
            active_options["unsupported"] = "unsupported service"
        elif cond == "churn50":
            active_options = {sid: all_svcs[sid]["description"] for sid in catalogs["v50"]}
            active_options["unsupported"] = "unsupported service"

        accepted_cases, first_pass_yield = pipeline.run_condition_split(
            condition=cond,
            split="test",
            tuples=tuples,
            active_service_options=active_options,
        )

        final_yield = pipeline.final_yields.get(cond, len(accepted_cases) / len(tuples))
        rejections = pipeline.get_rejections(cond)
        top_5grams = pipeline.top_5grams.get(
            cond, get_top_repeated_5grams([c.text for c in accepted_cases], top_k=5)
        )

        pilot_results[label] = {
            "first_pass_yield": first_pass_yield,
            "final_yield": final_yield,
            "rejections": rejections,
            "top_5grams": top_5grams,
            "cases": accepted_cases,
        }
        print(f"Condition {label}: First-Pass Yield = {first_pass_yield:.1%}, Final Yield = {final_yield:.1%}, Accepted = {len(accepted_cases)}/20")

    # Print Pilot Report
    print("\n" + "=" * 70)
    print("EDGEINTENT V1 PILOT (P3b) — SUMMARY REPORT")
    print("=" * 70)
    print(f"Total Pilot Cost: ${client.total_cost_usd:.4f} USD (Spend Cap: ${client.spend_cap_usd:.2f} USD)")
    print(f"Total API Calls: {client.call_count}")

    print("\n### 1. Yields and Rejections by Condition")
    print("| Condition | First-Pass Yield | Final Yield | Rejections by Reason |")
    print("|-----------|------------------|-------------|----------------------|")
    for label, res in pilot_results.items():
        rej_str = ", ".join(f"{k}: {v}" for k, v in res["rejections"].items()) if res["rejections"] else "none"
        print(f"| {label} | {res['first_pass_yield']:.1%} | {res['final_yield']:.1%} | {rej_str} |")

    print("\n### 2. Top Repeated 5-Grams per Condition")
    for label, res in pilot_results.items():
        print(f"\n**{label}**:")
        if not res["top_5grams"]:
            print("  (no 5-grams)")
        else:
            for gram, count in res["top_5grams"][:5]:
                print(f"  - ({count}x) \"{gram}\"")

    print("\n### 3. Example Texts (6 per condition)")
    for label, res in pilot_results.items():
        print(f"\n" + "-" * 50)
        print(f"Condition: {label}")
        print("-" * 50)
        for idx, vc in enumerate(res["cases"][:6], start=1):
            print(f"\n[{idx}] Case ID: {vc.item.tuple_id}")
            print(f"  Target Labels: {vc.item.tuple_labels}")
            print(f"  Scenario: {vc.item.meta.get('scenario')}")
            print(f"  Wording Family: {vc.item.meta.get('wording_family')}")

            # Specific requirements for RQ3/F8_high
            if "F8_high" in label:
                rev_f = vc.item.meta.get("revision_field", "N/A")
                rev_init = vc.item.meta.get("revision_initial_value", "N/A")
                print(f"  Revision Field: {rev_f} (Initial Value: '{rev_init}' -> Final: '{vc.item.tuple_labels.get(rev_f)}')")

            # Specific requirements for RQ4
            if is_rq4_condition(label):
                target_svc_id = vc.item.meta.get("target_service", vc.item.tuple_labels.get("service_type"))
                target_info = all_svcs.get(target_svc_id, {})
                target_desc = target_info.get("description", "N/A")
                if vc.item.meta.get("is_unsupported") or vc.item.tuple_labels.get("service_type") == "unsupported":
                    svc_class = "unsupported"
                elif target_svc_id in ("count", "detection", "ocr"):
                    svc_class = "generic"
                else:
                    svc_class = "specialised"
                print(f"  Target Service: `{target_svc_id}` [{svc_class}]")
                print(f"  Target Service Description: \"{target_desc}\"")

            print(f"  Generated Text: \"{vc.text}\"")
            print(f"  Verifier Labels: {vc.verifier_labels}")

    print("\n### 4. Git Status")
    try:
        git_res = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, check=True)
        print(git_res.stdout.strip() if git_res.stdout.strip() else "(working tree clean)")
    except Exception as e:
        print(f"Failed to check git status: {e}")

    print("\n### 5. Pytest Summary")
    try:
        py_res = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_eb_contract.py", "tests/test_eb_corpus.py", "-q"],
            capture_output=True,
            text=True,
        )
        print(py_res.stdout.strip())
    except Exception as e:
        print(f"Failed to run pytest: {e}")


def cmd_export(args: argparse.Namespace) -> None:
    exchange = CorpusExchange(
        exchange_dir=args.exchange_dir,
        data_dir=args.data_dir,
        seed=args.seed,
    )
    splits = ["test", "dev"] if args.split == "all" else [args.split]
    conditions = args.conditions
    if not conditions and getattr(args, "condition", None):
        conditions = [args.condition]

    if args.stage == "gen":
        files = exchange.export_gen(
            conditions=conditions,
            splits=splits,
            gen_batch_size=args.gen_batch,
            n_test=args.n_test,
            n_dev=args.n_dev,
        )
        print(f"Exported {len(files)} gen todo batch(es) to {exchange.gen_todo_dir}:")
        for f in files:
            print(f"  {f.name}")
    elif args.stage == "ver":
        files = exchange.export_ver(
            conditions=conditions,
            splits=splits,
            ver_batch_size=args.ver_batch,
        )
        print(f"Exported {len(files)} ver file(s) to {exchange.ver_todo_dir}:")
        for f in files:
            print(f"  {f.name}")


def cmd_ingest(args: argparse.Namespace) -> None:
    exchange = CorpusExchange(
        exchange_dir=args.exchange_dir,
        data_dir=args.data_dir,
        seed=args.seed,
    )
    if args.stage == "gen":
        res = exchange.ingest_gen()
        print(f"Ingested gen done files:\n  Passed: {res.get('items_passed', 0)}\n  Rejected: {res.get('items_rejected', 0)}")
        if res.get("rejections"):
            print("  Rejections by reason:")
            for reason, cnt in res["rejections"].items():
                print(f"    - {reason}: {cnt}")
    elif args.stage == "ver":
        res = exchange.ingest_ver()
        print(f"Ingested ver done files:\n  Accepted: {res.get('items_accepted', 0)}\n  Rejected: {res.get('items_rejected', 0)}")
        if res.get("rejections"):
            print("  Rejections by reason:")
            for reason, cnt in res["rejections"].items():
                print(f"    - {reason}: {cnt}")


def _read_item_ids_file(path: str) -> list[str]:
    # One item_id per line, or JSONL lines carrying "item_id" (a ver todo file works as-is)
    item_ids = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                item_ids.append(json.loads(line)["item_id"] if line.startswith("{") else line)
    return item_ids


def _parse_item_ids(value: str) -> list[str]:
    """Comma-separated item IDs, or @<file> (see _read_item_ids_file)."""
    return _read_item_ids_file(value[1:]) if value.startswith("@") else _parse_csv(value)


def cmd_requeue_ver(args: argparse.Namespace) -> None:
    exchange = CorpusExchange(
        exchange_dir=args.exchange_dir,
        data_dir=args.data_dir,
        seed=args.seed,
    )
    if (args.batches is None) == (args.items is None):
        raise ValueError("requeue-ver needs exactly one of --batches or --items")
    if args.items is not None:
        if args.items_file:
            raise ValueError("--items-file narrows --batches; with --items list the item IDs directly")
        res = exchange.requeue_ver_items(_parse_item_ids(args.items), reason=args.reason)
        print(f"Requeued {len(res['requeued'])} item(s) to done_gen")
        if res["archive_dir"]:
            print(f"  Archived batch files to {res['archive_dir']}")
        if res["skipped"]:
            print(f"  Skipped {len(res['skipped'])} item(s) not accepted/exported_ver: {res['skipped']}")
        return
    batch_ids = [b.strip() for b in args.batches.split(",") if b.strip()]
    item_ids = _read_item_ids_file(args.items_file) if args.items_file else None
    res = exchange.requeue_ver(batch_ids, item_ids=item_ids, reason=args.reason)
    print(f"Requeued {len(res['requeued'])} item(s) from {len(batch_ids)} batch(es) to done_gen")
    print(f"  Archived batch files to {res['archive_dir']}")
    if res["skipped"]:
        print(f"  Skipped {len(res['skipped'])} item(s) no longer exported/accepted in these batches")


def cmd_requeue_gen(args: argparse.Namespace) -> None:
    exchange = CorpusExchange(exchange_dir=args.exchange_dir, data_dir=args.data_dir, seed=args.seed)
    batch_ids = _parse_csv(args.batches) or []
    res = exchange.requeue_gen(batch_ids, reason=args.reason)
    print(f"Requeued {len(res['requeued'])} item(s) from {len(batch_ids)} gen batch(es) to pending_gen")
    print(f"  Archived todo files to {res['archive_dir']}")
    if res["skipped"]:
        print(f"  Skipped {len(res['skipped'])} item(s) no longer exported_gen in these batches")


def cmd_retarget(args: argparse.Namespace) -> None:
    exchange = CorpusExchange(exchange_dir=args.exchange_dir, data_dir=args.data_dir, seed=args.seed)
    res = exchange.retarget(_parse_item_ids(args.items), allow_accepted=args.allow_accepted, reason=args.reason)
    print(f"Retargeted {len(res['retargeted'])} item(s) to pending_gen:")
    for i, c in res["retargeted"].items():
        print(f"  {i} ({c['prior_status']}): {c['old']} -> {c['new']}")


def cmd_freeze_status(args: argparse.Namespace) -> None:
    print(freeze_status(args.exchange_dir, args.data_dir))


def cmd_status(args: argparse.Namespace) -> None:
    exchange = CorpusExchange(
        exchange_dir=args.exchange_dir,
        data_dir=args.data_dir,
        seed=args.seed,
    )
    print(exchange.print_status())


def main() -> None:
    parser = argparse.ArgumentParser(description="EdgeIntent v1 Corpus Builder")
    parser.add_argument("--data-dir", default=DEFAULT_DATA_DIR, help="Path to data/edgebench/v1")
    parser.add_argument("--exchange-dir", default=DEFAULT_EXCHANGE_DIR, help="Path to runs/_corpus_exchange")
    parser.add_argument("--transport", default="file", choices=["file", "api"], help="Transport mode: file or api (default: file)")
    parser.add_argument("--seed", type=int, default=20260924, help="Random seed")

    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # export
    p_exp = subparsers.add_parser("export", help="Export work batches for file exchange")
    p_exp.add_argument("--stage", required=True, choices=["gen", "ver"], help="Stage to export: gen or ver")
    p_exp.add_argument("--conditions", nargs="*", default=None, help="Conditions to export (default: all)")
    p_exp.add_argument("--condition", default=None, help="Single condition")
    p_exp.add_argument("--split", default="all", choices=["test", "dev", "all"], help="Split (default: all)")
    p_exp.add_argument("--gen-batch", type=int, default=100, help="Batch size for gen export (default: 100)")
    p_exp.add_argument("--ver-batch", type=int, default=100, help="Batch size for ver export (default: 100)")
    p_exp.add_argument("--n-test", type=int, default=300, help="Number of test tuples")
    p_exp.add_argument("--n-dev", type=int, default=60, help="Number of dev tuples")

    # ingest
    p_ing = subparsers.add_parser("ingest", help="Ingest done files from file exchange")
    p_ing.add_argument("--stage", required=True, choices=["gen", "ver"], help="Stage to ingest: gen or ver")

    # status
    p_status = subparsers.add_parser("status", help="Print corpus build status per condition")

    # requeue-ver
    p_req = subparsers.add_parser("requeue-ver", help="Requeue items of ver batches for fresh blind verification")
    p_req.add_argument("--batches", default=None, help="Comma-separated ver batch IDs, e.g. vbatch_0003,vbatch_0007")
    p_req.add_argument("--items-file", default=None, help="Optional with --batches: only requeue these item IDs (one per line or JSONL with item_id)")
    p_req.add_argument("--items", default=None, help="Item-level instead of --batches: comma-separated item IDs or @file")
    p_req.add_argument("--reason", default="requeue-ver", help="Reason recorded per item in state")

    # requeue-gen
    p_rqg = subparsers.add_parser("requeue-gen", help="Withdraw gen todo batches without a done file and re-export their items")
    p_rqg.add_argument("--batches", required=True, help="Comma-separated gen batch IDs, e.g. gen_K4_test_001")
    p_rqg.add_argument("--reason", default="requeue-gen", help="Reason recorded per item in state")

    # retarget
    p_ret = subparsers.add_parser("retarget", help="New unsupported target for RQ4 unsupported items; they are regenerated")
    p_ret.add_argument("--items", required=True, help="Comma-separated item IDs or @file (one per line or JSONL with item_id)")
    p_ret.add_argument("--allow-accepted", action="store_true", help="Also retarget accepted items (they leave accepted)")
    p_ret.add_argument("--reason", default="retarget", help="Reason recorded per item in state")

    # freeze-status
    subparsers.add_parser("freeze-status", help="Per (condition, split): accepted/target and frozen yes/no (read-only)")

    # catalog
    p_cat = subparsers.add_parser("catalog", help="Build service catalog and nested/churn catalogs")

    # tuples
    p_tup = subparsers.add_parser("tuples", help="Sample label tuples")
    p_tup.add_argument("--condition", default=None, help="Condition to sample (default: all)")
    p_tup.add_argument("--n-test", type=int, default=300, help="Number of test tuples")
    p_tup.add_argument("--n-dev", type=int, default=60, help="Number of dev tuples")

    # generate
    p_gen = subparsers.add_parser("generate", help="Generate request texts with generator LLM")
    p_gen.add_argument("--condition", required=True, help="Condition to generate")
    p_gen.add_argument("--split", default="test", choices=["test", "dev"], help="Split")

    # verify
    p_ver = subparsers.add_parser("verify", help="Blind verify generated texts")
    p_ver.add_argument("--condition", required=True, help="Condition to verify")
    p_ver.add_argument("--split", default="test", choices=["test", "dev"], help="Split")

    # noise
    p_noi = subparsers.add_parser("noise", help="Derive noise from RQ2 clean")
    p_noi.add_argument("--splits", default="test,dev", help="Comma-separated splits; each needs RQ2/clean/<split> frozen")

    # pad
    p_pad = subparsers.add_parser("pad", help="Produce padded versions for RQ1a")
    p_pad.add_argument("--splits", default="test,dev", help="Comma-separated splits; each needs RQ2/clean/<split> frozen")

    # bundle
    p_bun = subparsers.add_parser("bundle", help="Produce bundle messages for RQ1b")
    p_bun.add_argument("--splits", default="test,dev", help="Comma-separated splits; each needs RQ2/clean/<split> frozen")

    # assemble
    p_ass = subparsers.add_parser("assemble", help="Assemble cases, subsets, and manifest")
    p_ass.add_argument("--n-test", type=int, default=300, help="Accepted test cases required per condition")
    p_ass.add_argument("--n-dev", type=int, default=60, help="Accepted dev cases required per condition")
    p_ass.add_argument("--conditions", default=None, help="Comma-separated conditions (default: all); with a filter, written groups are frozen")
    p_ass.add_argument("--splits", default=None, help="Comma-separated splits: test,dev (default: both)")

    # stats
    p_sta = subparsers.add_parser("stats", help="Compute stats.md")

    # pilot
    p_pil = subparsers.add_parser("pilot", help="Run pilot build of 20 tuples for clean, F8_high, K254")

    args = parser.parse_args()

    if args.subcommand == "export":
        cmd_export(args)
    elif args.subcommand == "ingest":
        cmd_ingest(args)
    elif args.subcommand == "status":
        cmd_status(args)
    elif args.subcommand == "requeue-ver":
        cmd_requeue_ver(args)
    elif args.subcommand == "requeue-gen":
        cmd_requeue_gen(args)
    elif args.subcommand == "retarget":
        cmd_retarget(args)
    elif args.subcommand == "freeze-status":
        cmd_freeze_status(args)
    elif args.subcommand == "catalog":
        cmd_catalog(args)
    elif args.subcommand == "tuples":
        cmd_tuples(args)
    elif args.subcommand == "noise":
        cmd_noise(args)
    elif args.subcommand == "pad":
        cmd_pad(args)
    elif args.subcommand == "bundle":
        cmd_bundle(args)
    elif args.subcommand == "assemble":
        cmd_assemble(args)
    elif args.subcommand == "stats":
        cmd_stats(args)
    elif args.subcommand == "pilot":
        cmd_pilot(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
