"""系譜の乗り換え表の感度分析: 創始者の閾値(2 本 / 3 本)、創始窓(4 / 5 / 6 年)、
波の語の狭い定義、を変えて、主要セルの倍率が同じ向きに残るかを見る。
出力: results/core/lineage_sensitivity.csv"""
import sys, re, json, csv, numpy as np, collections
sys.path.insert(0, __file__.rsplit("/", 1)[0] + "/.."); import load
g = load.load(); V = np.array(g.venue); A = lambda a: a.get("id") if isinstance(a, dict) else a
src = open(__file__.rsplit("/", 1)[0] + "/critique.py").read()
exec(src[src.index("texts = list(g.title)"):src.index('print("  抄録の付与率 年別')])
exec(src[src.index('src = open("waves.py")'):src.index("STRICT = {")])
STRICT = {"LLMs & generative AI": r"large language model|\bllms?\b|\bgpt-?[34]|chatgpt"}
NARROW = {"Tabletop & multitouch": r"tabletop|multi-?touch", "Crowdsourcing (MTurk)": r"mechanical turk|crowdsourc|crowd work", "Deep learning": r"deep learning|deep neural|convolutional neural",
          "Voice assistants": r"voice assistant|alexa|smart speaker|conversational agent", "VR (consumer HMDs)": r"virtual reality|head-?mounted", "Personal fabrication": r"3d.print|digital fabrication|personal fabrication",
          "Wearables & smartwatches": r"smartwatch|wearable", "LLMs & generative AI": r"large language model|chatgpt"}
PAIRS = [("Tabletop & multitouch", "Personal fabrication"), ("Tabletop & multitouch", "VR (consumer HMDs)"), ("Tabletop & multitouch", "LLMs & generative AI"), ("Tabletop & multitouch", "Deep learning"),
         ("Crowdsourcing (MTurk)", "Deep learning"), ("Crowdsourcing (MTurk)", "Voice assistants"), ("Crowdsourcing (MTurk)", "LLMs & generative AI"), ("Crowdsourcing (MTurk)", "VR (consumer HMDs)"),
         ("Deep learning", "LLMs & generative AI"), ("Voice assistants", "LLMs & generative AI"), ("VR (consumer HMDs)", "LLMs & generative AI"), ("Personal fabrication", "LLMs & generative AI"), ("Wearables & smartwatches", "Voice assistants")]
def build(min_papers, win, narrow):
    cohort, prolific = {}, {}
    for name, start0, pat, trig in WAVES:
        if name in ("VR (1990s)", "WWW", "Mobile phones", "Social media", "Smartphones & apps", "Depth cameras (Kinect)"): continue
        p = NARROW[name] if narrow else STRICT.get(name, pat)
        m = wave_members(p, start0, trig); yc = collections.Counter(g.year[m].tolist())
        start = next((y for y in range(start0, 2025) if yc.get(y, 0) / corpus_y.get(y, 1) >= 0.005 and yc.get(y + 1, 0) / corpus_y.get(y + 1, 1) >= 0.005), start0)
        early = m[(g.year[m] >= start) & (g.year[m] < start + win)]
        c = collections.Counter(A(x) for i in early for x in g.authors[i] if A(x)); cohort[name] = (start, {k for k, v in c.items() if v >= min_papers})
        allw = np.flatnonzero((g.year >= start) & (g.year < start + win)); ca = collections.Counter(A(x) for i in allw for x in g.authors[i] if A(x)); prolific[name] = {k for k, v in ca.items() if v >= min_papers}
    return cohort, prolific
def lift(cohort, prolific, a, b):
    sa, Fa = cohort[a]; sb, Fb = cohort[b]
    if sb < sa + 3: return None
    Pb = prolific[b]; NF = prolific[a] - Fa; fa, nf = Fa & Pb, NF & Pb
    if len(fa) < 10 or len(nf) < 10: return None
    pf, pn = len(fa & Fb) / len(fa), len(nf & Fb) / len(nf)
    return (round(pf / pn, 1) if pn else float("inf"), len(fa))
rows = []
configs = [("base: >=2 papers, 5y", 2, 5, False), (">=3 papers, 5y", 3, 5, False), (">=2, 4y", 2, 4, False), (">=2, 6y", 2, 6, False), (">=2, 5y, narrow words", 2, 5, True)]
res = {}
for label, mp, win, narrow in configs:
    cohort, prolific = build(mp, win, narrow); res[label] = {}
    for a, b in PAIRS:
        r = lift(cohort, prolific, a, b); res[label][(a, b)] = r
print(f"{'pair':52} " + " ".join(f"{c[0][:22]:>22}" for c in configs))
for a, b in PAIRS:
    print(f"{a[:22]:22} → {b[:24]:24} " + " ".join((f"{res[l][(a,b)][0]:>6}x n={res[l][(a,b)][1]:<4}" if res[l][(a, b)] else f"{'(n)':>14}").rjust(22) for l, *_ in configs))
with (load.OUT / "lineage_sensitivity.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["from", "to"] + [c[0] for c in configs])
    for a, b in PAIRS: w.writerow([a, b] + [f"{res[l][(a,b)][0]}x (n={res[l][(a,b)][1]})" if res[l][(a, b)] else "" for l, *_ in configs])
