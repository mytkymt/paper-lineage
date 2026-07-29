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

  uv run python -m paperlineage.build_graph
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKS_PATH = ROOT / "data" / "openalex" / "works.jsonl"
OUT_DIR = ROOT / "data" / "graph"

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


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"reading {WORKS_PATH}")
    works = load_works()
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
        "by_year": dict(sorted(year_hist.items())),
    }

    with (OUT_DIR / "nodes.jsonl").open("w") as f:
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
                        "authors": [a["id"] for a in (w.get("authors") or []) if a.get("id")],
                        "last_author": next(
                            (a["id"] for a in reversed(w.get("authors") or []) if a.get("id")), None
                        ),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    with (OUT_DIR / "edges.tsv").open("w") as f:
        for cited, citing in edges:
            f.write(f"{cited}\t{citing}\n")

    (OUT_DIR / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2))

    print("\n--- graph stats ---")
    print(f"  nodes                 : {stats['nodes']:,}")
    print(f"  edges (in-corpus DAG) : {stats['edges_in_dag']:,}")
    print(f"  refs total            : {stats['refs_total']:,}")
    print(f"    -> external (dropped): {n_external:,}")
    print(f"    -> backward in time  : {n_backward:,}")
    print(f"    -> same-year dropped : {n_same_year_dropped:,}")
    print(f"    -> self / duplicate  : {n_self:,} / {n_dup:,}")
    print(f"  year range            : {stats['year_range']}")
    print(f"\nwrote {OUT_DIR}")


if __name__ == "__main__":
    main()
