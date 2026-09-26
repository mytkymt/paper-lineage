import sys, numpy as np, collections
sys.path.insert(0, "."); import load
g = load.load(); S = len(g.sub_name); sub = g.sub
A = lambda a: a.get("id") if isinstance(a, dict) else a
first_year = {}
for i in np.argsort(g.year, kind="stable"):
    for a in g.authors[i]:
        k = A(a)
        if k and k not in first_year: first_year[k] = int(g.year[i])
print("== Q3' 創始者の新参率 vs 同じ窓で 2 本以上書いた全著者の新参率(コーパス成長の偏りを除く)")
rows = collections.defaultdict(list)
for s in range(S):
    m = np.flatnonzero(sub == s)
    if len(m) < 50: continue
    b = g.birth(m); win = m[(g.year[m] >= b) & (g.year[m] < b + 5)]
    c = collections.Counter(A(x) for i in win for x in g.authors[i] if A(x)); F = {k for k, v in c.items() if v >= 2}
    if len(F) < 3 or b < 1990: continue
    allw = np.flatnonzero((g.year >= b) & (g.year < b + 5))
    ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x)); P = {k for k, v in ca.items() if v >= 2}
    nf = sum(1 for k in F if first_year[k] >= b) / len(F); npf = sum(1 for k in P if first_year[k] >= b) / len(P)
    rows[(b // 10) * 10].append((nf, npf))
for dec in sorted(rows):
    v = np.array(rows[dec]); print(f"  {dec}s (n={len(v)}): 創始者の新参率 {np.median(v[:,0]):.2f} / 同窓の多作著者の新参率 {np.median(v[:,1]):.2f} / 比 {np.median(v[:,0]/np.maximum(v[:,1],1e-9)):.2f}")
print("\n== Q2' 先行する波の創始者が次の波に居る割合 vs 同じ窓で 2 本以上書いた著者が居る割合")
src = open("waves.py").read(); exec(src[:src.index("WAVES = [")]); exec(src[src.index("WAVES = ["):src.index("waves = {}")])
corpus_y = g.corpus_by_year; cohort = {}
for name, start0, pat, trig in WAVES:
    if name == "VR (1990s)": continue
    m = wave_members(pat, start0, trig); yc = collections.Counter(g.year[m].tolist())
    start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
    early = m[(g.year[m] >= start) & (g.year[m] < start + 5)]
    c = collections.Counter(A(x) for i in early for x in g.authors[i] if A(x))
    cohort[name] = (start, {k for k, v in c.items() if v >= 2})   # 波の創始者 = 創始窓で 2 本以上
names = list(cohort)
for n in names:
    s, F = cohort[n]
    allw = np.flatnonzero((g.year >= s) & (g.year < s + 5)); ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x))
    P = {k for k, v in ca.items() if v >= 2}
    base = len(F & P) / len(P)
    prev = [(pn, cohort[pn][1]) for pn in names if cohort[pn][0] <= s - 3]
    if not prev: continue
    ratios = [(pn, len(pa & F) / max(1, len(pa & P))) for pn, pa in prev if len(pa & P) >= 20]
    print(f"  {n[:24]:24} ({s}) 多作著者の基準 {base:.2f} | " + "; ".join(f"{pn[:12]} {r:.2f} (x{r/base:.1f})" for pn, r in ratios[-4:]))
