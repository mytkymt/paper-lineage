"""拡張データ(20会場)で: (1) HCI の各サブ帯の初期論文が、コア13会場の外(HRI・VR・ISMAR・
SIGGRAPH/TOG・IJHCS・ToH)をどれだけ引用していたか。(2) 会場群ごとの積み上がり指標
(同サブ帯参照の割合・参照の年齢)を年で比べる: HCI コア vs グラフィックス vs ロボティクス。"""
from __future__ import annotations
import csv, sys
from collections import Counter, defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
assert load.EXT, "PL_DATASET=ext で実行"
g = load.load()
CORE = {"chi","pacmhci","uist","dis","assets","iui","cscw","tei","imwut","ubicomp","chiplay","mobilehci","tochi"}
GROUP = {"siggraph": "graphics", "tog": "graphics", "hri": "robotics", "ieeevr": "vr/ar", "ismar": "vr/ar", "toh": "haptics", "ijhcs": "ijhcs"}
grp = np.array([("hci" if v in CORE else GROUP.get(v, "other")) for v in g.venue])
sub, year = g.sub, g.year

# (1) 初期参照の会場群分布(サブ帯ごと)
rows = []
for s in range(len(g.sub_name)):
    m = np.flatnonzero(sub == s)
    if len(m) < 20: continue
    order = m[np.argsort(year[m], kind="stable")]; early = order[:max(20, int(0.1 * len(m)))]
    e = np.isin(g.citing, early)
    c = Counter(grp[g.cited[e]]); tot = sum(c.values())
    hci_share = float((grp[m] == "hci").mean())
    rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], len(m), round(hci_share, 2), tot,
                 *[round(c.get(k, 0) / tot, 3) if tot else "" for k in ("hci", "graphics", "robotics", "vr/ar", "haptics", "ijhcs")]])
with (load.OUT / "venue_origins.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["sub", "name", "band", "papers", "hci_member_share", "early_refs", "from_hci", "from_graphics", "from_robotics", "from_vrar", "from_haptics", "from_ijhcs"]); w.writerows(rows)
print("HCI 主体(構成員の 70% 以上がコア会場)のサブ帯で、初期参照の外部会場群の割合が高いもの:")
for r in sorted([r for r in rows if r[4] >= 0.7 and r[5] >= 30], key=lambda r: -(1 - r[6]))[:14]:
    print(f"  {r[1][:30]:30} n={r[3]:4}  HCI {r[6]:.2f}  graphics {r[7]:.2f}  robotics {r[8]:.2f}  vr/ar {r[9]:.2f}  haptics {r[10]:.2f}")

# (2) 会場群 × 年の積み上がり
a, b = g.cited, g.citing
ok = (sub[a] >= 0) & (sub[b] >= 0); a, b = a[ok], b[ok]
same = sub[a] == sub[b]; age = year[b] - year[a]
with (load.OUT / "accumulation_by_group.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["group", "period", "refs", "same_sub_share", "mean_ref_age", "median_ref_age"])
    print("\n会場群ごとの積み上がり(5年ごと):")
    for G in ("hci", "graphics", "robotics", "vr/ar"):
        for lo in range(1995, 2026, 5):
            m = (grp[b] == G) & (year[b] >= lo) & (year[b] <= lo + 4)
            if m.sum() < 200: continue
            w.writerow([G, f"{lo}-{lo+4}", int(m.sum()), round(float(same[m].mean()), 3), round(float(age[m].mean()), 2), int(np.median(age[m]))])
            print(f"  {G:9} {lo}-{lo+4}  参照{int(m.sum()):>6}  同サブ帯 {same[m].mean():.2f}  年齢 {age[m].mean():5.2f}")
