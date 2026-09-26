"""技術の波の図: 波ごとのコーパス占有率の推移(開始年で揃えた採用曲線)と、速さ×凝集の散布図。
waves.py の出力(wave_curves.csv, waves.csv)から描く。出力: results/core/fig_wave_curves.png, fig_wave_scatter.png"""
from __future__ import annotations
import csv, sys
from collections import defaultdict
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
curves = defaultdict(list)
for r in csv.DictReader((load.OUT / "wave_curves.csv").open()):
    curves[r["wave"]].append((int(r["year"]), float(r["share_of_corpus"])))
waves = list(csv.DictReader((load.OUT / "waves.csv").open()))
start = {r["wave"]: int(r["start"]) for r in waves}
fig, ax = plt.subplots(figsize=(9, 5.2))
cmap = plt.get_cmap("tab20")
for k, (name, pts) in enumerate(sorted(curves.items(), key=lambda kv: start[kv[0]])):
    xs = [y - start[name] for y, _ in pts]; ys = [100 * v for _, v in pts]
    lw = 2.6 if name.startswith("LLM") else 1.4
    ax.plot(xs, ys, lw=lw, color=cmap(k % 20), label=f"{name} ({start[name]})")
ax.set_xlabel("years since the wave started"); ax.set_ylabel("% of papers in the 13 core venues")
ax.set_xlim(0, 14); ax.grid(alpha=.3); ax.legend(fontsize=7.5, ncol=2, frameon=False)
ax.set_title("Technology waves in HCI, aligned at their start year (title/abstract keywords)")
fig.tight_layout(); fig.savefig(load.OUT / "fig_wave_curves.png", dpi=160)
fig, ax = plt.subplots(figsize=(7, 5))
for r in waves:
    x = float(r["cohesion_lift"]) if r["cohesion_lift"] not in ("", "nan") else None
    y = float(r["peak_share"]) * 100
    if x is None: continue
    nc = float(r["newcomer_author_share"]) - float(r["baseline_newcomer_share"])
    ax.scatter(x, y, s=40 + 400 * abs(nc), c="tab:red" if nc > 0 else "tab:blue", alpha=.7)
    ax.annotate(r["wave"], (x, y), fontsize=7.5, xytext=(4, 3), textcoords="offset points")
ax.set_xscale("log"); ax.set_xlabel("citation cohesion (lift over same-year non-wave papers)"); ax.set_ylabel("peak share of corpus (%)")
ax.set_title("Waves: did they form their own conversation, and how big did they get?\nred = more newcomers than baseline, blue = fewer; size = |difference|", fontsize=9)
ax.grid(alpha=.3); fig.tight_layout(); fig.savefig(load.OUT / "fig_wave_scatter.png", dpi=160)
print("wrote", load.OUT / "fig_wave_curves.png", load.OUT / "fig_wave_scatter.png")
