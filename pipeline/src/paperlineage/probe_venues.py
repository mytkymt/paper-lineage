"""各 venue の S2 正規化名と件数を実測する。

venues.py の s2_name は推測で書いてあるので、これで確認してから直す。
出力: data/venue_probe.json

  uv run python -m paperlineage.probe_venues
"""

from __future__ import annotations

import json
from pathlib import Path

from . import s2
from .venues import VENUES

OUT = Path(__file__).resolve().parents[3] / "data" / "venue_probe.json"


def main() -> None:
    results = []
    for v in VENUES:
        row: dict[str, object] = {"key": v.key, "label": v.label, "guessed": v.s2_name}
        if not v.probe_doi:
            # 実測済み(probe_doi なし)は件数の確認だけ行う
            try:
                page = s2.search_bulk(v.search_venue, fields="paperId")
                row["total"] = page.get("total")
                print(f"{v.label:10s} ---  total={row.get('total')!s:>7s}  (no probe_doi; count only)")
            except Exception as e:
                row["total_error"] = f"{type(e).__name__}: {e}"
                print(f"{v.label:10s} ERROR {row['total_error']}")
            results.append(row)
            continue
        try:
            paper = s2.get(f"/paper/DOI:{v.probe_doi}", fields="title,year,venue,publicationVenue")
            actual = paper.get("venue") or ""
            pv = (paper.get("publicationVenue") or {}).get("name")
            row["actual"] = actual
            row["publicationVenue"] = pv
            row["probe_title"] = paper.get("title")
            row["match"] = actual == v.s2_name
        except Exception as e:  # probe DOI が見つからない場合もある
            row["error"] = f"{type(e).__name__}: {e}"
            results.append(row)
            print(f"{v.label:10s} ERROR {row['error']}")
            continue

        # 実測名で件数を数える(1ページだけ取って total を読む)
        try:
            page = s2.search_bulk(actual, fields="paperId")
            row["total"] = page.get("total")
        except Exception as e:
            row["total_error"] = f"{type(e).__name__}: {e}"

        flag = "OK " if row.get("match") else "DIFF"
        print(f"{v.label:10s} {flag} total={row.get('total')!s:>7s}  actual={actual!r}")
        results.append(row)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()
