# Edge-Computing-JEV

Code, benchmark, and results for the paper

> **Replacing Large Language Models with Jev Decision Models for Low-Latency Edge Service Orchestration**
> Delong Li, Xu Wang, Haochen Gong, Rui Lang, and Guangsheng Yu. University of Technology Sydney.

The paper places an interpreter in an edge-service admission path. The interpreter turns a natural-language
request into a typed intent contract (service, locality, quality floor, urgency, and up to four further fields).
Jev-1.13.0 (a hosted decision model) and two self-hosted decision models are compared with three hosted LLMs
that are configured for short, structured JSON output.

| Experiment | Research questions | Where |
|---|---|---|
| Interpretation layer on the EdgeIntent v1 benchmark (8,280 verified requests, 33 conditions) | RQ1 input scale, RQ2 input quality, RQ3 task difficulty, RQ4 dynamic service catalog, plus tail latency, jitter, and energy | [`experiments/rq1-rq4-interpretation/`](experiments/rq1-rq4-interpretation/README.md) |
| End-to-end service outcome: live admission with modeled execution (Part A) and a real three-node OCR service (Part B) | RQ5 | [`experiments/rq5-end-to-end/`](experiments/rq5-end-to-end/README.md) |

The two experiments were pre-registered with hypotheses H1–H5 (RQ1–RQ4) and H6–H8 (RQ5). Their decision rules are
described in Section 4.6 of the paper.

## Repository layout

```
data/edgebench/v1/        EdgeIntent v1 benchmark: 33 conditions, test and dev splits, service catalog, provenance
traces/                   Frozen RQ5 Part A arrival traces (15 cells, seed 1)
calibration.json          Frozen RQ5 Part B service-time calibration (median of 40 images per node and tier)
configs/edgebench/        Interpreter manifest (models.json), OCR worker image, cross-platform alignment configs
src/edgebench/            Library: contract, interpreters, runner, scoring, corpus builder, RQ5 admission and simulator, analysis
src/*.py                  Shared helpers used by the library (schema, rule parser, intent cache, OCR client, simulator)
scripts/                  Command-line entry points (eb_*.py) and the figure/table generator (paper_assets.py)
tests/                    Offline test suite (no API key, no GPU)
experiments/*/results/    The analysis outputs every number, figure, and table in the paper is computed from
paper_assets/             Figure/table manifest and SHA-256 hashes of the paper's figure and table files
requirements/             Pinned dependencies (lightweight, Apple Silicon, and CUDA environments)
```

## Quick start (about 5 minutes, no API key, no GPU)

Requirements: Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/OniReimu/Edge-Computing-JEV.git
cd Edge-Computing-JEV
uv venv --python 3.13
uv pip install -r requirements/edgebench.txt -r requirements/analysis.txt

# 1. Offline tests. Tests that need the self-hosted model libraries are skipped in this environment.
uv run python -m pytest tests -q

