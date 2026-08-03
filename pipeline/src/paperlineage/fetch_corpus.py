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
    """1 venue 分を全ページ取得して JSONL に書く。戻り値は件数(重複除去後)。

    S2 の正規化名が複数ある会議(改称など)は全部の名前を引いて1ファイルに束ねる。
    名前をまたいで同じ論文が返ることがあるので paperId で重複を落とす。
    """
    seen: set[str] = set()
    n = 0
    off_venue = 0   # DOI 接頭辞で弾いた件数(venue クラスタの汚れ)
    with out_path.open("w") as f:
        for name in v.search_names:
            token: str | None = None
            got = 0
            while True:
                page = s2.search_bulk(name, fields=FIELDS, token=token)
                data = page.get("data") or []
                for paper in data:
                    pid = paper.get("paperId")
                    if pid and pid in seen:
                        continue
                    if v.doi_prefix:
                        doi = (paper.get("externalIds") or {}).get("DOI") or ""
                        if not doi.startswith(v.doi_prefix):
                            off_venue += 1
                            continue
                    if pid:
                        seen.add(pid)
                    # venue 完全一致で来ているはずだが、念のため記録しておく
                    paper["_venue_key"] = v.key
                    f.write(json.dumps(paper, ensure_ascii=False) + "\n")
                    n += 1
                    got += 1
                token = page.get("token")
                print(f"  {v.label} [{name[:34]}]: {got} / {page.get('total')} (計 {n})", flush=True)
                if not token or not data:
                    break
    if off_venue:
        print(f"  {v.label}: DOI 接頭辞 {v.doi_prefix} 以外を除外 {off_venue}", flush=True)
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
