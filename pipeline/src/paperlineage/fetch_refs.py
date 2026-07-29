"""Step 2: コーパスの DOI を OpenAlex に問い合わせ、引用エッジと著者を取る。

S2 のコーパス(data/corpus/*.jsonl)から DOI を集め、OpenAlex に 50 件ずつ
まとめて投げる。取るのは referenced_works(完全な参照リスト)と authorships。

出力: data/openalex/works.jsonl (1行1論文、必要なフィールドだけに削ったもの)
      data/openalex/_done_dois.txt (取得済み DOI。再実行時はスキップ)

  uv run python -m paperlineage.fetch_refs
"""

from __future__ import annotations

import json
from pathlib import Path

from . import openalex as oa

ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = ROOT / "data" / "corpus"
OUT_DIR = ROOT / "data" / "openalex"
WORKS_PATH = OUT_DIR / "works.jsonl"
DONE_PATH = OUT_DIR / "_done_dois.txt"

SELECT = "id,doi,title,publication_year,referenced_works,cited_by_count,authorships,type"


def load_corpus_dois() -> dict[str, dict]:
    """DOI -> {venue_key, s2_paper_id, year} の辞書。DOI がない論文は落とす。"""
    out: dict[str, dict] = {}
    for path in sorted(CORPUS_DIR.glob("*.jsonl")):
        for line in path.open():
            p = json.loads(line)
            doi = oa.normalize_doi((p.get("externalIds") or {}).get("DOI"))
            if not doi:
                continue
            # 同じ DOI が複数 venue に出ることがある(PACM HCI と CSCW など)。最初を優先。
            out.setdefault(
                doi,
                {
                    "venue_key": p.get("_venue_key"),
                    "s2_id": p.get("paperId"),
                    "s2_year": p.get("year"),
                    "s2_venue": p.get("venue"),
                },
            )
    return out


def slim(work: dict) -> dict:
    """保存サイズを抑えるため必要なフィールドだけに削る。"""
    authorships = work.get("authorships") or []
    authors = []
    for a in authorships:
        author = a.get("author") or {}
        authors.append(
            {
                "id": oa.short_id(author.get("id")),
                "name": author.get("display_name"),
                "pos": a.get("author_position"),
                "insts": [oa.short_id(i.get("id")) for i in (a.get("institutions") or [])],
            }
        )
    return {
        "id": oa.short_id(work.get("id")),
        "doi": oa.normalize_doi(work.get("doi")),
        "title": work.get("title"),
        "year": work.get("publication_year"),
        "type": work.get("type"),
        "cited_by_count": work.get("cited_by_count"),
        "refs": [oa.short_id(r) for r in (work.get("referenced_works") or [])],
        "authors": authors,
    }


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus_dois()
    done: set[str] = set()
    if DONE_PATH.exists():
        done = {line.strip() for line in DONE_PATH.open() if line.strip()}

    todo = [d for d in corpus if d not in done]
    print(f"corpus DOIs: {len(corpus)}  already fetched: {len(done)}  todo: {len(todo)}")

    found = 0
    with WORKS_PATH.open("a") as wf, DONE_PATH.open("a") as df:
        for i in range(0, len(todo), oa.OR_LIMIT):
            batch = todo[i : i + oa.OR_LIMIT]
            data = oa.get(
                "/works",
                params={
                    "filter": "doi:" + "|".join(batch),
                    "select": SELECT,
                    "per-page": oa.OR_LIMIT,
                },
            )
            for work in data.get("results") or []:
                rec = slim(work)
                doi = rec.get("doi")
                if doi and doi in corpus:
                    rec["venue_key"] = corpus[doi]["venue_key"]
                    rec["s2_venue"] = corpus[doi]["s2_venue"]
                wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                found += 1
            # 見つからなかった DOI も done に入れる(毎回引き直さないため)
            for d in batch:
                df.write(d + "\n")
            wf.flush()
            df.flush()
            done_n = i + len(batch)
            print(f"  {done_n}/{len(todo)} requested, {found} works found", flush=True)

    print(f"\nwrote {WORKS_PATH}")


if __name__ == "__main__":
    main()