# 2. Regenerate every data figure and table of the paper from the released results,
#    and verify that all 56 files are byte-identical to the ones in the paper.
uv run python scripts/paper_assets.py --check
uv run python scripts/paper_assets.py            # writes them to paper_assets/figures/eb and paper_assets/tables/eb
```

`--check` prints `CHECK OK: all 56 figure and table files are byte-identical to the paper (SHA-256)`. The light
environment runs 274 tests and skips 7 that need a model library. With the full environment of a self-hosted
interpreter, all 314 tests run.

The runner records the commit of the code in every run for provenance, so use a `git clone`. If you downloaded a ZIP
archive, run `git init && git add -A && git commit -m snapshot` once before running tests or experiments.

The numbers quoted in the text are listed, with the table row each one comes from, in
`experiments/rq1-rq4-interpretation/results/paper_numbers.md` and `experiments/rq5-end-to-end/results/paper_numbers.md`.

## Reproducing the experiments from scratch

Re-running the experiments makes live calls to hosted models and needs the self-hosted models. Raw run records
(about 1.5 GB of per-request ledgers) are not part of this repository. Each experiment README gives the exact
commands, and the analysis scripts rebuild `experiments/*/results/` from new runs.

### Credentials

Hosted interpreters (Jev-1.13.0, DeepSeek-V4.1-Flash, GLM-5.3-Flash, Qwen3.8-Flash) are called through
[OpenRouter](https://openrouter.ai). Set the key in the environment:

```bash
export OPENROUTER_API_KEY=...        # never commit it; src/credentials.py can also read ~/.config/jev/openrouter.env (mode 600)
```

### Self-hosted interpreters

| Display name | Model (pinned revision) | Server | Default port |
|---|---|---|---|
| SemIf-Qwen3.5-4B | [SemIf](https://github.com/TheoLeeCJ/SemIf-OpenJev) @ `23cf1f39` on [Qwen/Qwen3.5-4B](https://huggingface.co/Qwen/Qwen3.5-4B) @ `851bf6e8` | `scripts/eb_serve_semif.py` | 8601 |
| Laya | [convaiinnovations/laya-typed-decisions](https://huggingface.co/convaiinnovations/laya-typed-decisions) @ `bc76315b` | `scripts/eb_serve_laya.py` | 8602 |
| Qwen3.5-4B-JSON (generative reference) | Qwen/Qwen3.5-4B @ `851bf6e8`, greedy, schema-constrained | `scripts/eb_serve_qwen_json.py` | 8603 |

Environments:

- **Apple Silicon (MLX / MPS):** `uv pip install -r requirements/edgebench-local.txt`, then
  `uv run python scripts/eb_local.py start semif` (or `laya`, `qwen_json`). Use the display names above.
- **Linux + NVIDIA GPU (the paper's runs used one H100 NVL):** follow the header of `requirements/edgebench-cuda.txt`,
  start a server with `--backend cuda` (SemIf, Qwen3.5-4B-JSON) or `--device cuda` (Laya), and use the `@cuda` display names
  (`SemIf-Qwen3.5-4B@cuda`, `Laya@cuda`, `Qwen3.5-4B-JSON@cuda`) from `configs/edgebench/models.json`.

`scripts/eb_align_check.py` compares the choices and probabilities of the same server on two platforms on 20 fixed cases.

Only one self-hosted server runs at a time. The servers accept concurrent connections and serialize inference on one
accelerator.

## Mapping from the paper to this repository

| Paper element | Generator | Source data |
|---|---|---|
| EdgeIntent v1 condition table | `scripts/paper_assets.py` (`tab_corpus`) | `data/edgebench/v1/stats.md`, `_yields.json` |
| RQ1–RQ4 figures and tables, tail-latency/jitter/energy figures and table, pre-registered contrasts H1–H5 | `scripts/paper_assets.py` | `experiments/rq1-rq4-interpretation/results/*.csv` (built by `scripts/eb_analyze.py`) |
| RQ5 figures and tables, H6–H8 | `scripts/paper_assets.py` | `experiments/rq5-end-to-end/results/*.csv` (built by `scripts/eb_rq5_analyze.py`) |

`paper_assets/figure-manifest.yml` records, for every generated file, its generator function, source CSV, columns,
and filters.

## Model names

Interpreters are identified by versioned display names throughout the code, the results, and the paper:
Jev-1.13.0, SemIf-Qwen3.5-4B, Laya, DeepSeek-V4.1-Flash, GLM-5.3-Flash, Qwen3.8-Flash, and Qwen3.5-4B-JSON (reference).
Reference interpreters are the rule parser (Rule) and the label oracle (Oracle) in RQ1–RQ3, and MiniLM-Reranker and the
DistilBERT classifiers (DistilBERT-Clf-All, -Frozen, -Retrained) in RQ4.
Condition keys in the code map to the paper's names as follows: `pad_512` means padded to 512 tokens, `k4` means four
requests per message, `F8_high` means eight contract fields at high constraint density, `K254` means a catalog of 254
services, and `churn25` means 25% catalog churn.

## Third-party components

- IIIT5K-Word (scene-text images for the RQ5 OCR service) is downloaded by `scripts/eb_iiit5k.py` and is not redistributed.
- Tesseract runs inside the OCR worker image built from `configs/edgebench/ocr-worker/Dockerfile`.
- Model weights are downloaded from Hugging Face at the pinned revisions above.

Each third-party component keeps its own license.

## License

Code: [MIT](LICENSE). EdgeIntent v1, the traces, the calibration file, and the experiment results:
[CC BY 4.0](LICENSE-DATA). If you use the benchmark or the code, please cite the paper above.
