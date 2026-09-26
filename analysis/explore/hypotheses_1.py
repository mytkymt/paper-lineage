import sys, re, json, csv, numpy as np, collections
sys.path.insert(0, "."); import load
from metrics import make_cd
g = load.load(); S = len(g.sub_name); sub = g.sub
_aid = lambda a: a.get("id") if isinstance(a, dict) else a
first_year = {}
for i in np.argsort(g.year, kind="stable"):
    for a in g.authors[i]:
        k = _aid(a)
        if k and k not in first_year: first_year[k] = int(g.year[i])

print("== Q1 LLM の波で縮んだサブ帯(2019–21 の占有率 → 2023–25)")
def share(lo, hi):
    m = (g.year >= lo) & (g.year <= hi) & (sub >= 0); c = collections.Counter(sub[m].tolist()); n = m.sum()
    return {s: c.get(s, 0) / n for s in range(S)}
a, b = share(2019, 2021), share(2023, 2025)
d = sorted(((b[s] - a[s]) * 100, s) for s in range(S) if a[s] > 0.003 or b[s] > 0.003)
print("  縮小:", "; ".join(f"{g.sub_name[s][:24]} {x:+.2f}pt" for x, s in d[:8]))
print("  拡大:", "; ".join(f"{g.sub_name[s][:24]} {x:+.2f}pt" for x, s in d[-6:][::-1]))
print("  帯レベル:", "; ".join(f"{g.band_name[bb][:22]} {(sum(b[s] for s in range(S) if g.sub_band[s]==bb)-sum(a[s] for s in range(S) if g.sub_band[s]==bb))*100:+.1f}pt" for bb in range(len(g.band_name))))

print("\n== Q2 波に乗る人は同じ人か(創始 5 年の著者集合の重なり)")
src = open("waves.py").read(); exec(src[:src.index("WAVES = [")]); exec(src[src.index("WAVES = ["):src.index("waves = {}")])
corpus_y = g.corpus_by_year
cohort = {}
for name, start0, pat, trig in WAVES:
    if name in ("VR (1990s)",): continue
    m = wave_members(pat, start0, trig)
    yc = collections.Counter(g.year[m].tolist())
    start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
    early = m[(g.year[m] >= start) & (g.year[m] < start + 5)]
    cohort[name] = (start, {_aid(x) for i in early for x in g.authors[i] if _aid(x)})
names = [n for n in cohort]
for n in names:
    s, A = cohort[n]
    # 先行する波の創始者のうち、この波の創始窓にも居る割合 / 基準: 同じ年に活動していた全著者のうちこの波に居る割合
    active = {_aid(x) for i in range(g.n) if s <= g.year[i] < s + 5 for x in g.authors[i] if _aid(x)}
    base = len(A & active) / len(active)
    prev = [(pn, cohort[pn][1]) for pn in names if cohort[pn][0] < s - 2]
    if not prev: continue
    rid = "; ".join(f"{pn[:14]} {len(pa & A)/max(1,len(pa & active)):.2f}" for pn, pa in prev[-4:])
    print(f"  {n[:24]:24} ({s}) 基準 {base:.2f} | 先行する波の創始者がこの波にも居る割合: {rid}")

