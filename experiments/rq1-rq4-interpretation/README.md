# RQ1–RQ4: the interpretation layer on EdgeIntent v1

Every interpreter reads the same request texts and fills the same intent contract. The runs record decision latency,
semantic correctness, billed API cost, and, for self-hosted models, accelerator energy.

| RQ | Factor | Conditions (`data/edgebench/v1/<RQ>/<condition>/test.jsonl`) |
|---|---|---|
| RQ1a | Input length | `base`, `pad_512`, `pad_2048`, `pad_8192`, `pad_16384` |
| RQ1b | Requests bundled per message | `k1`, `k2`, `k4`, `k8` |
| RQ2 | Wording | `clean`, `codeswitch`, `colloquial`, `defaultbait`, `keyvalue`, `negation`, `noise`, `revised` |
| RQ3 | Contract fields $F$ × constraint density $D$ | `F{4,6,8}_{low,medium,high}` |
| RQ4 | Catalog size and churn | `K4`, `K15`, `K64`, `K128`, `K254`, `churn25`, `churn50` |

Each condition has 300 test and 60 development cases. Development cases are used only for prompt checks, classifier
training, and threshold calibration.

## Results in this directory

| File | Content |
|---|---|
| `results/cells.csv` | One row per (RQ, condition, interpreter): exact match with 95% CI, validity, field accuracy, latency percentiles, output tokens, API fees per 1,000 correct decisions, energy per decision, validity flags |
| `results/comms.csv` | Tail latency, jitter (IQR), probability of exceeding a latency budget, availability, goodput, SLA violations, payload bytes |
| `results/contrasts.csv` | Paired RQ2 contrasts against Jev-1.13.0 (EM and unsafe-locality differences, exact McNemar $p$) |
| `results/hypotheses.csv`, `results/hypotheses.md` | Every pre-registered contrast of H1–H5 with estimate, 95% CI, Holm-adjusted $p$, and verdict |
| `results/h5_classifier_reference.csv` | RQ4 descriptive references: frozen and retrained DistilBERT classifiers |
| `results/sensitivity.csv` | Sensitivity analysis (availability re-run) |
| `results/report.md` | Human-readable report of the analysis |
| `results/paper_numbers.md`, `results/paper_numbers.py` | Every RQ1–RQ4 number quoted in the paper, with its source row. Run `python paper_numbers.py` inside `results/` to rebuild |

## Re-running

Set `OPENROUTER_API_KEY` (see the root README). All commands run from the repository root.

**Hosted interpreters**, one run per condition. Each run writes a ledger and an integrity report:

```bash
HOSTED=Jev-1.13.0,DeepSeek-V4.1-Flash,GLM-5.3-Flash,Qwen3.8-Flash
for d in data/edgebench/v1/RQ*/*/; do
  rq=$(basename "$(dirname "$d")"); cond=$(basename "$d")
  uv run python scripts/eb_run.py --rq "$rq" --condition "$cond" --cases "$d/test.jsonl" \
      --models "$HOSTED" --out "runs/EXP-2026-001/$rq/$cond"
done
```

**Self-hosted interpreters.** Start one server (see the root README), run every condition with that model, stop
the server, and repeat for the next model. Output goes to `runs/EXP-2026-001/_selfhosted/<semif|laya|qwen_json>/<RQ>/<condition>`.
For example, for Laya on a CUDA machine:

```bash
uv run python scripts/eb_serve_laya.py --device cuda --port 8700 &
for d in data/edgebench/v1/RQ*/*/; do
  rq=$(basename "$(dirname "$d")"); cond=$(basename "$d")
  uv run python scripts/eb_run.py --rq "$rq" --condition "$cond" --cases "$d/test.jsonl" --models Laya@cuda \
      --base-url http://127.0.0.1:8700 --out "runs/EXP-2026-001/_selfhosted/laya/$rq/$cond"
done
```

Energy per decision is integrated from a GPU power trace. Record it next to the runs while the server is up:

```bash
trace=runs/EXP-2026-001/_selfhosted/laya/power.$$.csv
echo "# gpu=0 tz=$(date +%z) fields=timestamp,power.draw[W],utilization.gpu[%],memory.used[MiB]" > "$trace"
nvidia-smi -i 0 --query-gpu=timestamp,power.draw,utilization.gpu,memory.used \
    --format=csv,noheader,nounits -lms 200 >> "$trace" &
```

The first line of each trace carries the GPU index and the local time zone of the timestamps.

**Reference interpreters.** RQ1–RQ3 use the fixed rule parser (`Rule`) and the label oracle (`Oracle`). RQ4 uses the
MiniLM reranker and the DistilBERT classifiers, trained and calibrated on the development split only:

```bash
uv run python scripts/eb_rq4_train.py --device cuda      # writes runs/EXP-2026-001/_reference/_models/
# RQ1–RQ3:      --models Rule,Oracle
# RQ4 K*:       --models MiniLM-Reranker,DistilBERT-Clf-All
# RQ4 churn*:   --models MiniLM-Reranker,DistilBERT-Clf-Frozen,DistilBERT-Clf-Retrained
# with --out runs/EXP-2026-001/_reference/<RQ>/<condition>
```

The availability re-run of GLM-5.3-Flash goes to `runs/EXP-2026-001-sensitivity/RQ3/F4_low__GLM-5.3-Flash__rerun1`.

**Analysis.** This rebuilds every file in `results/`:

```bash
uv run python scripts/eb_analyze.py --runs-dir runs/EXP-2026-001 --out experiments/rq1-rq4-interpretation/results
```

## Recorded deviations from the pre-registered protocol

These eight deviations are also summarized in Section 4.6 of the paper.

1. GLM-5.3-Flash cannot disable reasoning on any endpoint, so it runs at the lowest reasoning setting. Its reasoning tokens are counted as output.
2. SemIf-Qwen3.5-4B accepts at most 16 options, so the 15-service catalog level was added for it.
3. Each case is run once per interpreter.
4. The corpus generators (Gemini-3.8-Flash, Claude-Opus-5.5) and the verifier (Claude-Opus-5.5) are named in `data/edgebench/v1/manifest.json`.
5. The self-hosted interpreters ran on an NVIDIA H100 NVL instead of the planned Apple Silicon machine. `scripts/eb_align_check.py` checked cross-platform agreement before the main runs.
6. Shared reading rules were added to the field instructions of every interpreter.
7. GLM-5.3-Flash has one availability re-run (`results/sensitivity.csv`).
8. The DistilBERT classifier training set is the development split plus one description example per service.
