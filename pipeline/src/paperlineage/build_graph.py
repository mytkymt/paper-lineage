"""Step 3: OpenAlex の生データからコーパス内引用 DAG を組む。

やること:
  1. works.jsonl を読み、コーパス内 OpenAlex ID の集合を作る
  2. 参照リストをコーパス内に閉じる(外部への参照は落とす)
  3. **サイクルを潰して厳密な DAG にする** ← ここを雑にやると SPC が全部壊れる

サイクルの原因(実データで実際に起きる):
  - 同年の相互引用(同じ会議のセッション内で互いに引用)
  - preprint と本刊で出版年がずれ、時間が逆行して見える
  - OpenAlex 側のデータ誤り

対処: 全ノードに (year, id) の**全順序**を与え、この順序に逆行するエッジを落とす。
順序が全順序なので結果は必ず DAG になり、かつ決定的。落とした本数は必ず報告する
(黙って捨てると「全部見た」と誤読されるため)。

出力: data/graph/nodes.jsonl, data/graph/edges.tsv, data/graph/stats.json

  uv run python -m paperlineage.build_graph              # コア13会場のみ
  uv run python -m paperlineage.build_graph --extended   # + 拡張venue(引用結合フィルタ)
                                                         #   -> data/graph-ext/

拡張モード: EXTRA_VENUES の論文は「コアと引用リンク≥1本」のものだけ残す
(引用結合フィルタ)。この地図は繋がっているものを描く道具なので、収録基準も
同じ論理に揃える。落とした本数は venue ごとに必ず報告する。
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from .venues import CORE_KEYS, EXTRA_KEYS, VENUES_BY_KEY

ROOT = Path(__file__).resolve().parents[3]
WORKS_PATH = ROOT / "data" / "openalex" / "works.jsonl"

# 出版年がこの範囲外のものは捨てる(明らかなデータ誤り除け)
MIN_YEAR = 1960
MAX_YEAR = 2027


def load_works() -> dict[str, dict]:
    works: dict[str, dict] = {}
    dropped_no_year = 0
    for line in WORKS_PATH.open():
        w = json.loads(line)
        wid = w.get("id")
        year = w.get("year")
        if not wid:
            continue
        if not isinstance(year, int) or not (MIN_YEAR <= year <= MAX_YEAR):
            dropped_no_year += 1
            continue
        # 同じ work が複数回書かれている可能性(再実行など)。後勝ちで上書き。
        works[wid] = w
    if dropped_no_year:
        print(f"  年が無い/範囲外で除外: {dropped_no_year}")
    return works


def load_author_merge() -> dict[str, str]:
    """著者 ID の統合マップ(authors.py の出力)。同名かつ同一 ORCID の
    OpenAlex 著者 ID を1つに寄せる。無ければ空 = 統合なし。

    (実測メモ: S2 著者 ID への切り替えも試したが、主要研究者の分裂が
    OpenAlex より多く逆効果だったため、OpenAlex ID + ORCID 統合を採る。)
    """
    merge_path = ROOT / "data" / "graph" / "author_merge.json"
    return json.loads(merge_path.read_text()) if merge_path.exists() else {}


def main() -> None:
    extended = "--extended" in sys.argv
    out_dir = ROOT / "data" / ("graph-ext" if extended else "graph")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"reading {WORKS_PATH}  (mode: {'extended' if extended else 'core'})")
    works = load_works()
    # コアビルドは拡張 venue の論文を最初から除外する。works.jsonl に拡張分が
    # 追記されていても、コアの出力は拡張導入前とバイト単位で一致し続ける。
    allowed = CORE_KEYS | EXTRA_KEYS if extended else CORE_KEYS
    works = {wid: w for wid, w in works.items() if w.get("venue_key") in allowed}
    print(f"  corpus nodes: {len(works)}")

    # (year, id) の全順序。この順序に沿う向きのエッジだけを残せば必ず DAG。
    order = {wid: (w["year"], wid) for wid, w in works.items()}

    n_raw_refs = 0
    n_external = 0
    n_backward = 0  # 時間逆行(引用先のほうが新しい)
    n_same_year_dropped = 0
    n_self = 0
    edges: list[tuple[str, str]] = []  # (cited=古い, citing=新しい) = 知識の流れの向き

    for citing, w in works.items():
        for cited in w.get("refs") or []:
            n_raw_refs += 1
            if cited not in works:
                n_external += 1
                continue
            if cited == citing:
                n_self += 1
                continue
            if order[cited] < order[citing]:
                # 正順: cited のほうが古い(または同年で id が小さい)
                edges.append((cited, citing))
            else:
                if works[cited]["year"] == works[citing]["year"]:
                    n_same_year_dropped += 1
                else:
                    n_backward += 1

    # 重複エッジの除去(同じ work が二重に参照を持つケース)
    before = len(edges)
    edges = sorted(set(edges))
    n_dup = before - len(edges)

    coupling_report: dict[str, dict[str, int]] = {}
    if extended:
        # 引用結合フィルタ: 拡張 venue の論文は、コアと直接引用リンクを持つものだけ
        # 収録する(この地図の描画対象 = 繋がっているもの、と同じ基準)。
        linked: set[str] = set()
        for a, b in edges:
            ka, kb = works[a].get("venue_key"), works[b].get("venue_key")
            if ka in EXTRA_KEYS and kb in CORE_KEYS:
                linked.add(a)
            elif kb in EXTRA_KEYS and ka in CORE_KEYS:
                linked.add(b)
        keep = {wid for wid, w in works.items()
                if w.get("venue_key") in CORE_KEYS or wid in linked}
        for key in sorted(EXTRA_KEYS):
            total = sum(1 for w in works.values() if w.get("venue_key") == key)
            kept = sum(1 for wid in keep if works[wid].get("venue_key") == key)
            coupling_report[key] = {"fetched": total, "kept": kept}
            label = VENUES_BY_KEY[key].label
            print(f"  coupling filter {label:9s}: kept {kept:5d} / {total:5d}")
        dropped_edges = sum(1 for a, b in edges if a not in keep or b not in keep)
        works = {wid: works[wid] for wid in keep}
        edges = [(a, b) for a, b in edges if a in keep and b in keep]
        order = {wid: order[wid] for wid in keep}
        print(f"  edges dropped by coupling filter: {dropped_edges}")

    year_hist = Counter(w["year"] for w in works.values())
    venue_hist = Counter(w.get("venue_key") for w in works.values())

    stats = {
        "nodes": len(works),
        "refs_total": n_raw_refs,
        "refs_external_dropped": n_external,
        "refs_self_dropped": n_self,
        "refs_backward_dropped": n_backward,
        "refs_same_year_dropped": n_same_year_dropped,
        "refs_duplicate_dropped": n_dup,
        "edges_in_dag": len(edges),
        "year_range": [min(year_hist), max(year_hist)],
        "by_venue": dict(venue_hist.most_common()),
        "coupling_filter": coupling_report or None,
        "by_year": dict(sorted(year_hist.items())),
    }

    author_merge = load_author_merge()
    am = lambda a: author_merge.get(a, a)  # noqa: E731
    with (out_dir / "nodes.jsonl").open("w") as f:
        for wid, w in sorted(works.items(), key=lambda kv: order[kv[0]]):
            f.write(
                json.dumps(
                    {
                        "id": wid,
                        "year": w["year"],
                        "title": w.get("title"),
                        "venue_key": w.get("venue_key"),
                        "doi": w.get("doi"),
                        "cited_by_count": w.get("cited_by_count"),
                        # 参照リスト全体の本数(コーパス外を含む)。
                        # 「系譜が空」がデータ欠損ではなくコーパス境界のせいだと
                        # UI 側で示すために持つ。
                        "refs_total": len(w.get("refs") or []),
                        "authors": [am(a["id"]) for a in (w.get("authors") or []) if a.get("id")],
                        "last_author": next(
                            (am(a["id"]) for a in reversed(w.get("authors") or []) if a.get("id")), None
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    with (out_dir / "edges.tsv").open("w") as f:
        for cited, citing in edges:
            f.write(f"{cited}\t{citing}\n")

    (out_dir / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    print(f"  author merge map: {len(author_merge):,} IDs folded")
    print("\n--- graph stats ---")
    print(f"  nodes                 : {stats['nodes']:,}")
    print(f"  edges (in-corpus DAG) : {stats['edges_in_dag']:,}")
    print(f"  refs total            : {stats['refs_total']:,}")
    print(f"    -> external (dropped): {n_external:,}")
    print(f"    -> backward in time  : {n_backward:,}")
    print(f"    -> same-year dropped : {n_same_year_dropped:,}")
    print(f"    -> self / duplicate  : {n_self:,} / {n_dup:,}")
    print(f"  year range            : {stats['year_range']}")
    print(f"\nwrote {out_dir}")


if __name__ == "__main__":
    main()
