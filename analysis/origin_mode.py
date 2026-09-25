"""分野の生まれ方(問4の差し替え候補): 自然発生か、作り上げたか。

創始窓(立ち上がりの年から 5 年)の論文について 3 つの集中度を測る。
  top_share  旗印の集中: 後続の同サブ帯論文から創始窓の論文への引用のうち、1 本に集まる割合
  largest    担い手の集中: 創始窓の論文のうち、最大の共著者グループ(共著でつながる連結成分)が書いた割合
  ext_top    外部トリガー: 創始窓の論文のうち、同じコーパス外の論文を引いているものの割合(最大の 1 本)
旗印論文は top_share が FLAG 以上かつ 2 位の 2 倍以上のときだけ「あり」とする(中身の確認は別途)。
出力: origin_mode.csv(サブ帯ごと)。"""
from __future__ import annotations
import csv, json, sys
from collections import Counter
import numpy as np
sys.path.insert(0, __file__.rsplit("/", 1)[0])
import load
g = load.load()
FLAG = 0.25
fs = {int(r["sub"]): r for r in csv.DictReader((load.OUT / "founder_share.csv").open())}
exp = {int(r["sub"]): r for r in csv.DictReader((load.OUT / "export.csv").open())} if (load.OUT / "export.csv").exists() else {}
raw_refs = {}
for line in (load.ROOT / "data/openalex/works.jsonl").open():
    w = json.loads(line); raw_refs[w["id"]] = w.get("refs") or []
ext_title = {}
ext_path = load.ROOT / "data/openalex/external.jsonl"
if ext_path.exists():
    for line in ext_path.open():
        w = json.loads(line); ext_title[w["id"]] = w.get("title") or ""
node_id = [r["id"] for r in g.rows]; in_corpus = set(node_id)

def author_groups(members: np.ndarray) -> Counter:
    """共著でつながる連結成分ごとの論文数。"""
    parent: dict = {}
    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for i in members:
        ids = [a.get("id") if isinstance(a, dict) else a for a in g.authors[i]]; ids = [a for a in ids if a]
        node = ("p", int(i)); parent.setdefault(node, node)
        for a in ids: parent[find(node)] = find(a)
    return Counter(find(("p", int(i))) for i in members)

rows = []
for s in range(len(g.sub_name)):
    m = np.flatnonzero(g.sub == s)
    if len(m) < 50: continue
    birth = g.birth(m)
    win = m[(g.year[m] >= birth) & (g.year[m] < birth + 5)]; later = m[g.year[m] >= birth + 5]
    if len(win) < 10 or len(later) < 20: continue
    comp = author_groups(win); largest = comp.most_common(1)[0][1] / len(win)
    winset = set(win.tolist()); cnt = Counter()
    for j in later:
        for i in g.upstream(int(j)):
            if i in winset: cnt[i] += 1
    tot = sum(cnt.values()); top2 = cnt.most_common(2)
    top_share = top2[0][1] / tot if tot else float("nan")
    flag = bool(tot and top_share >= FLAG and (len(top2) < 2 or top2[0][1] >= 2 * top2[1][1]))
    ec = Counter()
    for i in win:
        for r in raw_refs.get(node_id[i], []):
            if r not in in_corpus: ec[r] += 1
    etop = ec.most_common(1)[0] if ec else (None, 0)
    rows.append([s, g.sub_name[s], g.band_name[int(g.sub_band[s])], len(m), birth, len(win), len(comp), round(largest, 3),
                 round(top_share, 3), int(flag), g.title[top2[0][0]][:80] if tot else "", g.doi[top2[0][0]] if tot else "",
                 round(etop[1] / len(win), 3), ext_title.get(etop[0], "")[:60] if etop[0] else "",
                 exp.get(s, {}).get("export_share_median", ""), fs.get(s, {}).get("y6", "")])
with (load.OUT / "origin_mode.csv").open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["sub", "name", "band", "papers", "birth", "founding_papers", "author_groups", "largest_group_share",
                "top_paper_share", "flag_paper", "top_paper", "top_paper_doi", "ext_trigger_share", "ext_trigger", "export_share", "founder_share_y6"])
    w.writerows(rows)
a = np.array([[r[7], r[8], r[12]] for r in rows], dtype=float)
print(f"サブ帯 {len(rows)} 件。担い手の集中 中央値 {np.median(a[:,0]):.2f} (IQR {np.percentile(a[:,0],25):.2f}–{np.percentile(a[:,0],75):.2f}); "
      f"旗印の集中 中央値 {np.median(a[:,1]):.2f} (IQR {np.percentile(a[:,1],25):.2f}–{np.percentile(a[:,1],75):.2f}); 旗印あり {sum(r[9] for r in rows)} 件")
ml, mt = np.median(a[:, 0]), np.median(a[:, 1])
quad = {(True, True): "one group + flag paper", (True, False): "one group, no flag paper", (False, True): "many groups + flag paper", (False, False): "many groups, no flag paper"}
for key, label in quad.items():
    rs = [r for r in rows if (r[7] >= ml) == key[0] and (r[8] >= mt) == key[1]]
    print(f"\n== {label} ({len(rs)}) ==")
    for r in sorted(rs, key=lambda r: -r[3])[:8]:
        print(f"  {r[1][:32]:32} born {r[4]} n={r[3]:4} group {r[7]:.2f} flag {r[8]:.2f}{'*' if r[9] else ' '} {r[10][:38]:38} ext {r[12]:.2f}")
def rank(x): return np.argsort(np.argsort(x))
def spear(x, y):
    ok = ~np.isnan(x) & ~np.isnan(y); return np.corrcoef(rank(x[ok]), rank(y[ok]))[0, 1], int(ok.sum())
size = np.array([r[3] for r in rows], dtype=float); y6 = np.array([float(r[15]) if r[15] not in ("", "nan") else np.nan for r in rows])
expo = np.array([float(r[14]) if r[14] != "" else np.nan for r in rows])
print("\n順位相関(検定なし): largest×top %.2f; largest×size %.2f; top×size %.2f; top×founder_y6 %.2f (n=%d); largest×founder_y6 %.2f; largest×export %.2f; top×export %.2f"
      % (spear(a[:,0], a[:,1])[0], spear(a[:,0], size)[0], spear(a[:,1], size)[0], *spear(a[:,1], y6), spear(a[:,0], y6)[0], spear(a[:,0], expo)[0], spear(a[:,1], expo)[0]))
