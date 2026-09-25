# /// script
# requires-python = ">=3.11"
# dependencies = ["matplotlib==3.11.2", "numpy==2.2.6", "pandas==3.0.6"]
# ///
"""Build the RQ1-RQ4 and communication-metric figures and tables of the paper.

Every number is read from the frozen EXP-2026-001 analysis CSVs (and, for tab_corpus only, from the
EdgeIntent v1 corpus statistics); nothing is recomputed from ledgers and nothing is typed by hand.

    uv run scripts/paper_assets.py            # build into paper/, PNG previews into /tmp/paper_assets_png/
    uv run scripts/paper_assets.py --check    # rebuild into a temp dir; fail on any byte difference
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import os
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("pdf")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "experiments" / "rq1-rq4-interpretation" / "results"
RQ5_RESULTS = ROOT / "experiments" / "rq5-end-to-end" / "results"
CORPUS = ROOT / "data" / "edgebench" / "v1"
PAPER = ROOT / "paper_assets"
PNG_DIR = Path("/tmp/paper_assets_png")
SCRIPT_REL = "../scripts/paper_assets.py"
ANA_REL = "../experiments/rq1-rq4-interpretation/results"
MANIFEST_BEGIN = "  # >>> paper_assets.py: generated block, rebuilt on every run; do not edit by hand"
MANIFEST_END = "  # <<< paper_assets.py"

# ----------------------------------------------------------------------------------------------
# Palette (must equal paper/palette.tex; asserted on every run)
# ----------------------------------------------------------------------------------------------
PALETTE = {
    "ebBlue": "DCE3F0",
    "ebAmber": "F4CC79",
    "ebBeige": "ECD7BC",
    "ebCyan": "CCFDFE",
    "ebCoral": "ED8683",
    "ebPink": "F7D3D2",
    "ebWarm": "F2F2EE",
    "ebDeepBlue": "B9C6E0",
    "ebInk": "2E5BE6",
}
GREYS = ("D9D9D9", "BFBFBF", "A6A6A6")

JEV = "Jev-1.13.0"
MAIN7 = [JEV, "SemIf-Qwen3.5-4B", "Laya", "DeepSeek-V4.1-Flash", "GLM-5.3-Flash", "Qwen3.8-Flash",
         "Qwen3.5-4B-JSON"]
SIX = MAIN7[:6]
HOSTED = [JEV, "DeepSeek-V4.1-Flash", "GLM-5.3-Flash", "Qwen3.8-Flash"]
SELF_HOSTED = ["SemIf-Qwen3.5-4B", "Laya", "Qwen3.5-4B-JSON"]
RERANKER, CLF_ALL = "MiniLM-Reranker", "DistilBERT-Clf-All"
CLF_FROZEN, CLF_RETRAINED = "DistilBERT-Clf-Frozen", "DistilBERT-Clf-Retrained"
REFERENCES = [RERANKER, CLF_ALL, CLF_FROZEN, CLF_RETRAINED]

FILL = {
    JEV: PALETTE["ebCoral"], "SemIf-Qwen3.5-4B": PALETTE["ebBlue"], "Laya": PALETTE["ebCyan"],
    "Qwen3.5-4B-JSON": PALETTE["ebPink"], "DeepSeek-V4.1-Flash": PALETTE["ebBeige"],
    "GLM-5.3-Flash": PALETTE["ebAmber"], "Qwen3.8-Flash": PALETTE["ebDeepBlue"],
    RERANKER: GREYS[0], CLF_ALL: GREYS[1], CLF_FROZEN: GREYS[1], CLF_RETRAINED: GREYS[2],
}
MARKER = {
    JEV: "o", "SemIf-Qwen3.5-4B": "s", "Laya": "^", "DeepSeek-V4.1-Flash": "D", "GLM-5.3-Flash": "v",
    "Qwen3.8-Flash": "P", "Qwen3.5-4B-JSON": "X", RERANKER: "<", CLF_ALL: ">", CLF_FROZEN: "h",
    CLF_RETRAINED: "*",
}
DISPLAY = {m: m for m in FILL}
DISPLAY["Qwen3.5-4B-JSON"] = "Qwen3.5-4B-JSON (ref.)"
TEX_NAME = {
    JEV: r"\jev", "SemIf-Qwen3.5-4B": r"\semif", "Laya": r"\laya", "DeepSeek-V4.1-Flash": r"\deepseek",
    "GLM-5.3-Flash": r"\glm", "Qwen3.8-Flash": r"\qwenflash", "Qwen3.5-4B-JSON": r"\qwenjson{} (ref.)",
    RERANKER: "MiniLM-Reranker", CLF_ALL: "DistilBERT-Clf-All", CLF_FROZEN: "DistilBERT-Clf-Frozen",
    CLF_RETRAINED: "DistilBERT-Clf-Retrained",
}
MODEL_CODE = {
    JEV: "JEV", "SemIf-Qwen3.5-4B": "SIF", "Laya": "LAY",
    "DeepSeek-V4.1-Flash": "DSK", "GLM-5.3-Flash": "GLM",
    "Qwen3.8-Flash": "Q38", "Qwen3.5-4B-JSON": "QJS",
}

RQ2_LONG = {"clean": "Clean", "codeswitch": "Code-switched", "colloquial": "Colloquial",
            "defaultbait": "Default-baiting", "keyvalue": "Key--value", "negation": "Negation-heavy",
            "noise": "Noisy", "revised": "Self-revising"}
# Two-letter codes for RQ2 tick labels (no rotated labels); the key is spelled out once in the fig_rq2 caption.
RQ2_CODE = {"clean": "CL", "codeswitch": "CS", "colloquial": "CO", "defaultbait": "DB", "keyvalue": "KV",
            "negation": "NG", "noise": "NS", "revised": "RV"}
RQ2_SHORT = {"clean": "clean", "codeswitch": "code-sw.", "colloquial": "colloq.", "defaultbait": "def.-bait",
             "keyvalue": "key-val.", "negation": "negation", "noise": "noise", "revised": "revised"}
COMMS_CONDS = [("RQ2", "clean"), ("RQ1a", "pad_16384"), ("RQ3", "F8_high"), ("RQ4", "K254")]

FIGSTAR_W, FIG_W, PANEL_H = 1.70, 1.68, 1.30

# Captions: describe what each float shows; results and interpretation live in the prose.
CAPTIONS = {
    "fig_rq1": "RQ1, input scale. (a) Median decision latency and (b) exact match (EM) as irrelevant context pads each "
               "request to 16{,}384 tokens. (c) Per-request median latency and (d) request-level EM when $k$ requests "
               "share one message. Bands are 95\\% bootstrap confidence intervals; latency axes are logarithmic.",
    "fig_rq2": "RQ2, input quality, across eight wording conditions that keep the same label tuples. (a) EM, "
               "(b) unsafe-locality rate, (c) spurious-specification rate, with 95\\% confidence intervals; "
               "(d) decision latency on clean requests, bars at the median with whiskers to p95. Conditions: CL clean, "
               "CS code-switched, CO colloquial, DB default-baiting, KV key--value, NG negation-heavy, NS noisy, "
               "RV self-revising.",
    "fig_rq3": "RQ3, task difficulty. (a) EM, (b) median decision latency, and (c) median output tokens as the "
               "contract grows from four to eight fields at medium constraint density; (d) EM across constraint "
               "density with eight fields.",
    "fig_rq4": "RQ4, dynamic service catalog. (a) Top-1 service accuracy on seen (solid) and unseen (dotted) services "
               "and (b) median decision latency as the catalog grows from 4 to 254 services; (c) top-1 accuracy "
               "when 25\\% or 50\\% of a 64-service catalog is replaced; (d) F1 score for detecting unsupported "
               "requests. Crosses mark cells with fewer than half valid outputs.",
    "fig_comms_latency": "Decision-latency distributions as the probability that a decision exceeds a latency "
                         "budget, (a) on clean requests and (b) on requests padded to 16{,}384 tokens.",
    "fig_comms_efficiency": "Efficiency per decision: (a) API fees per 1{,}000 correct decisions for the hosted "
                            "interpreters and (b) accelerator energy per decision for the self-hosted ones, in four "
                            "representative conditions.",
    "tab_corpus": "\\corpus conditions: test and development cases, input length percentiles, and first-pass and "
                  "final yield of the blind-verification gate. Derived conditions are built programmatically from "
                  "verified text.",
    "tab_rq1a": "RQ1a, input length. EM with 95\\% confidence interval, valid-output rate, macro field accuracy, decision "
                "latency percentiles, output tokens, API fees per 1{,}000 correct decisions, and energy per decision. "
                "Best value per block in bold.",
    "tab_rq1b": "RQ1b, bundled requests. Request-level EM, share of messages with every request correct, per-request "
                "and per-message latency, API fees, and energy for $k$ requests per message.",
    "tab_rq2": "RQ2, input quality. Quality, safety, and latency of every interpreter under each wording condition.",
    "tab_rq2_contrasts": "RQ2 paired contrasts against \\jev per wording condition: differences in EM and in the "
                         "unsafe-locality rate with 95\\% confidence intervals, exact McNemar $p$, and the Holm-adjusted "
                         "$p$ of H3.",
    "tab_rq3": "RQ3, task difficulty. EM and median decision latency for each contract size $F$ and constraint "
               "density $D$, and median output tokens at medium density.",
    "tab_rq4a": "RQ4a, catalog size. Service accuracy on seen and unseen services, unsupported-request detection, "
                "admission errors, EM, validity, and latency for catalogs of 4 to 254 services, with the trained "
                "classifier and the sentence-embedding reranker as references.",
    "tab_rq4b": "RQ4b, catalog churn at 64 services. Seen and unseen top-1 accuracy, their gap (H5), and the "
                "adaptation cost of the retrained classifier.",
    "tab_comms": "Communication-level metrics in four representative conditions: tail latency, jitter, probability "
                 "of exceeding a latency budget, availability, goodput, SLA violations, payload bytes, API fees, and "
                 "energy per decision.",
    "tab_hypotheses": "Pre-registered confirmatory contrasts H1--H5 (the paired H3 contrasts are in "
                      "Table~\\ref{tab:rq2_contrasts}). A contrast is resolved when its 95\\% confidence interval "
                      "excludes the null value and its Holm-adjusted $p$ is below 0.05.",
    "fig_rq5a": "RQ5, modeled execution (Part~A). (a) Primary completion and (b) 95th percentile of full request "
                "latency $T$ on completions as offered load $\\lambda$ increases from 1 to 16 requests/s. (c) Primary "
                "completion across request deadline $D$ from 0.5 to 4~s ($D=2$~s is the $\\lambda=4$ cell). Bands are "
                "95\\% bootstrap confidence intervals. (d) Primary completion under cache reuse conditions: CO changing "
                "text with cache off, CN changing text with cache on, RO repeated text with cache off, RN repeated text "
                "with cache on.",
    "fig_rq5b": "RQ5, real OCR service (Part~B). (a) Correct-completion rate with cache off (whiskers are 95\\% "
                "confidence intervals) and (b) cache on across operational conditions: S steady, B bursty, C changing "
                "text, R repeated text. (c) 95th percentile request latency $T$ on completions with cache off. "
                "(d) Stacked mean time decomposition into admission wait, decision, and service execution for SC0. "
                "Model codes: JEV \\jev, SIF \\semif, LAY \\laya, DSK \\deepseek, GLM \\glm, Q38 \\qwenflash, "
                "QJS \\qwenjson{} (ref.).",
    "tab_rq5a": "RQ5, modeled execution (Part~A). Primary completion rate and 95th percentile request latency $T$ on "
                "completions across offered load, deadline, topology, cache reuse, and burstiness sweeps. The $\\lambda=4$ "
                "cell serves as the reference for $D=2$\\,s, $N=5$, and changing text with cache off. Model codes: "
                "JEV \\jev, SIF \\semif, LAY \\laya, DSK \\deepseek, GLM \\glm, Q38 \\qwenflash, QJS \\qwenjson{} (ref.). "
                "Best value per row within each metric block in bold (QJS reference excluded). 95\\% confidence intervals "
                "are drawn in Fig.~\\ref{fig:rq5a}.",
    "tab_rq5b": "RQ5, real OCR service (Part~B). Correct completion rate and 95th percentile request latency $T$ on "
                "completions across operational conditions under steady and bursty arrivals. Model codes: JEV \\jev, "
                "SIF \\semif, LAY \\laya, DSK \\deepseek, GLM \\glm, Q38 \\qwenflash, QJS \\qwenjson{} (ref.). Best value "
                "per row within each metric block in bold (QJS reference excluded). 95\\% confidence intervals are drawn "
                "in Fig.~\\ref{fig:rq5b}.",
}


def hexcol(h: str) -> str:
    return "#" + h


def dark(h: str) -> str:
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb(hh, max(0.0, ll - 0.35), ss)
    return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))


def linestyle(m: str) -> str:
    if m in HOSTED:
        return "-"
    if m in SELF_HOSTED:
        return "--"
    return "-."


def check_palette() -> None:
    if not (PAPER / "palette.tex").exists():  # the paper's LaTeX sources are not distributed with the code
        return
    tex = (PAPER / "palette.tex").read_text()
    found = dict(re.findall(r"\\definecolor\{(\w+)\}\{HTML\}\{([0-9A-Fa-f]{6})\}", tex))
    found = {k: v.upper() for k, v in found.items()}
    if found != PALETTE:
        sys.exit(f"PALETTE mismatch with paper/palette.tex:\n  tex={found}\n  py ={PALETTE}")


# ----------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------
class Data:
    def __init__(self) -> None:
        cells = pd.read_csv(ANALYSIS / "cells.csv")
        comms = pd.read_csv(ANALYSIS / "comms.csv")
        key = ["model", "role", "rq", "condition"]
        assert (cells[key].values == comms[key].values).all(), "cells/comms row order differs"
        for col in ("n", "output_tokens_median", "flag_valid_lt_50"):
            a, b = cells[col], comms[col]
            assert ((a == b) | (a.isna() & b.isna())).all(), f"cells/comms disagree on {col}"
        self.df = cells.merge(comms.drop(columns=["n", "output_tokens_median", "flag_valid_lt_50"]), on=key)
        assert len(self.df) == len(cells)
        self.df = self.df[self.df["role"].isin(["main", "reference"])]
        self.hyp = pd.read_csv(ANALYSIS / "hypotheses.csv")
        self.con = pd.read_csv(ANALYSIS / "contrasts.csv")
        self.h5 = pd.read_csv(ANALYSIS / "h5_classifier_reference.csv")
        # hosted/self-hosted split must match the data (cost only for hosted, energy only for self-hosted)
        main = self.df[self.df["model"].isin(MAIN7)]
        for m in MAIN7:
            sub = main[main["model"] == m]
            assert sub["cost_usd_per_1000_correct"].notna().any() == (m in HOSTED), m
            assert sub["energy_j_per_decision"].notna().any() == (m in SELF_HOSTED), m

    def conds(self, rq: str) -> list[str]:
        return list(dict.fromkeys(self.df.loc[self.df["rq"] == rq, "condition"]))

    def row(self, rq: str, cond: str, model: str) -> pd.Series:
        r = self.df[(self.df["rq"] == rq) & (self.df["condition"] == cond) & (self.df["model"] == model)]
        assert len(r) == 1, (rq, cond, model, len(r))
        return r.iloc[0]

    def get(self, rq: str, cond: str, model: str, col: str) -> float:
        v = self.row(rq, cond, model)[col]
        return float("nan") if pd.isna(v) else float(v)

    def flag(self, rq: str, cond: str, model: str) -> bool:
        return bool(self.row(rq, cond, model)["flag_valid_lt_50"])


class RQ5Data:
    def __init__(self, rq5_dir: Path) -> None:
        self.dir = rq5_dir
        self.cells = pd.read_csv(rq5_dir / "cells.csv")
        self.gaps = pd.read_csv(rq5_dir / "gaps.csv") if (rq5_dir / "gaps.csv").exists() else None
        self.hyp = pd.read_csv(rq5_dir / "hypotheses.csv") if (rq5_dir / "hypotheses.csv").exists() else None

    def row(self, part: str, cell: str, model: str) -> pd.Series | None:
        sub = self.cells[(self.cells["part"] == part) & (self.cells["cell"] == cell) & (self.cells["model"] == model)]
        return sub.iloc[0] if len(sub) == 1 else None

    def get(self, part: str, cell: str, model: str, col: str) -> float:
        r = self.row(part, cell, model)
        if r is None or col not in r.index or pd.isna(r[col]):
            return float("nan")
        return float(r[col])

    def ci(self, part: str, cell: str, model: str, metric: str) -> tuple[float, float]:
        return (self.get(part, cell, model, metric + "_ci_low"), self.get(part, cell, model, metric + "_ci_high"))

    def part_cells(self, part: str) -> list[str]:
        return list(dict.fromkeys(self.cells.loc[self.cells["part"] == part, "cell"]))


# ----------------------------------------------------------------------------------------------
# Figures
# ----------------------------------------------------------------------------------------------
def setup_mpl() -> None:
    matplotlib.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "Nimbus Roman", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 7, "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
        "pdf.fonttype": 42, "ps.fonttype": 42,
        "axes.facecolor": "white", "figure.facecolor": "white",
        "axes.edgecolor": "black", "axes.linewidth": 0.6,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "axes.grid.which": "major",
        "grid.color": "#D9D9D9", "grid.linewidth": 0.5, "axes.axisbelow": True,
        "xtick.major.width": 0.6, "ytick.major.width": 0.6, "xtick.minor.width": 0.4, "ytick.minor.width": 0.4,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5, "xtick.minor.size": 1.5, "ytick.minor.size": 1.5,
        "xtick.major.pad": 1.5, "ytick.major.pad": 1.5, "axes.labelpad": 1.5,
        "hatch.linewidth": 0.4, "lines.linewidth": 1.0, "lines.markersize": 3.0,
        "figure.constrained_layout.h_pad": 0.01, "figure.constrained_layout.w_pad": 0.01,
        "figure.constrained_layout.hspace": 0.0, "figure.constrained_layout.wspace": 0.0,
        "svg.hashsalt": "paper_assets",
    })


PDF_META = {"Creator": "scripts/paper_assets.py", "Producer": None, "CreationDate": None, "ModDate": None}


class Out:
    """Collects written files (relative to the paper dir) and manifest entries."""

    def __init__(self, paper_dir: Path, png: bool) -> None:
        self.paper = paper_dir
        self.png = png
        self.files: list[str] = []
        self.manifest: list[dict] = []
        (paper_dir / "figures" / "eb").mkdir(parents=True, exist_ok=True)
        (paper_dir / "tables" / "eb").mkdir(parents=True, exist_ok=True)

    def save_fig(self, fig, rel: str) -> None:
        fig.savefig(self.paper / rel, metadata=PDF_META)
        if self.png:
            PNG_DIR.mkdir(parents=True, exist_ok=True)
            fig.savefig(PNG_DIR / (Path(rel).stem + ".png"), dpi=150)
        plt.close(fig)
        self.files.append(rel)

    def write(self, rel: str, text: str) -> None:
        (self.paper / rel).write_text(text)
        self.files.append(rel)

    def entry(self, **kw) -> None:
        self.manifest.append(kw)


def new_panel(width: float):
    fig, ax = plt.subplots(figsize=(width, PANEL_H), layout="constrained")
    return fig, ax


def plot_lines(ax, xs, data: Data, models, getter, ci=None, flagger=None, ls_override=None, hollow=False,
               band=True, jev_top=True):
    """getter(model, i) -> y; ci(model, i) -> (lo, hi); flagger(model, i) -> bool."""
    order = [m for m in models if m != JEV] + ([JEV] if JEV in models else []) if jev_top else list(models)
    for m in order:
        ys = np.array([getter(m, i) for i in range(len(xs))], dtype=float)
        fill, line = hexcol(FILL[m]), dark(FILL[m])
        z = 5 if m == JEV else 3
        if ci is not None and band:
            lo_hi = np.array([ci(m, i) for i in range(len(xs))], dtype=float)
            ax.fill_between(xs, lo_hi[:, 0], lo_hi[:, 1], color=fill, alpha=0.45, lw=0, zorder=z - 1)
        ax.plot(xs, ys, ls=ls_override or linestyle(m), color=line, lw=1.3 if m == JEV else 0.9,
                marker=MARKER[m], ms=3.4 if m == JEV else 3.0,
                mfc="white" if hollow else fill, mec=line, mew=0.6, zorder=z)
        if flagger is not None:
            fx = [xs[i] for i in range(len(xs)) if flagger(m, i) and not math.isnan(ys[i])]
            fy = [ys[i] for i in range(len(xs)) if flagger(m, i) and not math.isnan(ys[i])]
            if fx:
                ax.plot(fx, fy, ls="none", marker="x", color="black", ms=3.6, mew=0.7, zorder=z + 1)


def plot_bars(ax, ngroups: int, models, getter, ci=None, flagger=None, width=0.84, log=False):
    n = len(models)
    w = width / n
    for gi in range(ngroups):
        for mi, m in enumerate(models):
            v = getter(m, gi)
            if v is None or math.isnan(v):
                continue
            x = gi + (mi - (n - 1) / 2) * w
            flagged = flagger(m, gi) if flagger else False
            hatch = "xxxx" if flagged else ("////" if m in SELF_HOSTED else None)
            z = 4 if m == JEV else 3
            ax.bar(x, v, width=w, color=hexcol(FILL[m]), edgecolor="black", lw=0.9 if m == JEV else 0.6,
                   hatch=hatch, zorder=z, log=log)
            if ci is not None:
                lo, hi = ci(m, gi)
                if not (math.isnan(lo) or math.isnan(hi)):
                    ax.errorbar(x, v, yerr=[[max(0.0, v - lo)], [max(0.0, hi - v)]], fmt="none", ecolor="black",
                                elinewidth=0.5, capsize=0.9, capthick=0.5, zorder=6)
    ax.set_xlim(-0.5, ngroups - 0.5)


def line_handle(m: str) -> Line2D:
    return Line2D([0], [0], color=dark(FILL[m]), ls=linestyle(m), lw=1.3 if m == JEV else 0.9, marker=MARKER[m],
                  ms=3.4, mfc=hexcol(FILL[m]), mec=dark(FILL[m]), mew=0.6)


def bar_handle(m: str) -> Patch:
    return Patch(facecolor=hexcol(FILL[m]), edgecolor="black", lw=0.9 if m == JEV else 0.6,
                 hatch="////" if m in SELF_HOSTED else None)


FLAG_LINE = Line2D([0], [0], ls="none", marker="x", color="black", ms=3.6, mew=0.7)
FLAG_BAR = Patch(facecolor="white", edgecolor="black", lw=0.6, hatch="xxxx")


def legend_strip(out: Out, rel: str, handles, labels, width: float, ncol: int) -> None:
    """One-row-first legend; drops columns until the strip fits the given width."""
    fig = plt.figure(figsize=(width, 0.25))
    for nc in range(ncol, 0, -1):
        leg = fig.legend(handles, labels, loc="center", ncol=nc, frameon=False, handlelength=2.0, handleheight=0.9,
                         columnspacing=0.9, handletextpad=0.4, borderaxespad=0.0, labelspacing=0.3)
        if leg.get_window_extent().width <= 0.99 * fig.bbox.width:
            break
        leg.remove()
    rows = math.ceil(len(handles) / nc)
    fig.set_size_inches(width, 0.07 + 0.155 * rows)
    out.save_fig(fig, rel)


def wrapper(out: Out, name: str, star: bool, panels: list[tuple[str, str]], legend_w: float) -> None:
    env = "figure*" if star else "figure"
    pw = FIGSTAR_W if star else FIG_W
    lines = [f"% Generated by scripts/paper_assets.py; do not edit by hand.",
             f"\\begin{{{env}}}[!t]", "\\centering",
             f"\\includegraphics[width={legend_w:.2f}in]{{figures/eb/{name}_legend.pdf}}\\\\[-2pt]"]
    subs = []
    for letter, sub in panels:
        subs.append(f"\\subfloat[{sub}]{{\\includegraphics[width={pw:.2f}in]{{figures/eb/{name}_{letter}.pdf}}"
                    f"\\label{{fig:{name[4:]}_{letter}}}}}")
    lines.append("\\hfill\n".join(subs))
    lines += [f"\\caption{{{CAPTIONS[name]}}}", f"\\label{{fig:{name[4:]}}}", f"\\end{{{env}}}", ""]
    out.write(f"figures/eb/{name}.tex", "\n".join(lines))


def ci_cols(data: Data, rq: str, conds: list[str], metric: str):
    return lambda m, i: (data.get(rq, conds[i], m, metric + "_ci_low"), data.get(rq, conds[i], m, metric + "_ci_high"))


def tick_len(cond: str) -> str:
    if cond == "base":
        return "base"
    n = int(cond.split("_")[1])
    return f"{n // 1024}K" if n >= 1024 else str(n)


def fig_rq1(data: Data, out: Out) -> None:
    name = "fig_rq1"
    ca, cb = data.conds("RQ1a"), data.conds("RQ1b")
    xa, xb = list(range(len(ca))), [int(c[1:]) for c in cb]
    fl_a = lambda m, i: data.flag("RQ1a", ca[i], m)
    fl_b = lambda m, i: data.flag("RQ1b", cb[i], m)

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, xa, data, MAIN7, lambda m, i: data.get("RQ1a", ca[i], m, "latency_p50"),
               ci_cols(data, "RQ1a", ca, "latency_p50"), fl_a)
    ax.set_yscale("log")
    ax.set_xticks(xa, [tick_len(c) for c in ca])
    ax.set_xlabel("Input length (tokens)")
    ax.set_ylabel("Latency p50 (s)")
    out.save_fig(fig, f"figures/eb/{name}_a.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, xa, data, MAIN7, lambda m, i: data.get("RQ1a", ca[i], m, "em"), ci_cols(data, "RQ1a", ca, "em"),
               fl_a)
    ax.set_xticks(xa, [tick_len(c) for c in ca])
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Input length (tokens)")
    ax.set_ylabel("Exact match")
    out.save_fig(fig, f"figures/eb/{name}_b.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    kk = [int(c[1:]) for c in cb]
    plot_lines(ax, xb, data, MAIN7, lambda m, i: data.get("RQ1b", cb[i], m, "latency_p50") / kk[i],
               lambda m, i: (data.get("RQ1b", cb[i], m, "latency_p50_ci_low") / kk[i],
                             data.get("RQ1b", cb[i], m, "latency_p50_ci_high") / kk[i]), fl_b)
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_xticks(xb, [str(k) for k in kk])
    ax.minorticks_off()
    ax.set_xlabel("Requests per message $k$")
    ax.set_ylabel("Per-request p50 (s)")
    out.save_fig(fig, f"figures/eb/{name}_c.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, xb, data, MAIN7, lambda m, i: data.get("RQ1b", cb[i], m, "rq1b_request_em"),
               ci_cols(data, "RQ1b", cb, "rq1b_request_em"), fl_b)
    ax.set_xscale("log", base=2)
    ax.set_xticks(xb, [str(k) for k in kk])
    ax.minorticks_off()
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Requests per message $k$")
    ax.set_ylabel("Request-level EM")
    out.save_fig(fig, f"figures/eb/{name}_d.pdf")

    handles = [line_handle(m) for m in MAIN7]
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, [DISPLAY[m] for m in MAIN7], 7.0, 7)
    wrapper(out, name, True, [("a", "p50 latency vs.\\ input length"), ("b", "EM vs.\\ input length"),
                              ("c", "Per-request p50 vs.\\ $k$"),
                              ("d", "Request-level EM vs.\\ $k$")], 7.0)
    src = f"{ANA_REL}/cells.csv"
    flt = "role in {main, reference}; model in the 7-model roster (Rule excluded)"
    out.entry(id=f"{name}_a", file=f"figures/eb/{name}_a.pdf", plot_type="line (log-y, 95% CI band)", source=[src],
              columns=["latency_p50", "latency_p50_ci_low", "latency_p50_ci_high", "flag_valid_lt_50"],
              filters=f"rq == RQ1a; {flt}")
    out.entry(id=f"{name}_b", file=f"figures/eb/{name}_b.pdf", plot_type="line (95% CI band)", source=[src],
              columns=["em", "em_ci_low", "em_ci_high", "flag_valid_lt_50"], filters=f"rq == RQ1a; {flt}")
    out.entry(id=f"{name}_c", file=f"figures/eb/{name}_c.pdf", plot_type="line (log-x, log-y, 95% CI band)",
              source=[src], columns=["latency_p50", "latency_p50_ci_low", "latency_p50_ci_high", "flag_valid_lt_50"],
              filters=f"rq == RQ1b; {flt}; per-request value = column / k (k from condition name)")
    out.entry(id=f"{name}_d", file=f"figures/eb/{name}_d.pdf", plot_type="line (log-x, 95% CI band)", source=[src],
              columns=["rq1b_request_em", "rq1b_request_em_ci_low", "rq1b_request_em_ci_high", "flag_valid_lt_50"],
              filters=f"rq == RQ1b; {flt}")
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip", source=[],
              columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure* wrapper (4 panels)", source=[], columns=[],
              filters="")


def fig_rq2(data: Data, out: Out) -> None:
    name = "fig_rq2"
    conds = data.conds("RQ2")
    fl = lambda m, i: data.flag("RQ2", conds[i], m)
    specs = [("a", "em", "Exact match", "EM"),
             ("b", "unsafe_rate", "Unsafe-locality rate", "Unsafe-locality rate"),
             ("c", "spurious_rate", "Spurious-spec.\\ rate", "Spurious-specification rate")]
    any_flag = any(fl(m, i) for m in MAIN7 for i in range(len(conds)))
    for letter, col, ylabel, _ in specs:
        fig, ax = new_panel(FIGSTAR_W)
        plot_bars(ax, len(conds), MAIN7, lambda m, i, c=col: data.get("RQ2", conds[i], m, c),
                  ci_cols(data, "RQ2", conds, col), fl)
        ax.set_xticks(range(len(conds)), [RQ2_CODE[c] for c in conds])
        ax.tick_params(axis="x", length=0)
        ax.set_ylabel(ylabel.replace("\\ ", " "))
        if col == "em":
            ax.set_ylim(0, 1.05)
        else:
            ax.set_ylim(bottom=0)
        out.save_fig(fig, f"figures/eb/{name}_{letter}.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, 1, MAIN7, lambda m, i: data.get("RQ2", "clean", m, "latency_p50"),
              lambda m, i: (data.get("RQ2", "clean", m, "latency_p50"), data.get("RQ2", "clean", m, "latency_p95")),
              lambda m, i: data.flag("RQ2", "clean", m), log=True)
    ax.set_xticks([0], [RQ2_CODE["clean"]])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Latency (s)")
    out.save_fig(fig, f"figures/eb/{name}_d.pdf")

    handles = [bar_handle(m) for m in MAIN7]
    labels = [DISPLAY[m] for m in MAIN7]
    if any_flag:
        handles.append(FLAG_BAR)
        labels.append("valid < 50%")
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, labels, 7.0, len(handles))
    wrapper(out, name, True, [(s[0], s[3]) for s in specs] +
            [("d", "Latency, clean (p50 to p95)")], 7.0)
    src = f"{ANA_REL}/cells.csv"
    flt = "rq == RQ2; model in the 7-model roster"
    for letter, col, _, _ in specs:
        out.entry(id=f"{name}_{letter}", file=f"figures/eb/{name}_{letter}.pdf",
                  plot_type="grouped bar (95% CI error bars)", source=[src],
                  columns=[col, col + "_ci_low", col + "_ci_high", "flag_valid_lt_50"], filters=flt)
    out.entry(id=f"{name}_d", file=f"figures/eb/{name}_d.pdf",
              plot_type="bar + range (bar = p50, whisker to p95; raw latencies are not in the CSVs, so no box plot)",
              source=[src], columns=["latency_p50", "latency_p95", "flag_valid_lt_50"],
              filters="rq == RQ2; condition == clean; model in the 7-model roster")
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip", source=[],
              columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure* wrapper (4 panels)", source=[], columns=[],
              filters="")


def fig_rq3(data: Data, out: Out) -> None:
    name = "fig_rq3"
    fs = sorted({int(c.split("_")[0][1:]) for c in data.conds("RQ3")})
    ds = list(dict.fromkeys(c.split("_")[1] for c in data.conds("RQ3")))
    assert ds == ["low", "medium", "high"], ds
    cF = [f"F{f}_medium" for f in fs]
    cD = [f"F{fs[-1]}_{d}" for d in ds]
    flF = lambda m, i: data.flag("RQ3", cF[i], m)
    flD = lambda m, i: data.flag("RQ3", cD[i], m)

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, fs, data, MAIN7, lambda m, i: data.get("RQ3", cF[i], m, "em"), ci_cols(data, "RQ3", cF, "em"), flF)
    ax.set_xticks(fs, [str(f) for f in fs])
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Contract fields $F$")
    ax.set_ylabel("Exact match")
    out.save_fig(fig, f"figures/eb/{name}_a.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, fs, data, MAIN7, lambda m, i: data.get("RQ3", cF[i], m, "latency_p50"),
               ci_cols(data, "RQ3", cF, "latency_p50"), flF)
    ax.set_yscale("log")
    ax.set_xticks(fs, [str(f) for f in fs])
    ax.set_xlabel("Contract fields $F$")
    ax.set_ylabel("Latency p50 (s)")
    out.save_fig(fig, f"figures/eb/{name}_b.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, len(fs), MAIN7, lambda m, i: data.get("RQ3", cF[i], m, "output_tokens_median"), None, flF)
    ax.set_xticks(range(len(fs)), [f"$F$ = {f}" for f in fs])
    ax.tick_params(axis="x", length=0)
    ax.set_xlabel("Contract fields")
    ax.set_ylabel("Output tokens")
    ax.set_ylim(bottom=0)
    out.save_fig(fig, f"figures/eb/{name}_c.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    xd = list(range(len(ds)))
    plot_lines(ax, xd, data, MAIN7, lambda m, i: data.get("RQ3", cD[i], m, "em"), ci_cols(data, "RQ3", cD, "em"), flD)
    ax.set_xticks(xd, ds)
    ax.set_xlim(-0.25, len(ds) - 0.75)
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel(f"Constraint density $D$ ($F$ = {fs[-1]})")
    ax.set_ylabel("Exact match")
    out.save_fig(fig, f"figures/eb/{name}_d.pdf")

    handles = [line_handle(m) for m in MAIN7]
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, [DISPLAY[m] for m in MAIN7], 7.0, 7)
    wrapper(out, name, True, [("a", "EM vs.\\ $F$ ($D$ = medium)"), ("b", "p50 latency vs.\\ $F$ ($D$ = medium)"),
                              ("c", "Output tokens ($D$ = medium)"),
                              ("d", f"EM vs.\\ $D$ ($F$ = {fs[-1]})")], 7.0)
    src = f"{ANA_REL}/cells.csv"
    out.entry(id=f"{name}_a", file=f"figures/eb/{name}_a.pdf", plot_type="line (95% CI band)", source=[src],
              columns=["em", "em_ci_low", "em_ci_high", "flag_valid_lt_50"],
              filters="rq == RQ3; condition in {F4,F6,F8}_medium; 7-model roster")
    out.entry(id=f"{name}_b", file=f"figures/eb/{name}_b.pdf", plot_type="line (log-y, 95% CI band)", source=[src],
              columns=["latency_p50", "latency_p50_ci_low", "latency_p50_ci_high", "flag_valid_lt_50"],
              filters="rq == RQ3; condition in {F4,F6,F8}_medium; 7-model roster")
    out.entry(id=f"{name}_c", file=f"figures/eb/{name}_c.pdf", plot_type="grouped bar (no CI column in CSV)",
              source=[src], columns=["output_tokens_median", "flag_valid_lt_50"],
              filters="rq == RQ3; condition in {F4,F6,F8}_medium; 7-model roster")
    out.entry(id=f"{name}_d", file=f"figures/eb/{name}_d.pdf", plot_type="line (95% CI band)", source=[src],
              columns=["em", "em_ci_low", "em_ci_high", "flag_valid_lt_50"],
              filters="rq == RQ3; condition in F8_{low,medium,high}; 7-model roster")
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip", source=[],
              columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure* wrapper (4 panels)", source=[], columns=[],
              filters="")


def fig_rq4(data: Data, out: Out) -> None:
    name = "fig_rq4"
    cK = [c for c in data.conds("RQ4") if c.startswith("K")]
    ks = [int(c[1:]) for c in cK]
    roster = MAIN7 + [RERANKER, CLF_ALL]
    flK = lambda m, i: data.flag("RQ4", cK[i], m)

    def log_k(ax):
        ax.set_xscale("log")
        ax.set_xticks(ks, [str(k) for k in ks])
        ax.minorticks_off()
        ax.set_xlabel("Catalog size $K$ (services)")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, ks, data, roster, lambda m, i: data.get("RQ4", cK[i], m, "seen_top1"),
               ci_cols(data, "RQ4", cK, "seen_top1"), flK, band=False)
    plot_lines(ax, ks, data, roster, lambda m, i: data.get("RQ4", cK[i], m, "unseen_top1"),
               ci_cols(data, "RQ4", cK, "unseen_top1"), flK, ls_override=":", hollow=True, band=False)
    log_k(ax)
    ax.set_ylim(-0.03, 1.03)
    ax.set_ylabel("Service top-1 accuracy")
    out.save_fig(fig, f"figures/eb/{name}_a.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, ks, data, roster, lambda m, i: data.get("RQ4", cK[i], m, "latency_p50"),
               ci_cols(data, "RQ4", cK, "latency_p50"), flK)
    log_k(ax)
    ax.set_yscale("log")
    ax.set_ylabel("Latency p50 (s)")
    out.save_fig(fig, f"figures/eb/{name}_b.pdf")

    churn = [c for c in data.conds("RQ4") if c.startswith("churn")]
    churn_models = SIX + ["Qwen3.5-4B-JSON", RERANKER, CLF_FROZEN, CLF_RETRAINED]
    groups = [(c, kind) for c in churn for kind in ("seen", "unseen")]
    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, len(groups), churn_models,
              lambda m, i: data.get("RQ4", groups[i][0], m, f"{groups[i][1]}_top1"),
              lambda m, i: (data.get("RQ4", groups[i][0], m, f"{groups[i][1]}_top1_ci_low"),
                            data.get("RQ4", groups[i][0], m, f"{groups[i][1]}_top1_ci_high")),
              lambda m, i: data.flag("RQ4", groups[i][0], m), width=0.88)
    ax.set_xticks(range(len(groups)), [f"{c[5:]}%\n{kind}" for c, kind in groups])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Top-1 accuracy")
    out.save_fig(fig, f"figures/eb/{name}_c.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, ks, data, roster, lambda m, i: data.get("RQ4", cK[i], m, "unsupported_f1"),
               ci_cols(data, "RQ4", cK, "unsupported_f1"), flK, band=False)
    log_k(ax)
    ax.set_ylim(-0.03, 1.03)
    ax.set_ylabel("Unsupported F1")
    out.save_fig(fig, f"figures/eb/{name}_d.pdf")

    legend_models = MAIN7 + [RERANKER, CLF_ALL, CLF_FROZEN, CLF_RETRAINED]
    handles = [line_handle(m) for m in legend_models]
    labels = [DISPLAY[m] for m in legend_models]
    grey = dark(GREYS[1])
    handles += [Line2D([0], [0], color=grey, ls="-", marker="o", ms=3.4, mfc=hexcol(GREYS[1]), mec=grey, mew=0.6),
                Line2D([0], [0], color=grey, ls=":", marker="o", ms=3.4, mfc="white", mec=grey, mew=0.6),
                Patch(facecolor="white", edgecolor="black", lw=0.6, hatch="////"), FLAG_LINE, FLAG_BAR]
    labels += ["seen top-1", "unseen top-1", "self-hosted (bars)", "valid < 50% (lines)", "valid < 50% (bars)"]
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, labels, 7.0, len(handles))
    wrapper(out, name, True, [("a", "Seen and unseen top-1 vs.\\ $K$"),
                              ("b", "p50 latency vs.\\ $K$"),
                              ("c", "Top-1 under churn"),
                              ("d", "Unsupported F1 vs.\\ $K$")], 7.0)
    src = f"{ANA_REL}/cells.csv"
    flt = "rq == RQ4; condition in K4..K254; 7-model roster + MiniLM-Reranker + DistilBERT-Clf-All"
    out.entry(id=f"{name}_a", file=f"figures/eb/{name}_a.pdf", plot_type="line (log-x; no CI band, 18 series)",
              source=[src], columns=["seen_top1", "unseen_top1", "flag_valid_lt_50"], filters=flt)
    out.entry(id=f"{name}_b", file=f"figures/eb/{name}_b.pdf", plot_type="line (log-x, log-y, 95% CI band)",
              source=[src], columns=["latency_p50", "latency_p50_ci_low", "latency_p50_ci_high", "flag_valid_lt_50"],
              filters=flt)
    out.entry(id=f"{name}_c", file=f"figures/eb/{name}_c.pdf", plot_type="grouped bar (95% CI error bars)",
              source=[src], columns=["seen_top1", "seen_top1_ci_low", "seen_top1_ci_high", "unseen_top1",
                                     "unseen_top1_ci_low", "unseen_top1_ci_high", "flag_valid_lt_50"],
              filters="rq == RQ4; condition in {churn25, churn50}; six + Qwen3.5-4B-JSON + MiniLM-Reranker + "
                      "DistilBERT-Clf-Frozen + DistilBERT-Clf-Retrained")
    out.entry(id=f"{name}_d", file=f"figures/eb/{name}_d.pdf", plot_type="line (log-x; no CI band)", source=[src],
              columns=["unsupported_f1", "flag_valid_lt_50"], filters=flt)
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip", source=[],
              columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure* wrapper (4 panels)", source=[], columns=[],
              filters="")


def fig_comms(data: Data, out: Out) -> None:
    # --- latency: deadline-violation probability
    name = "fig_comms_latency"
    cols = [c for c in data.df.columns if re.fullmatch(r"p_gt_\d_\d{3}", c)]
    taus = [round(float(c[5:].replace("_", ".")) * 1000) for c in cols]
    for letter, (rq, cond) in zip("ab", [("RQ2", "clean"), ("RQ1a", "pad_16384")]):
        fig, ax = new_panel(FIG_W)
        plot_lines(ax, taus, data, MAIN7, lambda m, i: data.get(rq, cond, m, cols[i]),
                   lambda m, i: (data.get(rq, cond, m, cols[i] + "_ci_low"), data.get(rq, cond, m, cols[i] + "_ci_high")),
                   lambda m, i: data.flag(rq, cond, m))
        ax.set_xscale("log")
        ax.set_xticks(taus, [str(t) for t in taus])
        ax.minorticks_off()
        ax.set_ylim(-0.03, 1.03)
        ax.set_xlabel("Deadline $\\tau$ (ms)")
        ax.set_ylabel("P(latency > $\\tau$)")
        out.save_fig(fig, f"figures/eb/{name}_{letter}.pdf")
        out.entry(id=f"{name}_{letter}", file=f"figures/eb/{name}_{letter}.pdf",
                  plot_type="line (log-x, 95% CI band)", source=[f"{ANA_REL}/comms.csv"],
                  columns=cols + [c + s for c in cols for s in ("_ci_low", "_ci_high")] + ["flag_valid_lt_50"],
                  filters=f"rq == {rq}; condition == {cond}; 7-model roster")
    handles = [line_handle(m) for m in MAIN7]
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, [DISPLAY[m] for m in MAIN7], 3.36, 4)
    wrapper(out, name, False, [("a", "Clean requests (RQ2)"), ("b", "16{,}384-token inputs (RQ1a)")], 3.36)
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip", source=[],
              columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure wrapper (2 panels)", source=[], columns=[],
              filters="")

    # --- efficiency: cost and energy
    name = "fig_comms_efficiency"
    ticks = ["RQ2\nclean", "RQ1a\n16K", "RQ3\nF8 high", "RQ4\nK254"]
    fl = lambda m, i: data.flag(COMMS_CONDS[i][0], COMMS_CONDS[i][1], m)
    fig, ax = new_panel(FIG_W)
    plot_bars(ax, len(COMMS_CONDS), HOSTED,
              lambda m, i: data.get(*COMMS_CONDS[i], m, "cost_usd_per_1000_correct"), None, fl, log=True)
    ax.set_xticks(range(len(COMMS_CONDS)), ticks)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("USD per 1k correct")
    out.save_fig(fig, f"figures/eb/{name}_a.pdf")
    fig, ax = new_panel(FIG_W)
    plot_bars(ax, len(COMMS_CONDS), SELF_HOSTED,
              lambda m, i: data.get(*COMMS_CONDS[i], m, "energy_j_per_decision"), None, fl)
    ax.set_xticks(range(len(COMMS_CONDS)), ticks)
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(bottom=0)
    ax.set_ylabel("Energy (J/decision)")
    out.save_fig(fig, f"figures/eb/{name}_b.pdf")
    any_flag = any(fl(m, i) for m in HOSTED + SELF_HOSTED for i in range(len(COMMS_CONDS)))
    models = HOSTED + SELF_HOSTED
    models = [m for m in MAIN7 if m in models]
    handles = [bar_handle(m) for m in models]
    labels = [DISPLAY[m] for m in models]
    if any_flag:
        handles.append(FLAG_BAR)
        labels.append("valid < 50%")
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, labels, 3.36, 4)
    wrapper(out, name, False, [("a", "Hosted: USD per 1k correct"),
                               ("b", "Self-hosted: J per decision")], 3.36)
    conds_txt = "; ".join(f"{rq}/{c}" for rq, c in COMMS_CONDS)
    out.entry(id=f"{name}_a", file=f"figures/eb/{name}_a.pdf", plot_type="grouped bar (log-y; no CI column in CSV)",
              source=[f"{ANA_REL}/cells.csv"], columns=["cost_usd_per_1000_correct", "flag_valid_lt_50"],
              filters=f"(rq, condition) in {{{conds_txt}}}; hosted models")
    out.entry(id=f"{name}_b", file=f"figures/eb/{name}_b.pdf", plot_type="grouped bar (no CI column in CSV)",
              source=[f"{ANA_REL}/comms.csv"], columns=["energy_j_per_decision", "flag_valid_lt_50"],
              filters=f"(rq, condition) in {{{conds_txt}}}; self-hosted models")
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip", source=[],
              columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure wrapper (2 panels)", source=[], columns=[],
              filters="")


def fig_rq5a(data: RQ5Data, out: Out) -> None:
    name = "fig_rq5a"
    lambdas = [1, 2, 4, 8, 16]
    l_cells = [f"load_{l}" for l in lambdas]

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, lambdas, data, MAIN7,
               lambda m, i: data.get("A", l_cells[i], m, "strict_completion"),
               lambda m, i: data.ci("A", l_cells[i], m, "strict"))
    ax.set_xscale("log", base=2)
    ax.set_xticks(lambdas, [str(l) for l in lambdas])
    ax.minorticks_off()
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel(r"Offered load $\lambda$ (req/s)")
    ax.set_ylabel("Primary completion")
    out.save_fig(fig, f"figures/eb/{name}_a.pdf")

    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, lambdas, data, MAIN7,
               lambda m, i: data.get("A", l_cells[i], m, "T_p95_completions"),
               lambda m, i: data.ci("A", l_cells[i], m, "T_p95_completions"))
    ax.set_xscale("log", base=2)
    ax.set_xticks(lambdas, [str(l) for l in lambdas])
    ax.minorticks_off()
    ax.set_ylim(0, 2.15)
    ax.set_xlabel(r"Offered load $\lambda$ (req/s)")
    ax.set_ylabel("Latency p95 (s)")
    out.save_fig(fig, f"figures/eb/{name}_b.pdf")

    deadlines = [0.5, 1.0, 2.0, 4.0]
    d_cells = ["deadline_0.5", "deadline_1", "load_4", "deadline_4"]
    fig, ax = new_panel(FIGSTAR_W)
    plot_lines(ax, deadlines, data, MAIN7,
               lambda m, i: data.get("A", d_cells[i], m, "strict_completion"),
               lambda m, i: data.ci("A", d_cells[i], m, "strict"))
    ax.set_xscale("log", base=2)
    ax.set_xticks(deadlines, ["0.5", "1", "2", "4"])
    ax.minorticks_off()
    ax.set_ylim(-0.03, 1.03)
    ax.set_xlabel("Deadline $D$ (s)")
    ax.set_ylabel("Primary completion")
    out.save_fig(fig, f"figures/eb/{name}_c.pdf")

    reuse_cells = ["load_4", "reuse_changing_on", "reuse_repeated_off", "reuse_repeated_on"]
    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, 4, MAIN7,
              lambda m, i: data.get("A", reuse_cells[i], m, "strict_completion"),
              lambda m, i: data.ci("A", reuse_cells[i], m, "strict"))
    ax.set_xticks(range(4), ["CO", "CN", "RO", "RN"])
    ax.tick_params(axis="x", length=0)
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Primary completion")
    out.save_fig(fig, f"figures/eb/{name}_d.pdf")

    handles = [line_handle(m) for m in MAIN7]
    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, [DISPLAY[m] for m in MAIN7], 7.0, 7)
    wrapper(out, name, True, [("a", r"Completion vs.\ $\lambda$"),
                              ("b", r"Latency p95 vs.\ $\lambda$"),
                              ("c", r"Completion vs.\ deadline $D$"),
                              ("d", "Cache reuse block")], 7.0)

    src = "../experiments/rq5-end-to-end/results/cells.csv"
    flt = "part == A; 7-model roster"
    out.entry(id=f"{name}_a", file=f"figures/eb/{name}_a.pdf", plot_type="line (log-x, 95% CI band)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["strict_completion", "strict_ci_low", "strict_ci_high"],
              filters=f"{flt}; cell in {{load_1, load_2, load_4, load_8, load_16}}")
    out.entry(id=f"{name}_b", file=f"figures/eb/{name}_b.pdf", plot_type="line (log-x, 95% CI band)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["T_p95_completions", "T_p95_completions_ci_low", "T_p95_completions_ci_high"],
              filters=f"{flt}; cell in {{load_1, load_2, load_4, load_8, load_16}}")
    out.entry(id=f"{name}_c", file=f"figures/eb/{name}_c.pdf", plot_type="line (log-x, 95% CI band)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["strict_completion", "strict_ci_low", "strict_ci_high"],
              filters=f"{flt}; cell in {{deadline_0.5, deadline_1, load_4, deadline_4}}")
    out.entry(id=f"{name}_d", file=f"figures/eb/{name}_d.pdf", plot_type="grouped bar (95% CI error bars)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["strict_completion", "strict_ci_low", "strict_ci_high"],
              filters=f"{flt}; cell in {{load_4, reuse_changing_on, reuse_repeated_off, reuse_repeated_on}}")
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip",
              experiment_id="EXP-2026-002", source=[], columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure* wrapper (4 panels)",
              experiment_id="EXP-2026-002", source=[], columns=[], filters="")


def fig_rq5b(data: RQ5Data, out: Out) -> None:
    name = "fig_rq5b"
    conds_off = ["steady_changing_off", "steady_repeated_off", "bursty_changing_off", "bursty_repeated_off"]
    conds_on = ["steady_changing_on", "steady_repeated_on", "bursty_changing_on", "bursty_repeated_on"]
    codes = ["SC", "SR", "BC", "BR"]

    # (a) Correct completion, cache OFF
    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, 4, MAIN7,
              lambda m, i: data.get("B", conds_off[i], m, "operational_completion"),
              lambda m, i: data.ci("B", conds_off[i], m, "operational"),
              width=0.84)
    ax.set_xticks(range(4), codes)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Correct completion")
    ax.set_ylim(0, 0.65)
    out.save_fig(fig, f"figures/eb/{name}_a.pdf")

    # (b) Correct completion, cache ON
    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, 4, MAIN7,
              lambda m, i: data.get("B", conds_on[i], m, "operational_completion"),
              lambda m, i: data.ci("B", conds_on[i], m, "operational"),
              width=0.84)
    ax.set_xticks(range(4), codes)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Correct completion")
    ax.set_ylim(0, 0.65)
    out.save_fig(fig, f"figures/eb/{name}_b.pdf")

    # (c) p95 T of completions, cache OFF
    fig, ax = new_panel(FIGSTAR_W)
    plot_bars(ax, 4, MAIN7,
              lambda m, i: data.get("B", conds_off[i], m, "T_p95_completions"),
              lambda m, i: data.ci("B", conds_off[i], m, "T_p95_completions"),
              width=0.84)
    ax.set_xticks(range(4), codes)
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Latency p95 (s)")
    ax.set_ylim(0, 2.15)
    out.save_fig(fig, f"figures/eb/{name}_c.pdf")

    # (d) Stacked mean time decomposition for SC0
    fig, ax = new_panel(FIGSTAR_W)
    bar_w = 0.72
    for mi, m in enumerate(MAIN7):
        r = data.row("B", "steady_changing_off", m)
        if r is None or pd.isna(r["mean_decision_s"]):
            continue
        w = float(r["mean_admission_wait_s"]) if pd.notna(r["mean_admission_wait_s"]) else 0.0
        d = float(r["mean_decision_s"]) if pd.notna(r["mean_decision_s"]) else 0.0
        s_exec = float(r["mean_execution_s"]) if pd.notna(r["mean_execution_s"]) else 0.0
        s_q = float(r["mean_service_queue_s"]) if pd.notna(r["mean_service_queue_s"]) else 0.0
        s_tr = float(r["mean_transfer_s"]) if pd.notna(r["mean_transfer_s"]) else 0.0
        s = s_exec + s_q + s_tr

        lw = 0.9 if m == JEV else 0.6
        hatch = "////" if m in SELF_HOSTED else None

        ax.bar(mi, w, width=bar_w, bottom=0, color=hexcol(PALETTE["ebBlue"]),
               edgecolor="black", lw=lw, hatch=hatch, zorder=3)
        ax.bar(mi, d, width=bar_w, bottom=w, color=hexcol(PALETTE["ebDeepBlue"]),
               edgecolor="black", lw=lw, hatch=hatch, zorder=3)
        ax.bar(mi, s, width=bar_w, bottom=w + d, color=hexcol(PALETTE["ebCoral"]),
               edgecolor="black", lw=lw, hatch=hatch, zorder=3)

    ax.set_xlim(-0.5, len(MAIN7) - 0.5)
    # Seven three-letter codes do not fit side by side; stagger every other one instead of rotating.
    ax.set_xticks(range(len(MAIN7)), [("" if i % 2 == 0 else "\n") + MODEL_CODE[m] for i, m in enumerate(MAIN7)])
    ax.tick_params(axis="x", length=0)
    ax.set_ylabel("Mean request time (s)")
    ax.set_ylim(bottom=0)
    out.save_fig(fig, f"figures/eb/{name}_d.pdf")

    handles = [bar_handle(m) for m in MAIN7]
    labels = [DISPLAY[m] for m in MAIN7]
    handles += [
        Patch(facecolor=hexcol(PALETTE["ebBlue"]), edgecolor="black", lw=0.6),
        Patch(facecolor=hexcol(PALETTE["ebDeepBlue"]), edgecolor="black", lw=0.6),
        Patch(facecolor=hexcol(PALETTE["ebCoral"]), edgecolor="black", lw=0.6),
    ]
    labels += ["Wait", "Decision", "Service"]

    legend_strip(out, f"figures/eb/{name}_legend.pdf", handles, labels, 7.0, 7)
    wrapper(out, name, True, [("a", "Correct completion, cache off"),
                              ("b", "Correct completion, cache on"),
                              ("c", r"Latency p95, cache off"),
                              ("d", "Time breakdown (SC0)")], 7.0)

    src = "../experiments/rq5-end-to-end/results/cells.csv"
    flt = "part == B; 7-model roster"
    out.entry(id=f"{name}_a", file=f"figures/eb/{name}_a.pdf", plot_type="grouped bar (95% CI error bars)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["operational_completion", "operational_ci_low", "operational_ci_high"],
              filters=f"{flt}; cache off (SC, SR, BC, BR)")
    out.entry(id=f"{name}_b", file=f"figures/eb/{name}_b.pdf", plot_type="grouped bar (95% CI error bars)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["operational_completion", "operational_ci_low", "operational_ci_high"],
              filters=f"{flt}; cache on (SC, SR, BC, BR)")
    out.entry(id=f"{name}_c", file=f"figures/eb/{name}_c.pdf", plot_type="grouped bar (95% CI error bars)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["T_p95_completions", "T_p95_completions_ci_low", "T_p95_completions_ci_high"],
              filters=f"{flt}; cache off (SC, SR, BC, BR)")
    out.entry(id=f"{name}_d", file=f"figures/eb/{name}_d.pdf", plot_type="stacked bar",
              experiment_id="EXP-2026-002", source=[src],
              columns=["mean_admission_wait_s", "mean_decision_s", "mean_execution_s",
                       "mean_service_queue_s", "mean_transfer_s"],
              filters=f"{flt}; cell == steady_changing_off")
    out.entry(id=f"{name}_legend", file=f"figures/eb/{name}_legend.pdf", plot_type="legend strip",
              experiment_id="EXP-2026-002", source=[], columns=[], filters="")
    out.entry(id=name, file=f"figures/eb/{name}.tex", plot_type="figure* wrapper (4 panels)",
              experiment_id="EXP-2026-002", source=[], columns=[], filters="")


# ----------------------------------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------------------------------
def isnan(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))


def signed(s: str) -> str:
    """Typeset a minus sign; a value that rounds to zero prints unsigned."""
    if not s.startswith("-"):
        return s
    return s[1:] if float(s) == 0 else "$-$" + s[1:]


def f3(v) -> str:
    return "--" if isnan(v) else signed(f"{v:.3f}")


def f1(v) -> str:
    return "--" if isnan(v) else signed(f"{v:.1f}")


def f2(v) -> str:
    return "--" if isnan(v) else f"{v:.2f}"


def fusd(v) -> str:
    return "--" if isnan(v) else f"{v:#.4g}"


def fnum(v) -> str:
    """Byte / token medians: integer when integral, one decimal otherwise."""
    if isnan(v):
        return "--"
    return f"{v:.0f}" if float(v).is_integer() else f"{v:.1f}"


def fsig2(p: float) -> str:
    if isnan(p):
        return "--"
    if p == 0:
        return "0"
    if p >= 0.001:
        s = f"{p:.2g}"
        return s if "e" not in s else f"{p:.4f}"
    mant, exp = f"{p:.1e}".split("e")
    return f"{mant}e{int(exp)}"


def fp_holm(p: float, floor: bool) -> str:
    # p_floor: the raw p sits at the resampling floor, so the adjusted value is an upper bound.
    return f"$\\le${fsig2(p)}" if floor else fsig2(p)


def ci_txt(lo, hi, fmt=f3) -> str:
    if isnan(lo) or isnan(hi):
        return ""
    return f"\\,{{\\color{{black!60}}[{fmt(lo)}, {fmt(hi)}]}}"


class Cell:
    def __init__(self, text: str, key: float | None = None, ci: str = "", flagged: bool = False,
                 bg: str | None = None):
        self.text, self.key, self.ci, self.flagged, self.bg = text, key, ci, flagged, bg
        self.best = False

    def render(self) -> str:
        if self.flagged:
            return f"\\cellcolor{{ebPink}}{self.text}{self.ci}"
        if self.best:
            return f"\\cellcolor{{ebCoral!35}}\\textbf{{{self.text}}}{self.ci}"
        if self.bg:
            return f"\\cellcolor{{{self.bg}}}{self.text}{self.ci}"
        return f"{self.text}{self.ci}"


def mark_block(cells: list[Cell], direction: str) -> None:
    """Best per row within a 7-model block (excluding QJS at index 6 from best)."""
    cands = [c for c in cells[:6] if not c.flagged and c.key is not None and not isnan(c.key)]
    if not cands:
        return
    keyf = {"max": lambda v: -v, "min": lambda v: v}[direction]
    best_cand = min(cands, key=lambda c: keyf(c.key))
    best_text = best_cand.text
    winners = [c for c in cands if c.text == best_text]
    if len(winners) == len(cands):
        return
    for c in winners:
        c.best = True


def mark_best(rows: list[list[Cell]], directions: list[str | None]) -> None:
    """directions[j] in {'max','min','absmin',None} for data column j (rows exclude the label column)."""
    for j, d in enumerate(directions):
        if d is None:
            continue
        cand = [(r[j].key, r[j]) for r in rows if not r[j].flagged and r[j].key is not None and not isnan(r[j].key)]
        if len(cand) < 2:
            continue
        keyf = {"max": lambda v: -v, "min": lambda v: v, "absmin": lambda v: abs(v)}[d]
        best_text = min(cand, key=lambda t: keyf(t[0]))[1].text
        winners = [c for _, c in cand if c.text == best_text]  # ties at print precision
        if len(winners) * 2 > len(cand):
            continue  # a best value shared by most rows does not discriminate; leave the column unmarked
        for c in winners:
            c.best = True


def label_cell(m: str, flagged: bool) -> str:
    name = "{" + TEX_NAME[m] + "}" + ("$^\\dagger$" if flagged else "")
    return f"\\cellcolor{{ebPink}}{name}" if flagged else name


FLAG_NOTE = ("\\providecommand{\\ebflagnote}{$^\\dagger$Valid output rate below 0.5; "
             "the row is printed but excluded from the best-value marking.}")


def render_table(*, name: str, star: bool, colspec: str, header: list[str], blocks: list[tuple[str, list]],
                 ncols: int, tabcolsep: str = "3pt", size: str = "\\scriptsize", source: str, rowpad: str = "0pt") -> str:
    """blocks: (group title or '', [(model or None, label_tex, [Cell...], flagged_row)])."""
    env = "table*" if star else "table"
    any_flag = any(r[3] for _, rows in blocks for r in rows)
    L = [f"% Generated by scripts/paper_assets.py from {source}; do not edit by hand.",
         f"\\begin{{{env}}}[!t]", "\\centering", f"\\caption{{{CAPTIONS[name]}}}", f"\\label{{tab:{name[4:]}}}", size,
         f"\\setlength{{\\tabcolsep}}{{{tabcolsep}}}",
         f"\\setlength{{\\aboverulesep}}{{0pt}}\\setlength{{\\belowrulesep}}{{0pt}}\\setlength{{\\extrarowheight}}{{{rowpad}}}",
         "\\renewcommand{\\arraystretch}{0.94}"]
    if any_flag:
        L.append(FLAG_NOTE)
    L += ["\\def\\ebtab{%", f"\\begin{{tabular}}{{{colspec}}}", "\\toprule"]
    for h in header:
        L.append(h)
    L.append("\\midrule")
    for title, rows in blocks:
        if title:
            L.append(f"\\rowcolor{{ebAmber!45}}\\multicolumn{{{ncols}}}{{l}}{{\\textbf{{\\textit{{{title}}}}}}} \\\\")
        for model, label, cells, flagged in rows:
            pre = "\\rowcolor{ebCoral!10}" if model == JEV else ""
            L.append(pre + " & ".join([label] + [c.render() for c in cells]) + " \\\\")
    L += ["\\bottomrule", "\\end{tabular}}",
          # fill \linewidth: spread the difference to the natural width over the 2*ncols column gaps
          # headers go on one line when the table fits, otherwise name and unit are stacked; the gap never drops
          # below 1.5pt, since a negative gap makes neighbouring cells and their colours overlap
          "\\def\\ebh#1#2{#1 #2}\\sbox0{\\ebtab}",
          "\\ifdim\\wd0>\\dimexpr\\linewidth-1pt\\relax"
          "\\def\\ebh#1#2{\\shortstack{#1\\\\{}#2}}\\sbox0{\\ebtab}\\fi",
          f"\\setlength{{\\tabcolsep}}{{\\dimexpr\\tabcolsep+(\\linewidth-\\wd0-1pt)/{2 * ncols}\\relax}}",
          "\\ifdim\\tabcolsep<1.5pt\\setlength{\\tabcolsep}{1.5pt}\\fi",
          f"\\typeout{{EBTAB {name} natural=\\the\\wd0\\space line=\\the\\linewidth\\space sep=\\the\\tabcolsep}}",
          "\\ebtab"]
    if any_flag:
        L.append("\\par\\smallskip{\\scriptsize\\ebflagnote\\par}")
    L += [f"\\end{{{env}}}", ""]
    return "\n".join(L)


def hdr(cells: list[str]) -> str:
    """Header row; 'name|unit' becomes \\ebh{name}{unit}: one line when the table fits, stacked when it does not."""
    def cell(c: str) -> str:
        if "|" not in c:
            return c
        name, unit = c.split("|", 1)
        return f"\\ebh{{{name}}}{{{unit}}}"
    return "\\rowcolor{ebBlue}" + " & ".join(cell(c) for c in cells) + " \\\\"


UP, DOWN = "$\\uparrow$", "$\\downarrow$"


def mrow(data: Data, rq: str, cond: str, m: str, spec: list[tuple]) -> tuple:
    """spec entries: (kind, col[, extra]); kinds: prop, propci, s, s_div (col, k), usd, j, num."""
    r = data.row(rq, cond, m)
    flagged = bool(r["flag_valid_lt_50"])
    cells = []
    for item in spec:
        kind, col = item[0], item[1]
        v = r[col] if col in r.index else float("nan")
        v = float("nan") if pd.isna(v) else float(v)
        if kind == "propci":
            c = Cell(f3(v), v, ci_txt(float(r[col + "_ci_low"]) if not pd.isna(r[col + "_ci_low"]) else float("nan"),
                                      float(r[col + "_ci_high"]) if not pd.isna(r[col + "_ci_high"]) else float("nan")))
        elif kind in ("prop", "s"):
            c = Cell(f3(v), v)
        elif kind == "s_div":
            v = v / item[2]
            c = Cell(f3(v), v)
        elif kind == "usd":
            c = Cell(fusd(v), v)
        elif kind == "j":
            c = Cell(f1(v), v)
        elif kind == "rate2":
            c = Cell(f2(v), v)
        elif kind == "num":
            c = Cell(fnum(v), v)
        else:
            raise ValueError(kind)
        if isnan(v):
            c.key = None
        c.flagged = flagged and not isnan(v)
        cells.append(c)
    return (m, label_cell(m, flagged), cells, flagged)


def model_blocks(data: Data, rq: str, conds: list[str], titles: dict, models: list[str], spec, directions):
    blocks = []
    for cond in conds:
        rows = [mrow(data, rq, cond, m, spec(cond) if callable(spec) else spec) for m in models]
        mark_best([r[2] for r in rows], directions)
        blocks.append((titles[cond], rows))
    return blocks


def rq1a_title(c: str) -> str:
    return "Base length" if c == "base" else f"Padded to {int(c.split('_')[1]):,} tokens".replace(",", "{,}")


def tab_rq1a(data: Data, out: Out) -> None:
    conds = data.conds("RQ1a")
    spec = [("propci", "em"), ("prop", "valid_rate"), ("prop", "macro_field_acc"), ("s", "latency_p50"),
            ("s", "latency_p95"), ("s", "latency_p99"), ("num", "output_tokens_median"),
            ("usd", "cost_usd_per_1000_correct"), ("j", "energy_j_per_decision")]
    dirs = ["max", "max", "max", "min", "min", "min", None, "min", "min"]
    blocks = model_blocks(data, "RQ1a", conds, {c: rq1a_title(c) for c in conds}, MAIN7, spec, dirs)
    header = [hdr(["Model", f"EM [95\\% CI]|{UP}", f"Valid|{UP}", f"Macro acc.|{UP}", f"p50|(s) {DOWN}",
                   f"p95|(s) {DOWN}", f"p99|(s) {DOWN}", "Output|tokens", f"USD per 1k|correct {DOWN}",
                   f"Energy|(J/dec.) {DOWN}"])]
    text = render_table(name="tab_rq1a", star=True, colspec="l" + "r" * 9, header=header, blocks=blocks, ncols=10,
                        source="cells.csv + comms.csv")
    out.write("tables/eb/tab_rq1a.tex", text)
    out.entry(id="tab_rq1a", file="tables/eb/tab_rq1a.tex", plot_type="table* (35 rows)",
              source=[f"{ANA_REL}/cells.csv", f"{ANA_REL}/comms.csv"],
              columns=["em", "em_ci_low", "em_ci_high", "valid_rate", "macro_field_acc", "latency_p50", "latency_p95",
                       "latency_p99", "output_tokens_median", "cost_usd_per_1000_correct", "energy_j_per_decision",
                       "flag_valid_lt_50"], filters="rq == RQ1a; 7-model roster")


def tab_rq1b(data: Data, out: Out) -> None:
    conds = data.conds("RQ1b")
    spec = lambda c: [("propci", "rq1b_request_em"), ("prop", "rq1b_message_all_correct"),
                      ("s_div", "latency_p50", int(c[1:])), ("s", "latency_p50"), ("s", "latency_p95"),
                      ("usd", "cost_usd_per_1000_correct"), ("j", "energy_j_per_decision")]
    dirs = ["max", "max", "min", "min", "min", "min", "min"]
    titles = {c: f"$k={int(c[1:])}$ request{'s' if int(c[1:]) > 1 else ''} per message" for c in conds}
    blocks = model_blocks(data, "RQ1b", conds, titles, MAIN7, spec, dirs)
    header = [hdr(["Model", f"Request EM [95\\% CI]|{UP}", f"Message|all-correct {UP}", f"Per-request|p50 (s) {DOWN}",
                   f"Message|p50 (s) {DOWN}", f"Message|p95 (s) {DOWN}", f"USD per 1k|correct {DOWN}",
                   f"Energy|(J/dec.) {DOWN}"])]
    text = render_table(name="tab_rq1b", star=True, colspec="l" + "r" * 7, header=header, blocks=blocks, ncols=8,
                        tabcolsep="5pt", source="cells.csv + comms.csv")
    out.write("tables/eb/tab_rq1b.tex", text)
    out.entry(id="tab_rq1b", file="tables/eb/tab_rq1b.tex", plot_type="table* (28 rows)",
              source=[f"{ANA_REL}/cells.csv", f"{ANA_REL}/comms.csv"],
              columns=["rq1b_request_em", "rq1b_request_em_ci_low", "rq1b_request_em_ci_high",
                       "rq1b_message_all_correct", "latency_p50", "latency_p95", "cost_usd_per_1000_correct",
                       "energy_j_per_decision", "flag_valid_lt_50"],
              filters="rq == RQ1b; 7-model roster; per-request p50 = latency_p50 / k")


def tab_rq2(data: Data, out: Out) -> None:
    conds = data.conds("RQ2")
    spec = [("propci", "em"), ("prop", "macro_field_acc"), ("prop", "valid_rate"), ("prop", "unsafe_rate"),
            ("prop", "spurious_rate"), ("prop", "missed_rate"), ("s", "latency_p50"), ("s", "latency_p95")]
    dirs = ["max", "max", "max", "min", "min", "min", "min", "min"]
    blocks = model_blocks(data, "RQ2", conds, RQ2_LONG, MAIN7, spec, dirs)
    header = [hdr(["Model", f"EM [95\\% CI]|{UP}", f"Macro acc.|{UP}", f"Valid|{UP}", f"Unsafe|{DOWN}",
                   f"Spurious|{DOWN}", f"Missed|{DOWN}", f"p50|(s) {DOWN}", f"p95|(s) {DOWN}"])]
    text = render_table(name="tab_rq2", star=True, colspec="l" + "r" * 8, header=header, blocks=blocks, ncols=9,
                        tabcolsep="5pt", source="cells.csv")
    out.write("tables/eb/tab_rq2.tex", text)
    out.entry(id="tab_rq2", file="tables/eb/tab_rq2.tex", plot_type="table* (56 rows)", source=[f"{ANA_REL}/cells.csv"],
              columns=[s[1] for s in spec] + ["em_ci_low", "em_ci_high", "flag_valid_lt_50"],
              filters="rq == RQ2; 7-model roster")


def tab_rq2_contrasts(data: Data, out: Out) -> None:
    con = data.con[data.con["rq"] == "RQ2"]
    hyp = data.hyp[data.hyp["hypothesis"] == "H3_paired"]
    conds = data.conds("RQ2")
    others = [m for m in SIX if m != JEV]
    blocks = []
    for cond in conds:
        rows = []
        for m in others:
            r = con[(con["condition"] == cond) & (con["model"] == m) & (con["reference_model"] == JEV)]
            h = hyp[(hyp["level"] == cond) & (hyp["model"] == m) & (hyp["reference_model"] == JEV)]
            assert len(r) == 1 and len(h) == 1, (cond, m)
            r, h = r.iloc[0], h.iloc[0]
            # the Holm-adjusted H3 contrast must be the same unsafe difference as contrasts.csv
            assert abs(float(h["estimate"]) - float(r["unsafe_diff"])) < 1e-12, (cond, m)
            flagged = not pd.isna(h["flag_low_valid"]) or data.flag("RQ2", cond, m)
            verdict = str(h["verdict"])
            cells = [Cell(f3(r["em_diff"]), None, ci_txt(r["em_diff_ci_low"], r["em_diff_ci_high"])),
                     Cell(fsig2(float(r["em_mcnemar_p"]))),
                     Cell(f3(r["unsafe_diff"]), None, ci_txt(r["unsafe_diff_ci_low"], r["unsafe_diff_ci_high"])),
                     Cell(fsig2(float(r["unsafe_mcnemar_p"]))),
                     Cell(fp_holm(float(h["holm_p"]), bool(h["p_floor"]))),
                     Cell(verdict)]
            if verdict == "resolved":
                cells[-1].best = True
            for c in cells:
                c.flagged = flagged
            label = f"{{{TEX_NAME[m]}}} $-$ {{\\jev}}" + ("$^\\dagger$" if flagged else "")
            rows.append((m, f"\\cellcolor{{ebPink}}{label}" if flagged else label, cells, flagged))
        blocks.append((RQ2_LONG[cond], rows))
    header = [hdr(["Contrast", "EM diff.|[95\\% CI]", "EM|McNemar $p$", "Unsafe diff.|[95\\% CI]", "Unsafe|McNemar $p$",
                   "Unsafe Holm|$p$ (H3)", "Verdict"])]
    text = render_table(name="tab_rq2_contrasts", star=True, colspec="l" + "r" * 5 + "l", header=header,
                        blocks=blocks, ncols=7, tabcolsep="6pt", source="contrasts.csv + hypotheses.csv (H3_paired)")
    out.write("tables/eb/tab_rq2_contrasts.tex", text)
    out.entry(id="tab_rq2_contrasts", file="tables/eb/tab_rq2_contrasts.tex", plot_type="table* (40 rows)",
              source=[f"{ANA_REL}/contrasts.csv", f"{ANA_REL}/hypotheses.csv"],
              columns=["em_diff", "em_diff_ci_low", "em_diff_ci_high", "em_mcnemar_p", "unsafe_diff",
                       "unsafe_diff_ci_low", "unsafe_diff_ci_high", "unsafe_mcnemar_p", "holm_p", "p_floor",
                       "verdict", "flag_low_valid"],
              filters="contrasts: rq == RQ2, reference_model == Jev-1.13.0; hypotheses: hypothesis == H3_paired, "
                      "joined on (model, level == condition); 'resolved' verdicts highlighted")


def tab_rq3(data: Data, out: Out) -> None:
    conds = data.conds("RQ3")
    fs = sorted({int(c.split("_")[0][1:]) for c in conds})
    ds = ["low", "medium", "high"]
    blocks = []
    for f in fs:
        rows = []
        for m in MAIN7:
            cells, flags = [], []
            spec_cells = []
            for d in ds:
                spec_cells.append((f"F{f}_{d}", "em", f3))
            for d in ds:
                spec_cells.append((f"F{f}_{d}", "latency_p50", f3))
            spec_cells.append((f"F{f}_medium", "output_tokens_median", fnum))
            for cond, col, fmt in spec_cells:
                v = data.get("RQ3", cond, m, col)
                fl = data.flag("RQ3", cond, m)
                c = Cell(fmt(v), None if isnan(v) else v)
                c.flagged = fl
                cells.append(c)
                flags.append(fl)
            flagged = any(flags)
            rows.append((m, label_cell(m, flagged), cells, flagged))
        mark_best([r[2] for r in rows], ["max"] * 3 + ["min"] * 3 + [None])
        blocks.append((f"$F={f}$ contract fields", rows))
    header = ["\\rowcolor{ebBlue} & \\multicolumn{3}{c}{EM " + UP + " by constraint density $D$} & "
              "\\multicolumn{3}{c}{p50 (s) " + DOWN + " by constraint density $D$} & Out.\\ tokens \\\\",
              "\\cmidrule(lr){2-4}\\cmidrule(lr){5-7}",
              hdr(["Model"] + ds + ds + ["$D$ = medium"])]
    text = render_table(name="tab_rq3", star=True, colspec="l" + "r" * 7, header=header, blocks=blocks, ncols=8,
                        tabcolsep="7pt", source="cells.csv")
    out.write("tables/eb/tab_rq3.tex", text)
    out.entry(id="tab_rq3", file="tables/eb/tab_rq3.tex", plot_type="table* (21 rows)", source=[f"{ANA_REL}/cells.csv"],
              columns=["em", "latency_p50", "output_tokens_median", "flag_valid_lt_50"],
              filters="rq == RQ3; 7-model roster; columns grouped by constraint density D")


def tab_rq4a(data: Data, out: Out) -> None:
    conds = [c for c in data.conds("RQ4") if c.startswith("K")]
    roster = MAIN7 + [RERANKER, CLF_ALL]
    spec = [("prop", "seen_top1"), ("prop", "unseen_top1"), ("prop", "unsupported_f1"),
            ("prop", "rq4_false_admission_rate"), ("prop", "rq4_false_blocking_rate"), ("prop", "em"),
            ("prop", "valid_rate"), ("s", "latency_p50"), ("s", "latency_p95")]
    dirs = ["max", "max", "max", "min", "min", "max", "max", "min", "min"]
    blocks = model_blocks(data, "RQ4", conds, {c: f"$K={int(c[1:])}$ services" for c in conds}, roster, spec, dirs)
    header = [hdr(["Model", f"Seen|top-1 {UP}", f"Unseen|top-1 {UP}", f"Unsupported|F1 {UP}", f"False|admission {DOWN}",
                   f"False|blocking {DOWN}", f"EM|{UP}", f"Valid|{UP}", f"p50|(s) {DOWN}", f"p95|(s) {DOWN}"])]
    text = render_table(name="tab_rq4a", star=True, colspec="l" + "r" * 9, header=header, blocks=blocks, ncols=10,
                        tabcolsep="5pt", source="cells.csv + comms.csv")
    out.write("tables/eb/tab_rq4a.tex", text)
    out.entry(id="tab_rq4a", file="tables/eb/tab_rq4a.tex", plot_type="table* (45 rows)",
              source=[f"{ANA_REL}/cells.csv", f"{ANA_REL}/comms.csv"],
              columns=[s[1] for s in spec] + ["flag_valid_lt_50"],
              filters="rq == RQ4; condition in K4..K254; 7-model roster + MiniLM-Reranker + DistilBERT-Clf-All")


def tab_rq4b(data: Data, out: Out) -> None:
    churn = [c for c in data.conds("RQ4") if c.startswith("churn")]
    models = SIX + ["Qwen3.5-4B-JSON", RERANKER, CLF_FROZEN, CLF_RETRAINED]
    h5 = data.hyp[data.hyp["hypothesis"] == "H5"]
    blocks = []
    for cond in churn:
        rows = []
        for m in models:
            flagged = data.flag("RQ4", cond, m)
            seen = data.get("RQ4", cond, m, "seen_top1")
            unseen = data.get("RQ4", cond, m, "unseen_top1")
            if m in (CLF_FROZEN, CLF_RETRAINED):
                g = data.h5[(data.h5["condition"] == cond) & (data.h5["model"] == m)]
                assert len(g) == 1
                g = g.iloc[0]
                assert abs(float(g["seen_top1"]) - seen) < 1e-12 and abs(float(g["unseen_top1"]) - unseen) < 1e-12
                gap, lo, hi = float(g["gap"]), float(g["gap_ci_low"]), float(g["gap_ci_high"])
                ex = float(g["added_labelled_examples"])
                t = float("nan") if pd.isna(g["training_wall_time_s"]) else float(g["training_wall_time_s"])
            else:
                g = h5[(h5["level"] == cond) & (h5["model"] == m)]
                assert len(g) == 1, (cond, m)
                g = g.iloc[0]
                flagged = flagged or not pd.isna(g["flag_low_valid"])
                gap, lo, hi = float(g["estimate"]), float(g["ci_low"]), float(g["ci_high"])
                ex, t = float("nan"), float("nan")
            cells = [Cell(f3(seen), seen), Cell(f3(unseen), unseen), Cell(f3(gap), gap, ci_txt(lo, hi)),
                     Cell(fnum(ex)), Cell(f1(t))]
            for c in cells:
                c.flagged = flagged and c.text != "--"
            rows.append((m, label_cell(m, flagged), cells, flagged))
        mark_best([r[2] for r in rows], ["max", "max", "absmin", None, None])
        blocks.append((f"{cond[5:]}\\% churn", rows))
    header = [hdr(["Model", f"Seen|{UP}", f"Unseen|{UP}", "Gap|[95\\% CI] $\\to0$", "Adapt.|ex.", "Adapt.|(s)"])]
    text = render_table(name="tab_rq4b", star=False, colspec="lrrrrr", header=header, blocks=blocks, ncols=6,
                        tabcolsep="1.5pt", source="cells.csv + hypotheses.csv (H5) + h5_classifier_reference.csv")
    out.write("tables/eb/tab_rq4b.tex", text)
    out.entry(id="tab_rq4b", file="tables/eb/tab_rq4b.tex", plot_type="table (20 rows)",
              source=[f"{ANA_REL}/cells.csv", f"{ANA_REL}/hypotheses.csv", f"{ANA_REL}/h5_classifier_reference.csv"],
              columns=["seen_top1", "unseen_top1", "estimate", "ci_low", "ci_high", "gap", "gap_ci_low", "gap_ci_high",
                       "added_labelled_examples", "training_wall_time_s", "flag_valid_lt_50", "flag_low_valid"],
              filters="rq == RQ4; condition in {churn25, churn50}; gap from hypotheses.csv H5 (interpreters, "
                      "reranker) or h5_classifier_reference.csv (DistilBERT frozen / retrained)")


def tab_comms(data: Data, out: Out) -> None:
    spec = [("s", "latency_p95"), ("s", "latency_p99"), ("s", "jitter_iqr_s"), ("prop", "p_gt_0_200"),
            ("prop", "p_gt_1_000"), ("prop", "availability"), ("rate2", "goodput_correct_per_s"),
            ("prop", "sla_violation_rate"), ("num", "request_bytes_median"), ("num", "response_bytes_median"),
            ("usd", "cost_usd_per_1000_correct"), ("j", "energy_j_per_decision")]
    dirs = ["min", "min", "min", "min", "min", "max", "max", "min", "min", "min", "min", "min"]
    titles = {"clean": "RQ2, clean", "pad_16384": "RQ1a, 16{,}384-token input", "F8_high": "RQ3, $F=8$, high density",
              "K254": "RQ4, $K=254$ services"}
    blocks = []
    for rq, cond in COMMS_CONDS:
        rows = [mrow(data, rq, cond, m, spec) for m in MAIN7]
        mark_best([r[2] for r in rows], dirs)
        blocks.append((titles[cond], rows))
    header = [hdr(["Model", f"p95|(s) {DOWN}", f"p99|(s) {DOWN}", f"Jitter IQR|(s) {DOWN}", f"P($>$0.2\\,s)|{DOWN}",
                   f"P($>$1\\,s)|{DOWN}", f"Avail.|{UP}", f"Goodput|(corr./s) {UP}", f"SLA|violation {DOWN}",
                   f"Request|(B) {DOWN}", f"Response|(B) {DOWN}", f"USD per 1k|correct {DOWN}",
                   f"Energy|(J/dec.) {DOWN}"])]
    text = render_table(name="tab_comms", star=True, colspec="l" + "r" * 12, header=header, blocks=blocks, ncols=13,
                        tabcolsep="3.2pt", source="cells.csv + comms.csv")
    out.write("tables/eb/tab_comms.tex", text)
    out.entry(id="tab_comms", file="tables/eb/tab_comms.tex", plot_type="table* (28 rows)",
              source=[f"{ANA_REL}/cells.csv", f"{ANA_REL}/comms.csv"], columns=[s[1] for s in spec] + ["flag_valid_lt_50"],
              filters="(rq, condition) in {RQ2/clean, RQ1a/pad_16384, RQ3/F8_high, RQ4/K254}; 7-model roster")


def tex_escape(s: str) -> str:
    return s.replace("_", "\\_").replace("%", "\\%").replace("&", "\\&")


def contrast_tex(s: str) -> str:
    s = re.sub(r"\b([GR])_([^()]+)\(([^)]*)\)", lambda mm: f"${mm.group(1)}$({mm.group(2)}; {mm.group(3)})", s)
    s = s.replace(" @ ", " at ")
    parts = re.split(r"(\$[^$]*\$)", s)
    return "".join(p if p.startswith("$") else tex_escape(p).replace(" - ", " $-$ ") for p in parts)


HYP_TITLE = {
    "latency_contrast": "paired p50 latency difference (s)",
    "ratio_test": "ratio of latency growth factors",
    "omnibus_unsafe": "Cochran's $Q$ on unsafe decisions (statistic)",
    "tokens_contrast": "paired output-token difference (tokens)",
    "catalog_gap": "seen $-$ unseen top-1 gap (proportion)",
}


def hyp_level(level: str) -> str:
    """Reader-facing name for a hypotheses.csv level (the same names as tab_corpus; no internal identifiers)."""
    if level == "base" or level.startswith("pad_") and " " not in level:
        return corpus_label("RQ1a", level)
    if level == "pad_16384 vs base":
        return "16{,}384 tokens vs base"
    if level == "k8 vs k1":
        return "$k=8$ vs $k=1$"
    if level == "F8 vs F4 pooled over D":
        return "$F=8$ vs $F=4$, all $D$"
    if level.startswith("churn"):
        return f"{level[5:]}\\% churn"
    return RQ2_LONG[level]


def tab_hypotheses(data: Data, out: Out) -> None:
    hyp = data.hyp[data.hyp["hypothesis"] != "H3_paired"]
    assert len(hyp) == len(data.hyp) - 40
    blocks = []
    for hname in list(dict.fromkeys(hyp["hypothesis"])):
        sub = hyp[hyp["hypothesis"] == hname]
        fam = sub["family"].iloc[0]
        assert (sub["family"] == fam).all()
        rows = []
        for _, r in sub.iterrows():
            flagged = not pd.isna(r["flag_low_valid"])
            est, lo, hi = float(r["estimate"]), float(r["ci_low"]), float(r["ci_high"])
            if fam == "omnibus_unsafe":
                assert lo == est == hi
                ec = Cell(f1(est))
            elif fam == "tokens_contrast":
                ec = Cell(f1(est), None, ci_txt(lo, hi, f1))
            else:
                ec = Cell(f3(est), None, ci_txt(lo, hi))
            verdict = str(r["verdict"])
            cells = [Cell(hyp_level(str(r["level"]))), ec, Cell(fp_holm(float(r["holm_p"]), bool(r["p_floor"]))),
                     Cell(verdict)]
            if verdict == "resolved":
                cells[-1].best = True
            for c in cells:
                c.flagged = flagged
            label = contrast_tex(re.sub(r" @ .*$", "", str(r["contrast"]))) + ("$^\\dagger$" if flagged else "")
            model = r["model"] if r["model"] in FILL else None
            rows.append((model, f"\\cellcolor{{ebPink}}{label}" if flagged else label, cells, flagged))
        blocks.append((f"{hname.split('_')[0]}: {HYP_TITLE[fam]}", rows))
    header = [hdr(["Contrast", "Level", "Estimate [95\\% CI]", "Holm $p$", "Verdict"])]
    text = render_table(name="tab_hypotheses", star=True, colspec="p{3.05in}lrrl", header=header, blocks=blocks,
                        ncols=5, tabcolsep="6pt", source="hypotheses.csv (all rows except H3_paired)")
    out.write("tables/eb/tab_hypotheses.tex", text)
    out.entry(id="tab_hypotheses", file="tables/eb/tab_hypotheses.tex", plot_type=f"table* ({len(hyp)} rows)",
              source=[f"{ANA_REL}/hypotheses.csv"],
              columns=["hypothesis", "family", "contrast", "level", "estimate", "ci_low", "ci_high", "holm_p", "p_floor",
                       "verdict", "flag_low_valid"],
              filters="hypothesis != H3_paired (those 40 rows are in tab_rq2_contrasts); 'resolved' verdicts "
                      "highlighted; p_floor rows print the Holm value as an upper bound")


def corpus_label(rq: str, cond: str) -> str:
    """Reader-facing condition name for tab_corpus (no internal identifiers in the paper)."""
    if rq == "RQ1a":
        return "Base length" if cond == "base" else f"Padded to {int(cond.split('_')[1]):,} tokens".replace(",", "{,}")
    if rq == "RQ1b":
        k = int(cond[1:])
        return f"$k={k}$ request" + ("" if k == 1 else "s") + " per message"
    if rq == "RQ2":
        return RQ2_LONG[cond]
    if rq == "RQ3":
        f, d = cond.split("_")
        return f"$F={f[1:]}$, {d} density"
    if cond.startswith("churn"):
        return f"{cond[5:]}\\% churn at $K=64$"
    return f"$K={cond[1:]}$ services"


def tab_corpus(data: Data, out: Out) -> None:
    stats = {}
    for line in (CORPUS / "stats.md").read_text().splitlines():
        mm = re.match(r"\|\s*(RQ\w+)/(\w+)\s*\|\s*(test|dev)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|"
                      r"\s*([\d.]+)\s*\|", line)
        if mm:
            rq, cond, split = mm.group(1), mm.group(2), mm.group(3)
            stats[(rq, cond, split)] = [float(mm.group(i)) for i in (4, 5, 6, 7)]
    yields = json.loads((CORPUS / "_yields.json").read_text())
    blocks, n_gen, n_der = [], 0, 0
    for rq in ["RQ1a", "RQ1b", "RQ2", "RQ3", "RQ4"]:
        rows = []
        for cond in data.conds(rq):
            t, d = stats[(rq, cond, "test")], stats[(rq, cond, "dev")]
            y = yields.get(cond)
            n_gen += y is not None
            n_der += y is None
            cells = [Cell("generated" if y else "derived"), Cell(fnum(t[0])), Cell(fnum(d[0])),
                     Cell(fnum(t[1])), Cell(fnum(t[2])), Cell(fnum(t[3])),
                     Cell(f3(y["first_pass"]) if y else "--"), Cell(f3(y["final"]) if y else "--")]
            rows.append((None, corpus_label(rq, cond), cells, False))
        blocks.append((rq, rows))
    assert (n_gen, n_der) == (23, 10), (n_gen, n_der)
    assert len(stats) == 2 * (n_gen + n_der)
    header = [hdr(["Condition", "Kind", "$N$|test", "$N$|dev", "Length|p5", "Length|p50", "Length|p95",
                   "First-pass|yield", "Final|yield"])]
    text = render_table(name="tab_corpus", star=True, colspec="llrrrrrrr", header=header, blocks=blocks, ncols=9,
                        tabcolsep="8pt", source="EdgeIntent v1 stats.md + _yields.json")
    text = text.replace("\\end{tabular}\n", "\\end{tabular}\n\\par\\smallskip{\\scriptsize Lengths are tiktoken "
                        "tokens of the test split.\\par}\n")
    out.write("tables/eb/tab_corpus.tex", text)
    out.entry(id="tab_corpus", file="tables/eb/tab_corpus.tex", plot_type="table* (33 rows)",
              source=[os.path.relpath(CORPUS / f, PAPER) for f in ("stats.md", "_yields.json")],
              columns=["N (test, dev)", "Length p5/p50/p95 (test)", "first_pass", "final"],
              filters="one row per condition; generated = present in _yields.json (23), derived otherwise (10); "
                      "condition order from cells.csv")


def tab_rq5a(data: RQ5Data, out: Out) -> None:
    sweeps_a = [
        ("Offered load sweep ($\\lambda \\in \\{1, 2, 4, 8, 16\\}$ req/s)",
         [("load_1", r"$\lambda{=}1$"), ("load_2", r"$\lambda{=}2$"),
          ("load_4", r"$\lambda{=}4$"), ("load_8", r"$\lambda{=}8$"),
          ("load_16", r"$\lambda{=}16$")]),
        ("Deadline sweep ($D \\in \\{0.5, 1, 4\\}$ s; $D=2$\\,s in load sweep)",
         [("deadline_0.5", r"$D{=}0.5$\,s"), ("deadline_1", r"$D{=}1$\,s"),
          ("deadline_4", r"$D{=}4$\,s")]),
        ("Topology sweep ($N \\in \\{10, 20, 40\\}$ nodes; $N=5$ in load sweep)",
         [("topo_10", r"$N{=}10$"), ("topo_20", r"$N{=}20$"), ("topo_40", r"$N{=}40$")]),
        ("Cache reuse sweep ($\\lambda=4$, $D=2$\\,s; CO in load sweep)",
         [("reuse_changing_on", "changing, on"),
          ("reuse_repeated_off", "repeated, off"),
          ("reuse_repeated_on", "repeated, on")]),
        ("Burstiness sweep ($\\lambda=4$, $D=2$\\,s, Poisson bursts)",
         [("bursty", "bursty")]),
    ]

    blocks = []
    for sweep_title, cell_list in sweeps_a:
        sweep_rows = []
        for cell_id, cell_label in cell_list:
            row_cells = []
            for m in MAIN7:
                v = data.get("A", cell_id, m, "strict_completion")
                txt = f3(v)
                c = Cell(txt, None if isnan(v) else v, bg="ebCoral!10" if m == JEV else None)
                row_cells.append(c)
            for m in MAIN7:
                v = data.get("A", cell_id, m, "T_p95_completions")
                txt = f2(v)
                c = Cell(txt, None if isnan(v) else v, bg="ebCoral!10" if m == JEV else None)
                row_cells.append(c)
            mark_block(row_cells[:7], "max")
            mark_block(row_cells[7:14], "min")
            sweep_rows.append((None, cell_label, row_cells, False))
        blocks.append((sweep_title, sweep_rows))

    header = [
        r"\rowcolor{ebBlue} & \multicolumn{7}{c}{Primary completion " + UP + r"} & \multicolumn{7}{c}{p95 $T$ (s) " + DOWN + r"} \\",
        r"\cmidrule(lr){2-8}\cmidrule(lr){9-15}",
        hdr(["Cell"] + [MODEL_CODE[m] for m in MAIN7] + [MODEL_CODE[m] for m in MAIN7]),
    ]
    text = render_table(name="tab_rq5a", star=True, colspec="l" + "r" * 14, header=header,
                        blocks=blocks, ncols=15, tabcolsep="3pt",
                        size=r"\scriptsize", source="cells.csv")
    out.write("tables/eb/tab_rq5a.tex", text)
    src = "../experiments/rq5-end-to-end/results/cells.csv"
    out.entry(id="tab_rq5a", file="tables/eb/tab_rq5a.tex", plot_type="table* (15 rows)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["strict_completion", "T_p95_completions"],
              filters="part == A; sweeps: load, deadline, topology, reuse, burstiness; 7-model roster")


def tab_rq5b(data: RQ5Data, out: Out) -> None:
    groups_b = [
        ("Steady arrivals",
         [("steady_changing_off", "changing, off"),
          ("steady_changing_on", "changing, on"),
          ("steady_repeated_off", "repeated, off"),
          ("steady_repeated_on", "repeated, on")]),
        ("Bursty arrivals",
         [("bursty_changing_off", "changing, off"),
          ("bursty_changing_on", "changing, on"),
          ("bursty_repeated_off", "repeated, off"),
          ("bursty_repeated_on", "repeated, on")]),
    ]
    blocks = []
    n_total_rows = 0
    for group_title, cell_list in groups_b:
        group_rows = []
        for cell_id, cell_label in cell_list:
            row_cells = []
            for m in MAIN7:
                v = data.get("B", cell_id, m, "operational_completion")
                txt = f3(v)
                c = Cell(txt, None if isnan(v) else v, bg="ebCoral!10" if m == JEV else None)
                row_cells.append(c)
            for m in MAIN7:
                v = data.get("B", cell_id, m, "T_p95_completions")
                txt = f2(v)
                c = Cell(txt, None if isnan(v) else v, bg="ebCoral!10" if m == JEV else None)
                row_cells.append(c)
            mark_block(row_cells[:7], "max")
            mark_block(row_cells[7:14], "min")
            group_rows.append((None, cell_label, row_cells, False))
        blocks.append((group_title, group_rows))
        n_total_rows += len(group_rows)

    header = [
        r"\rowcolor{ebBlue} & \multicolumn{7}{c}{Correct completion " + UP + r"} & \multicolumn{7}{c}{p95 $T$ (s) " + DOWN + r"} \\",
        r"\cmidrule(lr){2-8}\cmidrule(lr){9-15}",
        hdr(["Condition"] + [MODEL_CODE[m] for m in MAIN7] + [MODEL_CODE[m] for m in MAIN7]),
    ]
    text = render_table(name="tab_rq5b", star=True, colspec="l" + "r" * 14, header=header,
                        blocks=blocks, ncols=15, tabcolsep="3pt",
                        size=r"\scriptsize", source="cells.csv")
    out.write("tables/eb/tab_rq5b.tex", text)
    src = "../experiments/rq5-end-to-end/results/cells.csv"
    out.entry(id="tab_rq5b", file="tables/eb/tab_rq5b.tex", plot_type=f"table* ({n_total_rows} rows)",
              experiment_id="EXP-2026-002", source=[src],
              columns=["operational_completion", "T_p95_completions"],
              filters="part == B; operational conditions; 7-model roster")


# ----------------------------------------------------------------------------------------------
# Manifest
# ----------------------------------------------------------------------------------------------
def git_sha(path: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def yq(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def write_manifest(out: Out, manifest_path: Path) -> None:
    code_sha, paper_sha = git_sha(ROOT), git_sha(PAPER)
    L = [MANIFEST_BEGIN]
    for e in out.manifest:
        exp_id = e.get("experiment_id", "EXP-2026-001")
        L += [f"  - artifact_id: {yq(e['id'])}",
              f"    paper_path: {yq(e['file'])}",
              f"    experiment_id: {yq(exp_id)}",
              '    run_id: ""',
              f"    source_data: [{', '.join(yq(s) for s in e['source'])}]",
              f"    columns: [{', '.join(yq(c) for c in e['columns'])}]",
              f"    filters: {yq(e['filters'])}",
              f"    plot_type: {yq(e['plot_type'])}",
              f"    generator: {yq(SCRIPT_REL)}",
              f"    code_git_sha: {yq(code_sha)}",
              f"    paper_git_sha: {yq(paper_sha)}",
              '    status: "draft"', ""]
    L.append(MANIFEST_END)
    block = "\n".join(L) + "\n"
    text = manifest_path.read_text()
    if MANIFEST_BEGIN in text:
        pre, rest = text.split(MANIFEST_BEGIN, 1)
        post = rest.split(MANIFEST_END + "\n", 1)[1]
        text = pre + block + post
    else:
        text = text.rstrip("\n") + "\n\n" + block
    manifest_path.write_text(text)


# ----------------------------------------------------------------------------------------------
def build(paper_dir: Path, png: bool, rq5_dir: Path | None = None) -> list[str]:
    check_palette()
    setup_mpl()
    data = Data()
    out = Out(paper_dir, png)
    fig_rq1(data, out)
    fig_rq2(data, out)
    fig_rq3(data, out)
    fig_rq4(data, out)
    fig_comms(data, out)
    tab_corpus(data, out)
    tab_rq1a(data, out)
    tab_rq1b(data, out)
    tab_rq2(data, out)
    tab_rq2_contrasts(data, out)
    tab_rq3(data, out)
    tab_rq4a(data, out)
    tab_rq4b(data, out)
    tab_comms(data, out)
    tab_hypotheses(data, out)

    if rq5_dir is None:
        rq5_dir = RQ5_RESULTS
    if (rq5_dir / "cells.csv").exists():
        rq5_data = RQ5Data(rq5_dir)
        fig_rq5a(rq5_data, out)
        fig_rq5b(rq5_data, out)
        tab_rq5a(rq5_data, out)
        tab_rq5b(rq5_data, out)
    else:
        print(f"RQ5 analysis inputs not found in {rq5_dir}; skipping RQ5 assets.")

    write_manifest(out, paper_dir / "figure-manifest.yml")
    return out.files


SHA_RE = re.compile(r'(code_git_sha|paper_git_sha): "[^"]*"')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="rebuild into a temp dir and compare SHA-256 hashes with the paper's files")
    ap.add_argument("--rq5-dir", type=Path, default=RQ5_RESULTS,
                    help="RQ5 results directory (default: experiments/rq5-end-to-end/results)")
    args = ap.parse_args()
    if not args.check:
        files = build(PAPER, png=True, rq5_dir=args.rq5_dir)
        print(f"wrote {len(files)} files + figure-manifest.yml block; PNG previews in {PNG_DIR}")
        return
    expected = json.loads((PAPER / "expected_sha256.json").read_text())
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        shutil.copy(PAPER / "figure-manifest.yml", tmp / "figure-manifest.yml")
        files = build(tmp, png=False, rq5_dir=args.rq5_dir)
        got = {f: hashlib.sha256((tmp / f).read_bytes()).hexdigest() for f in files}
    differs = sorted(f for f in expected if got.get(f) != expected[f])
    unexpected = sorted(set(got) - set(expected))
    if differs or unexpected:
        print("CHECK FAILED")
        for f in differs:
            print("  differs from the paper:", f)
        for f in unexpected:
            print("  not in the paper:", f)
        sys.exit(1)
    print(f"CHECK OK: all {len(expected)} figure and table files are byte-identical to the paper (SHA-256)")

if __name__ == "__main__":
    main()
