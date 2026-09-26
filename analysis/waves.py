"""技術の波の代謝(TOCHI 案 A の試作): HCI は外から来る技術の波をどう取り込み、何を残すか。

波 = 題名の語(と引き金論文への引用)で定めた論文集合と開始年。波ごとに同じ物差しで測る:
  速さ   開始年からコーパスの 1%・2% に達するまでの年数、ピーク年とピークの割合
  広がり 最初の 5 年で波の論文が 5 本以上あるサブ帯の数、サブ帯分布の正規化エントロピー
  分化   凝集(lift) = 波の論文が波の論文を引く割合 / 同じ年の波でない論文が波の論文を引く割合。
         1 なら周囲に溶けている、大きいほど自分たちの会話を作っている。サブ帯(116 個)は粗すぎて
         波の分化を捉えないので、参照から直接測る
  担い手 最初の 3 年の波の論文の著者のうち、開始前にコーパスに論文が無い新参の割合。同年の全論文と比べる
  残存   開始 10 年後の割合 / ピークの割合(古い波のみ)、波の論文の参照年齢
  記憶   波の論文(最初の 5 年)のコーパス内参照のうち、前の波の論文に向かう割合(波×波の行列)
題名だけで定めるので取りこぼしはある(抄録は公開 API から取っていない)。出力: waves.csv, wave_memory.csv, wave_curves.csv"""
from __future__ import annotations
import csv, json, re, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
LAST = 2025   # 2026 は年の途中
raw_refs = {}
for line in (load.ROOT / "data/openalex/works.jsonl").open():
    w = json.loads(line); raw_refs[w["id"]] = w.get("refs") or []
ext_id_by_title = {}
ext_path = load.ROOT / "data/openalex/external.jsonl"
if ext_path.exists():
    for line in ext_path.open():
        w = json.loads(line); ext_id_by_title[(w.get("title") or "").lower()] = w["id"]
node_id = [r["id"] for r in g.rows]; idx = {n: i for i, n in enumerate(node_id)}
titles_l = [t.lower() for t in g.title]
# 抄録(data/s2/abstracts.jsonl、S2 の paperId)を DOI と題名+年でコーパスの行に結ぶ
texts = list(g.title)
abs_path = load.ROOT / "data/s2/abstracts.jsonl"
if abs_path.exists():
    abstracts = {}
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
    n_abs = 0
    for i, row in enumerate(g.rows):
        pid = by_doi.get((row.get("doi") or "").lower()) or by_key.get((re.sub(r"[^a-z0-9]+", " ", g.title[i].lower()).strip(), int(g.year[i])))
        if pid: texts[i] = g.title[i] + "\n" + abstracts[pid]; n_abs += 1
    print(f"抄録つき {n_abs:,}/{g.n:,} 本(語の判定は題名+抄録)")
else:
    print("抄録なし(語の判定は題名だけ)")

