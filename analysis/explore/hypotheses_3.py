import sys, json, numpy as np, collections
sys.path.insert(0, "."); import load
g = load.load(); S = len(g.sub_name); sub = g.sub
A = lambda a: a.get("id") if isinstance(a, dict) else a
refs_total = {}
for l in open("../data/openalex/works.jsonl"):
    w = json.loads(l)
    if w["id"] in g.idx: refs_total[g.idx[w["id"]]] = len(w.get("refs") or [])
indeg = np.bincount(g.cited, minlength=g.n); outdeg = np.bincount(g.citing, minlength=g.n)
print("== A. 外部参照率(参照のうちコーパス外の割合)の四分位 × 被引用(2005–2018、参照 10 本以上)")
for label, vmask in (("全会場", np.ones(g.n, bool)), ("CHI のみ", np.array([v == "chi" for v in g.venue]))):
    acc = collections.defaultdict(list)
    for y in range(2005, 2019):
        idx = np.array([i for i in np.flatnonzero((g.year == y) & vmask) if refs_total.get(i, 0) >= 10])
        e = np.array([1 - outdeg[i] / refs_total[i] for i in idx]); qs = np.quantile(e, [0.25, 0.5, 0.75])
        grp = np.digitize(e, qs)
        for q in range(4):
            sel = idx[grp == q]
            acc[q].append((np.median(indeg[sel]), np.median(g.cited_by[sel]), np.mean(np.log1p(g.cited_by[sel]))))
    print(f"  {label}: 四分位(外を引く割合 低→高) | コーパス内被引用の中央値 | OpenAlex 総被引用の中央値 | log 平均")
    for q in range(4):
        v = np.array(acc[q]); print(f"    Q{q+1}: {np.mean(v[:,0]):5.1f} | {np.mean(v[:,1]):5.1f} | {np.mean(v[:,2]):.2f}")
print("\n== B. LLM 期の帯の増減、絶対本数と CHI のみ(2019–21 → 2023–25)")
for label, vmask in (("全会場", np.ones(g.n, bool)), ("CHI のみ", np.array([v == "chi" for v in g.venue]))):
    def cnt(lo, hi):
        m = (g.year >= lo) & (g.year <= hi) & (sub >= 0) & vmask; c = collections.Counter(g.band[m].tolist()); return c, int(m.sum())
    c1, n1 = cnt(2019, 2021); c2, n2 = cnt(2023, 2025)
    out = []
    for b in range(len(g.band_name)):
        if g.band_name[b].startswith("("): continue
        s1, s2 = c1.get(b, 0) / n1, c2.get(b, 0) / n2
        out.append((s2 / s1 if s1 else float("nan"), g.band_name[b], c1.get(b, 0), c2.get(b, 0), s1, s2))
    print(f"  {label} (n {n1} → {n2}): 帯の占有率の比(後/前)、絶対本数")
    for r, name, a, b_, s1, s2 in sorted(out):
        print(f"    {name[:36]:36} x{r:.2f}  {a:5} → {b_:5}  ({s1*100:.1f}% → {s2*100:.1f}%)")
print("\n== C. 波に乗る系譜: 行=先行する波の創始者(創始窓で 2 本以上)、列=後の波の創始者に居る割合の、多作著者基準に対する倍率")
src = open("waves.py").read(); exec(src[:src.index("WAVES = [")]); exec(src[src.index("WAVES = ["):src.index("waves = {}")])
corpus_y = g.corpus_by_year; cohort = {}; prolific = {}
for name, start0, pat, trig in WAVES:
    if name in ("VR (1990s)", "WWW", "Mobile phones"): continue
    m = wave_members(pat, start0, trig); yc = collections.Counter(g.year[m].tolist())
    start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
    early = m[(g.year[m] >= start) & (g.year[m] < start + 5)]
    c = collections.Counter(A(x) for i in early for x in g.authors[i] if A(x)); cohort[name] = (start, {k for k, v in c.items() if v >= 2})
    allw = np.flatnonzero((g.year >= start) & (g.year < start + 5)); ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x))
    prolific[name] = {k for k, v in ca.items() if v >= 2}
names = sorted(cohort, key=lambda n: cohort[n][0])
short = {n: n[:10] for n in names}
print("  " + " " * 26 + " ".join(f"{short[n]:>10}" for n in names))
for a in names:
    sa, Fa = cohort[a]; row = []
    for b in names:
        sb, Fb = cohort[b]
        if sb < sa + 3: row.append("        · "); continue
        P = prolific[b]; base = len(Fb & P) / len(P); denom = len(Fa & P)
        row.append(f"{(len(Fa & Fb)/denom)/base:9.1f}x" if denom >= 15 and base else "      (n)")
    print(f"  {a[:24]:24} ({sa}) " + " ".join(row))
print("  (n) = 先行波の創始者で後の窓に居た人が 15 人未満。倍率 = 先行波の創始者が後の波の創始者に居る割合 / 同窓の多作著者全体が居る割合")
