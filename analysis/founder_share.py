"""学派性の連続量: 創始者(誕生後5年で2本以上)の関与率を、誕生からの経過年ごとに平均する。
サブ帯をまたいで曲線を出し、HCI コアと(拡張データでは)グラフィックス・ロボティクス主体の
サブ帯で比べる。離陸年の「下限張り付き」を避けるため、年ではなく曲線で見る。"""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, year = g.sub, g.year
CORE = {"chi","pacmhci","uist","dis","assets","iui","cscw","tei","imwut","ubicomp","chiplay","mobilehci","tochi"}
GROUP = {"siggraph": "graphics", "tog": "graphics", "hri": "robotics", "ieeevr": "vr/ar", "ismar": "vr/ar", "toh": "haptics", "ijhcs": "hci"}
grp = np.array([("hci" if v in CORE else GROUP.get(v, "other")) for v in g.venue])
birth = {int(r["sub"]): int(r["birth_year"]) for r in csv.DictReader((load.OUT / "subfield_summary.csv").open())}
curves = defaultdict(lambda: defaultdict(list))   # group -> years since birth -> [founder share]
per_sub = []
for s in range(len(g.sub_name)):
    m = np.flatnonzero(sub == s)
    if len(m) < 40 or s not in birth: continue
    b = birth[s]
    fw = m[(year[m] >= b) & (year[m] <= b + 4)]
    cnt = Counter(a for i in fw for a in g.authors[i])
    founders = {a for a, c in cnt.items() if c >= 2}
    if len(founders) < 2: continue
    dom = Counter(grp[m]).most_common(1)[0][0]
    by = defaultdict(lambda: [0, 0])
    for i in m:
        d = int(year[i]) - b
        if d < 0: continue
        by[min(d, 20)][0 if founders & set(g.authors[i]) else 1] += 1
    shares = {}
    for d, (f, o) in by.items():
        if f + o >= 3: shares[d] = f / (f + o); curves[dom][d].append(f / (f + o))
    per_sub.append([s, g.sub_name[s], dom, len(m), b, len(founders)] + [round(shares.get(d, float("nan")), 2) for d in (0, 2, 4, 6, 8, 10, 15)])
with (load.OUT / "founder_share.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "group", "papers", "birth", "founders", "y0", "y2", "y4", "y6", "y8", "y10", "y15"]); w.writerows(per_sub)
print(f"データ: {'ext' if load.EXT else 'core'} / サブ帯 {len(per_sub)}")
print("誕生からの年数 → 創始者関与率の中央値(群ごと):")
for G in sorted(curves, key=lambda k: -len(curves[k][0])):
    line = "  ".join(f"{d:>2}:{np.median(curves[G][d]):.2f}" for d in (0, 1, 2, 3, 4, 5, 6, 8, 10, 15) if len(curves[G][d]) >= 5)
    print(f"  {G:9} (n={len(curves[G][0])}) {line}")
