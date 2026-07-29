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


def layout_spectral(
    nodes: list[dict], edges: np.ndarray, iters: int
) -> tuple[np.ndarray, int]:
    """引用グラフの 1 次元スペクトル埋め込み(Fiedler ベクトル)を cross axis にする。

    barycenter + 年内順位正規化には致命的な欠点がある: まとまったコミュニティでも、
    その年の論文数に応じて画面いっぱいに引き伸ばされる。結果、同じ流れが年をまたいで
    同じ帯に留まらず、幹だけを描いてもジグザグにしか見えない(2026-07-29 実測)。

    ここでは年ごとの正規化をやめ、**グラフ構造だけ**から y を決める:
        y <- (隣接ノードの y の平均) を繰り返し、毎回 平均0・分散1 に正規化
    平均を引くのは自明な固有ベクトル(全ノード同値)を落とすため。これは正規化隣接行列の
    べき乗法で、密に引用し合う集団が同じ y に集まる。

    孤立ノード(コーパス内に引用リンクを持たない)は構造の情報がないので中央に置く。
    """
    n = len(nodes)
    src, dst = edges[:, 0].astype(np.int64), edges[:, 1].astype(np.int64)
    both_from = np.concatenate([src, dst])
    both_to = np.concatenate([dst, src])
    deg = np.bincount(both_from, minlength=n)
    connected = deg > 0

    rng = np.random.default_rng(20260729)  # 決定的であること(docs/scope.md の要求)
    y = rng.standard_normal(n)
    y[~connected] = 0.0
    y -= y[connected].mean()
    y /= y[connected].std() or 1.0

    for _ in range(iters):
        sums = np.bincount(both_from, weights=y[both_to], minlength=n)
        nxt = np.divide(sums, deg, out=np.zeros(n), where=connected)
        m = nxt[connected].mean()
        nxt[connected] -= m
        s = nxt[connected].std()
        if s < 1e-12:
            break  # 潰れたら打ち切る(これ以上回しても情報が増えない)
        nxt[connected] /= s
        y = nxt

    # 表示用に全体で順位変換して [0,1] に均す。順位変換は単調なので順序は保たれ、
    # 年ごとではなく**全体で1回だけ**なので帯は保たれる。
    out = np.full(n, 0.5, dtype=np.float32)
    idx = np.flatnonzero(connected)
    order = idx[np.argsort(y[idx], kind="stable")]
    out[order] = np.linspace(0.0, 1.0, len(order), dtype=np.float32)
    return out, int((~connected).sum())


def _spectral_1d(n: int, src: np.ndarray, dst: np.ndarray, iters: int, seed: int) -> np.ndarray:
    """無向グラフの 1 次元スペクトル埋め込み(平均0・分散1)。孤立ノードは 0。"""
    both_from = np.concatenate([src, dst])
    both_to = np.concatenate([dst, src])
    deg = np.bincount(both_from, minlength=n)
    connected = deg > 0
    if connected.sum() < 2:
        return np.zeros(n)

    rng = np.random.default_rng(seed)
    y = rng.standard_normal(n)
    y[~connected] = 0.0
    y[connected] -= y[connected].mean()
    y[connected] /= y[connected].std() or 1.0

    for _ in range(iters):
        sums = np.bincount(both_from, weights=y[both_to], minlength=n)
        nxt = np.divide(sums, deg, out=np.zeros(n), where=connected)
        nxt[connected] -= nxt[connected].mean()
        s = nxt[connected].std()
        if s < 1e-12:
            break
        nxt[connected] /= s
        y = nxt
    return y


