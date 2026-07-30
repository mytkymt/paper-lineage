"""Step 1: S2 の venue 検索でコーパス(論文リスト)を確定する。

引用エッジはここでは取らない(S2 は無認証だとレート制限が厳しすぎる)。
ここで得た DOI をキーに、Step 2 で OpenAlex から referenced_works を取る。

出力: data/corpus/<venue_key>.jsonl  (1行1論文)
再実行時は既存ファイルをスキップするので、途中で落ちても続きから流せる。

  uv run python -m paperlineage.fetch_corpus            # 全 venue
  uv run python -m paperlineage.fetch_corpus chi uist   # 一部だけ
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import s2
from .venues import VENUES, VENUES_BY_KEY, Venue

FIELDS = "paperId,externalIds,title,year,venue,citationCount,referenceCount,authors"
OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "corpus"


def fetch_venue(v: Venue, out_path: Path) -> int:
    """1 venue 分を全ページ取得して JSONL に書く。戻り値は件数。"""
    n = 0
    token: str | None = None
    with out_path.open("w") as f:
        while True:
            page = s2.search_bulk(v.search_venue, fields=FIELDS, token=token)
            data = page.get("data") or []
            for paper in data:
                # venue 完全一致で来ているはずだが、念のため記録しておく
                paper["_venue_key"] = v.key
                f.write(json.dumps(paper, ensure_ascii=False) + "\n")
                n += 1
            token = page.get("token")
            print(f"  {v.label}: {n} / {page.get('total')}", flush=True)
            if not token or not data:
                break
    return n


def main(argv: list[str]) -> None:
    keys = argv or [v.key for v in VENUES]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for key in keys:
        v = VENUES_BY_KEY[key]
        out_path = OUT_DIR / f"{key}.jsonl"
        if out_path.exists():
            n = sum(1 for _ in out_path.open())
            print(f"{v.label}: skip (already have {n})")
            total += n
            continue
        print(f"{v.label}: fetching…")
        total += fetch_venue(v, out_path)

    print(f"\ncorpus total: {total} papers -> {OUT_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
