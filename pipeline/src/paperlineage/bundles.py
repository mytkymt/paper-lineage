"""Step 5: 太いラインを束(bundle)として取り出し、「誰が作った太さか」を判定する。

やること:
  1. SPC 上位 p% のエッジを取る = 幹ネットワーク
  2. その部分グラフの弱連結成分を「バンドル」とする(= 1本の太い流れ)
  3. 各バンドルについて、それが
       (a) 特定ラボ / ラストオーサーの自己参照ライン なのか
       (b) 独立した複数グループが乗った分野トレンド なのか
     を数値で出す

判定に使う指標:
  - self_citation_rate : バンドル内エッジのうち、引用元と引用先で著者が1人以上重なる割合
  - independent_groups : バンドル内論文を「著者を共有するか」で連結したときの成分数
  - last_author_entropy: ラストオーサー分布のエントロピー(正規化済み 0..1)
                         HCI は last author = PI の慣行が強いので効くはず

self_citation_rate が高く independent_groups が少ないほど (a) 寄り。
**(a) を捨てない。** ラボの系譜自体も見たい情報なので、色を分けるための指標として使う。

出力: data/graph/bundles.json

  uv run python -m paperlineage.bundles [--top-percent 1.0]
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRAPH_DIR = ROOT / "data" / "graph"


class DisjointSet:
    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:  # 経路圧縮
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def normalized_entropy(counts: list[int]) -> float:
    """0(1人に集中)..1(均等に分散)。要素が1つなら 0 を返す。"""
    total = sum(counts)
    if total == 0 or len(counts) <= 1:
        return 0.0
    h = -sum((c / total) * math.log(c / total) for c in counts if c > 0)
    return h / math.log(len(counts))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--top-percent",
        type=float,
        default=1.0,
        help="SPC 上位何%%のエッジを幹とみなすか(既定 1.0%%)",
    )
    ap.add_argument("--min-size", type=int, default=5, help="この本数未満のバンドルは出力しない")
    args = ap.parse_args()

    nodes = {n["id"]: n for n in (json.loads(l) for l in (GRAPH_DIR / "nodes.jsonl").open())}

    spc: list[tuple[str, str, float]] = []
    for line in (GRAPH_DIR / "spc.tsv").open():
        a, b, w = line.rstrip("\n").split("\t")
        spc.append((a, b, float(w)))
    spc.sort(key=lambda e: -e[2])

    k = max(1, int(len(spc) * args.top_percent / 100.0))
    trunk = spc[:k]
    print(f"edges total={len(spc):,}  trunk (top {args.top_percent}%)={len(trunk):,}")
    print(f"  logSPC threshold: {trunk[-1][2]:.2f}  (max {trunk[0][2]:.2f})")

    # --- バンドル = 幹ネットワークの弱連結成分 ---
    ds = DisjointSet()
    for a, b, _ in trunk:
        ds.union(a, b)

    members: dict[str, set[str]] = defaultdict(set)
    bundle_edges: dict[str, list[tuple[str, str, float]]] = defaultdict(list)
    for a, b, w in trunk:
        root = ds.find(a)
        members[root].update((a, b))
        bundle_edges[root].append((a, b, w))

    results = []
    for root, papers in members.items():
        if len(papers) < args.min_size:
            continue
        edges = bundle_edges[root]

        # 著者集合(欠損している論文は判定から除く)
        author_sets = {p: set(nodes[p].get("authors") or []) for p in papers}

        # (a) 自己引用率: 引用元と引用先で著者が重なるエッジの割合
        judged = [e for e in edges if author_sets[e[0]] and author_sets[e[1]]]
        shared = sum(1 for a, b, _ in judged if author_sets[a] & author_sets[b])
        self_rate = shared / len(judged) if judged else None

        # (b) 独立グループ数: 著者を共有する論文どうしを連結した成分数
        grp = DisjointSet()
        by_author: dict[str, list[str]] = defaultdict(list)
        for p in papers:
            grp.find(p)
            for a in author_sets[p]:
                by_author[a].append(p)
        for plist in by_author.values():
            for p in plist[1:]:
                grp.union(plist[0], p)
        independent_groups = len({grp.find(p) for p in papers})

        # (c) ラストオーサー分布
        last_authors = Counter(
            nodes[p].get("last_author") for p in papers if nodes[p].get("last_author")
        )
        la_entropy = normalized_entropy(list(last_authors.values()))

        years = [nodes[p]["year"] for p in papers]
        venues = Counter(nodes[p].get("venue_key") for p in papers)
        top_papers = sorted(papers, key=lambda p: -(nodes[p].get("cited_by_count") or 0))[:12]

        results.append(
            {
                "bundle_id": root,
                "papers": len(papers),
                "edges": len(edges),
                "year_range": [min(years), max(years)],
                "venues": dict(venues.most_common()),
                "self_citation_rate": self_rate,
                "independent_groups": independent_groups,
                "groups_per_paper": independent_groups / len(papers),
                "last_author_entropy": la_entropy,
                "distinct_last_authors": len(last_authors),
                "top_papers": [
                    {
                        "year": nodes[p]["year"],
                        "cited_by": nodes[p].get("cited_by_count"),
                        "venue": nodes[p].get("venue_key"),
                        "title": nodes[p].get("title"),
                    }
                    for p in top_papers
                ],
            }
        )

    results.sort(key=lambda r: -r["papers"])
    (GRAPH_DIR / "bundles.json").write_text(json.dumps(results, ensure_ascii=False, indent=2))

    print(f"\nbundles (>= {args.min_size} papers): {len(results)}")
    print(f"{'papers':>7} {'yrs':>11} {'selfcite':>9} {'groups':>7} {'LAent':>6}  top paper")
    for r in results[:25]:
        sc = f"{r['self_citation_rate']:.2f}" if r["self_citation_rate"] is not None else "  n/a"
        title = (r["top_papers"][0]["title"] or "")[:56] if r["top_papers"] else ""
        print(
            f"{r['papers']:>7} {r['year_range'][0]}-{r['year_range'][1]:>4} "
            f"{sc:>9} {r['independent_groups']:>7} {r['last_author_entropy']:>6.2f}  {title}"
        )
    print(f"\nwrote {GRAPH_DIR / 'bundles.json'}")


if __name__ == "__main__":
    main()
