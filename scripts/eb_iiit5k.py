#!/usr/bin/env python3
"""Download IIIT5K-Word v3.0, extract safely, and select calibration/test images."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import random
import tarfile
import urllib.request
from typing import Any

from PIL import Image
from scipy.io import loadmat

IIIT5K_URL = "https://cvit.iiit.ac.in/images/Projects/SceneTextUnderstanding/IIIT5K-Word_V3.0.tar.gz"
DEFAULT_ARCHIVE_PATH = Path("data/external/iiit5k/IIIT5K-Word_V3.0.tar.gz")
DEFAULT_EXTRACT_DIR = Path("data/external/iiit5k")
DEFAULT_MANIFEST_DIR = Path("data/edgebench/v1/ocr")
SEED = 20260924
N_CALIBRATION = 40
N_TEST = 200


def download_archive(url: str, dest_path: Path) -> str:
    """Download IIIT5K archive and return its SHA-256."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        print(f"Archive already exists at {dest_path}, verifying digest...")
        h = hashlib.sha256()
        with open(dest_path, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    print(f"Downloading {url} to {dest_path}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Edgebench/1.0"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest_path, "wb") as out:
        while chunk := resp.read(65536):
            h.update(chunk)
            out.write(chunk)
    digest = h.hexdigest()
    print(f"Downloaded {dest_path.stat().st_size} bytes, SHA-256: {digest}")
    return digest


def extract_and_select(
    archive_path: Path,
    extract_dir: Path,
    manifest_dir: Path,
    seed: int = SEED,
) -> dict[str, Any]:
    """Safely extract archive members and select calibration and test images."""
    extract_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    sha_archive = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    archive_bytes = archive_path.stat().st_size
    rng = random.Random(seed)

    calibration_images: list[dict[str, Any]] = []
    test_images: list[dict[str, Any]] = []

    with tarfile.open(archive_path) as tar:
        members = tar.getmembers()
        # Verify archive safety
        for m in members:
            p = PurePosixPath(m.name)
            if p.is_absolute() or ".." in p.parts:
                raise ValueError(f"Suspicious path in archive: {m.name}")

        train_char = loadmat(
            io.BytesIO(tar.extractfile("IIIT5K/trainCharBound.mat").read()),
            simplify_cells=True,
        )["trainCharBound"]
        train_data = loadmat(
            io.BytesIO(tar.extractfile("IIIT5K/traindata.mat").read()),
            simplify_cells=True,
        )["traindata"]
        train_words = {r["ImgName"]: str(r["GroundTruth"]) for r in train_data}

        test_char = loadmat(
            io.BytesIO(tar.extractfile("IIIT5K/testCharBound.mat").read()),
            simplify_cells=True,
        )["testCharBound"]
        test_data = loadmat(
            io.BytesIO(tar.extractfile("IIIT5K/testdata.mat").read()),
            simplify_cells=True,
        )["testdata"]
        test_words = {r["ImgName"]: str(r["GroundTruth"]) for r in test_data}

        # Select 40 calibration images from sorted train identifiers
        train_candidates = sorted(train_char, key=lambda r: str(r["ImgName"]))
        selected_train = sorted(
            rng.sample(train_candidates, N_CALIBRATION),
            key=lambda r: str(r["ImgName"]),
        )

        # Select 200 test images from sorted test identifiers
        test_candidates = sorted(test_char, key=lambda r: str(r["ImgName"]))
        selected_test = sorted(
            rng.sample(test_candidates, N_TEST),
            key=lambda r: str(r["ImgName"]),
        )

        # Extract selected images to extract_dir / "IIIT5K"
        for row in selected_train:
            name = str(row["ImgName"])
            raw = tar.extractfile(f"IIIT5K/{name}").read()
            with Image.open(io.BytesIO(raw)) as im:
                assert im.format == "PNG"
                width, height = im.size
                im.verify()

            out_img = extract_dir / "IIIT5K" / name
            out_img.parent.mkdir(parents=True, exist_ok=True)
            out_img.write_bytes(raw)

            calibration_images.append({
                "id": name,
                "split": "calibration",
                "path": str(out_img),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "width": width,
                "height": height,
                "ground_truth": str(row["chars"]),
                "recognition_label": train_words.get(name, str(row["chars"])),
            })

        for row in selected_test:
            name = str(row["ImgName"])
            raw = tar.extractfile(f"IIIT5K/{name}").read()
            with Image.open(io.BytesIO(raw)) as im:
                assert im.format == "PNG"
                width, height = im.size
                im.verify()

            out_img = extract_dir / "IIIT5K" / name
            out_img.parent.mkdir(parents=True, exist_ok=True)
            out_img.write_bytes(raw)

            test_images.append({
                "id": name,
                "split": "test",
                "path": str(out_img),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "bytes": len(raw),
                "width": width,
                "height": height,
                "ground_truth": str(row["chars"]),
                "recognition_label": test_words.get(name, str(row["chars"])),
            })

    manifest = {
        "dataset": "IIIT5K-Word v3.0",
        "archive_url": IIIT5K_URL,
        "archive_sha256": sha_archive,
        "archive_bytes": archive_bytes,
        "seed": seed,
        "n_calibration": len(calibration_images),
        "n_test": len(test_images),
        "selection_rule": "seed 20260924; 40 calibration sampled from sorted train identifiers; 200 test sampled from sorted test identifiers before recognition",
        "calibration_images": calibration_images,
        "test_images": test_images,
    }

    manifest_path = manifest_dir / "selection.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    # Also write manifest.json copy
    with open(manifest_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(
        f"Selected and extracted {len(calibration_images)} calibration and "
        f"{len(test_images)} test images. Manifest written to {manifest_path}"
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare IIIT5K OCR dataset for Edgebench Part B.")
    parser.add_argument("--url", default=IIIT5K_URL, help="URL to IIIT5K archive")
    parser.add_argument("--archive", default=str(DEFAULT_ARCHIVE_PATH), help="Path for downloaded archive")
    parser.add_argument("--extract-dir", default=str(DEFAULT_EXTRACT_DIR), help="Directory to extract images to")
    parser.add_argument("--manifest-dir", default=str(DEFAULT_MANIFEST_DIR), help="Directory for selection manifest")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed for selection")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    download_archive(args.url, archive_path)
    extract_and_select(
        archive_path=archive_path,
        extract_dir=Path(args.extract_dir),
        manifest_dir=Path(args.manifest_dir),
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
