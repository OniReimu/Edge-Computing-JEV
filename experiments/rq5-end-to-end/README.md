# RQ5: end-to-end service outcome

RQ5 places each interpreter in a live admission path. The path has four interpretation slots, an admission queue of
capacity 32, no automatic retries, and a shared validator and scheduler. Two parts are measured.

- **Part A, modeled execution.** Live admission events drive an N-node execution model on the same elapsed-time
  axis. No images are processed. There are 15 cells, each with 300 arrivals from the frozen traces in `traces/`:
  - load sweep: offered load of 1, 2, 4, 8, and 16 requests/s;
  - deadline sweep: 0.5, 1, 2, and 4 s;
  - topology sweep: 5, 10, 20, and 40 edge nodes;
  - reuse block: changing or repeated descriptions, with the cache off or on;
  - burstiness: one bursty cell.
- **Part B, real OCR service.** Three Docker workers run Tesseract on IIIT5K scene-text images: a local node, a
  second edge node (netem, 10 ms and 100 Mbit/s), and a cloud node (netem, 30 ms and 50 Mbit/s). There are eight
  conditions: steady or bursty arrivals × changing or repeated descriptions × cache off or on. Each condition has
  240 arrivals: 180 OCR requests and 60 counting or detection requests, which the testbed must reject.

Positive controls: the label oracle (`oracle`) and fixed-latency interpreters (`fixed-latency-0.3`, `-0.6`, `-1.2`)
run on the load sweep. Oracle completion is the feasibility ceiling. With four slots, a fixed decision time of $d$
seconds saturates near $\lambda = 4/d$.

## Results in this directory

| File | Content |
|---|---|
| `results/cells.csv` | One row per (part, cell, interpreter): strict and operational completion with block-bootstrap 95% CIs, status shares, latency percentiles on all completions and on shared successes, API fees per correct completion, cache hits, locality violations, false admissions, correct rejections, mean time decomposition |
| `results/gaps.csv` | Completion gap and latency gap to Jev-1.13.0 (or SemIf-Qwen3.5-4B for the self-hosted pair) per cell |
| `results/hypotheses.csv`, `results/hypotheses.md` | H6 (gap slope over load), H7 (p95 latency on shared successes), and H8 (cache difference-in-differences), with Holm adjustment within each part |
| `results/controls.csv` | Positive-control completion per cell |
| `results/topology_replay.csv` | Exploratory: the load-8 admission timeline replayed for 5, 10, 20, and 40 edge nodes |
| `results/paper_numbers.md` | Every RQ5 number quoted in the paper, with its source row |

## Re-running

Set `OPENROUTER_API_KEY` (see the root README). The self-hosted interpreters run on the same host as the admission
controller, one server at a time (`scripts/eb_local.py start <semif|laya|qwen_json>`).

**Part A.**

```bash
# Hosted interpreters, all 15 cells
uv run python scripts/eb_rq5a.py --cells all --seeds 1 \
    --models Jev-1.13.0 DeepSeek-V4.1-Flash GLM-5.3-Flash Qwen3.8-Flash --out runs/EXP-2026-002/rq5a
# Each self-hosted interpreter with its server running, e.g.
uv run python scripts/eb_rq5a.py --cells all --seeds 1 --models Laya --out runs/EXP-2026-002/rq5a
# Positive controls (no model calls)
uv run python scripts/eb_rq5a.py --cells load_1 load_2 load_4 load_8 load_16 --seeds 1 \
    --models oracle fixed-latency-0.3 fixed-latency-0.6 fixed-latency-1.2 --out runs/EXP-2026-002/rq5a
```

The traces in `traces/` are frozen. `uv run python -m src.edgebench.e2e.traces --out <dir>` regenerates them byte-identically from their seeds.

**Part B.** This part needs Docker with `NET_ADMIN` for the netem link shaping. The pinned base image in the
Dockerfile is the linux/arm64 build, which is the platform the paper's testbed ran on.

```bash
uv run python scripts/eb_iiit5k.py                  # download IIIT5K-Word v3.0 and select calibration/test images
docker build -f configs/edgebench/ocr-worker/Dockerfile -t edgebench-ocr-worker:latest .
uv run python scripts/eb_testbed.py up
uv run python scripts/eb_testbed.py verify          # checks the RTT ordering local < edge2 < cloud
uv run python scripts/eb_rq5b.py --conditions all --seeds 1 \
    --models Jev-1.13.0 DeepSeek-V4.1-Flash GLM-5.3-Flash Qwen3.8-Flash --out runs/EXP-2026-002/rq5b
uv run python scripts/eb_rq5b.py --conditions all --seeds 1 --models Laya --out runs/EXP-2026-002/rq5b   # per self-hosted model
uv run python scripts/eb_testbed.py down
```

`calibration.json` holds the frozen per-node, per-tier service-time estimates used by the scheduler. Each estimate
is the median over 40 calibration images. `--calibrate` measures them again on your testbed.

**Analysis.** This rebuilds every file in `results/` and fails if any expected (cell, interpreter) arm is missing:

```bash
uv run python scripts/eb_rq5_analyze.py
```

## Recorded deviations from the pre-registered protocol

- **D-1.** One arrival trace (seed 1) per cell.
- **D-2.** The Part B changing-text conditions use 180 distinct OCR descriptions: the 100 clean OCR texts plus 80
  sampled with a fixed seed from the four-field constraint-density test splits of RQ3.
- **D-3.** The self-hosted servers accept concurrent connections and serialize inference on the one accelerator. A
  single-threaded server with keep-alive connections starved the other interpretation slots in the pilot.
