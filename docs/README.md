# Interactive paper website

Static HTML/CSS/JavaScript with an English root and a Chinese `zh/` route. No build tool, API key,
model calls, or external JavaScript dependency is needed. Paper links open the arXiv PDF.

## Preview

From the repository root:

```sh
python3 scripts/check_pages.py
python3 -m http.server 8123 --bind 127.0.0.1 --directory docs
```

Open http://127.0.0.1:8123/ or http://127.0.0.1:8123/zh/.
All assets use relative paths and support the `/Edge-Computing-JEV/` project-site prefix.

## GitHub Pages

A repository administrator must select **Settings → Pages → Build and deployment → Source: GitHub Actions**.
After this PR is merged into `main`, the Pages workflow checks the package and uploads only `docs/`.
It deploys only on a push to `main` or a manual run on `main` in `OniReimu/Edge-Computing-JEV`.
Pull requests run validation without publishing. If Pages is enabled after the merge, run the
**Paper website** workflow manually from the Actions tab.

Expected URLs after deployment:

- English: https://onireimu.github.io/Edge-Computing-JEV/
- Chinese: https://onireimu.github.io/Edge-Computing-JEV/zh/

## Data and maintenance

- `assets/explorer-data.json`: RQ3 and RQ5 values, rounded as in the manuscript tables.
- `assets/extended-data.json`: RQ1a and RQ4 values, rounded as in the manuscript tables.
- `assets/system-architecture.png`: raster rendering of the manuscript system architecture.
- `script.js`: shared bilingual content and service outcome controls.
- `extended.js`: study design, input-length charts, and catalog matrix.

The validator compares every displayed numeric dataset entry with the released CSV results in
`experiments/*/results/`, within manuscript rounding precision. It also checks local asset paths,
project-prefix compatibility, the arXiv reading links, and the publishing boundary.
Update the JSON snapshots together with their source results. The source CSV files, not this website,
remain the research record. The JSON snapshots retain zero-output failures and null latency for
conditions without completions.

RQ3 latency is median decision latency; RQ5 latency is the full-request p95 over each model's own
completions. It is not the paired shared-success statistic. Graphs show point estimates at discrete
conditions; intervals remain in the paper. API fees are recorded experiment costs, not current prices.

The site does not redistribute the paper PDF, LaTeX sources, run records, credentials, or model weights.
Text and visualizations summarize the manuscript; they do not independently validate the experiments.
