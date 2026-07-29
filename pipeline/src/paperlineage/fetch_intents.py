"""Step 2b(任意): citation intent(background / method / result)を S2 から取る。

intent をエッジ単位で返すのは S2 だけ(docs/data-sources.md)。引用**する側**の論文ごとに
/paper/{id}/references を1回叩き、コーパス内(nodes.jsonl にある DOI)への参照だけを
intent 付きで保存する。

- **レジューム前提**: data/graph/intents.jsonl に引用側 paperId 単位で追記し、
  取得済みはスキップする。途中で止めても続きから流せる。
- 所要: 無認証 4秒/req(s2.py の throttle)で全 38,791 論文 ≈ 43時間。
  `S2_API_KEY` があれば 1秒/req ≈ 11時間。少しずつ流す運用でよい
  (ビューアは部分データでも動き、カバレッジを凡例に出す)。
- 取得後は `uv run python -m paperlineage.intents` で edge_intent.bin を作り直す。

usage: uv run python -m paperlineage.fetch_intents [--limit N]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from . import s2

ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = ROOT / "data" / "corpus"
GRAPH_DIR = ROOT / "data" / "graph"
OUT_PATH = GRAPH_DIR / "intents.jsonl"

FIELDS = "intents,externalIds"
PAGE = 1000


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.lower().removeprefix("https://doi.org/")


def node_dois() -> set[str]:
    dois = set()
    for line in (GRAPH_DIR / "nodes.jsonl").open():
        d = norm_doi(json.loads(line).get("doi"))
        if d:
            dois.add(d)
    return dois


def corpus_papers(in_graph: set[str]) -> list[tuple[str, str]]:
    """(s2 paperId, doi) をグラフに載っている論文だけ、paperId 順(決定論)で。"""
    seen: dict[str, str] = {}
    for path in sorted(CORPUS_DIR.glob("*.jsonl")):
        for line in path.open():
            p = json.loads(line)
            doi = norm_doi((p.get("externalIds") or {}).get("DOI"))
            if doi and doi in in_graph:
                seen.setdefault(p["paperId"], doi)
    return sorted(seen.items())


def fetch_refs(paper_id: str) -> list[dict]:
    """references を全ページ。エントリは {intents, citedPaper:{externalIds}}。"""
    out: list[dict] = []
    offset = 0
    while True:
        page = s2.get(f"/paper/{paper_id}/references", fields=FIELDS, limit=PAGE, offset=offset)
        out.extend(page.get("data") or [])
        if page.get("next") is None:
            return out
        offset = page["next"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="この実行で新規に取る論文数の上限(プローブ用)")
    args = ap.parse_args()

    in_graph = node_dois()
    papers = corpus_papers(in_graph)
    done = set()
    if OUT_PATH.exists():
        for line in OUT_PATH.open():
            done.add(json.loads(line)["paperId"])
    todo = [(pid, doi) for pid, doi in papers if pid not in done]
    print(f"papers on graph: {len(papers):,} · fetched: {len(done):,} · todo: {len(todo):,}"
          + (f" (limit {args.limit})" if args.limit else ""))
    if args.limit:
        todo = todo[: args.limit]

    with OUT_PATH.open("a") as out:
        for k, (pid, doi) in enumerate(todo):
            refs = fetch_refs(pid)
            matched = []
            for r in refs:
                rd = norm_doi(((r.get("citedPaper") or {}).get("externalIds") or {}).get("DOI"))
                if rd and rd in in_graph:
                    matched.append([rd, r.get("intents") or []])
            out.write(json.dumps(
                {"paperId": pid, "doi": doi, "n_refs": len(refs), "in_corpus": matched},
                ensure_ascii=False) + "\n")
            out.flush()
            if (k + 1) % 25 == 0 or k + 1 == len(todo):
                print(f"  {k + 1:,}/{len(todo):,} fetched (total {len(done) + k + 1:,})")

    print("done — rebuild the bin with: uv run python -m paperlineage.intents")


if __name__ == "__main__":
    main()
