#!/usr/bin/env python3
"""Train and calibrate RQ4 reference models: MiniLM reranker and DistilBERT service classifiers.

Never reads test.jsonl during training or calibration.
Outputs models and configs under runs/EXP-2026-001/_reference/_models/.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import time
from typing import Any

# Ensure repo root is on sys.path
_repo_root = Path(__file__).resolve().parent.parent
import sys
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

MINILM_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
MINILM_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

DISTILBERT_MODEL = "distilbert/distilbert-base-uncased"
DISTILBERT_REVISION = "12040accade4e8a0f71eabdb258fecc2e7e948be"

SEED = 20260924
BATCH_SIZE = 16
EPOCHS = 10
LR = 5e-5
WEIGHT_DECAY = 0.01
MAX_LEN = 128


def load_catalog_data(repo_root: Path = _repo_root) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Load catalogs.json and services.json descriptions."""
    cat_path = repo_root / "data" / "edgebench" / "v1" / "catalog" / "catalogs.json"
    services_path = repo_root / "data" / "edgebench" / "v1" / "catalog" / "services.json"

    with open(cat_path, "r", encoding="utf-8") as f:
        catalogs = json.load(f)

    with open(services_path, "r", encoding="utf-8") as f:
        services_data = json.load(f)

    descriptions: dict[str, str] = {}
    for item in services_data.get("services", []):
        descriptions[item["id"]] = item["description"]
    for item in services_data.get("novel_services", []):
        descriptions[item["id"]] = item["description"]

    return catalogs, descriptions


def build_label_space(model_type: str, catalogs: dict[str, list[str]]) -> list[str]:
    """Construct ordered label space for the given model type.

    Frozen excludes v25/v50 new services; retrained includes them.
    'unsupported' is always included.
    """
    if model_type == "clf_all":
        services = sorted(list(catalogs["C_254"]))
    elif model_type == "clf_frozen":
        services = sorted(list(catalogs["v0"]))
    elif model_type in ("clf_retrained_25", "retrained_25"):
        services = sorted(list(catalogs["v25"]))
    elif model_type in ("clf_retrained_50", "retrained_50"):
        services = sorted(list(catalogs["v50"]))
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

    if "unsupported" not in services:
        services.append("unsupported")
    return services


