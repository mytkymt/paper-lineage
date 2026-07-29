"""Step 4: Main Path Analysis (SPC) — 引用 DAG の「太い線」をエッジ重みとして出す。

SPC (Search Path Count, Batagelj 2003):
  全 source(入次数0)から全 sink(出次数0)への全パスを走ったとき、
  各エッジが何回通過されるか。
      SPC(u->v) = f(u) * b(v)
      f(u) = source から u に至るパス数
      b(v) = v から sink に至るパス数

パス数は指数的に爆発し、40k ノード規模では数千桁の整数になる。
そこで **log 空間**で持つ(log は単調なのでエッジのランキングは厳密に保たれる)。
  log SPC(u->v) = log f(u) + log b(v)

(year, id) の全順序でソート済みのノード列 = そのままトポロジカル順序、という
build_graph.py の性質を使うので、別途トポロジカルソートは不要。

出力: data/graph/spc.tsv        (cited, citing, log_spc)
      data/graph/main_path.json (グローバル main path = SPC 合計最大のパス)

  uv run python -m paperlineage.spc
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
GRAPH_DIR = ROOT / "data" / "graph"

NEG_INF = float("-inf")


def logsumexp(values: list[float]) -> float:
    if not values:
        return NEG_INF
    m = max(values)
    if m == NEG_INF:
        return NEG_INF
    return m + math.log(sum(math.exp(v - m) for v in values))


def main() -> None:
    # --- 読み込み(nodes.jsonl はトポロジカル順) ---
    nodes: list[dict] = [json.loads(line) for line in (GRAPH_DIR / "nodes.jsonl").open()]
    idx = {n["id"]: i for i, n in enumerate(nodes)}
    N = len(nodes)

    preds: list[list[int]] = [[] for _ in range(N)]
    succs: list[list[int]] = [[] for _ in range(N)]
    edges: list[tuple[int, int]] = []
    for line in (GRAPH_DIR / "edges.tsv").open():
        a, b = line.rstrip("\n").split("\t")
        u, v = idx[a], idx[b]
        if u >= v:  # トポロジカル順が壊れていたら即座に気づけるようにする
            raise AssertionError(f"edge violates topological order: {a} -> {b}")
        edges.append((u, v))
        succs[u].append(v)
        preds[v].append(u)

    print(f"nodes={N:,} edges={len(edges):,}")

    # --- 前向き: log f ---
    f = [0.0] * N  # 入次数0(source)は log(1)=0
    for v in range(N):
        if preds[v]:
            f[v] = logsumexp([f[u] for u in preds[v]])

    # --- 後ろ向き: log b ---
    b = [0.0] * N  # 出次数0(sink)は log(1)=0
    for v in range(N - 1, -1, -1):
        if succs[v]:
            b[v] = logsumexp([b[w] for w in succs[v]])

    # --- エッジ重み ---
    weights = [f[u] + b[v] for (u, v) in edges]

    with (GRAPH_DIR / "spc.tsv").open("w") as out:
        for (u, v), w in zip(edges, weights):
            out.write(f"{nodes[u]['id']}\t{nodes[v]['id']}\t{w:.6f}\n")

    # --- グローバル main path: SPC 合計が最大のパス(DAG 上の最長経路 DP) ---
    # ノードはトポロジカル順に並んでいるので、v を昇順に見る1パスで済む
    # (v の全 predecessor u は必ず u < v なので、best[u] は確定済み)。
    best = [NEG_INF] * N
    prev: list[int | None] = [None] * N
    for v in range(N):
        if not preds[v]:
            best[v] = 0.0
            continue
        bu, pu = NEG_INF, None
        for u in preds[v]:
            cand = best[u] + f[u] + b[v]
            if cand > bu:
                bu, pu = cand, u
        best[v], prev[v] = bu, pu

    end = max((v for v in range(N) if not succs[v]), key=lambda v: best[v], default=None)
    path: list[int] = []
    cur = end
    while cur is not None:
        path.append(cur)
        cur = prev[cur]
    path.reverse()

    main_path = [
        {
            "id": nodes[i]["id"],
            "year": nodes[i]["year"],
            "venue": nodes[i]["venue_key"],
            "cited_by": nodes[i]["cited_by_count"],
            "title": nodes[i]["title"],
        }
        for i in path
    ]
    (GRAPH_DIR / "main_path.json").write_text(json.dumps(main_path, ensure_ascii=False, indent=2))

    # --- 目視確認用の出力 ---
    print(f"\n=== global main path ({len(main_path)} papers) ===")
    for p in main_path:
        title = (p["title"] or "")[:88]
        print(f"  {p['year']}  {str(p['venue'] or ''):9s} cited={p['cited_by']:>6}  {title}")

    top = sorted(zip(edges, weights), key=lambda ew: -ew[1])[:25]
    print("\n=== top 25 edges by SPC ===")
    for (u, v), w in top:
        print(
            f"  logSPC={w:9.2f}  {nodes[u]['year']} -> {nodes[v]['year']}  "
            f"{(nodes[u]['title'] or '')[:44]!r:46s} -> {(nodes[v]['title'] or '')[:44]!r}"
        )

    print(f"\nwrote {GRAPH_DIR / 'spc.tsv'}, {GRAPH_DIR / 'main_path.json'}")


if __name__ == "__main__":
    main()
