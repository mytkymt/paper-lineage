import sys, re, json, numpy as np, collections
sys.path.insert(0, "."); import load
g = load.load(); S = len(g.sub_name); sub = g.sub
V = np.array(g.venue); A = lambda a: a.get("id") if isinstance(a, dict) else a
refs_total = {}
for l in open("../data/openalex/works.jsonl"):
    w = json.loads(l)
    if w["id"] in g.idx: refs_total[g.idx[w["id"]]] = len(w.get("refs") or [])
indeg = np.bincount(g.cited, minlength=g.n); outdeg = np.bincount(g.citing, minlength=g.n)
chi_mask = V == "chi"
cites_from_chi = np.bincount(g.cited[chi_mask[g.citing]], minlength=g.n)

print("==== F1 境界越えの罰: 統制つき ====")
def f1(venue, label):
    vm = V == venue
    idx = np.array([i for i in np.flatnonzero(vm & (g.year >= 2005) & (g.year <= 2018)) if refs_total.get(i, 0) >= 10 and outdeg[i] >= 3 and sub[i] >= 0])
    ext = np.array([1 - outdeg[i] / refs_total[i] for i in idx])
    # (a) 年×サブ帯のセル内で四分位に分ける(セル 20 本以上)
    cells = collections.defaultdict(list)
    for k, i in enumerate(idx): cells[(int(g.year[i]), int(sub[i]))].append(k)
    q_in, q_chi, q_tot = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for ks in cells.values():
        if len(ks) < 20: continue
        ks = np.array(ks); e = ext[ks]; qs = np.quantile(e, [0.25, 0.5, 0.75]); grp = np.digitize(e, qs)
        for q in range(4):
            sel = idx[ks[grp == q]]
            if len(sel): q_in[q].append(np.mean(np.log1p(indeg[sel]))); q_chi[q].append(np.mean(np.log1p(cites_from_chi[sel]))); q_tot[q].append(np.mean(np.log1p(g.cited_by[sel])))
    print(f"  {label} n={len(idx)}, セル {sum(1 for ks in cells.values() if len(ks)>=20)}: 四分位(内向き→外向き) log 被引用の平均 [コーパス内 / CHI から / 総]")
    for q in range(4): print(f"    Q{q+1}: {np.mean(q_in[q]):.2f} / {np.mean(q_chi[q]):.2f} / {np.mean(q_tot[q]):.2f}")
    # (b) 回帰: log1p(被引用) ~ ext + log(参照数) + log(コーパス内参照数) + 年FE + サブ帯FE
    ys = sorted(set(int(g.year[i]) for i in idx)); ss = sorted(set(int(sub[i]) for i in idx))
    X = np.zeros((len(idx), 3 + len(ys) - 1 + len(ss) - 1))
    X[:, 0] = ext; X[:, 1] = np.log([refs_total[i] for i in idx]); X[:, 2] = np.log([outdeg[i] for i in idx])
    for k, i in enumerate(idx):
        y = int(g.year[i]); s = int(sub[i])
        if y != ys[0]: X[k, 3 + ys.index(y) - 1] = 1
        if s != ss[0]: X[k, 3 + len(ys) - 1 + ss.index(s) - 1] = 1
    X = np.hstack([np.ones((len(idx), 1)), X])
    for name, yv in (("コーパス内", np.log1p(indeg[idx])), ("CHI から", np.log1p(cites_from_chi[idx])), ("総(OpenAlex)", np.log1p(g.cited_by[idx]))):
        beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
        resid = yv - X @ beta; sigma2 = resid @ resid / (len(yv) - X.shape[1]); se = np.sqrt(sigma2 * np.linalg.pinv(X.T @ X)[1, 1])
        print(f"    回帰 {name}: 外部参照率の係数 {beta[1]:+.2f} (SE {se:.2f}) → 外部率 0.6→0.9 で被引用 x{np.exp(beta[1]*0.3):.2f}; log参照数 {beta[2]:+.2f}, logコーパス内参照数 {beta[3]:+.2f}")
for v, lab in (("chi", "CHI"), ("uist", "UIST"), ("pacmhci", "PACM HCI (CSCW)"), ("dis", "DIS"), ("iui", "IUI")): f1(v, lab)

print("\n==== F2 LLM 期の縮小: 語ベース・先行トレンド・会場移動 ====")
texts = list(g.title)
abs_path = load.ROOT / "data/s2/abstracts.jsonl"; abstracts = {}
for line in abs_path.open():
    r = json.loads(line)
    if r.get("abstract"): abstracts[r["paperId"]] = r["abstract"]