def read_dev_split_cases(condition_dir: Path) -> list[dict[str, Any]]:
    """Read cases from dev.jsonl ONLY. Never touches test.jsonl."""
    dev_path = condition_dir / "dev.jsonl"
    if not dev_path.exists():
        raise FileNotFoundError(f"dev.jsonl not found in {condition_dir}")
    cases = []
    with open(dev_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def build_training_data(
    model_type: str,
    repo_root: Path = _repo_root,
) -> tuple[list[dict[str, str]], list[str], dict[str, Any]]:
    """Build training data and label space for the specified classifier.

    Asserts and ensures that test.jsonl is NEVER opened or read.
    Returns (examples, label_space, stats).
    """
    catalogs, descriptions = load_catalog_data(repo_root)
    label_space = build_label_space(model_type, catalogs)
    label_set = set(label_space)
    v0_set = set(catalogs["v0"])
    v25_set = set(catalogs["v25"])
    v50_set = set(catalogs["v50"])

    rq4_dir = repo_root / "data" / "edgebench" / "v1" / "RQ4"

    examples_by_id: dict[str, dict[str, str]] = {}
    stats: dict[str, Any] = {
        "model_type": model_type,
        "label_space_size": len(label_space),
        "synthetic_descriptions": 0,
        "dev_cases": 0,
        "adaptation_examples": 0,
    }

    if model_type == "clf_all":
        # 1. Synthetic descriptions of C_254
        for s in catalogs["C_254"]:
            if s in descriptions:
                examples_by_id[f"desc_{s}"] = {
                    "text": descriptions[s],
                    "label": s,
                    "source": "synthetic_description",
                }
                stats["synthetic_descriptions"] += 1

        # 2. Dev cases of K4, K15, K64, K128, K254
        for cond in ["K4", "K15", "K64", "K128", "K254"]:
            cases = read_dev_split_cases(rq4_dir / cond)
            for c in cases:
                gold = c["truth"][0]["service_type"]
                if gold in label_set:
                    examples_by_id[c["case_id"]] = {
                        "text": c["text"],
                        "label": gold,
                        "source": f"dev_{cond}",
                    }
                    stats["dev_cases"] += 1

    elif model_type == "clf_frozen":
        # 1. Synthetic descriptions of v0
        for s in catalogs["v0"]:
            if s in descriptions:
                examples_by_id[f"desc_{s}"] = {
                    "text": descriptions[s],
                    "label": s,
                    "source": "synthetic_description",
                }
                stats["synthetic_descriptions"] += 1

        # 2. Dev cases of K4, K15, K64, churn25, churn50 whose gold is in v0 ∪ {unsupported}
        for cond in ["K4", "K15", "K64", "churn25", "churn50"]:
            cases = read_dev_split_cases(rq4_dir / cond)
            for c in cases:
                gold = c["truth"][0]["service_type"]
                if gold in v0_set or gold == "unsupported":
                    examples_by_id[c["case_id"]] = {
                        "text": c["text"],
                        "label": gold,
                        "source": f"dev_{cond}",
                    }
                    stats["dev_cases"] += 1

    elif model_type in ("clf_retrained_25", "retrained_25"):
        # First build frozen data
        frozen_examples, _, _ = build_training_data("clf_frozen", repo_root)
        # Keep frozen examples whose label is in v25 ∪ {unsupported}
        for idx, ex in enumerate(frozen_examples):
            if ex["label"] in label_set:
                examples_by_id[f"frozen_{idx}_{ex['label']}"] = dict(ex)

        # New service descriptions in v25 - v0
        new_services = sorted(list(v25_set - v0_set))
        new_desc_count = 0
        for s in new_services:
            if s in descriptions:
                examples_by_id[f"desc_{s}"] = {
                    "text": descriptions[s],
                    "label": s,
                    "source": "synthetic_description_new",
                }
                new_desc_count += 1

        # churn25 dev cases
        churn_cases = read_dev_split_cases(rq4_dir / "churn25")
        churn_case_count = 0
        for c in churn_cases:
            gold = c["truth"][0]["service_type"]
            if gold in label_set:
                examples_by_id[c["case_id"]] = {
                    "text": c["text"],
                    "label": gold,
                    "source": "dev_churn25",
                }
                churn_case_count += 1

        stats["adaptation_examples"] = new_desc_count + churn_case_count
        stats["new_descriptions"] = new_desc_count
        stats["churn_dev_cases"] = churn_case_count

    elif model_type in ("clf_retrained_50", "retrained_50"):
        # First build frozen data
        frozen_examples, _, _ = build_training_data("clf_frozen", repo_root)
        # Keep frozen examples whose label is in v50 ∪ {unsupported}
        for idx, ex in enumerate(frozen_examples):
            if ex["label"] in label_set:
                examples_by_id[f"frozen_{idx}_{ex['label']}"] = dict(ex)

        # New service descriptions in v50 - v0
        new_services = sorted(list(v50_set - v0_set))
        new_desc_count = 0
        for s in new_services:
            if s in descriptions:
                examples_by_id[f"desc_{s}"] = {
                    "text": descriptions[s],
                    "label": s,
                    "source": "synthetic_description_new",
                }
                new_desc_count += 1

        # churn50 dev cases
        churn_cases = read_dev_split_cases(rq4_dir / "churn50")
        churn_case_count = 0
        for c in churn_cases:
            gold = c["truth"][0]["service_type"]
            if gold in label_set:
                examples_by_id[c["case_id"]] = {
                    "text": c["text"],
                    "label": gold,
                    "source": "dev_churn50",
                }
                churn_case_count += 1

        stats["adaptation_examples"] = new_desc_count + churn_case_count
        stats["new_descriptions"] = new_desc_count
        stats["churn_dev_cases"] = churn_case_count

    examples = list(examples_by_id.values())
    stats["total_examples"] = len(examples)
    return examples, label_space, stats


def calibrate_reranker_on_dev(
    repo_root: Path = _repo_root,
    out_dir: Path | None = None,
    device: str | None = None,
) -> dict[str, Any]:
    """Pool all 7 RQ4 dev splits (420 cases) and calibrate theta."""
    from src.edgebench.contract import Case
    from src.edgebench.interpreters.reranker import RerankerInterpreter, calibrate_reranker

    rq4_dir = repo_root / "data" / "edgebench" / "v1" / "RQ4"
    conditions = ["K4", "K15", "K64", "K128", "K254", "churn25", "churn50"]

    all_cases: list[Case] = []
    for cond in conditions:
        cases_raw = read_dev_split_cases(rq4_dir / cond)
        for raw in cases_raw:
            all_cases.append(Case.from_dict(raw))

    if len(all_cases) != 420:
        raise ValueError(f"Expected 420 pooled dev cases, found {len(all_cases)}")

    print(f"Calibrating MiniLM reranker on {len(all_cases)} pooled dev cases...")
    interpreter = RerankerInterpreter(
        model_name_or_path=MINILM_MODEL,
        revision=MINILM_REVISION,
        device=device,
    )

    t0 = time.time()
    best_theta, best_acc, curve = calibrate_reranker(all_cases, encoder=interpreter._ensure_encoder())
    calib_time_s = time.time() - t0

    result = {
        "model": MINILM_MODEL,
        "revision": MINILM_REVISION,
        "theta": best_theta,
        "best_theta": best_theta,
        "dev_accuracy": best_acc,
        "best_accuracy": best_acc,
        "n_dev_cases": len(all_cases),
        "calibration_time_s": calib_time_s,
        "accuracy_curve": curve,
    }

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "reranker.json"
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Reranker calibration saved to {out_file}: theta={best_theta:.4f}, dev_acc={best_acc:.4f}")

    return result


def train_classifier(
    model_type: str,
    out_dir: Path,
    repo_root: Path = _repo_root,
    device_name: str | None = None,
) -> dict[str, Any]:
    """Train DistilBERT on the dataset for the specified model_type."""
    import numpy as np
    import torch
    from torch.optim import AdamW
    from torch.utils.data import DataLoader, Dataset
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    # Set seeds
    random.seed(SEED)
    np.random.seed(SEED)
    torch.manual_seed(SEED)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(SEED)

    # Determine device
    if device_name is not None:
        device = torch.device(device_name)
    elif torch.backends.mps.is_available():
        device = torch.device("mps")
    elif torch.cuda.is_available():
        device = torch.device("cuda")
    else:
        device = torch.device("cpu")

    examples, label_space, stats = build_training_data(model_type, repo_root)
    label2id = {label: i for i, label in enumerate(label_space)}
    id2label = {i: label for i, label in enumerate(label_space)}

    print(
        f"Training {model_type}: {len(examples)} examples, label space size={len(label_space)} on {device}..."
    )

    tokenizer = AutoTokenizer.from_pretrained(DISTILBERT_MODEL, revision=DISTILBERT_REVISION)
    model = AutoModelForSequenceClassification.from_pretrained(
        DISTILBERT_MODEL,
        revision=DISTILBERT_REVISION,
        num_labels=len(label_space),
        id2label=id2label,
        label2id=label2id,
    )
    model.to(device)

    class TextDataset(Dataset):
        def __init__(self, data: list[dict[str, str]]):
            self.data = data

        def __len__(self) -> int:
            return len(self.data)

        def __getitem__(self, idx: int) -> dict[str, Any]:
            item = self.data[idx]
            return {
                "text": item["text"],
                "label": label2id[item["label"]],
            }

    dataset = TextDataset(examples)
    generator = torch.Generator().manual_seed(SEED)
    dataloader = DataLoader(dataset, batch_size=BATCH_SIZE, shuffle=True, generator=generator)

    optimizer = AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

    t0 = time.time()
    final_loss = 0.0

    model.train()
    for epoch in range(EPOCHS):
        total_epoch_loss = 0.0
        for batch in dataloader:
            optimizer.zero_grad()
            texts = list(batch["text"])
            targets = batch["label"].to(device)

            inputs = tokenizer(
                texts,
                max_length=MAX_LEN,
                truncation=True,
                padding=True,
                return_tensors="pt",
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}

            outputs = model(**inputs, labels=targets)
            loss = outputs.loss
            loss.backward()
            optimizer.step()

            total_epoch_loss += loss.item() * len(texts)

        final_loss = total_epoch_loss / len(examples) if examples else 0.0
        if (epoch + 1) % 2 == 0 or epoch == EPOCHS - 1:
            print(f"Epoch {epoch + 1}/{EPOCHS} - Loss: {final_loss:.4f}")

    wall_time_s = time.time() - t0

    # Save model, tokenizer, and training.json
    out_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    training_meta = {
        "model_type": model_type,
        "base_model": DISTILBERT_MODEL,
        "pinned_revision": DISTILBERT_REVISION,
        "label_space_size": len(label_space),
        "label_space": label_space,
        "data_counts": stats,
        "adaptation_examples_count": stats.get("adaptation_examples", 0),
        "epochs": EPOCHS,
        "batch_size": BATCH_SIZE,
        "learning_rate": LR,
        "weight_decay": WEIGHT_DECAY,
        "max_len": MAX_LEN,
        "seed": SEED,
        "device": str(device),
        "wall_time_s": wall_time_s,
        "final_train_loss": final_loss,
    }

    meta_file = out_dir / "training.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(training_meta, f, indent=2)

    print(
        f"Completed {model_type} in {wall_time_s:.2f}s (loss: {final_loss:.4f}). Saved to {out_dir}"
    )
    return training_meta


def main() -> None:
    parser = argparse.ArgumentParser(description="RQ4 Reference models training and calibration")
    parser.add_argument(
        "--models-dir",
        default=str(_repo_root / "runs" / "EXP-2026-001" / "_reference" / "_models"),
        help="Target directory for trained models and calibration JSONs",
    )
    parser.add_argument(
        "--device",
        default=None,
        help="Device to use ('mps', 'cuda', 'cpu')",
    )
    args = parser.parse_args()

    models_dir = Path(args.models_dir)
    models_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Step 1: Calibrating MiniLM Reranker on Pooled Dev Split ===")
    reranker_info = calibrate_reranker_on_dev(out_dir=models_dir, device=args.device)

    print(f"\n=== Step 2: Training DistilBERT Classifiers ===")
    clf_types = ["clf_all", "clf_frozen", "clf_retrained_25", "clf_retrained_50"]
    training_summaries = {}
    for ctype in clf_types:
        target_dir = models_dir / ctype
        summary = train_classifier(ctype, out_dir=target_dir, device_name=args.device)
        training_summaries[ctype] = summary

    print("\n=== RQ4 Training & Calibration Summary ===")
    print(f"MiniLM Reranker: theta={reranker_info['theta']:.4f}, dev_acc={reranker_info['dev_accuracy']:.4f}")
    for ctype, s in training_summaries.items():
        print(
            f"{ctype:18s}: {s['data_counts']['total_examples']} examples (adaptation: {s['adaptation_examples_count']}), "
            f"wall_time={s['wall_time_s']:.2f}s, loss={s['final_train_loss']:.4f}"
        )


if __name__ == "__main__":
    main()
