"""貢献類型の分類サンプルを作る(系譜の違いが「方法」ではなく「素材」だと示すため)。

二つの系譜の論文(創始者を著者に含む 2005 年以降の論文)から年で層化して各 1,000 本、
比較用にコーパス全体から 500 本、いずれも抄録つきのものを取り、100 本ずつのバッチに分ける。
分類は LLM(Claude)に、Wobbrock & Kientz (2016) の 7 類型と、素材(物理的な装置・素材を
作る/扱うか、データ・モデル・エージェントを扱うか)の 2 軸で付けさせる。
出力: data/contrib/sample.jsonl, data/contrib/batch_NN.jsonl, data/contrib/RUBRIC.md"""
from __future__ import annotations
import json, random, re, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
OUT = load.ROOT / "data" / "contrib"; OUT.mkdir(exist_ok=True)
lin = json.load((OUT / "lineages.json").open())
abstracts = {}
for line in (load.ROOT / "data/s2/abstracts.jsonl").open():
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
def abstract_of(i):
    pid = by_doi.get((g.rows[i].get("doi") or "").lower()) or by_key.get((re.sub(r"[^a-z0-9]+", " ", g.title[i].lower()).strip(), int(g.year[i])))
    return abstracts.get(pid) if pid else None
rng = random.Random(20260927)
def stratified(ids, n):
    ids = [i for i in ids if g.year[i] >= 2010 and abstract_of(i)]
    by_year = {}
    for i in ids: by_year.setdefault(int(g.year[i]), []).append(i)
    per = max(1, n // len(by_year)); out = []
    for y, xs in sorted(by_year.items()):
        rng.shuffle(xs); out += xs[:per]
    rng.shuffle(out); return out[:n]
setH, setD = set(lin["papers_H"]), set(lin["papers_D"])
sample = [(i, "H") for i in stratified([i for i in setH if i not in setD], 1000)] + [(i, "D") for i in stratified([i for i in setD if i not in setH], 1000)] + \
         [(i, "base") for i in stratified([i for i in range(g.n) if i not in setH and i not in setD], 500)]
rng.shuffle(sample)
with (OUT / "sample.jsonl").open("w") as f:
    for i, lab in sample:
        f.write(json.dumps({"i": int(i), "group": lab, "year": int(g.year[i]), "venue": g.venue[i], "title": g.title[i], "abstract": abstract_of(i)}, ensure_ascii=False) + "\n")
for b, k in enumerate(range(0, len(sample), 100)):
    with (OUT / f"batch_{b:02d}.jsonl").open("w") as f:
        for i, lab in sample[k:k + 100]:
            f.write(json.dumps({"i": int(i), "title": g.title[i], "abstract": abstract_of(i)}, ensure_ascii=False) + "\n")
(OUT / "RUBRIC.md").write_text("""# Contribution-type rubric (for the classifier)

Label each paper from its title and abstract only. Output one JSON object per line:
{"i": <id>, "type": <one of the 7>, "physical": 0|1, "computational": 0|1, "confidence": "high"|"low"}

`type` follows Wobbrock & Kientz (2016), pick the PRIMARY contribution:
- empirical: findings from studies of people (interviews, surveys, experiments, observation, log analysis)
- artifact: a new system, technique, device, tool, material, algorithm or design that is built and demonstrated
- methodological: a new method, measure, instrument or process for doing research or design
- theoretical: a concept, framework, model or critique that organises thinking
- dataset: a corpus, benchmark or dataset released for others
- survey: a review or synthesis of existing work
- opinion: an argument, position or reflection

`physical` = 1 if the work builds, modifies or centrally studies a physical device, material,
fabricated object, sensor hardware, haptic/tangible/wearable/VR-AR hardware, robot body or
physical space. `computational` = 1 if it builds or centrally studies data-driven models,
machine learning, language models, agents/chatbots, recommender or crowd-computation systems,
or large-scale data analysis. Both may be 1 (e.g. a robot with a language model) or both 0
(e.g. an interview study of families).
""")
print(f"sample {len(sample)} papers, batches {b + 1}, written to {OUT}")
