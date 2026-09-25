"""RQ1–2: 下位分野の時系列と「生んだ論文」。出力は analysis/out/<core|ext>/。

  subfield_timeseries.csv  サブ帯 × 年: 論文数、その年に受けた内部引用
  subfield_summary.csv     サブ帯ごと: 誕生年、ピーク、成長、深さ
  founders.csv             サブ帯ごと上位候補: 内部子孫数 / SPC / CD 指数
  depth_by_year.csv        年ごとの系譜の深さ(最長引用連鎖)の分布
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load  # noqa: E402

g = load.load()
n, year, sub = g.n, g.year, g.sub
S = len(g.sub_name)
print(f"nodes {n} subfields {S}", flush=True)

# ---------- 系譜の深さ: 各論文に至る最長の引用連鎖(DP、年順) ----------
depth = np.zeros(n, dtype=np.int32)
for i in g.topo:                       # 年の昇順 = トポロジカル順
    ups = g.upstream(i)
    if ups:
        depth[i] = depth[ups].max() + 1
# 下流側: その論文から始まる最長連鎖(逆順)
reach_depth = np.zeros(n, dtype=np.int32)
for i in g.topo[::-1]:
    downs = g.downstream(i)
    if downs:
        reach_depth[i] = reach_depth[downs].max() + 1

with (load.OUT / "depth_by_year.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["year", "papers", "mean_depth", "median_depth", "p90_depth", "share_depth0"])
    for y in range(int(year.min()), int(year.max()) + 1):
        m = year == y
        if m.sum():
            d = depth[m]
            w.writerow([y, int(m.sum()), round(float(d.mean()), 3), int(np.median(d)),
                        int(np.percentile(d, 90)), round(float((d == 0).mean()), 3)])

# ---------- サブ帯の時系列 ----------
cite_year = year[g.citing]             # 引用が起きた年(引用側の刊行年)
rows = []
for s in range(S):
    members = np.flatnonzero(sub == s)
    if not len(members): continue
    in_sub = set(members.tolist())
    by_year = defaultdict(lambda: [0, 0])
    for i in members: by_year[int(year[i])][0] += 1
    # その年に受けた内部引用(引用元がどこでも)
    m = np.isin(g.cited, members)
    for cy in cite_year[m]: by_year[int(cy)][1] += 1
    for y in sorted(by_year):
        rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], y, by_year[y][0], by_year[y][1]])
with (load.OUT / "subfield_timeseries.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "band", "year", "papers", "cites_received"]); w.writerows(rows)

# ---------- 生んだ論文: 内部子孫数(ビット集合の DP)、SPC、CD 指数 ----------
def cd_index(i: int, horizon: int | None) -> float | None:
    """Funk & Owen-Smith の CD 指数(コーパス内の引用のみ)。horizon は年数、None なら無期限。"""
    refs = set(g.upstream(i))
    citers_i = set(g.downstream(i))
    citers_refs = set()
    for r in refs: citers_refs.update(g.downstream(r))
    later = {j for j in citers_i | citers_refs if year[j] > year[i]}
    if horizon is not None:
        later = {j for j in later if year[j] <= year[i] + horizon}
    if not later: return None
    n_i = sum(1 for j in later if j in citers_i and j not in citers_refs)
    n_j = sum(1 for j in later if j in citers_i and j in citers_refs)
    n_k = sum(1 for j in later if j not in citers_i)
    return (n_i - n_j) / (n_i + n_j + n_k)

summary, founders = [], []
for s in range(S):
    members = np.flatnonzero(sub == s)
    if len(members) < 20: continue
    in_sub = {int(i): k for k, i in enumerate(members)}
    ys = year[members]
    order = np.argsort(ys, kind="stable")
    # 子孫集合を後ろから前へビット集合で畳む(サブ帯内の辺だけ)
    desc = {}
    for k in order[::-1]:
        i = int(members[k]); bits = 0
        for j in g.downstream(i):
            if j in in_sub:
                bits |= (1 << in_sub[j]) | desc.get(j, 0)
        desc[i] = bits
    n_desc = {i: bin(b).count("1") for i, b in desc.items()}
    # SPC: サブ帯内の下流辺の重み合計
    spc_out = defaultdict(float)
    m = np.isin(g.cited, members) & np.isin(g.citing, members)
    for a, w in zip(g.cited[m], g.spc[m]): spc_out[int(a)] += w
    size = len(members)
    cum = np.cumsum(np.bincount(ys - ys.min()))
    birth = int(ys.min() + np.searchsorted(cum, max(5, 0.02 * size)))     # 5本 or 2% に達した年
    peak = int(np.bincount(ys - ys.min()).argmax() + ys.min())
    q1, q3 = np.percentile(ys, [25, 75])
    summary.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], size, int(ys.min()), birth, peak,
                    int(np.median(ys)), int(q1), int(q3), round(float(depth[members].mean()), 2),
                    int(depth[members].max())])
    # 候補: 各指標の上位5
    cand = set()
    by_desc = sorted(n_desc, key=lambda i: -n_desc[i])[:5]
    by_spc = sorted(spc_out, key=lambda i: -spc_out[i])[:5]
    cand.update(by_desc); cand.update(by_spc)
    for i in cand:
        founders.append([s, g.sub_name[s], i, year[i], g.venue[i], g.title[i][:90], g.doi[i],
                         n_desc.get(i, 0), round(n_desc.get(i, 0) / size, 3), round(spc_out.get(i, 0.0), 1),
                         int(g.cited_by[i]), cd_index(i, None), cd_index(i, 5), int(reach_depth[i])])
    print(f"  sub {s:3} {g.sub_name[s][:32]:32} n={size:4} birth={birth} top={g.title[by_desc[0]][:40]}", flush=True)

with (load.OUT / "subfield_summary.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "name", "band", "papers", "first_year", "birth_year", "peak_year", "median_year", "q1_year", "q3_year", "mean_depth", "max_depth"])
    w.writerows(summary)
with (load.OUT / "founders.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "sub_name", "node", "year", "venue", "title", "doi", "desc_in_sub", "desc_share", "spc_out", "cited_by", "cd", "cd5", "reach_depth"])
    w.writerows(founders)
print("done", load.OUT)
