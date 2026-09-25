"""問3の軸「輸出」: サブ帯の論文が受けた引用のうち、コーパスの外から来た割合。
OpenAlex の cited_by_count(全体)と、コーパス内で受けた引用数から
  export_share = 1 - in_corpus / total
を論文ごとに出し、サブ帯ごとに集計(2020 年以前の論文に限る: 新しい論文は両方とも小さい)。
併せて「輸入」= 初期参照の外部率(parents.csv)と並べ、型分けの材料にする。"""
from __future__ import annotations
import csv, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, year = g.sub, g.year
in_c = np.bincount(g.cited, minlength=g.n)
tot = g.cited_by
parents = {int(r["sub"]): r for r in csv.DictReader((load.OUT / "parents.csv").open())}
rows = []
for s in range(len(g.sub_name)):
    m = np.flatnonzero((sub == s) & (year <= 2020) & (tot >= 5))
    if len(m) < 20: continue
    exp = 1 - in_c[m] / np.maximum(tot[m], in_c[m])
    p = parents.get(s)
    ext_in = (int(p["external_refs"]) / (int(p["in_corpus_refs"]) + int(p["external_refs"]))) if p and (int(p["in_corpus_refs"]) + int(p["external_refs"])) else ""
    rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], int((sub == s).sum()), len(m),
                 round(float(np.median(exp)), 3), round(float(exp.mean()), 3), round(ext_in, 3) if ext_in != "" else "",
                 int(np.median(tot[m]))])
with (load.OUT / "export.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "band", "papers", "papers_used", "export_share_median", "export_share_mean", "import_share_early", "median_cited_by"]); w.writerows(rows)
print("輸出率(外から引かれる割合)が高い / 低いサブ帯:")
for r in sorted(rows, key=lambda r: -r[5])[:8]: print(f"  高 {r[1][:32]:32} 輸出 {r[5]:.2f}  輸入(初期外部参照) {r[7]}  n={r[3]}")
for r in sorted(rows, key=lambda r: r[5])[:8]: print(f"  低 {r[1][:32]:32} 輸出 {r[5]:.2f}  輸入(初期外部参照) {r[7]}  n={r[3]}")
xs = [r[5] for r in rows]; print(f"全体: 輸出率の中央値 {np.median(xs):.2f}, 四分位 {np.percentile(xs,25):.2f}–{np.percentile(xs,75):.2f}")
im = [(r[7], r[5]) for r in rows if r[7] != ""]
print("輸入と輸出の相関(Spearman):", round(float(np.corrcoef(np.argsort(np.argsort([a for a,_ in im])), np.argsort(np.argsort([b for _,b in im])))[0,1]), 2))
