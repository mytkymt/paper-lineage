"""コーパス論文の抄録を Semantic Scholar から取る(題名だけでは技術の波の論文を取りこぼすため)。

batch エンドポイントで 500 本ずつ。S2_API_KEY が無くても動く(遅いだけ)。途中で止めても
取れたぶんは残り、次回はその続きだけ引く。抄録は S2 の利用規約の範囲で分析にだけ使い、
公開データ(data/viz)には入れない。

出力: data/s2/abstracts.jsonl(paperId, abstract)

  uv run python -m paperlineage.fetch_abstracts
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from . import s2

ROOT = Path(__file__).resolve().parents[3]
CORPUS_DIR = ROOT / "data" / "corpus"
OUT = ROOT / "data" / "s2" / "abstracts.jsonl"
BATCH = 500


def main() -> None:
    ids: list[str] = []
    for path in sorted(CORPUS_DIR.glob("*.jsonl")):
        for line in path.open():
            ids.append(json.loads(line)["paperId"])
    done = {json.loads(l)["paperId"] for l in OUT.open()} if OUT.exists() else set()
    todo = [i for i in dict.fromkeys(ids) if i not in done]
    print(f"論文 {len(set(ids)):,} 件、抄録未取得 {len(todo):,} 件", flush=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("a") as f:
        for k in range(0, len(todo), BATCH):
            batch = todo[k : k + BATCH]
            delay = 4.0
            for attempt in range(6):
                s2._throttle()
                try:
                    r = httpx.post(f"{s2.BASE}/paper/batch", params={"fields": "abstract"}, json={"ids": batch}, headers=s2._headers(), timeout=120.0)
                except httpx.TransportError:
                    time.sleep(delay); delay *= 2; continue
                if r.status_code == 200:
                    for pid, rec in zip(batch, r.json()):
                        f.write(json.dumps({"paperId": pid, "abstract": (rec or {}).get("abstract")}, ensure_ascii=False) + "\n")
                    f.flush(); break
                time.sleep(delay); delay = min(delay * 2, 60.0)
            else:
                print(f"  失敗: {k}-{k + len(batch)}(次回に回す)", flush=True)
            if (k // BATCH) % 10 == 0:
                print(f"  {min(k + BATCH, len(todo)):,}/{len(todo):,}", flush=True)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