by_doi, by_key = {}, {}
for path in sorted((load.ROOT / "data/corpus").glob("*.jsonl")):
    for line in path.open():
        r = json.loads(line); pid = r["paperId"]
        if pid not in abstracts: continue
        doi = ((r.get("externalIds") or {}).get("DOI") or "").lower()
        if doi: by_doi[doi] = pid
        by_key[(re.sub(r"[^a-z0-9]+", " ", (r.get("title") or "").lower()).strip(), r.get("year"))] = pid
has_abs = np.zeros(g.n, bool)
for i, row in enumerate(g.rows):
    pid = by_doi.get((row.get("doi") or "").lower()) or by_key.get((re.sub(r"[^a-z0-9]+", " ", g.title[i].lower()).strip(), int(g.year[i])))
    if pid: texts[i] = g.title[i] + "\n" + abstracts[pid]; has_abs[i] = True
print("  抄録の付与率 年別(CHI):", {y: f"{has_abs[chi_mask & (g.year==y)].mean():.2f}" for y in (2010, 2015, 2019, 2021, 2023, 2024, 2025)})
print("  抄録の付与率 会場別:", {v: f"{has_abs[V==v].mean():.2f}" for v in ("chi","uist","pacmhci","dis","iui","tei","imwut","recsys","hri","icmi","vrst")})
TOPICS = {
 "input/haptics/gesture": r"haptic|tactile|gesture|touch input|pointing|text entry|input technique|input device|mid-air|finger|stylus",
 "vr/ar hardware": r"head-mounted|\bhmd\b|virtual reality|augmented reality|mixed reality",
 "fabrication/tangible": r"fabricat|3d.print|tangible|shape-changing|actuat|e-textile|circuit",
 "gaze/eye": r"eye.?track|gaze",
 "games/play": r"\bgame|player|gamif|esports",
 "social computing": r"social media|online communit|reddit|twitter|facebook|moderation|misinformation|platform",
 "health/wellbeing": r"health|clinic|patient|mental|wellbeing|caregiver|chronic",
 "accessibility": r"accessib|blind|deaf|disabilit|screen reader|autis",
 "design research": r"research through design|speculative|design fiction|participatory design|co-design|critical design",
}
LLM = re.compile(r"large language model|\bllms?\b|\bgpt|chatgpt|generative ai|foundation model|diffusion model", re.I)
print("  CHI: 語ベースの話題の本数(抄録つき論文のみ、率は抄録つき論文に対する%)。LLM 語を含むものは分けて数える")
yrs = [2017, 2019, 2021, 2023, 2025]
hdr = "  " + " " * 24 + " ".join(f"{y:>12}" for y in yrs); print(hdr)
for name, pat in TOPICS.items():
    rx = re.compile(pat, re.I); row = []
    for y in yrs:
        idx = np.flatnonzero(chi_mask & (g.year == y) & has_abs); hit = [i for i in idx if rx.search(texts[i])]
        llm = sum(1 for i in hit if LLM.search(texts[i]))
        row.append(f"{100*len(hit)/len(idx):5.1f}%({llm:3})")
    print(f"  {name:24} " + " ".join(f"{r:>12}" for r in row))
print("  CHI 帯の占有率の先行トレンド(2015–17 → 2019–21 → 2023–25)")
def bshare(lo, hi, vm):
    m = (g.year >= lo) & (g.year <= hi) & (sub >= 0) & vm; c = collections.Counter(g.band[m].tolist()); n = m.sum(); return {b: c.get(b, 0) / n for b in range(len(g.band_name))}
s0, s1, s2 = bshare(2015, 2017, chi_mask), bshare(2019, 2021, chi_mask), bshare(2023, 2025, chi_mask)
for b in sorted(range(len(g.band_name)), key=lambda b: s2[b] / max(s1[b], 1e-9)):
    if g.band_name[b].startswith("(") or s1[b] < 0.01: continue
    print(f"    {g.band_name[b][:34]:34} {100*s0[b]:5.1f}% → {100*s1[b]:5.1f}% → {100*s2[b]:5.1f}%   前期比 x{s1[b]/max(s0[b],1e-9):.2f} → 後期比 x{s2[b]/max(s1[b],1e-9):.2f}")
print("  会場移動の確認: 全会場での絶対本数(2019–21 → 2023–25)、ハード系の帯")
for b in range(len(g.band_name)):
    if g.band_name[b].startswith(("Input", "Tangible", "Gaze", "Collab", "Games")):
        a = int(((g.year >= 2019) & (g.year <= 2021) & (g.band == b)).sum()); c = int(((g.year >= 2023) & (g.year <= 2025) & (g.band == b)).sum())
        ach = int(((g.year >= 2019) & (g.year <= 2021) & (g.band == b) & chi_mask).sum()); cch = int(((g.year >= 2023) & (g.year <= 2025) & (g.band == b) & chi_mask).sum())
        print(f"    {g.band_name[b][:34]:34} 全会場 {a} → {c} (x{c/a:.2f})  CHI {ach} → {cch} (x{cch/ach:.2f})  CHI 以外 {a-ach} → {c-cch} (x{(c-cch)/max(1,a-ach):.2f})")