WAVES = [  # (名前, 開始年, 題名の正規表現, 引き金論文の題名(前方一致, 小文字))
    ("WWW", 1994, r"world wide web|\bwww\b|web site|website|web browser|web page|hypertext|\bhtml\b|web-based", []),
    ("Mobile phones", 1999, r"mobile phone|cell ?phone|handheld|\bpda\b|pocket pc|palm", []),
    ("Tabletop & multitouch", 2005, r"multi-?touch|tabletop|touch ?screen|interactive surface", []),
    ("Social media", 2007, r"facebook|twitter|social network(ing)? sites?|social media|myspace|instagram|reddit|youtube", []),
    ("Smartphones & apps", 2008, r"smartphone|iphone|android|mobile app|app store|smart phone", []),
    ("Crowdsourcing (MTurk)", 2008, r"mechanical turk|crowdsourc|crowd ?work|human computation|microtask|crowd-?powered|crowd worker", ["crowdsourcing user studies with mechanical turk", "labeling images with a computer game", "recaptcha"]),
    ("Depth cameras (Kinect)", 2011, r"kinect|depth camera|depth sensor|rgb-?d|skeleton tracking|body tracking", ["kinectfusion", "real-time human pose recognition in parts"]),
    ("Personal fabrication", 2012, r"3d.print|digital fabrication|personal fabrication|fabricat|laser.?cut", []),
    ("Wearables & smartwatches", 2014, r"smartwatch|smart watch|wrist-?worn|google glass|fitness tracker|activity tracker|fitbit", []),
    ("Deep learning", 2015, r"deep learning|deep neural|convolutional neural|recurrent neural|\blstm\b|\bcnn\b", ["imagenet classification with deep convolutional", "deep learning"]),
    ("VR (consumer HMDs)", 2016, r"virtual reality|\bvr\b|head-?mounted|\bhmds?\b|oculus|htc vive", []),
    ("Voice assistants", 2016, r"voice assistant|alexa|smart speaker|conversational agent|chatbot|voice interface|voice user interface|\bsiri\b|google home", []),
    ("LLMs & generative AI", 2022, r"large language model|\bllms?\b|\bgpt-?[34]|chatgpt|generative ai|foundation model|diffusion model|text-to-image|stable diffusion|midjourney|copilot", ["language models are few-shot learners", "attention is all you need", "sparks of artificial general intelligence"]),
    ("VR (1990s)", 1992, r"virtual reality|virtual environment|head-?mounted|immersive", []),
]
sub_birth = {s: g.birth(np.flatnonzero(g.sub == s)) for s in range(len(g.sub_name)) if (g.sub == s).sum() >= 20}
corpus_y = g.corpus_by_year
first_year_of_author: dict = {}
for i in np.argsort(g.year, kind="stable"):
    for a in g.authors[i]:
        aid = a.get("id") if isinstance(a, dict) else a
        if aid and aid not in first_year_of_author: first_year_of_author[aid] = int(g.year[i])

def wave_members(pat: str, start: int, triggers: list[str], end: int | None = None) -> np.ndarray:
    rx = re.compile(pat, re.I)
    trig_ids = set()
    for t in triggers:
        for tl, eid in ext_id_by_title.items():
            if tl.startswith(t): trig_ids.add(eid)
        for i, tl in enumerate(titles_l):
            if tl.startswith(t): trig_ids.add(node_id[i])
    hit = np.zeros(g.n, dtype=bool)
    for i in range(g.n):
        if g.year[i] < start or (end and g.year[i] > end): continue
        if rx.search(texts[i]) or (trig_ids and any(r in trig_ids for r in raw_refs.get(node_id[i], []))):
            hit[i] = True
    return np.flatnonzero(hit)

