"""Step 2: コーパスの DOI を OpenAlex に問い合わせ、引用エッジと著者を取る。

S2 のコーパス(data/corpus/*.jsonl)から DOI を集め、OpenAlex に 50 件ずつ
まとめて投げる。取るのは referenced_works(完全な参照リスト)と authorships。

出力: data/openalex/works.jsonl (1行1論文、必要なフィールドだけに削ったもの)
      data/openalex/_done_dois.txt (取得済み DOI。再実行時はスキップ)

  uv run python -m paperlineage.fetch_refs            # 新しい DOI だけ
  uv run python -m paperlineage.fetch_refs --refresh  # + 参照が空の直近論文を引き直す
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
    from .venues import EXTRA_KEYS

    out: dict[str, dict] = {}
    # コア venue を先に読む: 同じ DOI がコアと拡張の両方にある場合(例: UIST 論文が
    # TOG にも載る)、venue_key はコア側でなければコアビルドから論文が消えてしまう。
    paths = sorted(CORPUS_DIR.glob("*.jsonl"), key=lambda p: (p.stem in EXTRA_KEYS, p.name))
    for path in paths:
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


def stale_recent_dois(corpus: dict[str, dict], years_back: int = 1) -> list[str]:
    """刊行が直近(今年と前年)で、参照リストが空のまま保存されている DOI。"""
    import datetime

    if not WORKS_PATH.exists():
        return []
    floor = datetime.date.today().year - years_back
    latest: dict[str, dict] = {}
    for line in WORKS_PATH.open():
        w = json.loads(line)
        if w.get("doi"):
            latest[w["doi"]] = w          # 後勝ち
    return sorted(
        d for d, w in latest.items()
        if d in corpus and isinstance(w.get("year"), int) and w["year"] >= floor and not w.get("refs")
    )


def compact() -> None:
    """works.jsonl を後勝ちで畳む(引き直しの追記で同じ論文が重なるため)。"""
    if not WORKS_PATH.exists():
        return
    latest: dict[str, str] = {}
    total = 0
    for line in WORKS_PATH.open():
        total += 1
        w = json.loads(line)
        latest[w.get("id") or w.get("doi") or str(total)] = line
    if total > len(latest) * 1.02:        # 2% 以上だぶついたら書き直す
        tmp = WORKS_PATH.with_suffix(".jsonl.tmp")
        tmp.write_text("".join(latest.values()))
        tmp.replace(WORKS_PATH)
        print(f"  works.jsonl を畳みました: {total:,} → {len(latest):,} 行")


def main(refresh: bool = False) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    corpus = load_corpus_dois()
    done: set[str] = set()
    if DONE_PATH.exists():
        done = {line.strip() for line in DONE_PATH.open() if line.strip()}

    todo = [d for d in corpus if d not in done]
    print(f"corpus DOIs: {len(corpus)}  already fetched: {len(done)}  todo: {len(todo)}")

    # OpenAlex は新しい論文の参照リストを数か月遅れで埋める(実測: 刊行年の論文の
    # 約2割が空)。一度取ったきりにすると、その論文は地図の上でずっと孤立したままに
    # なるので、直近2年ぶんで参照が空のものは毎回引き直す。works.jsonl は後勝ちで
    # 読まれるので、追記するだけで置き換わる。
    if refresh:
        stale = stale_recent_dois(corpus)
        todo_set = set(todo)
        extra = [d for d in stale if d not in todo_set]
        print(f"  参照が空の直近論文を引き直し: {len(extra):,}")
        todo += extra

    found = 0
    recovered = 0   # フィルタ検索から漏れて単体取得で拾えた分
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
            got: set[str] = set()
            for work in data.get("results") or []:
                rec = slim(work)
                doi = rec.get("doi")
                if doi and doi in corpus:
                    rec["venue_key"] = corpus[doi]["venue_key"]
                    rec["s2_venue"] = corpus[doi]["s2_venue"]
                    got.add(doi)
                wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                found += 1

            # フィルタ検索から漏れた DOI は単体エンドポイントで引き直す。
            # OpenAlex は「/works/doi:X は返すが filter=doi:X は 0 件」という
            # 状態を取ることがあり(登録直後の論文で実測)、バッチだけだと
            # 新しい論文が恒久的に欠落する。
            for d in batch:
                if d in got:
                    continue
                try:
                    work = oa.get(f"/works/doi:{d}", params={"select": SELECT})
                except Exception:
                    continue          # 本当に無い DOI(404)はここで諦める
                rec = slim(work)
                if rec.get("doi"):
                    rec["venue_key"] = corpus[d]["venue_key"]
                    rec["s2_venue"] = corpus[d]["s2_venue"]
                    wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    found += 1
                    recovered += 1
            # 見つからなかった DOI も done に入れる(毎回引き直さないため)
            for d in batch:
                df.write(d + "\n")
            wf.flush()
            df.flush()
            done_n = i + len(batch)
            print(f"  {done_n}/{len(todo)} requested, {found} works found", flush=True)

    if recovered:
        print(f"  filter 検索から漏れて単体取得で回収: {recovered:,}")
    if refresh:
        compact()
    print(f"\nwrote {WORKS_PATH}")


if __name__ == "__main__":
    import sys

    main(refresh="--refresh" in sys.argv[1:])