print("  コーパス全体の伸び: ", int(((g.year >= 2019) & (g.year <= 2021)).sum()), "→", int(((g.year >= 2023) & (g.year <= 2025)).sum()))

print("\n==== F3 系譜: 対照を「先行窓で多作だが創始者でない人」にし、順列で区間を出す ====")
src = open("waves.py").read(); exec(src[src.index("WAVES = ["):src.index("sub_birth = ")])
first_year = {}
for i in np.argsort(g.year, kind="stable"):
    for a in g.authors[i]:
        k = A(a)
        if k and k not in first_year: first_year[k] = int(g.year[i])
corpus_y = g.corpus_by_year
node_id = [r["id"] for r in g.rows]; in_corpus = set(node_id)
raw_refs = {}
for line in (load.ROOT / "data/openalex/works.jsonl").open():
    w = json.loads(line); raw_refs[w["id"]] = w.get("refs") or []
ext_id_by_title = {}
for line in (load.ROOT / "data/openalex/external.jsonl").open():
    w = json.loads(line); ext_id_by_title[(w.get("title") or "").lower()] = w["id"]
titles_l = [t.lower() for t in g.title]
def wave_members(pat, start, triggers, end=None):
    rx = re.compile(pat, re.I); trig_ids = set()
    for t in triggers:
        for tl, eid in ext_id_by_title.items():
            if tl.startswith(t): trig_ids.add(eid)
        for i, tl in enumerate(titles_l):
            if tl.startswith(t): trig_ids.add(node_id[i])
    return np.array([i for i in range(g.n) if g.year[i] >= start and (not end or g.year[i] <= end) and (rx.search(texts[i]) or (trig_ids and any(r in trig_ids for r in raw_refs.get(node_id[i], []))))])
STRICT = {"LLMs & generative AI": r"large language model|\bllms?\b|\bgpt-?[34]|chatgpt"}
cohort, prolific, members = {}, {}, {}
for name, start0, pat, trig in WAVES:
    if name in ("VR (1990s)", "WWW", "Mobile phones"): continue
    m = wave_members(STRICT.get(name, pat), start0, trig); yc = collections.Counter(g.year[m].tolist())
    start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
    early = m[(g.year[m] >= start) & (g.year[m] < start + 5)]; members[name] = set(early.tolist())
    c = collections.Counter(A(x) for i in early for x in g.authors[i] if A(x)); cohort[name] = (start, {k for k, v in c.items() if v >= 2})
    allw = np.flatnonzero((g.year >= start) & (g.year < start + 5)); ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x)); prolific[name] = {k for k, v in ca.items() if v >= 2}
names = sorted(cohort, key=lambda n: cohort[n][0]); rng = np.random.default_rng(1)
print("  倍率 = P(後の波の創始者 | 先行波の創始者) / P(後の波の創始者 | 先行窓で多作だが創始者でない)。後の窓でも多作な人に限る。[95% 順列区間]")
print("  LLM は厳格な語(large language model / LLM / GPT / ChatGPT)だけで定義")
targets = ["Deep learning", "Personal fabrication", "VR (consumer HMDs)", "Voice assistants", "LLMs & generative AI"]
for a in names:
    sa, Fa = cohort[a]; Pa = prolific[a]; NF = Pa - Fa; row = []
    for b in targets:
        sb, Fb = cohort[b]
        if sb < sa + 3: row.append(f"{'·':>22}"); continue
        Pb = prolific[b]; fa, nf = Fa & Pb, NF & Pb
        if len(fa) < 15 or len(nf) < 15: row.append(f"{'(n<15)':>22}"); continue
        pf, pn = len(fa & Fb) / len(fa), len(nf & Fb) / len(nf)
        pool = np.array(sorted(fa | nf)); inb = np.array([k in Fb for k in pool]); k = len(fa); sims = []
        for _ in range(400):
            perm = rng.permutation(len(pool)); sims.append(inb[perm[:k]].mean() / max(inb[perm[k:]].mean(), 1e-9))
        lo, hi = np.percentile(sims, [2.5, 97.5])
        row.append(f"{pf/max(pn,1e-9):5.1f}x [{lo:.1f}-{hi:.1f}] n={len(fa)}")
    print(f"  {a[:22]:22} ({sa}) " + " | ".join(row))
print("  (順列区間は帰無仮説「創始者と非創始者に差がない」の下での倍率の範囲。観測値がその外なら差がある)")
