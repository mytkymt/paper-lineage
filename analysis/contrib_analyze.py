"""LLM が付けた貢献類型・素材ラベルを系譜ごとに集計する(contrib_sample.py の出力を使う)。
問い: 二つの系譜は方法(作る/調べる)で分かれているのか、素材(物理/計算)で分かれているのか。
出力: results/core/contrib_types.csv"""
from __future__ import annotations
import csv, json, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
D = load.ROOT / "data" / "contrib"
sample = {r["i"]: r for r in (json.loads(l) for l in (D / "sample.jsonl").open())}
labels = {}
for p in sorted(D.glob("labels_*.jsonl")):
    for l in p.open():
        l = l.strip()
        if not l: continue
        r = json.loads(l); labels[r["i"]] = r
print(f"sample {len(sample)}, labelled {len(labels)}, missing {len(set(sample) - set(labels))}")
TYPES = ["artifact", "empirical", "methodological", "theoretical", "dataset", "survey", "opinion"]
rows = []
def summarize(name, ids):
    n = len(ids); t = Counter(labels[i]["type"] for i in ids)
    ph = np.mean([labels[i]["physical"] for i in ids]); co = np.mean([labels[i]["computational"] for i in ids])
    both = np.mean([labels[i]["physical"] and labels[i]["computational"] for i in ids]); neither = np.mean([not labels[i]["physical"] and not labels[i]["computational"] for i in ids])
    hi = np.mean([labels[i]["confidence"] == "high" for i in ids])
    rows.append([name, n] + [round(t[k] / n, 3) for k in TYPES] + [round(ph, 3), round(co, 3), round(both, 3), round(neither, 3), round(hi, 2)])
    print(f"  {name:22} n={n:4}  " + " ".join(f"{k[:5]} {t[k]/n:.2f}" for k in TYPES) + f" | physical {ph:.2f} computational {co:.2f} both {both:.2f} neither {neither:.2f} | high-conf {hi:.2f}")
groups = defaultdict(list)
for i, r in sample.items():
    if i in labels: groups[r["group"]].append(i)
print("== 系譜別(2010–2025)")
for gname, lab in (("H", "ハード系譜"), ("D", "データ系譜"), ("base", "その他(基準)")): summarize(lab, groups[gname])
print("== 年代別(系譜 × 2010–16 / 2017–25)")
for gname, lab in (("H", "ハード系譜"), ("D", "データ系譜"), ("base", "その他(基準)")):
    for lo, hi, tag in ((2010, 2016, "2010–16"), (2017, 2025, "2017–25")):
        summarize(f"{lab} {tag}", [i for i in groups[gname] if lo <= sample[i]["year"] <= hi])
print("== 作る/調べるの 2 値に潰した場合(artifact+methodological+dataset = 作る、empirical+theoretical+survey+opinion = 調べる・考える)")
for gname, lab in (("H", "ハード系譜"), ("D", "データ系譜"), ("base", "その他(基準)")):
    ids = groups[gname]; build = np.mean([labels[i]["type"] in ("artifact", "methodological", "dataset") for i in ids])
    print(f"  {lab:22} 作る {build:.2f}  調べる・考える {1-build:.2f}")
# 素材の軸と方法の軸の独立性: 系譜を素材でどれだけ当てられるか vs 方法でどれだけ当てられるか
H, Dd = groups["H"], groups["D"]
def acc(feat):
    # 単純な規則: feat が 1 ならハード、0 ならデータ、と当てたときの精度(多数決ベースライン 0.5)
    correct = sum(1 for i in H if feat(i)) + sum(1 for i in Dd if not feat(i)); return correct / (len(H) + len(Dd))
print("== 系譜の当てやすさ(H と D を各 1,000 本、当て推量 0.50)")
print(f"  physical=1 → ハード: {acc(lambda i: labels[i]['physical'] == 1):.2f}")
print(f"  computational=0 → ハード: {acc(lambda i: labels[i]['computational'] == 0):.2f}")
print(f"  physical=1 or computational=0 → ハード: {acc(lambda i: labels[i]['physical'] == 1 or labels[i]['computational'] == 0):.2f}")
print(f"  type=artifact → ハード: {acc(lambda i: labels[i]['type'] == 'artifact'):.2f}")
print(f"  type in (artifact, methodological, dataset) → ハード: {acc(lambda i: labels[i]['type'] in ('artifact','methodological','dataset')):.2f}")
with (load.OUT / "contrib_types.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["group", "n"] + TYPES + ["physical", "computational", "both", "neither", "high_confidence"]); w.writerows(rows)