print("\n== Q3 新サブ帯の創始者は HCI の新参か(創始窓で 2 本以上の著者のうち、誕生前にコーパスに論文が無い人の割合)")
by_dec = collections.defaultdict(list); serial = 0; n_sub = 0; founders_of = {}
births = {}
for s in range(S):
    m = np.flatnonzero(sub == s)
    if len(m) < 50: continue
    b = g.birth(m); births[s] = b; win = m[(g.year[m] >= b) & (g.year[m] < b + 5)]
    c = collections.Counter(_aid(x) for i in win for x in g.authors[i] if _aid(x))
    F = {k for k, v in c.items() if v >= 2}
    if len(F) < 3: continue
    founders_of[s] = (b, F)
    new = sum(1 for k in F if first_year.get(k, 0) >= b) / len(F)
    by_dec[(b // 10) * 10].append(new)
for dec in sorted(by_dec): print(f"  {dec}s: 新参の割合 中央値 {np.median(by_dec[dec]):.2f} (n={len(by_dec[dec])})")
print("== Q4 連続創始者: 別のサブ帯を先に(3〜15 年前に)創始した人を創始者に含むサブ帯の割合")
cnt = 0; tot = 0; serial_people = collections.Counter()
for s, (b, F) in founders_of.items():
    prev = {k for t, (b2, F2) in founders_of.items() if 3 <= b - b2 <= 15 for k in F2}
    tot += 1
    if F & prev: cnt += 1
    for k in F & prev: serial_people[k] += 1
print(f"  {cnt}/{tot} = {cnt/tot:.2f}; 2 帯以上を創始した人 {sum(1 for k,v in serial_people.items())} 人")

print("\n== Q5 賞は創始窓の論文に行くか")
rows = list(csv.DictReader(open("results/core/awards_matched.csv")))
by_title = {re.sub(r'[^a-z0-9]+', ' ', g.title[i].lower()).strip(): i for i in range(g.n)}
inwin = after = 0
for r in rows:
    i = by_title.get(re.sub(r'[^a-z0-9]+', ' ', (r.get("title") or "").lower()).strip())
    if i is None or sub[i] < 0 or int(sub[i]) not in births: continue
    b = births[int(sub[i])]
    if b <= g.year[i] < b + 5: inwin += 1
    elif g.year[i] >= b + 5: after += 1
print(f"  創始窓内 {inwin}, 創始窓後 {after}")

print("\n== Q6 破壊性(CD5)の年次中央値 — HCI は Park ら(2023)のように単調減少するか")
cd = make_cd(g)
for y in range(1990, 2021, 5):
    idx = np.flatnonzero((g.year >= y) & (g.year < y + 5))
    vals = [cd(int(i), 5) for i in idx[::max(1, len(idx) // 3000)] if (g.out_start[i+1]-g.out_start[i]) >= 5]
    print(f"  {y}-{y+4}: CD5 中央値 {np.median(vals):+.3f}  平均 {np.mean(vals):+.3f}  n={len(vals)}")

print("\n== Q7 外を多く引く論文ほど HCI 内で引かれるか(論文単位)")
refs_total = {}
for l in open("../data/openalex/works.jsonl"):
    w = json.loads(l)
    if w["id"] in g.idx: refs_total[g.idx[w["id"]]] = len(w.get("refs") or [])
indeg = np.bincount(g.cited, minlength=g.n); outdeg = np.bincount(g.citing, minlength=g.n)
xs, ys = [], []
for y in range(2005, 2019):
    idx = [i for i in np.flatnonzero(g.year == y) if refs_total.get(i, 0) >= 10]
    ext_share = np.array([1 - outdeg[i] / refs_total[i] for i in idx]); cites = np.array([indeg[i] for i in idx], float)
    q = np.quantile(ext_share, [0.25, 0.75])
    lo, hi = cites[ext_share <= q[0]], cites[ext_share >= q[1]]
    xs.append(np.mean(lo)); ys.append(np.mean(hi))
print(f"  外部参照率 下位 1/4 の論文のコーパス内被引用 平均 {np.mean(xs):.1f} vs 上位 1/4 {np.mean(ys):.1f} (2005–2018 の年ごと平均の平均)")
top = []
for y in range(2005, 2019):
    idx = [i for i in np.flatnonzero(g.year == y) if refs_total.get(i, 0) >= 10]
    c = np.array([indeg[i] for i in idx]); thr = np.quantile(c, 0.99)
    e = np.array([1 - outdeg[i] / refs_total[i] for i in idx])
    top.append((np.median(e[c >= thr]), np.median(e)))
print(f"  年の上位 1% 被引用論文の外部参照率 中央値 {np.median([t for t,_ in top]):.2f} vs 全体 {np.median([m for _,m in top]):.2f}")
