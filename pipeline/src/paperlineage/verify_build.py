"""無人更新の健全性ゲート。新しいビルドを、コミット済みの前回ビルドと見比べる。

人が確認しない前提なので、ここを通らなかったビルドは公開しない(exit 1)。
見ているのは「壊れたデータが黙って本番に出る」種類の事故だけ:

  - 論文数が急に減る/増えすぎる      … API の不調、venue 名の取り違え
  - 会場が丸ごと痩せる               … S2 の正規化名が変わった(DIS で実際に起きた)
  - 新着の DOI が会場の常と違う      … venue クラスタへの異分野の混入(同上)
  - 引用の密度が崩れる               … 参照の取得失敗
  - 孤立した論文の割合が跳ねる       … 同上
  - 年の範囲がおかしい / 名前が欠ける

  uv run python -m paperlineage.verify_build            # コア
  PL_DATASET=ext uv run python -m paperlineage.verify_build
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_EXT = os.environ.get("PL_DATASET") == "ext"
REL = "data/viz-ext/meta.json" if _EXT else "data/viz/meta.json"


def _prefix(doi: str | None) -> str:
    return (doi or "").split("/")[0]


def _load_prev() -> dict | None:
    try:
        out = subprocess.run(["git", "show", f"HEAD:{REL}"], cwd=ROOT, capture_output=True, check=True)
        return json.loads(out.stdout)
    except Exception:  # noqa: BLE001 - 初回など、前回が無ければ比較なしで通す
        return None


def check(new: dict, prev: dict | None) -> list[str]:
    bad: list[str] = []
    n_new = new["node_count"]
    this_year = datetime.date.today().year

    if not (1970 <= new["year_min"] <= 1990) or not (this_year - 1 <= new["year_max"] <= this_year + 1):
        bad.append(f"年の範囲が不自然: {new['year_min']}–{new['year_max']}")
    unnamed = [b for b in new["bands"] if b.get("community") is not None and not b.get("name")]
    unnamed += [s for s in new.get("subbands") or [] if not s.get("name")]
    if unnamed:
        bad.append(f"名前の無い帯・サブ帯: {len(unnamed)}")
    names = [o["name"] for o in [*new["bands"], *(new.get("subbands") or [])] if o.get("name")]
    dup = [k for k, v in Counter(names).items() if v > 1]
    if dup:
        bad.append(f"名前の重複: {dup[:5]}")
    if prev is None:
        return bad

    n_prev = prev["node_count"]
    if n_new < n_prev * 0.98:
        bad.append(f"論文数が減りすぎ: {n_prev:,} → {n_new:,}")
    if n_new > n_prev * 1.20:
        bad.append(f"論文数が増えすぎ: {n_prev:,} → {n_new:,}")

    dens_prev = prev["edge_count"] / max(1, n_prev)
    dens_new = new["edge_count"] / max(1, n_new)
    if not (0.85 <= dens_new / dens_prev <= 1.20):
        bad.append(f"1論文あたりの引用数が崩れた: {dens_prev:.2f} → {dens_new:.2f}")

    iso = lambda m: sum(1 for nd in m["nodes"] if nd.get("s", -1) < 0) / max(1, len(m["nodes"]))
    if iso(new) > iso(prev) + 0.05:
        bad.append(f"帯に属さない論文の割合が跳ねた: {iso(prev):.1%} → {iso(new):.1%}")

    v_prev = Counter(nd.get("v") for nd in prev["nodes"])
    v_new = Counter(nd.get("v") for nd in new["nodes"])
    for v, c in v_prev.items():
        if c >= 200 and v_new.get(v, 0) < c * 0.95:
            bad.append(f"会場 {v} が痩せた: {c:,} → {v_new.get(v, 0):,}")

    # 新着の DOI 接頭辞が、その会場のいつもの発行元と違っていないか
    seen = {nd.get("d") for nd in prev["nodes"]}
    home: dict[str, str] = {}
    by_v: dict[str, Counter] = {}
    for nd in prev["nodes"]:
        by_v.setdefault(nd.get("v"), Counter())[_prefix(nd.get("d"))] += 1
    for v, c in by_v.items():
        home[v] = c.most_common(1)[0][0]
    fresh: dict[str, list[str]] = {}
    for nd in new["nodes"]:
        if nd.get("d") not in seen:
            fresh.setdefault(nd.get("v"), []).append(_prefix(nd.get("d")))
    for v, prefixes in fresh.items():
        if len(prefixes) >= 30 and v in home:
            share = sum(1 for p in prefixes if p == home[v]) / len(prefixes)
            base = by_v[v][home[v]] / sum(by_v[v].values())
            if share < base - 0.25:
                bad.append(f"会場 {v} の新着 {len(prefixes)} 本のうち {home[v]} は {share:.0%}(通常 {base:.0%})— 混入の疑い")
    return bad


def main() -> None:
    new = json.loads((ROOT / REL).read_text())
    prev = _load_prev()
    bad = check(new, prev)
    tag = "ext" if _EXT else "core"
    delta = f"{prev['node_count']:,} → {new['node_count']:,}" if prev else f"{new['node_count']:,} (前回なし)"
    if bad:
        print(f"[{tag}] NG  論文 {delta}")
        for b in bad:
            print("  ✗", b)
        sys.exit(1)
    print(f"[{tag}] OK  論文 {delta} / 引用 {new['edge_count']:,}")


if __name__ == "__main__":
    main()
