import sys, re, json, numpy as np, collections
from pathlib import Path
sys.path.insert(0, "."); import load
g = load.load(); V = np.array(g.venue); A = lambda a: a.get("id") if isinstance(a, dict) else a
NAME = {}
for l in open("../data/openalex/works.jsonl"):
    w = json.loads(l)
    for a in w.get("authors") or []:
        if a.get("id") and a.get("name"): NAME[a["id"]] = a["name"]
src = open("explore/critique.py").read()
exec(src[src.index("texts = list(g.title)"):src.index('print("  抄録の付与率 年別')])
exec(src[src.index('src = open("waves.py")'):src.index("names = sorted(cohort")])
H_W = ["Tabletop & multitouch", "Depth cameras (Kinect)", "Wearables & smartwatches", "Personal fabrication", "VR (consumer HMDs)"]
D_W = ["Crowdsourcing (MTurk)", "Social media", "Deep learning", "Voice assistants", "LLMs & generative AI"]
H = set().union(*(cohort[w][1] for w in H_W)); D = set().union(*(cohort[w][1] for w in D_W))
both = H & D; H, D = H - both, D - both
print(f"ハード系譜の創始者 {len(H)} 人、データ系譜 {len(D)} 人、両方 {len(both)} 人(除外)")
def papers_of(P): return np.array([i for i in range(g.n) if g.year[i] >= 2005 and any(A(a) in P for a in g.authors[i])])
pH, pD = papers_of(H), papers_of(D); sH, sD = set(pH.tolist()), set(pD.tolist())
print(f"論文(2005 年以降、創始者を著者に含む): ハード {len(pH):,} 本、データ {len(pD):,} 本、両方に数えられる {len(sH & sD):,} 本")
def top(c, k=6): return ", ".join(f"{a} {b}" for a, b in c.most_common(k))
for lab, P, pp in (("ハード", H, pH), ("データ", D, pD)):
    print(f"\n== {lab}系譜 ==")
    print("  会場:", top(collections.Counter(V[pp].tolist()), 8))
    print("  帯:", top(collections.Counter(g.band_name[b][:26] for b in g.band[pp] if b >= 0), 6))
    words = collections.Counter(w for i in pp for w in set(re.findall(r"[a-z][a-z\-]{3,}", g.title[i].lower())))
    stop = set("with from using through toward towards study design interaction interactive user users based their which what when about into".split())
    print("  題名の語:", top(collections.Counter({w: c for w, c in words.items() if w not in stop}), 14))
    people = collections.Counter(A(a) for i in pp for a in g.authors[i] if A(a) in P)
    print("  多作な創始者:", ", ".join(f"{NAME.get(k, k)} ({c})" for k, c in people.most_common(10)))
# 所属
insts = collections.defaultdict(collections.Counter)
for l in open("../data/openalex/works.jsonl"):
    w = json.loads(l)
    if w["id"] not in g.idx: continue
    for a in w.get("authors") or []:
        k = a.get("id")
        if k in H or k in D:
            for inst in a.get("insts") or []: insts["H" if k in H else "D"][inst] += 1
names_i = {}
sys.path.insert(0, "../pipeline/src")
from paperlineage import openalex as oa
ids = [k for lab in ("H", "D") for k, _ in insts[lab].most_common(8)]
data = oa.get("/institutions", params={"filter": "openalex_id:" + "|".join(ids), "select": "id,display_name", "per-page": 50})
for r in data.get("results") or []: names_i[r["id"].rsplit("/", 1)[-1]] = r["display_name"]
for lab in ("H", "D"): print(f"  所属 {lab}:", ", ".join(f"{names_i.get(k, k)} {c}" for k, c in insts[lab].most_common(8)))
# 相互引用と外部参照の分野
def ref_mix(pp, own, other):
    tot = to_own = to_other = 0
    for j in pp:
        for i in g.upstream(int(j)):
            tot += 1; to_own += i in own; to_other += i in other
    return tot, to_own / tot, to_other / tot
