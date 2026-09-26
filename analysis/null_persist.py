"""引用クラスタの持続の帰無モデル: 引用を付け替えても持続率が出るなら、物差しが無意味。

付け替え: 引用先の年ごとに、辺の「引用先」端点をシャッフルする(引用元の参照数、引用先の
被引用数、参照の年齢分布はそのまま。どの論文がどの論文を引くかだけが壊れる)。
そのグラフで window_persist.py と同じ手続き(窓ごとに Louvain、隣の窓へ 30% 以上の集中で
「続く」)を回し、観測値と比べる。出力: null_persistence.csv(反復ごと・窓ごと)。"""
from __future__ import annotations
import csv, sys
from collections import Counter
import numpy as np
import networkx as nx
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
WINDOWS = [(1994, 1998), (1999, 2003), (2004, 2008), (2009, 2013), (2014, 2018), (2019, 2023), (2024, 2026)]
REPS = int(sys.argv[sys.argv.index("--reps") + 1]) if "--reps" in sys.argv else 5

def cite_clusters(cited, citing, idx, min_size=20):
    pos = {int(i): k for k, i in enumerate(idx)}
    m = np.isin(cited, idx) & np.isin(citing, idx)
    G = nx.Graph(); G.add_nodes_from(range(len(idx)))
    G.add_edges_from((pos[int(a)], pos[int(b)]) for a, b in zip(cited[m], citing[m]))
    parts = nx.community.louvain_communities(G, resolution=1.0, seed=20260729)
    return [np.array([idx[k] for k in p]) for p in parts if len(p) >= min_size]

def persistence(cited, citing, mask):
    up = {}
    for a, b in zip(cited, citing): up.setdefault(int(b), []).append(int(a))
    wins = []
    for lo, hi in WINDOWS:
        idx = np.flatnonzero(mask & (g.year >= lo) & (g.year <= hi))
        wins.append(((lo, hi), cite_clusters(cited, citing, idx)))
    out = []
    for k in range(1, len(wins)):
        (w0, cc0), (w1, cc1) = wins[k - 1], wins[k]
        owner0 = {int(i): ci for ci, c in enumerate(cc0) for i in c}
        kept = 0
        for c in cc1:
            cnt = Counter(owner0[a] for i in c for a in up.get(int(i), []) if a in owner0)
            tot = sum(cnt.values())
            if tot and cnt.most_common(1)[0][1] / tot >= 0.3: kept += 1
        out.append((f"{w0[0]}-{w0[1]}→{w1[0]}-{w1[1]}", kept, len(cc1)))
    return out

def rewire(rng):
    """引用先の年ごとに引用先端点をシャッフル。自己引用と重複辺はそのまま許す(まれ)。"""
    cited = g.cited.copy()
    years = g.year[cited]
    for y in np.unique(years):
        m = np.flatnonzero(years == y)
        cited[m] = cited[m][rng.permutation(len(m))]
    # 年の全順序で cited < citing になるものだけ残す(同年の付け替えで逆向きになった辺を落とす)
    ok = g.year[cited] < g.year[g.citing]
    return cited[ok], g.citing[ok]

mask = np.ones(g.n, dtype=bool)
rows = []
obs = persistence(g.cited, g.citing, mask)
for w, k, n in obs: rows.append(["observed", 0, w, k, n, round(k / n, 3) if n else ""])
print("observed:", " ".join(f"{k}/{n}" for _, k, n in obs), flush=True)
rng = np.random.default_rng(20260926)
for r in range(1, REPS + 1):
    c, d = rewire(rng)
    nl = persistence(c, d, mask)
    for w, k, n in nl: rows.append(["rewired", r, w, k, n, round(k / n, 3) if n else ""])
    print(f"rewired {r}:", " ".join(f"{k}/{n}" for _, k, n in nl), flush=True)
with (load.OUT / "null_persistence.csv").open("w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["graph", "rep", "windows", "persist", "clusters", "share"]); wr.writerows(rows)
