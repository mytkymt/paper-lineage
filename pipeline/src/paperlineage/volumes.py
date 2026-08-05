"""併設トラックの巻(Extended Abstracts / Adjunct / Companion)を外すための判定。

S2 の正規化 venue 名は本会議と併設トラックを区別しない。実測: CHI の Extended
Abstracts は別 venue 名になるので最初から入らないが、UIST Adjunct や CSCW
Companion、IUI Companion は本会議と同じ venue 名で入ってくる。

ACM の DOI は `10.1145/<巻ID>.<論文ID>` で、同じ巻の論文は巻IDを共有する。そこで
巻IDごとに1本だけ Crossref を引いて巻名を確かめ(`probe_volumes.py`)、併設トラック
だった巻IDを `excluded_volumes.json` に置いてある。ビルドはその一覧を見るだけで、
ネットワークには触らない。

含めないもの: ポスター・LBW・デモ・ワークショップ・ドクトラルコンソーシアムなど、
本会議の査読を通っていない発表。地図が追うのは通した論文の系譜なので、混ざると
「引用が少ない点」が大量に増えて帯の形が濁る。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# 巻名がこれに当たれば併設トラックとみなす(probe_volumes.py が使う)
EXCLUDE_TITLE = re.compile(r"extended abstract|\badjunct\b|\bcompanion\b", re.I)

# ACM 以外で拾えた併設トラック。数が少ないので DOI の形で直接見る。
EXCLUDE_DOI = re.compile(r"ismar-adjunct", re.I)

_ACM_VOLUME = re.compile(r"^10\.1145/(\d+)\.")
_LIST_PATH = Path(__file__).with_name("excluded_volumes.json")


def _load() -> dict[str, str]:
    if not _LIST_PATH.exists():
        return {}
    return json.loads(_LIST_PATH.read_text())


EXCLUDED_VOLUMES: dict[str, str] = _load()   # 巻ID -> 巻名(監査できるように名前も持つ)


def companion_volume(doi: str | None) -> str | None:
    """併設トラックの巻なら巻名を、本会議なら None を返す。"""
    if not doi:
        return None
    d = doi.strip()
    if EXCLUDE_DOI.search(d):
        return "ISMAR Adjunct"
    m = _ACM_VOLUME.match(d.lower())
    if not m:
        return None
    return EXCLUDED_VOLUMES.get(m.group(1))
