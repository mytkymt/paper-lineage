"""波の開放度: 各波の創始者(創始窓で 2 本以上)のうち、それ以前の仕事が相手側の素材だった人の割合。

前歴の素材は帯で決める。物理系の帯 = Tangible/VR/Fabrication、Input & Interaction Techniques、
Collaboration & MR、Gaze。計算系の帯 = Robots/Agents/AI、Crowds & Human-AI、Recommender。
前歴 3 本以上(帯あり)の創始者について、物理系が計算系より多く 40% 以上なら「物理出身」、
逆なら「計算出身」、どちらでもなければ「中立」。前歴 3 本未満は「新参」。
開放度 = 相手側出身の割合 / 同じ窓で多作(2 本以上)な著者全体に占める相手側出身の割合。
予想: 深層学習・ファブ・VR で低く、LLM で跳ね上がる(参入コストがほぼゼロの最初の波)。
出力: results/core/wave_openness.csv"""
import sys, re, json, csv, numpy as np, collections
sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/.."); import load
g = load.load(); A = lambda a: a.get("id") if isinstance(a, dict) else a
src = open(__file__.rsplit("/", 1)[0] + "/critique.py").read()
exec(src[src.index("texts = list(g.title)"):src.index('print("  抄録の付与率 年別')])
exec(src[src.index('src = open("waves.py")'):src.index("STRICT = {")])
STRICT = {"LLMs & generative AI": r"large language model|\bllms?\b|\bgpt-?[34]|chatgpt"}
PHYS = {b for b, n in enumerate(g.band_name) if n.startswith(("Tangible", "Input", "Collaboration", "Gaze"))}
COMP = {b for b, n in enumerate(g.band_name) if n.startswith(("Robots", "Crowds", "Recommender"))}
papers_by = collections.defaultdict(list)
for i in range(g.n):
    for a in g.authors[i]:
        k = A(a)
        if k: papers_by[k].append(i)
def origin(k, before):
    prior = [i for i in papers_by[k] if g.year[i] < before and g.band[i] >= 0]
    if len(prior) < 3: return "newcomer"
    p = sum(g.band[i] in PHYS for i in prior) / len(prior); c = sum(g.band[i] in COMP for i in prior) / len(prior)
    if p > c and p >= 0.4: return "physical"
    if c > p and c >= 0.4: return "computational"
    return "neutral"
KIND = {"Tabletop & multitouch": "physical", "Depth cameras (Kinect)": "physical", "Wearables & smartwatches": "physical", "Personal fabrication": "physical", "VR (consumer HMDs)": "physical",
        "Crowdsourcing (MTurk)": "computational", "Social media": "computational", "Smartphones & apps": "physical", "Deep learning": "computational", "Voice assistants": "computational", "LLMs & generative AI": "computational"}
rows = []
print(f"{'wave':26} {'start':5} {'kind':13} {'founders':8} {'newcomer':8} {'physical':8} {'computat':8} {'neutral':8} | {'other-side share':16} {'baseline':8} {'openness':8}")
for name, start0, pat, trig in WAVES:
    if name not in KIND: continue
    m = wave_members(STRICT.get(name, pat), start0, trig); yc = collections.Counter(g.year[m].tolist())
    start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
    early = m[(g.year[m] >= start) & (g.year[m] < start + 5)]
    c = collections.Counter(A(x) for i in early for x in g.authors[i] if A(x)); F = [k for k, v in c.items() if v >= 2]
    allw = np.flatnonzero((g.year >= start) & (g.year < start + 5)); ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x)); P = [k for k, v in ca.items() if v >= 2]
    of = collections.Counter(origin(k, start) for k in F); op = collections.Counter(origin(k, start) for k in P)
    other = "computational" if KIND[name] == "physical" else "physical"
    hist_f = sum(v for k, v in of.items() if k != "newcomer"); hist_p = sum(v for k, v in op.items() if k != "newcomer")
    share = of[other] / hist_f if hist_f else float("nan"); base = op[other] / hist_p if hist_p else float("nan")
    rows.append([name, start, KIND[name], len(F), round(of["newcomer"] / len(F), 2), round(of["physical"] / len(F), 2), round(of["computational"] / len(F), 2), round(of["neutral"] / len(F), 2), round(share, 3), round(base, 3), round(share / base, 2) if base else ""])
    print(f"{name[:26]:26} {start:5} {KIND[name]:13} {len(F):8} {of['newcomer']/len(F):8.2f} {of['physical']/len(F):8.2f} {of['computational']/len(F):8.2f} {of['neutral']/len(F):8.2f} | {share:16.2f} {base:8.2f} {share/base if base else float('nan'):8.2f}")
with (load.OUT / "wave_openness.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["wave", "start", "kind", "founders", "newcomer", "physical_origin", "computational_origin", "neutral", "other_side_share", "baseline_other_side", "openness"]); w.writerows(rows)
