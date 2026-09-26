"""共語と引用を**同じ条件**で比べる: どちらも5年窓ごとに独立にクラスタを作り、
隣の窓との対応の有無で持続を測る。

引用側の持続の定義(語の Jaccard に相当するもの):
  窓 w1 のクラスタ C について、C の論文が窓 w0 の論文へ張る引用の行き先を数え、
  行き先の 30% 以上が w0 の1つのクラスタ P に集中していれば「P から続いている」。
  (語集合の Jaccard ≥ 0.3 と同じ閾値の考え方)
共語側は coword.py と同じ手続き。"""
from __future__ import annotations
import csv, sys
from collections import Counter
import numpy as np
import networkx as nx
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
from coword import coword_clusters, WINDOWS  # noqa: E402  (import 時に coword.py の本体も走るので出力は捨てる)
g = load.load()

def cite_clusters(idx: np.ndarray, min_size: int = 20):
    idx_set = set(idx.tolist()); pos = {i: k for k, i in enumerate(idx)}
    m = np.isin(g.cited, idx) & np.isin(g.citing, idx)
    G = nx.Graph(); G.add_nodes_from(range(len(idx)))
    G.add_edges_from((pos[int(a)], pos[int(b)]) for a, b in zip(g.cited[m], g.citing[m]))
    parts = nx.community.louvain_communities(G, resolution=1.0, seed=20260729)
    return [np.array([idx[k] for k in p]) for p in parts if len(p) >= min_size]

def run(label, mask):
    wins = []
    for lo, hi in WINDOWS:
        idx = np.flatnonzero(mask & (g.year >= lo) & (g.year <= hi))
        wins.append(((lo, hi), idx, coword_clusters(idx), cite_clusters(idx)))
    rows = []
    for k in range(1, len(wins)):
        (w0, i0, cw0, cc0), (w1, i1, cw1, cc1) = wins[k - 1], wins[k]
        # 共語
        m0 = [c for c in cw0 if c["motor"]]; m1 = [c for c in cw1 if c["motor"]]
        cw_p = sum(1 for c in m1 if any(len(c["words"] & p["words"]) / len(c["words"] | p["words"]) >= 0.3 for p in m0))
        cw_all = sum(1 for c in cw1 if any(len(c["words"] & p["words"]) / len(c["words"] | p["words"]) >= 0.3 for p in cw0))
        # 引用
        owner0 = {}
        for pi, P in enumerate(cc0):
            for i in P: owner0[int(i)] = pi
        cc_p = 0
        for C in cc1:
            e = np.isin(g.citing, C) & np.isin(g.cited, i0)
            tgt = Counter(owner0.get(int(a), -1) for a in g.cited[e]); tgt.pop(-1, None)
            tot = sum(tgt.values())
            if tot >= 10 and tgt and max(tgt.values()) / tot >= 0.3: cc_p += 1
        rows.append([label, f"{w0[0]}-{w0[1]}", f"{w1[0]}-{w1[1]}", len(cw1), cw_all, len(m1), cw_p, len(cc1), cc_p])
        print(f"  {label:9} {w0[0]}-{w0[1]}→{w1[0]}-{w1[1]}  共語: 全クラスタ {cw_all}/{len(cw1)}  motor {cw_p}/{len(m1)}   引用: {cc_p}/{len(cc1)}", flush=True)
    return rows
out = []
for label, mask in [("CHI", np.array([v == "chi" for v in g.venue])), ("core venues", np.ones(g.n, bool))]:
    print(f"== {label} ==")
    out += run(label, mask)
with (load.OUT / "window_persistence.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["corpus", "window_prev", "window", "coword_clusters", "coword_persisted", "motor", "motor_persisted", "cite_clusters", "cite_persisted"]); w.writerows(out)
