"""無人更新の入口。新しい論文が十分たまっていれば再構築まで通す。

    uv run python -m paperlineage.update            # 判定して、必要なら再構築
    uv run python -m paperlineage.update --force    # 判定を飛ばして再構築
    uv run python -m paperlineage.update --check    # 取得と判定だけ(再構築しない)

流れ: コーパス取り直し → 増分を数える → (十分なら) 参照の取得と引き直し →
併設トラックの巻の確認 → 著者の名寄せ → グラフ → SPC → レイアウト(名前は前回から
引き継ぐ) → 健全性ゲート。ゲートに落ちたら exit 1 で、呼び出し側は何も公開しない。

再構築のたびに約 30MB の成果物がコミットされるので、毎週は回さない。
  - 新着が REBUILD_MIN_NEW 本以上             → 再構築
  - 新着が1本以上で、前回から MAX_DAYS 日以上  → 再構築(参照の引き直しを反映するため)
  - 前回から MIN_DAYS 日未満                   → 見送り(どれだけ増えていても)
結果は GITHUB_OUTPUT に rebuilt=true/false と summary で返す。
"""

from __future__ import annotations

import datetime
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path

from .venues import EXTRA_VENUES, VENUES
from .volumes import companion_volume

ROOT = Path(__file__).resolve().parents[3]
PIPE = ROOT / "pipeline"
STATE = PIPE / "state" / "last_build.json"
CORPUS = ROOT / "data" / "corpus"

REBUILD_MIN_NEW = 300
MIN_DAYS = 21
MAX_DAYS = 56


def run(*mod_args: str, env: dict | None = None) -> None:
    print(f"\n=== {' '.join(mod_args)} {'(ext)' if env else ''}", flush=True)
    subprocess.run([sys.executable, "-m", *mod_args], cwd=PIPE, check=True,
                   env={**os.environ, **(env or {})})


def corpus_counts() -> dict[str, int]:
    out: dict[str, int] = {}
    for v in [*VENUES, *EXTRA_VENUES]:
        path = CORPUS / f"{v.key}.jsonl"
        out[v.key] = sum(1 for _ in path.open()) if path.exists() else 0
    return out


def under_indexed(today: datetime.date) -> list[str]:
    """開催から4か月たっても今年のぶんが例年の半分に満たない会場。

    止めはしない(索引が遅いだけのこともある)。ただ S2 が会場の正規化名を変えると
    最新年だけが丸ごと欠けるので、気づけるように知らせる。
    """
    notes = []
    for v in [*VENUES, *EXTRA_VENUES]:
        path = CORPUS / f"{v.key}.jsonl"
        if not path.exists():
            continue
        # 地図に載る論文だけを数える。併設トラックの巻は年によって索引される時期が
        # ばらつくので、混ぜると本会議が揃っていても「少ない」と誤検知する
        # (実測: HRI 2026 は本会議 139 本で揃っていたが、例年値が Companion 込みの 342 本)。
        years: Counter = Counter()
        for line in path.open():
            rec = json.loads(line)
            if not companion_volume((rec.get("externalIds") or {}).get("DOI")):
                years[rec.get("year")] += 1
        due = datetime.date(today.year, min(12, int(v.month)), 1) + datetime.timedelta(days=120)
        if today < due:
            continue
        past = sorted(years.get(today.year - k, 0) for k in (1, 2, 3))
        usual = past[1]
        if usual >= 40 and years.get(today.year, 0) < usual * 0.5:
            notes.append(f"{v.label}: {today.year} 年が {years.get(today.year, 0)} 本(例年 {usual} 本前後)")
    return notes


def emit(**kv: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a") as f:
        for k, v in kv.items():
            f.write(f"{k}<<__EOF__\n{v}\n__EOF__\n")


def main(argv: list[str]) -> None:
    force, check_only = "--force" in argv, "--check" in argv
    today = datetime.datetime.now(datetime.timezone.utc).date()   # 実行環境に依らず UTC
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    run("paperlineage.fetch_corpus", "--refresh", *[v.key for v in [*VENUES, *EXTRA_VENUES]])
    counts = corpus_counts()
    prev_counts = state.get("counts") or {}
    grew = {k: counts[k] - prev_counts.get(k, 0) for k in counts if counts[k] != prev_counts.get(k, 0)}
    new_total = sum(max(0, d) for d in grew.values()) if prev_counts else 0
    days = max(0, (today - datetime.date.fromisoformat(state["date"])).days) if state.get("date") else 10**6
    notes = under_indexed(today)

    want = force or (not prev_counts) or (
        days >= MIN_DAYS and (new_total >= REBUILD_MIN_NEW or (new_total >= 1 and days >= MAX_DAYS)))
    print(f"\n新着 {new_total:,} 本 / 前回の再構築から {days if days < 10**6 else '—'} 日 → "
          f"{'再構築する' if want and not check_only else '見送り'}")
    for k, d in sorted(grew.items(), key=lambda kv: -kv[1]):
        print(f"  {k:10s} {d:+,}")
    for n in notes:
        print("  ! 索引が遅れている可能性:", n)
    if check_only or not want:
        emit(rebuilt="false", summary="", notes="\n".join(notes))
        return

    run("paperlineage.fetch_refs", "--refresh")
    run("paperlineage.probe_volumes")
    run("paperlineage.authors")
    ext = {"PL_DATASET": "ext"}
    run("paperlineage.build_graph")
    run("paperlineage.build_graph", "--extended")
    run("paperlineage.spc")
    run("paperlineage.spc", env=ext)
    run("paperlineage.layout", "--mode", "community")
    run("paperlineage.layout", "--mode", "community", env=ext)
    run("paperlineage.verify_build")            # 落ちたらここで exit 1(何も公開しない)
    run("paperlineage.verify_build", env=ext)

    core = json.loads((ROOT / "data/viz/meta.json").read_text())
    full = json.loads((ROOT / "data/viz-ext/meta.json").read_text())
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({
        "date": today.isoformat(), "counts": counts,
        "core_papers": core["node_count"], "all_papers": full["node_count"],
    }, indent=1) + "\n")
    top = ", ".join(f"{k} {d:+,}" for k, d in sorted(grew.items(), key=lambda kv: -kv[1])[:6] if d > 0)
    summary = (f"{full['node_count']:,} papers ({core['node_count']:,} core), "
               f"{new_total:,} new since {state.get('date', 'the first build')}" + (f": {top}" if top else ""))
    print("\n" + summary)
    emit(rebuilt="true", summary=summary, notes="\n".join(notes))


if __name__ == "__main__":
    main(sys.argv[1:])
