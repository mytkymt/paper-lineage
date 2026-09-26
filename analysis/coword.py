"""Kostakos(2015)の共語分析を、同じコーパスの**題名の語**で再現する。

Kostakos は CHI 1994–2013 の著者キーワードを使い、5年ごとの共起ネットワークを
クラスタに分け、Callon の戦略図(中心性 × 密度)で第I象限(motor themes)に入る
クラスタが期間をまたいで続かないと論じた。ここでは:
  - 語: 題名を小文字化しストップワードを除いた語(著者キーワードは公開 API に無い)
  - 期間: 5年窓(1994–98 … 2019–23)、CHI のみ / 13会場
  - クラスタ: 語の共起グラフ(上位語)を Louvain で分割
  - 中心性 = クラスタ外との共起の総和、密度 = クラスタ内の共起の平均
  - motor theme = 中心性・密度とも中央値以上
  - 持続 = 隣り合う窓の motor theme クラスタ間で語の Jaccard ≥ 0.3 の対応があるか
同じ窓割りで、引用コミュニティ(サブ帯)の持続(構成員の重なり)も出して並べる。
"""
from __future__ import annotations
import csv, re, sys
from collections import Counter, defaultdict
import numpy as np
import networkx as nx
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
STOP = set("""the a an of for and in on to with by from is are as at that this it its their into via using use used
toward towards through between over study studies design designing system systems user users interaction interactive
interface interfaces understanding exploring supporting how what why when we our you case based new novel human computing
computer proceedings conference chi acm sigchi extended abstracts an vs versus towards can do does not or two one
approach approaches method methods analysis evaluation evaluating exploration investigating investigation effects effect
experience experiences work practice practices technology technologies application applications tool tools model models
data information research""".split())
tok = lambda t: [w for w in re.findall(r"[a-z][a-z\-]+", t.lower()) if w not in STOP and len(w) > 2]
WINDOWS = [(y, y + 4) for y in range(1994, 2020, 5)] + [(2024, 2026)]
TOPK = 300

def coword_clusters(idx: np.ndarray):
    docs = [set(tok(g.title[i])) for i in idx]
    df = Counter(w for d in docs for w in d)
    vocab = [w for w, _ in df.most_common(TOPK)]
    vs = set(vocab)
    co = Counter()
    for d in docs:
        ws = sorted(d & vs)
        for a in range(len(ws)):
            for b in range(a + 1, len(ws)):
                co[(ws[a], ws[b])] += 1
    G = nx.Graph()
    for (a, b), c in co.items():
        if c >= 3: G.add_edge(a, b, weight=c)
    if G.number_of_nodes() < 10: return []
    parts = nx.community.louvain_communities(G, weight="weight", resolution=1.0, seed=20260729)
    out = []
    for p in parts:
        if len(p) < 4: continue
        inner = [G[a][b]["weight"] for a in p for b in G[a] if b in p and a < b]
        outer = sum(G[a][b]["weight"] for a in p for b in G[a] if b not in p)
        density = np.mean(inner) if inner else 0.0
        out.append({"words": set(p), "centrality": outer, "density": density,
                    "label": " ".join(sorted(p, key=lambda w: -df[w])[:4])})
    if out:
        c_med = np.median([o["centrality"] for o in out]); d_med = np.median([o["density"] for o in out])
        for o in out: o["motor"] = o["centrality"] >= c_med and o["density"] >= d_med
    return out

def run(label: str, mask: np.ndarray):
    per_win = []
    for lo, hi in WINDOWS:
        idx = np.flatnonzero(mask & (g.year >= lo) & (g.year <= hi))
        per_win.append(((lo, hi), idx, coword_clusters(idx)))
    rows = []
    for k in range(1, len(per_win)):
        (w0, i0, c0), (w1, i1, c1) = per_win[k - 1], per_win[k]
        m0 = [c for c in c0 if c["motor"]]; m1 = [c for c in c1 if c["motor"]]
        persisted = 0
        for c in m1:
            if any(len(c["words"] & p["words"]) / len(c["words"] | p["words"]) >= 0.3 for p in m0): persisted += 1
        # 引用コミュニティの持続: 窓 w1 のサブ帯のうち、窓 w0 にも構成員が 20 本以上あるものの割合
        s0 = Counter(int(s) for s in g.sub[i0] if s >= 0); s1 = Counter(int(s) for s in g.sub[i1] if s >= 0)
        subs1 = [s for s, n in s1.items() if n >= 20]
        sub_persist = sum(1 for s in subs1 if s0.get(s, 0) >= 20)
        rows.append([label, f"{w0[0]}-{w0[1]}", f"{w1[0]}-{w1[1]}", len(c0), len(m0), len(c1), len(m1), persisted,
                     round(persisted / len(m1), 2) if m1 else "", len(subs1), sub_persist, round(sub_persist / len(subs1), 2) if subs1 else ""])
    return rows, per_win

allrows = []
for label, mask in [("CHI", np.array([v == "chi" for v in g.venue])), ("core venues", np.ones(g.n, bool))]:
    rows, per_win = run(label, mask)
    allrows += rows
    print(f"\n== {label}: motor themes の顔ぶれ ==")
    for (lo, hi), idx, cl in per_win:
        ms = [c["label"] for c in cl if c.get("motor")]
        print(f"  {lo}-{hi} n={len(idx):5} clusters={len(cl):2} motor={len(ms):2}: " + " | ".join(ms[:6]))
with (load.OUT / "coword_vs_citation.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["corpus", "window_prev", "window", "clusters_prev", "motor_prev", "clusters", "motor", "motor_persisted", "motor_persist_rate",
                "cit_subfields", "cit_persisted", "cit_persist_rate"])
    w.writerows(allrows)
print("\n窓ごとの持続率(共語 motor themes vs 引用サブ帯):")
for r in allrows: print(f"  {r[0]:9} {r[1]}→{r[2]}  motor {r[7]}/{r[6]} = {r[8]}    引用サブ帯 {r[10]}/{r[9]} = {r[11]}")