for lab, pp, own, other in (("ハード", pH, sH, sD), ("データ", pD, sD, sH)):
    tot, a, b = ref_mix(pp, own, other); print(f"\n{lab}系譜の論文のコーパス内参照 {tot:,}: 自系譜へ {a:.2f}、相手系譜へ {b:.2f}(コーパス全体に占める相手系譜の論文の割合 {len(other)/((g.year>=2005).sum()):.2f})")
ns = {"__file__": str(Path("external_origins.py").resolve()), "g": g, "load": load}; exec(open("external_origins.py").read().split("# サブ帯 × 初期論文")[0].replace("g = load.load()", "").replace("print(", "(lambda *a, **k: None)("), ns)
raw_refs = {}
for line in open("../data/openalex/works.jsonl"):
    w = json.loads(line); raw_refs[w["id"]] = w.get("refs") or []
node_id = [r["id"] for r in g.rows]
for lab, pp in (("ハード", pH), ("データ", pD)):
    c = collections.Counter()
    for i in pp:
        for r in raw_refs.get(node_id[i], []):
            if r in ns["ext"]:
                f = ns["field_of"](ns["ext"][r])
                if f: c[f] += 1
    tot = sum(c.values()); print(f"{lab}系譜の外部参照の分野: " + ", ".join(f"{k} {v/tot:.0%}" for k, v in c.most_common(7)))

print("\n== 方法の型: 作る論文か調べる論文か(抄録つき、2019 年以降。語の代理指標)")
BUILD = re.compile(r"we (present|introduce|propose|design and implement|built|build|implement|develop)(ed)? (a|an|the)? ?(novel |new )?(system|technique|tool|toolkit|prototype|device|interface|method|approach|framework|model|algorithm|pipeline)|\bprototype\b|\btoolkit\b|\bwe implement", re.I)
STUDY = re.compile(r"\binterview|\bsurvey(ed)?\b|\bparticipants\b|qualitative|thematic analysis|we conducted (a|an) (study|experiment|field)|\bdiary study|\bethnograph|focus group|\bworkshop", re.I)
for lab, pp in (("ハード", pH), ("データ", pD)):
    idx = [i for i in pp if g.year[i] >= 2019 and has_abs[i]]
    b = np.array([bool(BUILD.search(texts[i])) for i in idx]); s = np.array([bool(STUDY.search(texts[i])) for i in idx])
    print(f"  {lab}系譜 n={len(idx):,}: 作る語あり {b.mean():.2f}、調べる語あり {s.mean():.2f}、作るのみ {(b & ~s).mean():.2f}、調べるのみ {(~b & s).mean():.2f}、両方 {(b & s).mean():.2f}")
idx = [i for i in range(g.n) if g.year[i] >= 2019 and has_abs[i]]
b = np.array([bool(BUILD.search(texts[i])) for i in idx]); s = np.array([bool(STUDY.search(texts[i])) for i in idx])
print(f"  コーパス全体 n={len(idx):,}: 作る語あり {b.mean():.2f}、調べる語あり {s.mean():.2f}、作るのみ {(b & ~s).mean():.2f}、調べるのみ {(~b & s).mean():.2f}")
print("\n== 橋渡し役(両方の系譜の創始者) 80 人のうち多作な人と、その人が乗った波")
bridge = collections.Counter(A(a) for i in range(g.n) if g.year[i] >= 2005 for a in g.authors[i] if A(a) in both)
for k, c in bridge.most_common(12):
    waves_k = [w for w in H_W + D_W if k in cohort[w][1]]
    print(f"  {NAME.get(k, k)} ({c}): " + ", ".join(w[:12] for w in waves_k))

# 系譜の創始者集合と論文集合を保存(貢献類型の分類サンプルなどが使う)
out = load.ROOT / "data" / "contrib"; out.mkdir(parents=True, exist_ok=True)
json.dump({"H": sorted(H), "D": sorted(D), "both": sorted(both), "papers_H": sorted(int(i) for i in pH), "papers_D": sorted(int(i) for i in pD),
           "doi_H": [g.doi[i] for i in pH], "doi_D": [g.doi[i] for i in pD]}, (out / "lineages.json").open("w"))
print("saved", out / "lineages.json")