waves = {}
rows, curves, memory = [], [], []
for name, start, pat, trig in WAVES:
    end = 2003 if name == "VR (1990s)" else None
    m = wave_members(pat, start, trig, end); waves[name] = set(m.tolist())
    yc = Counter(g.year[m].tolist())
    share = {y: yc.get(y, 0) / corpus_y[y] for y in range(start, LAST + 1) if y in corpus_y}
    for y, v in share.items(): curves.append([name, y, yc.get(y, 0), round(v, 4)])
    t1 = next((y - start for y, v in share.items() if v >= 0.01), None)
    t2 = next((y - start for y, v in share.items() if v >= 0.02), None)
    peak_y = max(share, key=share.get); peak = share[peak_y]
    after10 = share.get(start + 10); persist = round(after10 / peak, 2) if after10 is not None and start + 10 <= LAST and peak else ""
    early = m[g.year[m] < start + 5]; early3 = m[g.year[m] < start + 3]
    base = np.flatnonzero((g.year >= start) & (g.year < start + 5))
    subs = Counter(int(s) for s in g.sub[early] if s >= 0)
    breadth = sum(1 for c in subs.values() if c >= 5)
    p = np.array(list(subs.values()), dtype=float); p /= p.sum() if p.sum() else 1
    ent = float(-(p * np.log(p + 1e-12)).sum() / np.log(len(p))) if len(p) > 1 else 0.0
    # 凝集(lift): 波の論文が波の論文を引く割合 / 同じ年の波でない論文が波の論文を引く割合。
    # 1 なら周囲と区別がつかない(溶けている)、大きいほど自分たちの会話を作っている。
    wset = waves[name]
    def ref_share_to_wave(ids):
        tot = hit = 0
        for j in ids:
            for i in g.upstream(int(j)):
                tot += 1; hit += i in wset
        return hit / tot if tot else float("nan"), tot
    self_ref, _ = ref_share_to_wave(early)
    others = [j for j in base if j not in wset]
    other_ref, _ = ref_share_to_wave(others[::max(1, len(others) // 4000)])
    cohesion = round(self_ref / other_ref, 1) if other_ref else float("nan"); self_ref = round(self_ref, 3)
    # 吸収先: 最初の 5 年の波の論文が入ったサブ帯の上位
    top_subs = "; ".join(f"{g.sub_name[s][:28]} {c}" for s, c in subs.most_common(3))
    def newcomer_share(ids):
        tot = new = 0
        for i in ids:
            for a in g.authors[i]:
                aid = a.get("id") if isinstance(a, dict) else a
                if not aid: continue
                tot += 1; new += first_year_of_author.get(aid, 0) >= start
        return new / tot if tot else float("nan")
    base3 = np.flatnonzero((g.year >= start) & (g.year < start + 3))
    nc, nc_base = newcomer_share(early3), newcomer_share(base3)
    # 古参の出身サブ帯(開始前の論文が最も多いサブ帯)
    origin = Counter()
    for i in early3:
        for a in g.authors[i]:
            aid = a.get("id") if isinstance(a, dict) else a
            if aid and first_year_of_author.get(aid, 9999) < start: origin[aid] += 1
    inc_subs = Counter()
    if origin:
        by_author = defaultdict(Counter)
        for i in np.flatnonzero(g.year < start):
            for a in g.authors[i]:
                aid = a.get("id") if isinstance(a, dict) else a
                if aid in origin and g.sub[i] >= 0: by_author[aid][int(g.sub[i])] += 1
        for aid, c in by_author.items(): inc_subs[g.sub_name[c.most_common(1)[0][0]]] += 1
    # 参照年齢
    ages = [g.year[j] - g.year[i] for j in early for i in g.upstream(int(j))]
    base_ages = [g.year[j] - g.year[i] for j in base[::max(1, len(base) // 3000)] for i in g.upstream(int(j))]
    rows.append([name, start, len(m), t1, t2, peak_y, round(peak, 3), persist, breadth, round(ent, 2), self_ref, cohesion,
                 top_subs, round(nc, 2), round(nc_base, 2),
                 "; ".join(f"{n} {c}" for n, c in inc_subs.most_common(3)), round(float(np.mean(ages)), 1) if ages else "", round(float(np.mean(base_ages)), 1) if base_ages else ""])
    print(f"{name:26} start {start} n={len(m):5} →1% {t1} →2% {t2} peak {peak_y} {peak:.1%} keep10 {persist or '-':>4} breadth {breadth:3} ent {ent:.2f} self-ref {self_ref:.2f} cohesion x{cohesion} newcomers {nc:.2f} (base {nc_base:.2f}) refage {np.mean(ages) if ages else 0:.1f} (base {np.mean(base_ages) if base_ages else 0:.1f})")
    print(f"    absorbed into: {top_subs} | incumbents from: {'; '.join(f'{n} {c}' for n, c in inc_subs.most_common(3))}", flush=True)
# 記憶: 波×波
names = [w[0] for w in WAVES]
print("\n記憶: 行=引く波(最初の 5 年)、列=引かれる波、値=コーパス内参照に占める割合")
for name, start, *_ in WAVES:
    early = [i for i in waves[name] if g.year[i] < start + 5]
    refs = [i for j in early for i in g.upstream(int(j))]
    tot = len(refs); row = [name]
    for other in names:
        v = sum(1 for i in refs if i in waves[other]) / tot if tot else float("nan"); row.append(round(v, 3))
    memory.append(row)
    print(f"  {name:26} " + " ".join(f"{v:5.2f}" for v in row[1:]))
with (load.OUT / "waves.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["wave", "start", "papers", "years_to_1pct", "years_to_2pct", "peak_year", "peak_share", "share_at_10y_over_peak", "subs_with_5plus", "sub_entropy",
                                   "self_reference_share", "cohesion_lift", "absorbed_into", "newcomer_author_share", "baseline_newcomer_share", "incumbents_from", "ref_age", "baseline_ref_age"]); w.writerows(rows)
with (load.OUT / "wave_curves.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["wave", "year", "papers", "share_of_corpus"]); w.writerows(curves)
with (load.OUT / "wave_memory.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["citing_wave"] + names); w.writerows(memory)
