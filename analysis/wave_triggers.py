"""波の引き金をデータから抽出する: コーパス外の論文への引用が急に増えた年を探す。

外部論文ごとに、コーパスからの引用をコーパス 1,000 本あたりの率で年別に数え(コーパスは
40 年で 30 倍になるので生の件数では後年に偏る)、「その年からの 3 年間の率が、それ以前の年平均の
5 倍以上で、3 年の件数が 10 件以上」になった最初の年を急増年とする。引き金の種類は名前の規則で
粗く付ける(method / theory / technology / hci / other)。技術の波の引き金は technology のもの。
急増年ごとに上位を並べ、手で選んだ波(Kinect、GPT-3 など)が含まれているかを確かめる。
出力: wave_triggers.csv"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
ext = {}
for line in (load.ROOT / "data/openalex/external.jsonl").open():
    w = json.loads(line); ext[w["id"]] = w
node_id = [r["id"] for r in g.rows]
cites = defaultdict(Counter)   # ext id -> year -> n
for line in (load.ROOT / "data/openalex/works.jsonl").open():
    w = json.loads(line)
    if w["id"] not in g.idx: continue
    y = int(w["year"])
    for r in w.get("refs") or []:
        if r in ext: cites[r][y] += 1
import re
TYPE_RULES = [
    ("method", r"qualitative|grounded theory|thematic analysis|coding manual|nasa-tlx|task load|coefficient of agreement|questionnaire|survey research|statistic|prisma|likert|usability scale|interview|case study research|research methods|design research|research through design"),
    ("theory", r"presentation of self|situated|reflective practitioner|strength of weak ties|flow: the psychology|mindstorms|media equation|where the action is|technology as experience|theory|philosoph|meeting the universe|design justice|race after technology|automating inequality|custodians|ghost work|psychology of"),
    ("technology", r"kinect|depth|diffusion|language model|gpt|transformer|attention is all|neural|convolutional|lstm|word representation|glove|imagenet|libsvm|weka|d³|data-driven documents|toolkit|system|sensor|sensing|display|touch|printer|fabricat|arduino|badge|api|framework for|library|dataset|corpus\b|benchmark|model cards|clip|latent|stable diffusion|prompt"),
]
def trig_type(w):
    t = (w.get("title") or "").lower(); src = (w.get("source") or w.get("container") or "").lower()
    if re.search(r"human factors in computing|sigchi|user interface software|cscw|ubicomp|ubiquitous computing|tangible|human-computer interaction|interacting with computers|interactions$|pervasive", src): return "hci"
    for name, pat in TYPE_RULES:
        if re.search(pat, t): return name
    if w.get("type") in ("book", "book-chapter") or (not src): return "book/other"
    return "other"
cy = g.corpus_by_year
rows = []
VOLUME = re.compile(r"^(proceedings of|chi ?'\d\d|extended abstracts|advances in neural information|lecture notes|ubicomp 20|companion)", re.I)   # 巻全体への参照(誤解決)
for eid, yc in cites.items():
    tot = sum(yc.values())
    if tot < 15 or VOLUME.match(ext[eid].get("title") or ""): continue
    rate = {y: 1000 * n / cy[y] for y, n in yc.items() if y in cy}
    ys = sorted(rate); y0 = ys[0]
    for y in range(y0, 2024):
        three_n = sum(yc.get(y + k, 0) for k in range(3))
        three_r = sum(rate.get(y + k, 0) for k in range(3)) / 3
        before = [rate.get(k, 0) for k in range(y0, y)]
        prior = (sum(before) / len(before)) if before else 0.0
        if three_n >= 10 and three_r >= 5 * max(prior, 0.3):
            w = ext[eid]
            rows.append([y, eid, (w.get("title") or "")[:80], w.get("year"), (w.get("source") or w.get("container") or "")[:40], trig_type(w), three_n, round(three_r, 2), round(prior, 2), tot])
            break
rows.sort(key=lambda r: (r[0], -r[7]))
with (load.OUT / "wave_triggers.csv").open("w", newline="") as f:
    wr = csv.writer(f); wr.writerow(["burst_year", "openalex_id", "title", "published", "source", "type", "cites_3y", "rate_3y_per_1000", "prior_rate", "total_cites"]); wr.writerows(rows)
print(f"急増した外部論文 {len(rows):,} 件; 種類: {dict(Counter(r[5] for r in rows))}")
by_year = defaultdict(list)
for r in rows:
    if r[5] == "technology": by_year[r[0]].append(r)
print("technology の引き金(年ごと上位、率の順):")
for y in sorted(by_year):
    top = sorted(by_year[y], key=lambda r: -r[7])[:6]
    print(f"{y} ({len(by_year[y]):3}): " + " | ".join(f"{r[2][:42]} ({r[3]}, {r[6]})" for r in top))
print("\n手で選んだ引き金の急増年:")
CHECK = ["kinectfusion", "real-time human pose", "language models are few-shot", "attention is all you need", "imagenet classification", "labeling images with a computer game", "recaptcha", "high-resolution image synthesis", "sparks of artificial", "the active badge", "d³ data-driven"]
for r in rows:
    if any(r[2].lower().startswith(c) for c in CHECK): print(f"  {r[0]}  {r[2][:60]} ({r[3]}) type={r[5]} cites3y={r[6]}")
