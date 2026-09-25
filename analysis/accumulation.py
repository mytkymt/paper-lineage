"""RQ4: 積み上がりの測り方。

  同一サブ帯への引用の割合(サブ帯 × 年): その年のサブ帯の論文が持つコーパス内参照のうち
    同じサブ帯 / 同じ帯の別サブ / 別の帯 に向かう割合、および同一サブ帯参照の平均年齢
  サブ帯の持続: 活動期間、ピーク後の減衰
  全体: 年ごとの「同一サブ帯参照の割合」と「参照の平均年齢」
"""
from __future__ import annotations
import csv, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, band, year = g.sub, g.band, g.year
a, b = g.cited, g.citing          # a: 引用される(古い), b: 引用する(新しい)
ok = (sub[a] >= 0) & (sub[b] >= 0)
a, b = a[ok], b[ok]
same_sub = sub[a] == sub[b]
same_band = (band[a] == band[b]) & ~same_sub
age = year[b] - year[a]

# サブ帯 × 年
acc = defaultdict(lambda: [0, 0, 0, 0.0])   # [same_sub, same_band_other, other_band, sum_age_same_sub]
for i in range(len(a)):
    k = (int(sub[b[i]]), int(year[b[i]]))
    if same_sub[i]: acc[k][0] += 1; acc[k][3] += age[i]
    elif same_band[i]: acc[k][1] += 1
    else: acc[k][2] += 1
with (load.OUT / "accumulation_sub_year.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "band", "year", "refs", "same_sub_share", "same_band_share", "other_band_share", "mean_age_same_sub"])
    for (s, y), (ss, sb, ob, sa) in sorted(acc.items()):
        t = ss + sb + ob
        w.writerow([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], y, t, round(ss/t, 3), round(sb/t, 3), round(ob/t, 3), round(sa/ss, 2) if ss else ""])

# 全体 × 年(刊行年でまとめる)
with (load.OUT / "accumulation_year.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["year", "refs", "same_sub_share", "same_band_share", "other_band_share", "mean_ref_age", "median_ref_age"])
    for y in range(int(year.min()), int(year.max()) + 1):
        m = year[b] == y
        if m.sum() < 50: continue
        w.writerow([y, int(m.sum()), round(float(same_sub[m].mean()), 3), round(float(same_band[m].mean()), 3),
                    round(float((~same_sub[m] & ~same_band[m]).mean()), 3), round(float(age[m].mean()), 2), int(np.median(age[m]))])

# サブ帯ごとの持続(活動期間・重心・現在の勢い)
with (load.OUT / "persistence.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "band", "papers", "first", "last", "span", "peak", "share_last5", "same_sub_share_all"])
    for s in range(len(g.sub_name)):
        m = sub == s
        if m.sum() < 20: continue
        ys = year[m]; cnt = np.bincount(ys - ys.min())
        peak = int(ys.min() + cnt.argmax())
        last5 = float((ys >= year.max() - 4).mean())
        mm = (sub[b] == s)
        w.writerow([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], int(m.sum()), int(ys.min()), int(ys.max()),
                    int(ys.max() - ys.min()), peak, round(last5, 3), round(float(same_sub[mm].mean()), 3) if mm.sum() else ""])
print("accumulation done")
