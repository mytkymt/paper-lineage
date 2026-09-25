"""C4: 分野は学派として生まれ、他者が入って分野になる — 離陸年の測定(改訂)。

最初の 10% を「初期」にすると、後年のクラスタに紛れた 1980 年代の散発論文が初期扱いになり、
全分野が誕生直後に離陸してしまった。ここでは:
  誕生年 = サブ帯が 5 本または全体の 2% に達した年(subfield_summary と同じ定義)
  創始期 = 誕生年から 5 年間、創始者 = 創始期にそのサブ帯で 2 本以上持つ著者
  創始者関与 = 著者に創始者を 1 人でも含む論文
  離陸年 = 創始期の後、年間 5 本以上ある年で、創始者関与の割合が初めて 50% を下回った年
  さらに創始論文(founders2 の上位 3 本)ごとに、著者を共有しない論文 10 本に引用されるまでの年数(採用の遅れ)
"""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, year = g.sub, g.year
birth = {int(r["sub"]): int(r["birth_year"]) for r in csv.DictReader((load.OUT / "subfield_summary.csv").open())}
founder_papers = defaultdict(list)
for r in csv.DictReader((load.OUT / "founders2.csv").open()):
    if int(r["rank"]) <= 3:
        founder_papers[int(r["sub"])].append(r)
title_idx = {(t, int(y)): i for i, (t, y) in enumerate(zip(g.title, year))}

rows, adopt_rows = [], []
for s in range(len(g.sub_name)):
    m = np.flatnonzero(sub == s)
    if len(m) < 40 or s not in birth: continue
    b = birth[s]
    fw = m[(year[m] >= b) & (year[m] <= b + 4)]
    cnt = Counter(a for i in fw for a in g.authors[i])
    founders = {a for a, c in cnt.items() if c >= 2}
    if len(founders) < 2: continue
    by_year = defaultdict(lambda: [0, 0])
    for i in m:
        by_year[int(year[i])][0 if founders & set(g.authors[i]) else 1] += 1
    takeoff = None
    for y in sorted(by_year):
        f, o = by_year[y]
        if y > b + 4 and f + o >= 5 and f / (f + o) < 0.5:
            takeoff = y; break
    total_f = sum(v[0] for v in by_year.values())
    fw_share = sum(by_year[y][0] for y in range(b, b + 5)) / max(1, len(fw))
    last5 = float((year[m] >= year.max() - 4).mean())
    rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], len(m), b, len(fw), len(founders),
                 round(fw_share, 3), round(total_f / len(m), 3), takeoff if takeoff else "",
                 (takeoff - b) if takeoff else "", round(last5, 3)])
    # 採用の遅れ(創始論文ごと)
    for r in founder_papers.get(s, []):
        i = title_idx.get((r["title"][:90] if len(r["title"]) < 90 else r["title"], int(r["year"])))
        if i is None:
            cands = [j for j in m if g.title[j][:90] == r["title"] and year[j] == int(r["year"])]
            i = cands[0] if cands else None
        if i is None: continue
        au = set(g.authors[i])
        citers = sorted(g.downstream(i), key=lambda j: (year[j], j))
        outside = [j for j in citers if not (au & set(g.authors[j]))]
        first20 = citers[:20]
        self_share = sum(1 for j in first20 if au & set(g.authors[j])) / max(1, len(first20))
        lag = (year[outside[9]] - year[i]) if len(outside) >= 10 else ""
        adopt_rows.append([s, g.sub_name[s], int(year[i]), g.title[i][:70], len(citers), len(outside), lag, round(self_share, 2)])

with (load.OUT / "takeoff.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "name", "band", "papers", "birth", "founding_papers", "founders", "founder_share_in_founding", "founder_share_all", "takeoff_year", "years_to_takeoff", "share_last5"])
    w.writerows(rows)
with (load.OUT / "adoption.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "name", "year", "founder_paper", "citers", "citers_outside", "years_to_10_outside", "self_share_first20"])
    w.writerows(adopt_rows)

took = [r for r in rows if r[9] != ""]; never = [r for r in rows if r[9] == ""]
print(f"サブ帯 {len(rows)}: 離陸した {len(took)} / まだ創始者が過半 {len(never)}")
if took:
    yrs = sorted(r[10] for r in took)
    print(f"誕生から離陸まで: 中央値 {yrs[len(yrs)//2]} 年, 四分位 {yrs[len(yrs)//4]}–{yrs[3*len(yrs)//4]}, 最大 {yrs[-1]}")
print(f"創始期の創始者関与率: 中央値 {np.median([r[7] for r in rows]):.2f}")
print("\n離陸が早い(誕生→離陸 ≤6年、大きい順):")
for r in sorted([r for r in took if r[10] <= 6], key=lambda r: -r[3])[:10]:
    print(f"  {r[1][:32]:32} 誕生{r[4]} 創始者{r[6]:>3}人 関与率{r[7]:.2f} 離陸{r[9]}(+{r[10]}) 直近5年{r[11]:.2f}")
print("\n離陸が遅い:")
for r in sorted(took, key=lambda r: -r[10])[:10]:
    print(f"  {r[1][:32]:32} 誕生{r[4]} 創始者{r[6]:>3}人 関与率{r[7]:.2f} 離陸{r[9]}(+{r[10]}) 直近5年{r[11]:.2f}")
print("\nまだ創始者が過半:")
for r in sorted(never, key=lambda r: -r[3])[:10]:
    print(f"  {r[1][:32]:32} 誕生{r[4]} 創始者{r[6]:>3}人 関与率{r[7]:.2f} 全期間の関与率{r[8]:.2f} n={r[3]} 直近5年{r[11]:.2f}")
fast = [r[11] for r in took if r[10] <= 6]; slow = [r[11] for r in took if r[10] >= 10]
print(f"\n直近5年の活動割合(持続): 離陸≤6年 中央値 {np.median(fast):.2f} (n={len(fast)}) / 離陸≥10年 {np.median(slow):.2f} (n={len(slow)})" + (f" / 未離陸 {np.median([r[11] for r in never]):.2f} (n={len(never)})" if never else ""))
lags = [r[6] for r in adopt_rows if r[6] != ""]
print(f"\n創始論文の採用の遅れ(他者10本に引かれるまで): n={len(lags)} 中央値 {np.median(lags):.0f} 年, 四分位 {np.percentile(lags,25):.0f}–{np.percentile(lags,75):.0f}")
print(f"創始論文の最初の20引用のうち自己(著者共有)の割合: 中央値 {np.median([r[7] for r in adopt_rows]):.2f}")
