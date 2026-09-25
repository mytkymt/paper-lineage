"""外部祖先層: コーパスの論文から k 回以上引用されているコーパス外の論文のメタデータを取る。

参照の 75% はコーパス外に向いており、系譜の起点(何を輸入して分野が生まれたか)は
外を見ないと言えない。ここでは OpenAlex の referenced_works から、コーパス外で
k 回以上引かれた work を集め、題名・年・掲載先・種別だけを取る(その先の参照は取らない)。

掲載先名だけでは分野を当てにくい(本や未解決の参照は掲載先が空)ので、OpenAlex の
primary_topic(domain / field / subfield)も一緒に取る。以前の記録に topic が無ければ
`--topics` で埋め直す。無料の 1 日予算で止まったら、翌日そのまま再実行すれば続きから進む
(`OPENALEX_API_KEY` を環境変数に置けば予算の制限は外れる)。

出力: data/openalex/external.jsonl(1 行 1 論文)、data/openalex/_external_done.txt

  uv run python -m paperlineage.fetch_external            # k=5
  uv run python -m paperlineage.fetch_external --min 3
  uv run python -m paperlineage.fetch_external --topics   # topic の無い記録を埋める
  uv run python -m paperlineage.fetch_external --containers   # 掲載先の無い記録に Crossref の巻名を足す

OpenAlex は ACM / IEEE の会議論文の掲載先(source)をしばしば空で返す。DOI があれば
Crossref の container-title で補える。ACM は巻IDごとに 1 回引けば済む(probe_volumes と
同じ考え)。それ以外は DOI ごとに引き、`data/crossref/containers.json` に溜める。
"""
from __future__ import annotations

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
from pathlib import Path

from . import openalex as oa
from .probe_volumes import ACM, AUDIT_PATH as ACM_VOLUMES, container_title


ROOT = Path(__file__).resolve().parents[3]
WORKS = ROOT / "data" / "openalex" / "works.jsonl"
OUT = ROOT / "data" / "openalex" / "external.jsonl"
DONE = ROOT / "data" / "openalex" / "_external_done.txt"
CONTAINERS = ROOT / "data" / "crossref" / "containers.json"   # doi -> Crossref container-title
BOOK_PLATFORM = re.compile(r"ebooks?$|ebook platform|^lecture notes", re.I)
SELECT = "id,doi,title,publication_year,type,cited_by_count,primary_location,authorships,primary_topic"


def topic_of(w: dict) -> dict:
    t = w.get("primary_topic") or {}
    return {
        "topic": t.get("display_name"),
        "topic_subfield": (t.get("subfield") or {}).get("display_name"),
        "topic_field": (t.get("field") or {}).get("display_name"),
        "topic_domain": (t.get("domain") or {}).get("display_name"),
    }


