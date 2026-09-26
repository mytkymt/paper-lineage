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
print("\n==== F3 系譜(CHI を除く 28 会場): 対照を「先行窓で多作だが創始者でない人」にし、順列で区間を出す ====")
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
    m = wave_members(STRICT.get(name, pat), start0, trig); m = m[V[m] != "chi"]; yc = collections.Counter(g.year[m].tolist())
    start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
    early = m[(g.year[m] >= start) & (g.year[m] < start + 5)]; members[name] = set(early.tolist())
    c = collections.Counter(A(x) for i in early for x in g.authors[i] if A(x)); cohort[name] = (start, {k for k, v in c.items() if v >= 2})
    allw = np.flatnonzero((g.year >= start) & (g.year < start + 5) & (V != "chi")); ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x)); prolific[name] = {k for k, v in ca.items() if v >= 2}
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
