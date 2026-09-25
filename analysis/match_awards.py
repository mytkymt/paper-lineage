"""賞の論文をコーパスの論文に題名で対応付け、founders2 の候補との重なりを見る。"""
from __future__ import annotations
import csv, re, sys
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
norm = lambda t: re.sub(r"[^a-z0-9 ]", "", t.lower().replace("&", "and")).strip()
by_norm = {}
for i, t in enumerate(g.title): by_norm.setdefault(norm(t), i)
def find(title, yr):
    """完全一致 → 先頭一致 → 語集合の Jaccard(同年±1)の順で探す。副題や記号の違いを吸収する。"""
    t = norm(title)
    if t in by_norm: return by_norm[t]
    yr = int(yr)
    same_year = [i for i in range(g.n) if abs(int(g.year[i]) - yr) <= 1]
    # S2 の題名は副題を落としていることが多い("OmniTouch" だけ等)。主題で先頭一致させる
    head = norm(title.split(":")[0]) if ":" in title else t[:32]
    cands = [i for i in same_year if norm(g.title[i]).startswith(head)]
    if len(cands) == 1: return cands[0]
    tw = set(t.split())
    best, score = -1, 0.0
    for i in same_year:
        w = set(norm(g.title[i]).split())
        j = len(tw & w) / len(tw | w)
        if j > score: best, score = i, j
    return best if score >= 0.6 else -1
sub, year = g.sub, g.year
same = sub[g.cited] == sub[g.citing]
in_sub = np.bincount(g.cited[same & (sub[g.cited] >= 0)], minlength=g.n)
rows, hit = [], 0
for r in csv.DictReader(open(load.ROOT / "analysis/data/awards.csv")):
    i = find(r["title"], r["paper_year"])
    if i < 0:
        rows.append([r["award"], r["award_year"], r["paper_year"], r["title"][:60], "", "", "", "", "", ""]); continue
    hit += 1
    s = int(sub[i])
    members = np.flatnonzero(sub == s) if s >= 0 else np.array([], dtype=int)
    # サブ帯内での順位: 同サブ帯の全論文の中で、サブ帯内被引用の順位(1が最上位)
    rank_all = int((in_sub[members] > in_sub[i]).sum()) + 1 if s >= 0 else ""
    q1 = int(np.percentile(year[members], 25)) if s >= 0 else ""
    early = members[year[members] <= q1] if s >= 0 else members
    rank_early = int((in_sub[early] > in_sub[i]).sum()) + 1 if s >= 0 and year[i] <= q1 else ""
    rows.append([r["award"], r["award_year"], r["paper_year"], g.title[i][:60], g.venue[i], g.sub_name[s] if s >= 0 else "(孤立)",
                 len(members), int(in_sub[i]), rank_all, rank_early])
# 基準: 賞の論文と同じサブ帯・同じ年から無作為に選んだ論文の順位(中央値)
rng = np.random.default_rng(20260729)
base_rows = []
for r in rows:
    if not r[6]: continue
    s_idx = [k for k, nm in enumerate(g.sub_name) if nm == r[5]]
    if not s_idx: continue
    s = s_idx[0]; members = np.flatnonzero(sub == s)
    peers = members[year[members] == int(r[2])]
    if len(peers) < 3: continue
    pr = [int((in_sub[members] > in_sub[p]).sum()) + 1 for p in peers]
    base_rows.append((r[3][:40], r[8], int(np.median(pr)), len(peers)))
print("\n賞の論文の順位 vs 同年・同サブ帯の中央値:")
better = sum(1 for _, a, b, _ in base_rows if a < b)
for t, a, b, k in base_rows: print(f"  {t:40} 賞 {a:>4}  同年の中央値 {b:>4} (n={k})")
print(f"  賞の方が上位: {better}/{len(base_rows)}")

with (load.OUT / "awards_matched.csv").open("w", newline="") as f:
    w = csv.writer(f); w.writerow(["award", "award_year", "paper_year", "title", "venue", "sub_name", "sub_size", "in_sub_cites", "rank_in_sub", "rank_in_early_quartile"]); w.writerows(rows)
print(f"賞の論文 {len(rows)} 本中 {hit} 本をコーパスで同定")
for r in rows: print("  ", r[0], r[2], r[3][:44].ljust(44), (r[5] or '-')[:26].ljust(26), 'サブ内順位', r[8], '/', r[6], ' 初期四分位内順位', r[9])
