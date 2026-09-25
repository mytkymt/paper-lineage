"""問3の型分け: 輸入(初期参照の外部率)× 輸出(外から引かれる率)の 2×2。
中央値で四分し、各象限のサブ帯を列挙する。創始者関与(誕生後 5 年の中央値)も添える。"""
from __future__ import annotations
import csv, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
E = {int(r["sub"]): r for r in csv.DictReader((load.OUT / "export.csv").open()) if r["import_share_early"]}
FS = {int(r["sub"]): r for r in csv.DictReader((load.OUT / "founder_share.csv").open())}
im_med = np.median([float(r["import_share_early"]) for r in E.values()])
ex_med = np.median([float(r["export_share_median"]) for r in E.values()])
print(f"輸入の中央値 {im_med:.2f} / 輸出の中央値 {ex_med:.2f}")
quad = {("high", "high"): "橋渡し(輸入も輸出も多い)", ("low", "high"): "自前で作り外へ出す", ("high", "low"): "輸入して内で育てる", ("low", "low"): "内向き(自前で作り内で育てる)"}
rows = []
for s, r in E.items():
    im, ex = float(r["import_share_early"]), float(r["export_share_median"])
    q = ("high" if im >= im_med else "low", "high" if ex >= ex_med else "low")
    f = FS.get(s); fs = f and np.nanmedian([float(f[k]) for k in ("y1", "y2", "y3") if f.get(k) not in ("", "nan")] or [np.nan])
    rows.append([s, r["name"], r["band"], int(r["papers"]), im, ex, quad[q], "" if f is None or np.isnan(fs) else round(float(fs), 2)])
with (load.OUT / "typology.csv").open("w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["sub", "name", "band", "papers", "import_share", "export_share", "type", "founder_share_y1_3"]); w.writerows(rows)
for q in quad.values():
    rs = sorted([r for r in rows if r[6] == q], key=lambda r: -r[3])
    print(f"\n== {q} ({len(rs)}) ==")
    for r in rs[:9]: print(f"  {r[1][:34]:34} n={r[3]:4} 輸入{r[4]:.2f} 輸出{r[5]:.2f} 創始者{r[7]}")
