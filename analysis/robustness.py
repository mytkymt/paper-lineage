"""会場集合の頑健性: 主要な結果を 4 通りの会場集合で出し直して並べる。

  chi    = CHI だけ                      core13 = 2026-09 以前のコア 13 会場(拡張ビルドから抜く)
  core29 = SIGCHI 主催・共催の 29 会場   all36  = 29 + 引用結合の 7 会場(拡張ビルド)
各集合で genealogy → founder_share → export → window_persist → waves を回し(結果は
results/<集合名>/)、要点を robustness.csv にまとめる。会場で絞るときは load.PL_VENUES を使う。"""
from __future__ import annotations
import csv, os, subprocess, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
PY = sys.executable
SETS = {
    "chi": dict(PL_VENUES="chi"),
    "core13": dict(PL_DATASET="ext", PL_VENUES="chi,pacmhci,uist,dis,assets,iui,cscw,tei,imwut,ubicomp,chiplay,mobilehci,tochi"),
    "core29": dict(),
    "all36": dict(PL_DATASET="ext"),
}
STEPS = ["genealogy.py", "founder_share.py", "parents.py", "export.py", "window_persist.py", "waves.py"]

def run_all() -> None:
    for tag, env in SETS.items():
        e = {**os.environ, **env, "PL_TAG": tag}
        (HERE / "results" / tag).mkdir(parents=True, exist_ok=True)
        for step in STEPS:
            print(f"== {tag} {step}", flush=True)
            r = subprocess.run([PY, str(HERE / step)], env=e, capture_output=True, text=True)
            if r.returncode != 0:
                print(r.stderr[-1500:]); raise SystemExit(f"{tag} {step} failed")

def summarize() -> None:
    rows = []
    for tag in SETS:
        d = HERE / "results" / tag
        fs = list(csv.DictReader((d / "founder_share.csv").open()))
        def med(col):
            v = sorted(float(r[col]) for r in fs if r[col] not in ("", "nan")); return round(v[len(v) // 2], 2) if v else ""
        ex = list(csv.DictReader((d / "export.csv").open()))
        exm = sorted(float(r["export_share_median"]) for r in ex if r["export_share_median"] not in ("", "nan"))
        wp = list(csv.DictReader((d / "window_persistence.csv").open()))
        pers = [r for r in wp if r["corpus"] != "CHI"] or wp       # 集合全体の行(CHI だけの集合では両方同じ)
        cite = [f"{r['cite_persisted']}/{r['cite_clusters']}" for r in pers]
        motor = [f"{r['motor_persisted']}/{r['motor']}" for r in pers]
        wv = {r["wave"]: r for r in csv.DictReader((d / "waves.csv").open())}
        def w(name, col): return wv.get(name, {}).get(col, "")
        rows.append([tag, len(fs), med("y2"), med("y6"), med("y8"), round(exm[len(exm) // 2], 2) if exm else "",
                     " ".join(cite), " ".join(motor),
                     w("LLMs & generative AI", "peak_share"), w("LLMs & generative AI", "cohesion_lift"), w("LLMs & generative AI", "newcomer_author_share"),
                     w("VR (consumer HMDs)", "peak_share"), w("VR (consumer HMDs)", "cohesion_lift"),
                     w("Crowdsourcing (MTurk)", "peak_share"), w("Crowdsourcing (MTurk)", "cohesion_lift"),
                     w("WWW", "peak_share"), w("WWW", "cohesion_lift")])
    hdr = ["set", "subfields", "founder_y2", "founder_y6", "founder_y8", "export_median", "cite_persist_by_window", "motor_persist_by_window",
           "llm_peak", "llm_lift", "llm_newcomers", "vr_peak", "vr_lift", "mturk_peak", "mturk_lift", "www_peak", "www_lift"]
    with (HERE / "results" / "robustness.csv").open("w", newline="") as f:
        csv.writer(f).writerows([hdr] + rows)
    for r in rows: print(" | ".join(str(x) for x in r))

if __name__ == "__main__":
    if "--summary" not in sys.argv: run_all()
    summarize()