def backfill_topics() -> None:
    """topic の無い記録に primary_topic を足す(ファイルを書き直す)。"""
    recs = [json.loads(l) for l in OUT.open()]
    todo = [r["id"] for r in recs if "topic_field" not in r]
    print(f"記録 {len(recs):,} 件、topic 未取得 {len(todo):,} 件", flush=True)
    got: dict[str, dict] = {}
    try:
        for i in range(0, len(todo), oa.OR_LIMIT):
            batch = todo[i : i + oa.OR_LIMIT]
            data = oa.get("/works", params={"filter": "openalex_id:" + "|".join(batch), "select": "id,primary_topic", "per-page": oa.OR_LIMIT})
            for w in data.get("results") or []:
                got[oa.short_id(w["id"])] = topic_of(w)
            if (i // oa.OR_LIMIT) % 40 == 0:
                print(f"  {min(i + oa.OR_LIMIT, len(todo)):,}/{len(todo):,}", flush=True)
    finally:
        # 途中で予算切れになっても、取れたぶんは残す(次回はその続きだけ引く)
        tmp = OUT.with_suffix(".tmp")
        with tmp.open("w") as f:
            for r in recs:
                if r["id"] in got:
                    r.update(got[r["id"]])
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(OUT)
        print(f"topic を {len(got):,} 件追加 → {OUT}")


def backfill_containers() -> None:
    """掲載先が空(または電子書籍プラットフォーム名だけ)の記録に、Crossref の巻名を足す。"""
    recs = [json.loads(l) for l in OUT.open()]
    need = [r for r in recs if r.get("doi") and "container" not in r and (not r.get("source") or BOOK_PLATFORM.search(r["source"]))]
    cache: dict[str, str] = json.loads(CONTAINERS.read_text()) if CONTAINERS.exists() else {}
    volumes: dict[str, str] = json.loads(ACM_VOLUMES.read_text()) if ACM_VOLUMES.exists() else {}
    # ACM は巻ごとに代表 1 本、それ以外は DOI ごと
    vol_rep: dict[str, str] = {}
    per_doi: list[tuple[str, str]] = []
    for r in need:
        d = r["doi"].lower()
        m = ACM.match(d)
        if m:
            if not volumes.get(m.group(1)) or volumes[m.group(1)].startswith("__ERR__"):
                vol_rep.setdefault(m.group(1), d)
        elif d not in cache:
            per_doi.append((d, d))
    print(f"記録 {len(recs):,} 件、巻名が要るもの {len(need):,} 件 → Crossref: ACM の巻 {len(vol_rep):,} + その他 DOI {len(per_doi):,}", flush=True)
    try:
        with ThreadPoolExecutor(8) as pool:
            for i, (vol, title) in enumerate(pool.map(container_title, vol_rep.items()), 1):
                volumes[vol] = title
                if i % 200 == 0: print(f"  ACM 巻 {i}/{len(vol_rep)}", flush=True)
            for i, (d, title) in enumerate(pool.map(container_title, per_doi), 1):
                if not title.startswith("__ERR__"): cache[d] = title
                if i % 500 == 0: print(f"  DOI {i}/{len(per_doi)}", flush=True)
    finally:
        ACM_VOLUMES.write_text(json.dumps(volumes, ensure_ascii=False, indent=0))
        CONTAINERS.parent.mkdir(parents=True, exist_ok=True)
        CONTAINERS.write_text(json.dumps(cache, ensure_ascii=False, indent=0))
        n = 0
        for r in need:
            d = r["doi"].lower(); m = ACM.match(d)
            t = volumes.get(m.group(1)) if m else cache.get(d)
            if t and not t.startswith("__ERR__"):
                r["container"] = t; n += 1
        tmp = OUT.with_suffix(".tmp")
        with tmp.open("w") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(OUT)
        print(f"巻名を {n:,} 件追加 → {OUT}")


def main(argv: list[str]) -> None:
    if "--containers" in argv:
        backfill_containers()
        return
    if "--topics" in argv:
        backfill_topics()
        return
    k = int(argv[argv.index("--min") + 1]) if "--min" in argv else 5
    corpus, refs = set(), Counter()
    for line in WORKS.open():
        w = json.loads(line)
        corpus.add(w["id"])
    for line in WORKS.open():
        w = json.loads(line)
        for r in w.get("refs") or []:
            if r not in corpus:
                refs[r] += 1
    wanted = [r for r, c in refs.items() if c >= k]
    done = {l.strip() for l in DONE.open()} if DONE.exists() else set()
    todo = [r for r in wanted if r not in done]
    print(f"コーパス外の参照先 {len(refs):,} 件、{k} 回以上引かれたもの {len(wanted):,} 件、未取得 {len(todo):,} 件", flush=True)
    with OUT.open("a") as wf, DONE.open("a") as df:
        for i in range(0, len(todo), oa.OR_LIMIT):
            batch = todo[i : i + oa.OR_LIMIT]
            data = oa.get("/works", params={"filter": "openalex_id:" + "|".join(batch), "select": SELECT, "per-page": oa.OR_LIMIT})
            for w in data.get("results") or []:
                loc = (w.get("primary_location") or {}) or {}
                src = (loc.get("source") or {}) or {}
                rec = {
                    "id": oa.short_id(w["id"]), "doi": oa.normalize_doi(w.get("doi")), "title": w.get("title"),
                    "year": w.get("publication_year"), "type": w.get("type"), "cited_by_count": w.get("cited_by_count"),
                    "source": src.get("display_name"), "source_type": src.get("type"), "in_corpus_cites": refs[oa.short_id(w["id"])],
                    "authors": [((a.get("author") or {}).get("id") or "").rsplit("/", 1)[-1] for a in (w.get("authorships") or [])][:12],
                    **topic_of(w),
                }
                wf.write(json.dumps(rec, ensure_ascii=False) + "\n")
            for r in batch:
                df.write(r + "\n")
            wf.flush(); df.flush()
            if (i // oa.OR_LIMIT) % 40 == 0:
                print(f"  {min(i + oa.OR_LIMIT, len(todo)):,}/{len(todo):,}", flush=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:])
