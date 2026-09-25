"""RQ3: 分野の親子関係。各サブ帯の**初期**(最初の四分位)の論文が、コーパス内で何を引用
していたか。引用先のサブ帯の分布 = その分野が何から生まれたか。
自分自身への引用は除き、上位3つの親と、親からの引用割合、外部参照率も出す。"""
from __future__ import annotations
import csv, sys
from collections import Counter
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
sub, year = g.sub, g.year
refs_total = np.array([r.get("refs_total") or 0 for r in g.rows])
rows = []
for s in range(len(g.sub_name)):
    m = np.flatnonzero(sub == s)
    if len(m) < 20: continue
    # 「初期」= 年順で最初の 10%(最低 20 本)。四分位だと急成長した分野で初期が最近になってしまう
    order = m[np.argsort(year[m], kind="stable")]
    k = max(20, int(0.10 * len(m)))
    early = set(order[:k].tolist()); q1 = int(year[order[k - 1]])
    e = np.isin(g.citing, list(early))
    tgt = sub[g.cited[e]]
    c = Counter(int(t) for t in tgt if t >= 0 and t != s)
    n_in = int(e.sum()); n_self = int((tgt == s).sum())
    ext = int(refs_total[list(early)].sum()) - n_in          # コーパス外の参照数
    top = c.most_common(3)
    rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], len(m), int(q1), len(early), n_in, ext,
                 round(n_self / n_in, 3) if n_in else "",
                 *sum(([g.sub_name[t], round(k / n_in, 3)] for t, k in top), []),
                 *[""] * (6 - 2 * len(top))])
with (load.OUT / "parents.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "name", "band", "papers", "q1_year", "early_papers", "in_corpus_refs", "external_refs", "self_share",
                "parent1", "p1_share", "parent2", "p2_share", "parent3", "p3_share"])
    w.writerows(rows)
print("親子関係(初期論文の引用先)。大きいサブ帯から:")
for r in sorted(rows, key=lambda r: -r[3])[:30]:
    ext_rate = r[7] / (r[6] + r[7]) if (r[6] + r[7]) else 0
    print(f"  {r[1][:28]:28} 誕生~{r[4]}  自己{r[8]:>5}  外部{ext_rate:.0%}  ← {r[9][:24]}({r[10]}) / {r[11][:24]}({r[12]}) / {r[13][:20]}({r[14]})")
