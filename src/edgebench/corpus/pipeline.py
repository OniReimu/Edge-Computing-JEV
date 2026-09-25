"""Generation and blind verification pipeline with batching, retries, replacement, and resume."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import json
from pathlib import Path
import random
from typing import Any

from src.edgebench.contract import Case, DEFAULT_CRITERIA
from src.edgebench.corpus.client import CorpusLLMClient, GENERATOR_MODEL, VERIFIER_MODEL
from src.edgebench.corpus.lints import (
    check_catalog_leak_lint,
    check_copy_4gram_lint,
    check_diversity_lint,
    check_scaffold_lint,
    extract_ngrams,
    get_top_repeated_5grams,
    normalize_words,
)
from src.edgebench.corpus.prompts import (
    build_generator_batch_prompt,
    build_verifier_batch_prompt,
)
from src.edgebench.corpus.tuples import (
    TupleItem,
    is_rq4_condition,
    sample_tuples_for_condition,
)


@dataclass
class VerifiedCase:
    item: TupleItem
    text: str
    verifier_labels: dict[str, str]
    attempts: int
    is_replacement: bool = False
    generator_model: str = GENERATOR_MODEL
    verifier_model: str = VERIFIER_MODEL

    def to_case(self, active_service_options: dict[str, str] | None = None) -> Case:
        meta = dict(self.item.meta)
        meta["attempts"] = self.attempts
        meta["is_replacement"] = self.is_replacement
        meta["generator_model"] = self.generator_model
        meta["verifier_model"] = self.verifier_model

        return Case(
            case_id=self.item.tuple_id,
            text=self.text,
            fields=list(self.item.tuple_labels.keys()),
            service_options=active_service_options,
            bundle_size=1,
            truth=[dict(self.item.tuple_labels)],
            meta=meta,
        )


class CorpusPipeline:
    def __init__(
        self,
        client: CorpusLLMClient,
        service_catalog: dict[str, dict[str, str]],  # id -> {name, family, description}
        catalogs: dict[str, list[str]],
        accepted_dir: str | Path = "data/edgebench/v1/_accepted",
        batch_size: int = 10,
    ) -> None:
        self.client = client
        self.service_catalog = service_catalog
        self.catalogs = catalogs
        self.accepted_dir = Path(accepted_dir)
        self.accepted_dir.mkdir(parents=True, exist_ok=True)
        self.batch_size = batch_size
        self.rejection_counts: dict[str, Counter[str]] = {}
        self.final_yields: dict[str, float] = {}
        self.top_5grams: dict[str, list[tuple[str, int]]] = {}

    def record_rejection(self, condition: str, reason: str) -> None:
        if condition not in self.rejection_counts:
            self.rejection_counts[condition] = Counter()
        self.rejection_counts[condition][reason] += 1

    def get_rejections(self, condition: str) -> dict[str, int]:
        return dict(self.rejection_counts.get(condition, {}))

    def _get_accepted_file(self, condition: str, split: str) -> Path:
        return self.accepted_dir / f"{condition}_{split}.jsonl"

    def load_accepted_items(self, condition: str, split: str) -> dict[str, VerifiedCase]:
        acc_file = self._get_accepted_file(condition, split)
        accepted: dict[str, VerifiedCase] = {}
        if not acc_file.exists():
            return accepted

        with open(acc_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    t_item = TupleItem(
                        condition=d["condition"],
                        split=d["split"],
                        tuple_id=d["tuple_id"],
                        tuple_labels=d["tuple_labels"],
                        meta=d.get("meta", {}),
                    )
                    v_case = VerifiedCase(
                        item=t_item,
                        text=d["text"],
                        verifier_labels=d["verifier_labels"],
                        attempts=d.get("attempts", 1),
                        is_replacement=d.get("is_replacement", False),
                        generator_model=d.get("generator_model", GENERATOR_MODEL),
                        verifier_model=d.get("verifier_model", VERIFIER_MODEL),
                    )
                    accepted[t_item.tuple_id] = v_case
                except Exception:
                    pass
        return accepted

    def _record_accepted(self, case: VerifiedCase) -> None:
        acc_file = self._get_accepted_file(case.item.condition, case.item.split)
        record = {
            "condition": case.item.condition,
            "split": case.item.split,
            "tuple_id": case.item.tuple_id,
            "tuple_labels": case.item.tuple_labels,
            "meta": case.item.meta,
            "text": case.text,
            "verifier_labels": case.verifier_labels,
            "attempts": case.attempts,
            "is_replacement": case.is_replacement,
            "generator_model": case.generator_model,
            "verifier_model": case.verifier_model,
        }
        with open(acc_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")

    def _rewrite_accepted_file(self, condition: str, split: str, cases: list[VerifiedCase]) -> None:
        acc_file = self._get_accepted_file(condition, split)
        with open(acc_file, "w", encoding="utf-8") as f:
            for case in cases:
                record = {
                    "condition": case.item.condition,
                    "split": case.item.split,
                    "tuple_id": case.item.tuple_id,
                    "tuple_labels": case.item.tuple_labels,
                    "meta": case.item.meta,
                    "text": case.text,
                    "verifier_labels": case.verifier_labels,
                    "attempts": case.attempts,
                    "is_replacement": case.is_replacement,
                    "generator_model": case.generator_model,
                    "verifier_model": case.verifier_model,
                }
                f.write(json.dumps(record) + "\n")

    def run_condition_split(
        self,
        condition: str,
        split: str,
        tuples: list[TupleItem],
        active_service_options: dict[str, str] | None = None,
    ) -> tuple[list[VerifiedCase], float]:
        """Run generation and blind verification for all tuples in a condition/split.

        Returns (accepted_cases, yield_rate).
        """
        accepted_map = self.load_accepted_items(condition, split)
        pending: list[tuple[TupleItem, int, bool]] = []  # (item, attempt_count, is_replacement)

        for t in tuples:
            if t.tuple_id not in accepted_map:
                pending.append((t, 1, False))

        total_first_pass = len(tuples)
        first_pass_accepted = sum(1 for c in accepted_map.values() if c.attempts == 1 and not c.is_replacement)

        # Descriptions map for generator
        service_descs: dict[str, str] = {
            sid: data["description"] for sid, data in self.service_catalog.items()
        }

        # Fields for verifier
        sample_fields = list(tuples[0].tuple_labels.keys())

        # Collect active criteria descriptions for 4-gram copy lint. For RQ4 the service source is only the
        # target's own description (passed per item below), so the verdict is identical for every catalog size K.
        active_criteria_descs: list[str] = []
        for f in sample_fields:
            if f == "service_type":
                if not is_rq4_condition(condition):
                    active_criteria_descs.extend(DEFAULT_CRITERIA["service_type"].values())
            else:
                active_criteria_descs.extend(DEFAULT_CRITERIA[f].values())

        max_opening_count = max(1, int(len(tuples) * 0.05))
        max_5gram_count = max(1, int(len(tuples) * 0.10))

        while pending:
            # Process in batches
            batch_items = pending[: self.batch_size]
            pending = pending[self.batch_size :]

            curr_tuples = [t[0] for t in batch_items]
            attempts = [t[1] for t in batch_items]
            replacements = [t[2] for t in batch_items]

            # 1. Generator call
            gen_sys, gen_user, gen_schema = build_generator_batch_prompt(
                curr_tuples, service_descs
            )
            gen_resp = self.client.call_chat_completion(
                model=GENERATOR_MODEL,
                system_prompt=gen_sys,
                user_prompt=gen_user,
                schema=gen_schema,
                schema_name="generated_edge_requests",
                temperature=0.9,
                call_type="generation",
            )

            # Map generated texts
            generated_texts: dict[str, str] = {}
            for entry in gen_resp.get("items", []):
                generated_texts[str(entry.get("id"))] = str(entry.get("text", "")).strip()

            # 2. Static lints check (Scaffolds, Catalog leak, and 4-gram verbatim copy)
            static_failures: dict[str, str] = {}
            is_rq4 = is_rq4_condition(condition)

            for item in curr_tuples:
                text = generated_texts.get(item.tuple_id, "")
                sc_ok, _ = check_scaffold_lint(text)
                if not sc_ok:
                    static_failures[item.tuple_id] = "lint_scaffold"
                    continue

                if not is_rq4:
                    leak_ok, _ = check_catalog_leak_lint(text)
                    if not leak_ok:
                        static_failures[item.tuple_id] = "lint_catalog_leak"
                        continue

                target_svc_id = item.meta.get("target_service", item.tuple_labels.get("service_type"))
                target_svc_desc = service_descs.get(target_svc_id, "") if is_rq4 else ""
                cp_ok, _ = check_copy_4gram_lint(text, active_criteria_descs, target_svc_desc)
                if not cp_ok:
                    static_failures[item.tuple_id] = "lint_copy_4gram"
                    continue

            # 3. Blind verifier call for items passing static lints
            verif_input: list[tuple[str, str]] = []
            for item in curr_tuples:
                if item.tuple_id not in static_failures:
                    text = generated_texts.get(item.tuple_id, "")
                    verif_input.append((item.tuple_id, text))

            verifier_labels_map: dict[str, dict[str, str]] = {}
            if verif_input:
                ver_sys, ver_user, ver_schema = build_verifier_batch_prompt(
                    verif_input, sample_fields, active_service_options
                )
                ver_resp = self.client.call_chat_completion(
                    model=VERIFIER_MODEL,
                    system_prompt=ver_sys,
                    user_prompt=ver_user,
                    schema=ver_schema,
                    schema_name="blind_labeled_requests",
                    temperature=0.0,
                    call_type="verification",
                )
                for entry in ver_resp.get("items", []):
                    verifier_labels_map[str(entry.get("id"))] = entry.get("labels", {})

            # 4. Check acceptance for each item in batch
            for idx, item in enumerate(curr_tuples):
                attempt = attempts[idx]
                is_rep = replacements[idx]
                text = generated_texts.get(item.tuple_id, "")

                if item.tuple_id in static_failures:
                    reason = static_failures[item.tuple_id]
                    self.record_rejection(condition, reason)
                    matches = False
                else:
                    v_labels = verifier_labels_map.get(item.tuple_id, {})
                    label_match = True
                    for f_name, target_val in item.tuple_labels.items():
                        if v_labels.get(f_name) != target_val:
                            label_match = False
                            break

                    if not label_match:
                        self.record_rejection(condition, "verifier_mismatch")
                        matches = False
                    else:
                        # Check incremental diversity
                        words = normalize_words(text)
                        div_ok = True
                        div_reason = ""
                        if len(words) >= 4:
                            op = tuple(words[:4])
                            cur_op_cnt = sum(
                                1 for c in accepted_map.values()
                                if len(normalize_words(c.text)) >= 4 and tuple(normalize_words(c.text)[:4]) == op
                            )
                            if cur_op_cnt + 1 > max_opening_count:
                                div_ok = False
                                div_reason = "lint_diversity_opening_4gram"

                        if div_ok:
                            text_5grams = extract_ngrams(words, 5)
                            for g in text_5grams:
                                cur_g_cnt = sum(
                                    1 for c in accepted_map.values()
                                    if g in extract_ngrams(normalize_words(c.text), 5)
                                )
                                if cur_g_cnt + 1 > max_5gram_count:
                                    div_ok = False
                                    div_reason = "lint_diversity_5gram"
                                    break

                        if not div_ok:
                            self.record_rejection(condition, div_reason)
                            matches = False
                        else:
                            matches = True

                if matches:
                    if attempt == 1 and not is_rep:
                        first_pass_accepted += 1
                    verified_case = VerifiedCase(
                        item=item,
                        text=text,
                        verifier_labels=verifier_labels_map.get(item.tuple_id, {}),
                        attempts=attempt,
                        is_replacement=is_rep,
                    )
                    self._record_accepted(verified_case)
                    accepted_map[item.tuple_id] = verified_case
                else:
                    # Rejected: retry or replace
                    if attempt < 3:
                        pending.append((item, attempt + 1, is_rep))
                    else:
                        rep_meta = dict(item.meta)
                        rep_meta["replaced_from"] = item.tuple_id
                        rep_item = TupleItem(
                            condition=item.condition,
                            split=item.split,
                            tuple_id=item.tuple_id,
                            tuple_labels=dict(item.tuple_labels),
                            meta=rep_meta,
                        )
                        pending.append((rep_item, 1, True))

        # 5. Post-acceptance diversity verification
        all_cases = [accepted_map[t.tuple_id] for t in tuples if t.tuple_id in accepted_map]
        texts = [c.text for c in all_cases]
        div_passed, viol_indices, _ = check_diversity_lint(
            texts, max_5gram_ratio=0.10, max_opening_4gram_ratio=0.05
        )
        if not div_passed and viol_indices:
            # Re-queue violating indices
            viol_ids = {all_cases[i].item.tuple_id for i in viol_indices}
            accepted_map = {tid: c for tid, c in accepted_map.items() if tid not in viol_ids}
            self._rewrite_accepted_file(condition, split, list(accepted_map.values()))
            for t in tuples:
                if t.tuple_id in viol_ids:
                    pending.append((t, 1, True))
                    self.record_rejection(condition, "lint_diversity_post_check")

            # Re-run until resolved
            return self.run_condition_split(condition, split, tuples, active_service_options)

        yield_rate = (first_pass_accepted / total_first_pass) if total_first_pass > 0 else 1.0
        final_yield = (len(all_cases) / total_first_pass) if total_first_pass > 0 else 1.0
        self.final_yields[condition] = final_yield
        self.top_5grams[condition] = get_top_repeated_5grams([c.text for c in all_cases], top_k=5)

        return all_cases, yield_rate

