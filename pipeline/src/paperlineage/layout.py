"""Step 6: 時間単調レイアウトの座標を計算する。

時間軸(x)は年で**固定**。自由度は cross axis(y)だけ。ここの決め方で
「流れが見えるか / ただの散布図か」が決まる(docs/algorithms.md)。

実装している mode:
  index      候補D: 年内の並びを ID 順のまま。**比較のためのベースライン。**
             これで既に流れが見えるなら凝ったレイアウトは要らない。
  barycenter 候補A: 年 = 層とみなし、隣接層の接続先の平均位置に寄せる操作を反復
             (Sugiyama 系の交差最小化)。引用の連鎖が縦に揃って帯になることを狙う。

y は**年ごとに [0,1] に正規化**する。1985年は数十本・2024年は数千本と密度が違うので、
絶対間隔にすると古い年が細い線になって流れが読めなくなるため。

出力: data/viz/nodes.bin   (float32 x, y の交互列)
      data/viz/edges.bin   (uint32 のノードインデックス対)
      data/viz/weights.bin (float32、logSPC を 0..1 に正規化)
      data/viz/meta.json   (ノードのタイトル等 + 描画用の定数)

  uv run python -m paperlineage.layout --mode barycenter --sweeps 40
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GRAPH_DIR = ROOT / "data" / "graph"
OUT_DIR = ROOT / "data" / "viz"


def load() -> tuple[list[dict], np.ndarray, np.ndarray]:
    nodes = [json.loads(line) for line in (GRAPH_DIR / "nodes.jsonl").open()]
    idx = {n["id"]: i for i, n in enumerate(nodes)}

    src, dst, w = [], [], []
    for line in (GRAPH_DIR / "spc.tsv").open():
        a, b, ws = line.rstrip("\n").split("\t")
        src.append(idx[a])
        dst.append(idx[b])
        w.append(float(ws))
    edges = np.array([src, dst], dtype=np.uint32).T
    weights = np.array(w, dtype=np.float32)
    return nodes, edges, weights


def layout_index(nodes: list[dict], years: np.ndarray) -> np.ndarray:
    """ベースライン: 年内は元の順序のまま等間隔に置く。"""
    y = np.zeros(len(nodes), dtype=np.float32)
    for year in np.unique(years):
        m = np.flatnonzero(years == year)
        n = len(m)
        y[m] = np.linspace(0.0, 1.0, n) if n > 1 else 0.5
    return y


def layout_barycenter(
    nodes: list[dict], years: np.ndarray, edges: np.ndarray, sweeps: int
) -> np.ndarray:
    """年を層とみなし、隣接層の接続先の平均位置に寄せる操作を反復する。

    各スイープで、層ごとに「隣接ノードの y の平均」を計算し、その順に並べ替えて
    等間隔に置き直す。前向き・後ろ向きを交互に行う。
    """
    n = len(nodes)
    y = layout_index(nodes, years)

    # 隣接リスト(両方向)。numpy の bincount で平均を取るため CSR 風に持つ。
    src, dst = edges[:, 0].astype(np.int64), edges[:, 1].astype(np.int64)
    both_from = np.concatenate([src, dst])
    both_to = np.concatenate([dst, src])

    year_groups = {int(yr): np.flatnonzero(years == yr) for yr in np.unique(years)}
    ordered_years = sorted(year_groups)

    for sweep in range(sweeps):
        # 全ノードの barycenter を一括計算(隣接なしは NaN のまま = 現在位置を維持)
        sums = np.bincount(both_from, weights=y[both_to], minlength=n)
        cnts = np.bincount(both_from, minlength=n)
        bary = np.divide(sums, cnts, out=np.full(n, np.nan), where=cnts > 0)

        seq = ordered_years if sweep % 2 == 0 else ordered_years[::-1]
        for yr in seq:
            m = year_groups[yr]
            if len(m) < 2:
                continue
            key = np.where(np.isnan(bary[m]), y[m], bary[m])
            # 同値のときの順序を決定的にするため、y を第2キーにする
            order = np.lexsort((y[m], key))
            y[m[order]] = np.linspace(0.0, 1.0, len(m), dtype=np.float32)

    return y


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["index", "barycenter"], default="barycenter")
    ap.add_argument("--sweeps", type=int, default=40)
    ap.add_argument(
        "--jitter",
        type=float,
        default=0.35,
        help="年内の x ゆらぎ(年単位)。0 だと各年が1本の縦線に潰れて、"
        "エッジの始点・終点が完全に重なり流れが読みにくくなる。",
    )
    args = ap.parse_args()

    nodes, edges, weights = load()
    years = np.array([n["year"] for n in nodes], dtype=np.int32)
    print(f"nodes={len(nodes):,} edges={len(edges):,} years={years.min()}-{years.max()}")

    if args.mode == "index":
        y = layout_index(nodes, years)
    else:
        y = layout_barycenter(nodes, years, edges, args.sweeps)
        print(f"  barycenter sweeps: {args.sweeps}")

    # x は年そのもの。ビューア側で正規化する。
    # 年内は決定的な擬似乱数で ±jitter/2 だけ散らす(縦線への潰れ防止)。
    x = years.astype(np.float32)
    if args.jitter > 0:
        rng = np.random.default_rng(20260729)  # 決定的であること(docs/scope.md の要求)
        x = x + (rng.random(len(nodes)).astype(np.float32) - 0.5) * args.jitter
    pos = np.empty((len(nodes), 2), dtype=np.float32)
    pos[:, 0] = x
    pos[:, 1] = y

    # 重みは 0..1 に。logSPC は下側に長い裾を持つので、下位はまとめて 0 に潰す。
    lo = np.percentile(weights, 50.0)
    hi = weights.max()
    wnorm = np.clip((weights - lo) / max(hi - lo, 1e-9), 0.0, 1.0).astype(np.float32)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pos.tofile(OUT_DIR / "nodes.bin")
    edges.astype(np.uint32).tofile(OUT_DIR / "edges.bin")
    wnorm.tofile(OUT_DIR / "weights.bin")

    meta = {
        "mode": args.mode,
        "jitter": args.jitter,
        "node_count": len(nodes),
        "edge_count": int(len(edges)),
        "year_min": int(years.min()),
        "year_max": int(years.max()),
        "nodes": [
            {
                "y": n["year"],
                "v": n.get("venue_key"),
                "c": n.get("cited_by_count") or 0,
                "t": n.get("title") or "",
                "d": n.get("doi"),
            }
            for n in nodes
        ],
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))

    sizes = {p.name: p.stat().st_size for p in sorted(OUT_DIR.iterdir())}
    print("\nwrote " + str(OUT_DIR))
    for name, size in sizes.items():
        print(f"  {name:12s} {size/1e6:8.1f} MB")


if __name__ == "__main__":
    main()
