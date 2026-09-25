"""生んだ論文の候補を、飽和しない指標で出し直す。

子孫の割合は初期の論文なら何でも高くなる(到達可能性は飽和する)ので、
  - サブ帯内からの直接被引用数(in_sub_cites)
  - サブ帯内の下流辺の SPC 合計(spc_out)
  - CD 指数(5年)
  - 主経路(全体)に載っているか
を出し、「サブ帯の最初の四分位に刊行され、サブ帯内被引用が上位」を founder 候補とする。
"""
from __future__ import annotations
import csv, json, sys
from collections import defaultdict
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, year = g.sub, g.year
main_path = {r["id"] for r in json.loads((load.GRAPH / "main_path.json").read_text())}
on_main = np.array([g.rows[i]["id"] in main_path for i in range(g.n)])
same = sub[g.cited] == sub[g.citing]
in_sub = np.bincount(g.cited[same & (sub[g.cited] >= 0)], minlength=g.n)
spc_out = np.zeros(g.n); np.add.at(spc_out, g.cited[same], g.spc[same])
from metrics import make_cd  # noqa: E402
cd_index = make_cd(g)

rows = []
for s in range(len(g.sub_name)):
    members = np.flatnonzero(sub == s)
    if len(members) < 20: continue
    q1 = np.percentile(year[members], 25)
    early = members[year[members] <= q1]
    # 早い四分位の中で、サブ帯内からの直接被引用が多い順に5本
    top = early[np.argsort(-in_sub[early], kind="stable")[:5]]
    for rank, i in enumerate(top, 1):
        rows.append([s, g.sub_name[s], rank, int(year[i]), g.venue[i], g.title[i][:90], g.doi[i],
                     int(in_sub[i]), round(float(in_sub[i]) / len(members), 3), round(float(spc_out[i]), 1),
                     int(g.cited_by[i]), cd_index(int(i), 5), bool(on_main[i]), int(q1)])
with (load.OUT / "founders2.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "sub_name", "rank", "year", "venue", "title", "doi", "in_sub_cites", "in_sub_share",
                "spc_out", "cited_by", "cd5", "on_main_path", "q1_year"])
    w.writerows(rows)
print("founders2:", len(rows), "rows")