def layout_community(
    nodes: list[dict], edges: np.ndarray, iters: int, resolution: float, min_size: int
) -> tuple[np.ndarray, dict]:
    """コミュニティを検出し、論文数に比例した「帯」に割り当てる。

    スペクトル1軸(Fiedler ベクトル)だけでは足りなかった(2026-07-29 実測): 1本の軸は
    本質的に1回の分割しか表現できず、20〜数十あるトピック集団を分離できない。
    順位変換で全体を [0,1] に均すと、集中していた集団まで引き伸ばされてしまう。

    ここでは:
      1. 無向化した引用グラフに Louvain をかけてコミュニティを取る
      2. コミュニティ間の引用量でコミュニティ同士を並べる(小さいグラフのスペクトル順序)
         → 関係の強い集団が隣り合う
      3. 各コミュニティに**論文数に比例した幅の帯**を与える
         → 集団は引き伸ばされず、年をまたいでも同じ帯に留まる
      4. 帯の中はコミュニティ内スペクトル順で並べる(内部構造を残す)

    コーパス内に引用リンクを持たない孤立ノードは、最下部に専用の帯を作ってまとめる
    (中央に置くと横一直線の偽の「流れ」に見えてしまうため)。
    """
    import networkx as nx

    n = len(nodes)
    src, dst = edges[:, 0].astype(np.int64), edges[:, 1].astype(np.int64)

    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from(zip(src.tolist(), dst.tolist()))

    print("  Louvain 実行中…", flush=True)
    communities = nx.community.louvain_communities(g, resolution=resolution, seed=20260729)
    # 孤立ノードは Louvain 上は単独コミュニティになるので、まとめて別扱いにする
    deg = np.bincount(np.concatenate([src, dst]), minlength=n)
    isolated = np.flatnonzero(deg == 0)
    iso_set = set(isolated.tolist())
    comms = [sorted(c - iso_set) for c in communities]
    comms = [c for c in comms if c]
    comms.sort(key=len, reverse=True)
    found = len(comms)

    # 小さすぎるコミュニティは1本の「その他」帯にまとめる。
    # そのまま帯にすると、数十個の極細帯が密集して境界線だけが白い横線に見えてしまう。
    small = [c for c in comms if len(c) < min_size]
    comms = [c for c in comms if len(c) >= min_size]
    if small:
        comms.append(sorted(v for c in small for v in c))
    print(
        f"  コミュニティ数: {found} → 帯 {len(comms)} 本"
        f"(最大 {len(comms[0])} 本 / {min_size} 本未満は「その他」に統合)"
        f" / 孤立 {len(isolated):,} 本"
    )

    comm_of = np.full(n, -1, dtype=np.int64)
    for ci, members in enumerate(comms):
        comm_of[members] = ci

    # --- コミュニティ間グラフを作り、関係の強いものが隣り合う 1 次元順序を出す ---
    k = len(comms)
    cs, cd = comm_of[src], comm_of[dst]
    ok = (cs >= 0) & (cd >= 0) & (cs != cd)
    inter = np.zeros((k, k))
    np.add.at(inter, (cs[ok], cd[ok]), 1.0)
    inter += inter.T
    if k > 2:
        # 小さい行列なので固有分解で厳密に解く(第2固有ベクトル = Fiedler)
        d = inter.sum(axis=1)
        d[d == 0] = 1.0
        lap = np.diag(d) - inter
        vals, vecs = np.linalg.eigh(lap / np.sqrt(np.outer(d, d)))
        comm_order = np.argsort(vecs[:, 1])
    else:
        comm_order = np.arange(k)

    # --- 論文数に比例した帯を割り当てる ---
    y = np.zeros(n, dtype=np.float32)
    total = sum(len(c) for c in comms) + len(isolated)
    cursor = 0.0
    bands = []
    for ci in comm_order:
        members = np.array(comms[ci], dtype=np.int64)
        width = len(members) / total
        # 帯の中はコミュニティ内スペクトル順(内部構造を残す)
        mask = np.isin(src, members) & np.isin(dst, members)
        local = {g: i for i, g in enumerate(members)}
        ls = np.array([local[v] for v in src[mask]], dtype=np.int64)
        ld = np.array([local[v] for v in dst[mask]], dtype=np.int64)
        sub = _spectral_1d(len(members), ls, ld, iters, seed=20260729 + ci)
        order = np.argsort(sub, kind="stable")
        pos = np.empty(len(members), dtype=np.float32)
        pos[order] = np.linspace(0.0, 1.0, len(members), dtype=np.float32)
        y[members] = cursor + pos * width
        bands.append({"community": int(ci), "papers": len(members),
                      "y0": round(cursor, 5), "y1": round(cursor + width, 5)})
        cursor += width

    if len(isolated):
        width = len(isolated) / total
        y[isolated] = cursor + np.linspace(0.0, 1.0, len(isolated), dtype=np.float32) * width
        bands.append({"community": None, "papers": int(len(isolated)),
                      "y0": round(cursor, 5), "y1": round(cursor + width, 5),
                      "note": "コーパス内に引用リンクなし"})

    return y, {"bands": bands, "community_of": comm_of.tolist()}


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
    ap.add_argument(
        "--mode", choices=["index", "barycenter", "spectral", "community"], default="community"
    )
    ap.add_argument("--sweeps", type=int, default=40, help="barycenter の反復回数")
    ap.add_argument("--iters", type=int, default=100, help="spectral のべき乗法反復回数")
    ap.add_argument(
        "--resolution", type=float, default=1.0,
        help="Louvain の解像度。大きいほど細かいコミュニティに割れる",
    )
    ap.add_argument(
        "--min-community", type=int, default=400,
        help="この本数未満のコミュニティは「その他」帯に統合する",
    )
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

    extra: dict = {}
    if args.mode == "index":
        y = layout_index(nodes, years)
    elif args.mode == "barycenter":
        y = layout_barycenter(nodes, years, edges, args.sweeps)
        print(f"  barycenter sweeps: {args.sweeps}")
    elif args.mode == "spectral":
        y, isolated = layout_spectral(nodes, edges, args.iters)
        print(f"  spectral iters: {args.iters}")
        print(f"  孤立ノード(コーパス内リンクなし、中央に配置): {isolated:,}")
    else:
        y, extra = layout_community(nodes, edges, args.iters, args.resolution, args.min_community)
        # 帯が意味のある集団になっているか、代表論文で目視確認できるようにする
        comm_of = extra["community_of"]
        for band in extra["bands"]:
            ci = band["community"]
            if ci is None:
                band["label_hint"] = ["(コーパス内に引用リンクなし)"]
                continue
            members = [i for i, c in enumerate(comm_of) if c == ci]
            top = sorted(members, key=lambda i: -(nodes[i].get("cited_by_count") or 0))[:6]
            band["years"] = [
                min(nodes[i]["year"] for i in members),
                max(nodes[i]["year"] for i in members),
            ]
            band["label_hint"] = [nodes[i]["title"] for i in top]

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
        "bands": extra.get("bands"),
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

    if extra.get("bands"):
        print("\n--- 帯(上から順、幅は論文数に比例)---")
        for band in extra["bands"]:
            if band["papers"] < 200:
                continue
            yrs = band.get("years")
            head = "  ".join((band.get("label_hint") or [])[:3])
            print(
                f"  y={band['y0']:.3f}-{band['y1']:.3f} {band['papers']:>5}本 "
                f"{yrs[0] if yrs else '-'}-{yrs[1] if yrs else '-'}  {head[:150]}"
            )

    sizes = {p.name: p.stat().st_size for p in sorted(OUT_DIR.iterdir())}
    print("\nwrote " + str(OUT_DIR))
    for name, size in sizes.items():
        print(f"  {name:12s} {size/1e6:8.1f} MB")


if __name__ == "__main__":
    main()
