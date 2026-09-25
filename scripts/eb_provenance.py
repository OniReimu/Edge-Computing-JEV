#!/usr/bin/env python3
"""Write PROVENANCE.json (HEAD sha + sha256 of every `git ls-files` path and of every file under
data/edgebench/v1, tracked or not) before syncing to a git-less node.

Run on the Mac from a clean checkout; refuses if `git status --porcelain` is non-empty (untracked corpus
files under data/edgebench/v1 excepted: they are hashed and listed explicitly).
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from src.edgebench.provenance import PROVENANCE_FILE, build_provenance


def main() -> None:
    parser = argparse.ArgumentParser(description="Write PROVENANCE.json for a clean checkout")
    parser.add_argument("--repo", default=str(_repo_root), help="Repository root (default: this checkout)")
    args = parser.parse_args()
    root = Path(args.repo).resolve()
    try:
        data = build_provenance(root)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"{root / PROVENANCE_FILE}: head {data['head_sha']}, {len(data['files'])} files, "
          f"tree_sha256 {data['tree_sha256']}")


if __name__ == "__main__":
    main()
