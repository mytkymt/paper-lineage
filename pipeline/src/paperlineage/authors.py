"""著者の名寄せ: 同名複数の OpenAlex 著者 ID を ORCID で統合する。

背景: OpenAlex は同一人物を複数プロフィールに割ることがある(表記ゆれ・
所属移動など)。同名でも別人は多い(ありふれた名前)ので名前だけでは
統合できないが、**同名かつ同一 ORCID** なら同一人物と断定できる。

S2 著者 ID への切り替えも検討したが、実測では主要研究者の分裂が
OpenAlex より多かった(例: 6 ID vs 2 ID)ため採らない。

手順(2タイア):
  1. works.jsonl の著者から、同名で複数 ID を持つものを列挙
  2. ORCID タイア: OpenAlex /authors API で ORCID をバッチ取得(キャッシュ・再開可)、
     同名 + 同一 ORCID を統合
  3. 共著/所属タイア: 同名 ID 同士が共著者を2人以上共有、または共著者1人+所属を
     共有していれば統合(同名別人が共著者を複数共有することはまず無い)

出力: data/graph/author_merge.json     {重複ID: 正規ID}
      data/graph/author_orcid_oa.jsonl 取得キャッシュ

  uv run python -m paperlineage.authors
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from . import openalex as oa

ROOT = Path(__file__).resolve().parents[3]
WORKS = ROOT / "data" / "openalex" / "works.jsonl"
OUT_DIR = ROOT / "data" / "graph"
CACHE = OUT_DIR / "author_orcid_oa.jsonl"
MERGE = OUT_DIR / "author_merge.json"


def works_authors() -> dict[str, str]:
    """OpenAlex author ID -> 表示名。"""
    names: dict[str, str] = {}
    for line in WORKS.open():
        for a in json.loads(line).get("authors") or []:
            if a.get("id") and a.get("name"):
                names.setdefault(a["id"], a["name"])
    return names


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    names = works_authors()
    print(f"authors (OpenAlex): {len(names):,}")

    by_name: dict[str, list[str]] = defaultdict(list)
    for aid, nm in names.items():
        by_name[" ".join(nm.casefold().split())].append(aid)
    dup_ids = sorted(aid for ids in by_name.values() if len(ids) > 1 for aid in ids)
    dup_names = sum(1 for ids in by_name.values() if len(ids) > 1)
    print(f"names with multiple IDs: {dup_names:,}  (IDs to check: {len(dup_ids):,})")

    orcid: dict[str, str | None] = {}
    if CACHE.exists():
        for line in CACHE.open():
            rec = json.loads(line)
            orcid[rec["id"]] = rec.get("orcid")
    todo = [aid for aid in dup_ids if aid not in orcid]
    print(f"fetching ORCID for {len(todo):,} IDs (cached: {len(orcid):,})")
    with CACHE.open("a") as f:
        for i in range(0, len(todo), oa.OR_LIMIT):
            batch = todo[i : i + oa.OR_LIMIT]
            data = oa.get(
                "/authors",
                params={
                    "filter": "ids.openalex:" + "|".join(batch),
                    "select": "id,orcid",
                    "per-page": oa.OR_LIMIT,
                },
            )
            got = {}
            for rec in data.get("results") or []:
                aid = oa.short_id(rec.get("id"))
                oc = rec.get("orcid")
                got[aid] = oc.rsplit("/", 1)[-1] if oc else None
            for aid in batch:
                orcid[aid] = got.get(aid)
                f.write(json.dumps({"id": aid, "orcid": orcid[aid]}) + "\n")
            f.flush()
            print(f"  {min(i + oa.OR_LIMIT, len(todo))}/{len(todo)}", flush=True)

    merge: dict[str, str] = {}
    groups = 0
    for ids in by_name.values():
        if len(ids) < 2:
            continue
        by_orcid: dict[str, list[str]] = defaultdict(list)
        for aid in ids:
            oc = orcid.get(aid)
            if oc:
                by_orcid[oc].append(aid)
        for same in by_orcid.values():
            if len(same) < 2:
                continue
            canon = min(same)
            groups += 1
            for aid in same:
                if aid != canon:
                    merge[aid] = canon

    print(f"ORCID tier: {groups:,} groups, {len(merge):,} IDs folded")

    # --- 第2タイア: 共著者・所属の重なり(決定的・LLM不要) ---
    # 同名別人が共著者を2人以上共有することはまず無い。所属一致のみは
    # 同名同大学の別人で誤爆し得るので、共著1人+所属一致まで要求する。
    from collections import defaultdict as dd
    coauth: dict[str, set] = dd(set)
    insts: dict[str, set] = dd(set)
    for line in WORKS.open():
        w = json.loads(line)
        aus = [a for a in (w.get("authors") or []) if a.get("id")]
        ids = [a["id"] for a in aus]
        for a in aus:
            coauth[a["id"]].update(i for i in ids if i != a["id"])
            insts[a["id"]].update(a.get("insts") or [])

    def find(parent, x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    tier2_groups = 0
    for ids in by_name.values():
        ids = sorted({merge.get(i, i) for i in ids})
        if len(ids) < 2:
            continue
        parent = {i: i for i in ids}
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a, b = ids[i], ids[j]
                shared = len(coauth[a] & coauth[b])
                if shared >= 2 or (shared >= 1 and insts[a] & insts[b]):
                    parent[find(parent, a)] = find(parent, b)
        comps: dict[str, list[str]] = dd(list)
        for i in ids:
            comps[find(parent, i)].append(i)
        for c in comps.values():
            if len(c) < 2:
                continue
            canon = min(c)
            tier2_groups += 1
            for aid in c:
                if aid != canon:
                    merge[aid] = canon
    # マージの連鎖を平坦化(a->b, b->c を a->c に)
    for k in list(merge):
        v = merge[k]
        while v in merge:
            v = merge[v]
        merge[k] = v

    MERGE.write_text(json.dumps(merge, indent=0, sort_keys=True))
    resolved = sum(
        1 for ids in by_name.values()
        if len(ids) > 1 and len({merge.get(a, a) for a in ids}) < len(ids)
    )
    print(f"co-author/institution tier: {tier2_groups:,} groups")
    print(f"\ntotal: {len(merge):,} IDs folded "
          f"({resolved:,} of {dup_names:,} duplicate names at least partly resolved)")
    print(f"wrote {MERGE}")


if __name__ == "__main__":
    main()
