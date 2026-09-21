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
    refresh = "--refresh" in argv
    argv = [a for a in argv if not a.startswith("--")]
    keys = argv or [v.key for v in VENUES]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    total = 0
    for key in keys:
        v = VENUES_BY_KEY[key]
        out_path = OUT_DIR / f"{key}.jsonl"
        have = sum(1 for _ in out_path.open()) if out_path.exists() else 0
        if have and not refresh:
            print(f"{v.label}: skip (already have {have})")
            total += have
            continue
        print(f"{v.label}: fetching…")
        # 取り直しは別名に書いてから差し替える。途中で落ちたり、S2 側の不調で件数が
        # 急に減ったりしたときに、手元の正常なコーパスを壊さないため。
        tmp_path = out_path.with_suffix(".jsonl.tmp")
        try:
            try:
                n = fetch_venue(v, tmp_path)
            except Exception:  # noqa: BLE001 - 通信の途切れは一度だけやり直す
                print(f"  {v.label}: 途中で切れたのでやり直します", flush=True)
                n = fetch_venue(v, tmp_path)
        except Exception as exc:  # noqa: BLE001
            tmp_path.unlink(missing_ok=True)
            if not have:
                raise
            print(f"  {v.label}: 取得に失敗、前回の {have:,} 件を残します ({type(exc).__name__})")
            total += have
            continue
        if have and n < have * 0.97:
            tmp_path.unlink(missing_ok=True)
            print(f"  {v.label}: {have:,} → {n:,} 件に急減。前回のぶんを残します")
            total += have
            continue
        tmp_path.replace(out_path)
        if have:
            print(f"  {v.label}: {have:,} → {n:,} ({n - have:+,})")
        total += n

    print(f"\ncorpus total: {total} papers -> {OUT_DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
