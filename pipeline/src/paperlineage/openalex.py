"""OpenAlex API の薄いラッパー。

OpenAlex は API キー不要。mailto を付けると polite pool に入り、レート制限が緩む
(10 req/s, 100k req/day)。venue 情報は当てにならないが、`referenced_works` は完全で、
引用グラフの取得元としてはこちらが適している(docs/data-sources.md 参照)。
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

BASE = "https://api.openalex.org"
MAILTO = os.environ.get("OPENALEX_MAILTO", "ymt.mytk@gmail.com")

# OR フィルタ(`a|b|c`)に入れられる値の上限。OpenAlex の仕様。
OR_LIMIT = 50

_MIN_INTERVAL = 0.12  # ~8 req/s。polite pool の 10 req/s を下回るように。
_last_call = 0.0


def _throttle() -> None:
    global _last_call
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def get(path: str, *, params: dict[str, Any] | None = None, max_retries: int = 6) -> Any:
    params = dict(params or {})
    params["mailto"] = MAILTO
    url = f"{BASE}{path}"
    delay = 2.0
    last_err = ""
    for _ in range(max_retries):
        _throttle()
        try:
            with httpx.Client(timeout=90.0) as client:
                resp = client.get(url, params=params)
        except httpx.TransportError as e:
            last_err = f"transport: {e}"
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            last_err = f"{resp.status_code} {resp.text[:200]}"
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"OpenAlex request failed: {url} :: {last_err}")


def short_id(openalex_id: str | None) -> str | None:
    """'https://openalex.org/W123' -> 'W123'。保存量を減らすため常にこの形で持つ。"""
    if not openalex_id:
        return None
    return openalex_id.rsplit("/", 1)[-1]


def normalize_doi(doi: str | None) -> str | None:
    """OpenAlex の doi フィルタに渡せる形(小文字・プレフィックスなし)に正規化。"""
    if not doi:
        return None
    d = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.startswith(prefix):
            d = d[len(prefix) :]
    return d or None
