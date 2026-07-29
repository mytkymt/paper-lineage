"""Semantic Scholar Graph API の薄いラッパー。

無認証だとレート制限が厳しい(共有プールで実質 1 req/s 未満、すぐ 429 が返る)ので、
呼び出しは必ずこの関数を通し、429 は指数バックオフで待つ。
S2_API_KEY 環境変数があればヘッダに載せる。
"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx

BASE = "https://api.semanticscholar.org/graph/v1"

# 無認証時のベース間隔。キーがあれば短くできる。
_MIN_INTERVAL = 1.0 if os.environ.get("S2_API_KEY") else 4.0
_last_call = 0.0


def _headers() -> dict[str, str]:
    key = os.environ.get("S2_API_KEY")
    return {"x-api-key": key} if key else {}


def _throttle() -> None:
    global _last_call
    wait = _MIN_INTERVAL - (time.monotonic() - _last_call)
    if wait > 0:
        time.sleep(wait)
    _last_call = time.monotonic()


def request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    max_retries: int = 6,
) -> Any:
    """429/5xx を指数バックオフでリトライしつつ JSON を返す。"""
    url = f"{BASE}{path}"
    delay = 5.0
    last_err: str = ""
    for attempt in range(max_retries):
        _throttle()
        with httpx.Client(timeout=60.0) as client:
            resp = client.request(method, url, params=params, json=json, headers=_headers())
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (429, 500, 502, 503, 504):
            last_err = f"{resp.status_code} {resp.text[:200]}"
            time.sleep(delay)
            delay = min(delay * 2, 120.0)
            continue
        resp.raise_for_status()
    raise RuntimeError(f"S2 request failed after {max_retries} attempts: {method} {url} :: {last_err}")


def get(path: str, **params: Any) -> Any:
    return request("GET", path, params=params)


def search_bulk(venue: str, fields: str, token: str | None = None) -> Any:
    """venue 完全一致の bulk search を1ページ分。token でページング。"""
    params: dict[str, Any] = {"venue": venue, "fields": fields}
    if token:
        params["token"] = token
    return request("GET", "/paper/search/bulk", params=params)
