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
import os
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
# PL_DATASET=ext で拡張グラフを読み、data/viz-ext に出力する
_EXT = os.environ.get("PL_DATASET") == "ext"
GRAPH_DIR = ROOT / "data" / ("graph-ext" if _EXT else "graph")
OUT_DIR = ROOT / "data" / ("viz-ext" if _EXT else "viz")


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


def attribution(nodes: list[dict], edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """「その線を誰が作ったか」をエッジ単位・ノード単位で出す。

    色分けの方針(2026-07-29 決定): 位置(時間軸 + 帯)が「いつ・どのトレンドか」を
    既に表しているので、色は位置が表現していない情報に使う。→ **帰属**。

    エッジを3段階に分ける。「著者が1人でも重なれば同じラボ」は粗すぎるため:
      0 = 独立      著者の重なりなし
      1 = 著者重複  著者が重なるが、ラストオーサーは別
                    (指導教員が変わった / 共同研究 / 大規模著者リストの偶然の重なり)
      2 = 同一ラボ  **ラストオーサーが同じ**。HCI は last author = PI の慣行が強いので、
                    これが「1ラボの系譜」に一番近い信号。

    ノード側は、そのノードが引用している側のエッジについて、
    段階2の割合(same_lab)と段階1以上の割合(any_overlap)を別々に持つ。

    著者情報が無いノードに接するエッジは判定不能として 0 に倒す(自己引用を過大評価しない)。
    """
    author_sets = [set(n.get("authors") or []) for n in nodes]
    last_authors = [n.get("last_author") for n in nodes]
    src, dst = edges[:, 0].astype(np.int64), edges[:, 1].astype(np.int64)

    level = np.zeros(len(edges), dtype=np.uint8)
    for e in range(len(edges)):
        u, v = src[e], dst[e]
        au, av = author_sets[u], author_sets[v]
        if not au or not av or au.isdisjoint(av):
            continue
        lu, lv = last_authors[u], last_authors[v]
        level[e] = 2 if (lu is not None and lu == lv) else 1

    n = len(nodes)
    total = np.bincount(dst, minlength=n).astype(np.float64)
    same_lab = np.bincount(dst, weights=(level == 2).astype(np.float64), minlength=n)
    overlap = np.bincount(dst, weights=(level >= 1).astype(np.float64), minlength=n)
    out = np.zeros((n, 2), dtype=np.float32)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[:, 0] = np.divide(same_lab, total, out=np.zeros(n), where=total > 0)
        out[:, 1] = np.divide(overlap, total, out=np.zeros(n), where=total > 0)

    counts = np.bincount(level, minlength=3)
    print(
        f"  帰属: 独立 {counts[0]:,} / 著者重複 {counts[1]:,} / 同一ラストオーサー {counts[2]:,}"
        f"(全 {len(edges):,} エッジ)"
    )
    return level, out


# カテゴリカル配色は 8 スロットまで(dataviz: 9個目は生成せず「その他」に畳む)。
LAB_SLOTS = 8
NO_LAB = 0xFFFFFFFF   # ラボ線ではないエッジ / ノード


def lab_lines(
    nodes: list[dict], edges: np.ndarray, level: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """ラボ(= ラストオーサー)ごとの系譜を取り出す。

    ラボの定義は level 2、つまり**引用元と引用先のラストオーサーが同じ**エッジ。
    その本数が多いラストオーサーほど「長い自分の系譜」を持っている。

    色スロットの割当はここではやらない(**どのラボに色を付けるかはビューア側で
    選べるようにした**ため)。ここで出すのは「どのラボのエッジか」という ID だけ。

    戻り値: (エッジのラボ ID, ノードのラボ ID, ラボ一覧)
            ID は labs のインデックス、NO_LAB = ラボ線ではない
    """
    last_authors = [n.get("last_author") for n in nodes]
    src, dst = edges[:, 0].astype(np.int64), edges[:, 1].astype(np.int64)
    lab_mask = np.flatnonzero(level == 2)

    lab_edges: dict[str, int] = {}
    for e in lab_mask:
        a = last_authors[dst[e]]
        if a:
            lab_edges[a] = lab_edges.get(a, 0) + 1
    ranked = sorted(lab_edges.items(), key=lambda kv: (-kv[1], kv[0]))
    id_of = {a: i for i, (a, _) in enumerate(ranked)}

    edge_lab = np.full(len(edges), NO_LAB, dtype=np.uint32)
    on_lab = np.zeros(len(nodes), dtype=bool)
    for e in lab_mask:
        a = last_authors[dst[e]]
        if a:
            edge_lab[e] = id_of[a]
        on_lab[src[e]] = True
        on_lab[dst[e]] = True

    node_lab = np.full(len(nodes), NO_LAB, dtype=np.uint32)
    for i, a in enumerate(last_authors):
        if a and on_lab[i] and a in id_of:
            node_lab[i] = id_of[a]

    names = _author_names()
    papers_of: dict[str, list[int]] = defaultdict(list)
    for i, a in enumerate(last_authors):
        if a and on_lab[i]:
            papers_of[a].append(i)

    labs = []
    lab_author_ids = []
    for a, cnt in ranked:
        lab_author_ids.append(a)
        ps = papers_of.get(a) or []
        labs.append({
            "name": names.get(a, a),
            "edges": cnt,
            "papers": len(ps),
            "years": [min(nodes[i]["year"] for i in ps), max(nodes[i]["year"] for i in ps)]
            if ps else None,
        })

    print(f"  ラボ線: {len(ranked):,} ラボ(色を付けるラボはビューア側で選択)")
    for lab in labs[:8]:
        yr = f"{lab['years'][0]}-{lab['years'][1]}" if lab["years"] else "-"
        print(f"    {lab['edges']:>4} 本  {yr}  {lab['name']}")
    return edge_lab, node_lab, labs, lab_author_ids


def author_table(nodes: list[dict]) -> tuple[list[str], list[list[int]]]:
    """著者名テーブルと、ノードごとの著者インデックス列。

    名前を各ノードに直接持つと meta.json が数 MB 膨らむので、共有テーブルへの
    インデックスにする。順序は元のまま(最後の要素がラストオーサー)。
    """
    names = _author_names()
    table: list[str] = []
    index: dict[str, int] = {}
    author_table.index = index  # ラボ側から著者インデックスを引くため
    per_node: list[list[int]] = []
    for n in nodes:
        row = []
        for aid in n.get("authors") or []:
            if aid not in index:
                index[aid] = len(table)
                table.append(names.get(aid, aid))
            row.append(index[aid])
        per_node.append(row)
    print(f"  著者: {len(table):,} 人")
    return table, per_node


def related_terms(nodes: list[dict], vocab_size: int = 2000, k: int = 8) -> dict[str, list[str]]:
    """タイトルの共起から関連語を出す。

    「haptic で引いたら vibrotactile も拾いたい」への、API を使わない版。
    埋め込みではなく共起 PMI なので**意味的な類似ではなく「同じ文脈で使われる語」**。
    検索欄の候補として出し、クリックで語を足す用途。
    """
    import re
    from collections import Counter

    docs: list[list[int]] = []
    df: Counter[str] = Counter()
    tokenized = []
    for n in nodes:
        ws = {
            w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", (n.get("title") or "").lower())
            if w not in _STOP
        }
        tokenized.append(ws)
        df.update(ws)

    vocab = [w for w, c in df.most_common(vocab_size) if c >= 8]
    vid = {w: i for i, w in enumerate(vocab)}
    V, N = len(vocab), len(nodes)
    for ws in tokenized:
        docs.append(sorted(vid[w] for w in ws if w in vid))

    co = np.zeros((V, V), dtype=np.int32)
    for ids in docs:
        for a in range(len(ids)):
            ia = ids[a]
            for b in range(a + 1, len(ids)):
                co[ia, ids[b]] += 1
    co += co.T

    counts = np.array([df[w] for w in vocab], dtype=np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log((co * N) / np.outer(counts, counts))
    pmi[~np.isfinite(pmi)] = -1e9
    np.fill_diagonal(pmi, -1e9)
    pmi[co < 5] = -1e9   # 共起が少なすぎるペアはノイズなので捨てる

    out: dict[str, list[str]] = {}
    for i, w in enumerate(vocab):
        top = np.argsort(pmi[i])[::-1][:k]
        rel = [vocab[j] for j in top if pmi[i, j] > -1e8]
        if rel:
            out[w] = rel
    print(f"  関連語: {len(out):,} 語(語彙 {V:,}、共起 PMI)")
    return out


def _author_names() -> dict[str, str]:
    """著者 ID → 表示名。S2(corpus)と OpenAlex(works)の両方から拾う。

    nodes.jsonl の著者 ID は S2 優先・OpenAlex フォールバックなので、
    名前テーブルも両方を持つ(ID の名前空間は数値 vs 'A…' で衝突しない)。
    """
    names: dict[str, str] = {}
    for path in sorted((ROOT / "data" / "corpus").glob("*.jsonl")):
        for line in path.open():
            for a in (json.loads(line).get("authors") or []):
                if a.get("authorId") and a.get("name"):
                    names.setdefault(a["authorId"], a["name"])
    works = ROOT / "data" / "openalex" / "works.jsonl"
    if works.exists():
        for line in works.open():
            for a in (json.loads(line).get("authors") or []):
                if a.get("id") and a.get("name"):
                    names.setdefault(a["id"], a["name"])
    return names


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
    nodes: list[dict], edges: np.ndarray, iters: int, resolution: float,
    min_size: int, sub_min_size: int,
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

    # --- 論文数に比例した帯を割り当てる(帯の中はさらにサブ帯に割る)---
    y = np.zeros(n, dtype=np.float32)
    sub_of = np.full(n, -1, dtype=np.int64)
    total = sum(len(c) for c in comms) + len(isolated)
    cursor = 0.0
    bands: list[dict] = []
    subbands: list[dict] = []

    for ci in comm_order:
        members = np.array(comms[ci], dtype=np.int64)
        width = len(members) / total
        # コミュニティ内の部分グラフ
        mask = np.isin(src, members) & np.isin(dst, members)
        local = {g: i for i, g in enumerate(members)}
        ls = np.array([local[v] for v in src[mask]], dtype=np.int64)
        ld = np.array([local[v] for v in dst[mask]], dtype=np.int64)

        # 帯の中をさらに Louvain で割ってサブ分野にする。
        # 大きなトレンドの内訳(例: インタラクション技術 → タッチ / ジェスチャ / センシング)
        # を、時間軸を保ったまま見られるようにするため。
        subs = _split_subcommunities(len(members), ls, ld, sub_min_size, resolution)
        band_sub_ids: list[int] = []
        inner = 0.0
        for si, sub_members_local in enumerate(subs):
            sm = np.array(sub_members_local, dtype=np.int64)
            sub_width = len(sm) / len(members)
            # サブ帯の中はスペクトル順(内部構造を残す)
            smask = np.isin(ls, sm) & np.isin(ld, sm)
            slocal = {g: i for i, g in enumerate(sm)}
            spec = _spectral_1d(
                len(sm),
                np.array([slocal[v] for v in ls[smask]], dtype=np.int64),
                np.array([slocal[v] for v in ld[smask]], dtype=np.int64),
                iters,
                seed=20260729 + ci * 1000 + si,
            )
            order = np.argsort(spec, kind="stable")
            pos = np.empty(len(sm), dtype=np.float32)
            pos[order] = np.linspace(0.0, 1.0, len(sm), dtype=np.float32)

            gm = members[sm]  # グローバル index に戻す
            y0 = cursor + inner * width
            y[gm] = y0 + pos * (sub_width * width)
            sub_of[gm] = len(subbands)
            band_sub_ids.append(len(subbands))
            subbands.append({
                "band": len(bands),
                "papers": int(len(sm)),
                "y0": round(y0, 6),
                "y1": round(y0 + sub_width * width, 6),
            })
            inner += sub_width

        bands.append({"community": int(ci), "papers": len(members),
                      "y0": round(cursor, 5), "y1": round(cursor + width, 5),
                      "subbands": band_sub_ids})
        cursor += width

    if len(isolated):
        width = len(isolated) / total
        y[isolated] = cursor + np.linspace(0.0, 1.0, len(isolated), dtype=np.float32) * width
        bands.append({"community": None, "papers": int(len(isolated)),
                      "y0": round(cursor, 5), "y1": round(cursor + width, 5),
                      "subbands": [],
                      "note": "no in-corpus citation links"})

    print(f"  サブ帯: {len(subbands)} 本({sub_min_size} 本未満は帯内「その他」に統合)")
    return y, {
        "bands": bands,
        "subbands": subbands,
        "community_of": comm_of.tolist(),
        "subcommunity_of": sub_of.tolist(),
    }


_STOP = {
    "the", "a", "an", "of", "for", "and", "in", "on", "to", "with", "by", "from",
    "is", "are", "as", "at", "that", "this", "it", "its", "their", "into", "via",
    "using", "use", "used", "toward", "towards", "through", "between", "over",
    "study", "studies", "design", "designing", "system", "systems", "user", "users",
    "interaction", "interactive", "interface", "interfaces", "understanding",
    "exploring", "supporting", "how", "what", "why", "when", "we", "our", "you",
    "case", "based", "new", "novel", "towards", "human", "computing", "computer",
    "proceedings", "conference", "chi", "acm", "sigchi", "extended", "abstracts",
}


def _keywords(titles: list[str], global_df: dict[str, int], n_docs: int, k: int = 5) -> list[str]:
    """タイトル群を代表するキーワードを TF-IDF 風のスコアで選ぶ。

    帯のラベルに代表論文タイトル1本を出すと「Tangible bits」のような固有名詞になり、
    帯全体が何なのか分からない。語レベルに落として、その帯に偏っている語を出す。
    LLM 命名(F3)までのつなぎ。
    """
    import math
    import re

    tf: dict[str, int] = {}
    for t in titles:
        seen = set()
        for w in re.findall(r"[a-z][a-z0-9\-]{2,}", (t or "").lower()):
            if w in _STOP or w in seen:
                continue
            seen.add(w)
            tf[w] = tf.get(w, 0) + 1

    scored = [
        (c * math.log(n_docs / (1 + global_df.get(w, 0))), w)
        for w, c in tf.items()
        if c >= max(2, len(titles) // 100)
    ]
    scored.sort(reverse=True)
    return [w for _, w in scored[:k]]


def _global_df(nodes: list[dict]) -> tuple[dict[str, int], int]:
    """語ごとの文書頻度(何本のタイトルに出るか)。"""
    import re

    df: dict[str, int] = {}
    for nd in nodes:
        for w in set(re.findall(r"[a-z][a-z0-9\-]{2,}", (nd.get("title") or "").lower())):
            df[w] = df.get(w, 0) + 1
    return df, len(nodes)


def _split_subcommunities(
    n: int, src: np.ndarray, dst: np.ndarray, min_size: int, resolution: float
) -> list[list[int]]:
    """コミュニティ内部をさらに分割する。小さすぎるものは「その他」に統合。

    分割できない(小さい / エッジが無い)場合は 1 個のサブ帯として返す。
    """
    import networkx as nx

    if n < min_size * 2 or len(src) == 0:
        return [list(range(n))]

    g = nx.Graph()
    g.add_nodes_from(range(n))
    g.add_edges_from(zip(src.tolist(), dst.tolist()))
    parts = [sorted(c) for c in nx.community.louvain_communities(
        g, resolution=resolution, seed=20260729)]
    parts.sort(key=len, reverse=True)

    big = [p for p in parts if len(p) >= min_size]
    small = [v for p in parts if len(p) < min_size for v in p]
    if not big:
        return [list(range(n))]
    if small:
        big.append(sorted(small))
    return big


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
        "--min-subcommunity", type=int, default=120,
        help="この本数未満のサブコミュニティは帯内の「その他」サブ帯に統合する",
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
        y, extra = layout_community(
            nodes, edges, args.iters, args.resolution,
            args.min_community, args.min_subcommunity,
        )
        # 帯 / サブ帯が意味のある集団になっているか、キーワードと代表論文で確認できるようにする
        df, n_docs = _global_df(nodes)

        def describe(target: dict, members: list[int]) -> None:
            if not members:
                return
            target["years"] = [
                min(nodes[i]["year"] for i in members),
                max(nodes[i]["year"] for i in members),
            ]
            target["keywords"] = _keywords([nodes[i].get("title") or "" for i in members], df, n_docs)
            top = sorted(members, key=lambda i: -(nodes[i].get("cited_by_count") or 0))[:6]
            target["top_papers"] = [nodes[i]["title"] for i in top]

        by_band: dict[int, list[int]] = defaultdict(list)
        by_sub: dict[int, list[int]] = defaultdict(list)
        for i, (c, s) in enumerate(zip(extra["community_of"], extra["subcommunity_of"])):
            if c >= 0:
                by_band[c].append(i)
            if s >= 0:
                by_sub[s].append(i)

        for bi, band in enumerate(extra["bands"]):
            ci = band["community"]
            if ci is None:
                band["keywords"] = ["(no in-corpus citation links)"]
                band["top_papers"] = []
                continue
            describe(band, by_band[ci])
        for si, sub in enumerate(extra["subbands"]):
            describe(sub, by_sub[si])

    # x は年そのもの。ビューア側で正規化する。
    # 年内は乱数ではなく venue 順に並べる(縦線への潰れ防止 + 学会ごとに束になる)。
    # venue の順序は venues.py の定義順で全年共通 — CHI は常に年の左端、のように
    # 年をまたいで一貫し、完全に決定的。
    x = years.astype(np.float32)
    if args.jitter > 0:
        from .venues import EXTRA_VENUES, VENUES
        vrank = {v.key: i for i, v in enumerate([*VENUES, *EXTRA_VENUES])}
        vk = np.array([vrank.get(n.get("venue_key"), len(vrank)) for n in nodes], dtype=np.int64)
        for yr in np.unique(years):
            m = np.flatnonzero(years == yr)
            if len(m) < 2:
                continue
            order = m[np.lexsort((m, vk[m]))]   # venue 順 → 元順で安定
            x[order] += (np.linspace(0.0, 1.0, len(order), dtype=np.float32) - 0.5) * args.jitter
    pos = np.empty((len(nodes), 2), dtype=np.float32)
    pos[:, 0] = x
    pos[:, 1] = y

    # 重みは 0..1 に。logSPC は下側に長い裾を持つので、下位はまとめて 0 に潰す。
    lo = np.percentile(weights, 50.0)
    hi = weights.max()
    wnorm = np.clip((weights - lo) / max(hi - lo, 1e-9), 0.0, 1.0).astype(np.float32)

    level, node_attr = attribution(nodes, edges)
    edge_lab, node_lab, labs, lab_author_ids = lab_lines(nodes, edges, level)
    author_names, node_authors = author_table(nodes)
    # ラボ ↔ 著者テーブルを結ぶ。ビューアは著者を検索して色を付けるので、
    # 名前ではなく著者インデックスで一致させる。
    for lab, aid in zip(labs, lab_author_ids):
        lab["ai"] = author_table.index.get(aid, -1)
    related = related_terms(nodes)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    level.tofile(OUT_DIR / "edge_attr.bin")
    edge_lab.tofile(OUT_DIR / "edge_lab.bin")
    node_lab.tofile(OUT_DIR / "node_lab.bin")
    node_attr.tofile(OUT_DIR / "node_attr.bin")
    pos.tofile(OUT_DIR / "nodes.bin")
    edges.astype(np.uint32).tofile(OUT_DIR / "edges.bin")
    wnorm.tofile(OUT_DIR / "weights.bin")

    meta = {
        "mode": args.mode,
        "jitter": args.jitter,
        "bands": extra.get("bands"),
        "labs": labs,
        "authors": author_names,
        "related": related,
        "subbands": extra.get("subbands"),
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
                "r": n.get("refs_total") or 0,
                "a": au,
                # 帯 / サブ帯の所属。系譜を選んだとき「どのトレンドから来て
                # どのトレンドへ広がったか」を数えるのに使う。
                "s": s,
            }
            for n, s, au in zip(
                nodes,
                extra.get("subcommunity_of") or [-1] * len(nodes),
                node_authors,
            )
        ],
    }
    (OUT_DIR / "meta.json").write_text(json.dumps(meta, ensure_ascii=False))

    if extra.get("bands"):
        print("\n--- 帯(上から順、幅は論文数に比例)---")
        for band in extra["bands"]:
            if band["papers"] < 200:
                continue
            yrs = band.get("years")
            kw = " / ".join(band.get("keywords") or [])
            print(
                f"  y={band['y0']:.3f}-{band['y1']:.3f} {band['papers']:>5}本 "
                f"{yrs[0] if yrs else '-'}-{yrs[1] if yrs else '-'}  {kw}"
            )
            for si in band.get("subbands") or []:
                sub = extra["subbands"][si]
                if sub["papers"] < 150:
                    continue
                print(f"        └ {sub['papers']:>4}本  {' / '.join(sub.get('keywords') or [])}")

    sizes = {p.name: p.stat().st_size for p in sorted(OUT_DIR.iterdir())}
    print("\nwrote " + str(OUT_DIR))
    for name, size in sizes.items():
        print(f"  {name:12s} {size/1e6:8.1f} MB")


if __name__ == "__main__":
    main()
