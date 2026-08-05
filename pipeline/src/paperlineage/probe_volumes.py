"""コーパスに出てくる ACM の巻を Crossref で名寄せし、併設トラックの巻を書き出す。

S2 は本会議と併設トラック(Extended Abstracts / Adjunct / Companion)を同じ venue
名にまとめてしまうので、巻名は別のところから取るしかない。ACM の DOI は
`10.1145/<巻ID>.<論文ID>` なので、巻IDごとに代表を1本選んで Crossref を1回引けば
巻名が分かる。コーパス全体では 700 巻ほど、数分で終わる。

結果は `excluded_volumes.json`(巻ID -> 巻名)に保存し、ビルドはこれを読むだけ。
会場や年を足したら、このスクリプトを流し直す。

    uv run python -m paperlineage.probe_volumes
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .volumes import EXCLUDE_TITLE

CORPUS_DIR = Path("data/corpus")
OUT_PATH = Path(__file__).with_name("excluded_volumes.json")
AUDIT_PATH = Path("data/acm_volumes.json")   # 全巻の名前(git 管理外・確認用)
MAILTO = "ymt.mytk@gmail.com"                # Crossref の polite pool
UA = f"HCI-Research-Trails/1.0 (mailto:{MAILTO})"
ACM = re.compile(r"^10\.1145/(\d+)\.")


def representatives() -> dict[str, str]:
    """巻ID -> その巻の代表 DOI(1本あれば巻名が引ける)。"""
    rep: dict[str, str] = {}
    for path in sorted(CORPUS_DIR.glob("*.jsonl")):
        for line in path.open():
            rec = json.loads(line)
            doi = ((rec.get("externalIds") or {}).get("DOI") or "").lower()
            m = ACM.match(doi)
            if m:
                rep.setdefault(m.group(1), doi)
    return rep


def container_title(item: tuple[str, str]) -> tuple[str, str]:
    vol, doi = item
    url = f"https://api.crossref.org/works/{urllib.parse.quote(doi)}?mailto={MAILTO}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25) as res:
                msg = json.load(res)["message"]
                return vol, (msg.get("container-title") or [""])[0]
        except Exception as exc:  # noqa: BLE001 - 失敗は落とさず印を残す
            if attempt == 2:
                return vol, f"__ERR__{type(exc).__name__}"
            time.sleep(1.5 * (attempt + 1))
    return vol, "__ERR__"


def main() -> None:
    rep = representatives()
    print(f"ACM の巻: {len(rep)} 件。Crossref で巻名を引きます", flush=True)
    titles: dict[str, str] = {}
    with ThreadPoolExecutor(8) as pool:
        for i, (vol, title) in enumerate(pool.map(container_title, rep.items()), 1):
            titles[vol] = title
            if i % 150 == 0:
                print(f"  ...{i}/{len(rep)}", flush=True)

    failed = {v: t for v, t in titles.items() if t.startswith("__ERR__")}
    excluded = {v: t for v, t in titles.items() if EXCLUDE_TITLE.search(t or "")}
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(titles, ensure_ascii=False, indent=0))
    OUT_PATH.write_text(json.dumps(dict(sorted(excluded.items())), ensure_ascii=False, indent=1))

    print(f"併設トラックの巻: {len(excluded)} 件 → {OUT_PATH.name}")
    for vol, title in sorted(excluded.items(), key=lambda kv: kv[1]):
        print(f"  {vol}  {title}")
    if failed:
        print(f"引けなかった巻: {len(failed)} 件(その巻は残ります)", file=sys.stderr)
        for vol, err in failed.items():
            print(f"  {vol}  {rep[vol]}  {err}", file=sys.stderr)


if __name__ == "__main__":
    main()
