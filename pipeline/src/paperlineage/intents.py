"""Step 6b: intents.jsonl → data/viz/edge_intent.bin(uint8、**spc.tsv のエッジ順**)。

layout.py は spc.tsv の行順で edges.bin を書くので、この bin も同じ順に揃える
(順序がずれると全エッジの intent が別のエッジに付く)。

値はビットマスク:
  bit3 (8) = 引用側の論文を S2 から取得済み(「未取得」と「取得したが intent なし」を区別する)
  bit0 (1) = background   bit1 (2) = method   bit2 (4) = result
  0        = 未取得

S2 が返す intent 文字列は明示的な対応表で変換し、未知の値は**数えて必ず表示する**
(サイレントに落とさない)。部分取得のままでもよい — ビューアがカバレッジを凡例に出す。

usage: uv run python -m paperlineage.intents
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
GRAPH_DIR = ROOT / "data" / "graph"
VIZ_DIR = ROOT / "data" / "viz"

FETCHED = 8
INTENT_BITS = {"background": 1, "method": 2, "methodology": 2, "result": 4}


def norm_doi(doi: str | None) -> str | None:
    if not doi:
        return None
    return doi.lower().removeprefix("https://doi.org/")


def main() -> None:
    nodes = [json.loads(line) for line in (GRAPH_DIR / "nodes.jsonl").open()]
    doi_of = [norm_doi(n.get("doi")) for n in nodes]
    idx = {n["id"]: i for i, n in enumerate(nodes)}

    # 引用側 doi -> {引用先 doi: bits}
    fetched: dict[str, dict[str, int]] = {}
    unknown: dict[str, int] = {}
    path = GRAPH_DIR / "intents.jsonl"
    if path.exists():
        for line in path.open():
            rec = json.loads(line)
            refs: dict[str, int] = {}
            for rd, intents in rec["in_corpus"]:
                bits = 0
                for s in intents:
                    if s in INTENT_BITS:
                        bits |= INTENT_BITS[s]
                    else:
                        unknown[s] = unknown.get(s, 0) + 1
                refs[rd] = refs.get(rd, 0) | bits
            fetched[rec["doi"]] = refs
    else:
        print(f"note: {path} not found — writing an all-zero bin (no intents fetched yet)")

    # spc.tsv の行順 = layout.py が edges.bin を書く順
    out = []
    counts = {"unfetched": 0, "no_intent": 0, "background": 0, "method": 0, "result": 0}
    for line in (GRAPH_DIR / "spc.tsv").open():
        a, b, _ = line.rstrip("\n").split("\t")           # a = cited(古い), b = citing(新しい)
        citing_doi = doi_of[idx[b]]
        refs = fetched.get(citing_doi)
        if refs is None:
            out.append(0)
            counts["unfetched"] += 1
            continue
        bits = refs.get(doi_of[idx[a]] or "", 0)
        out.append(FETCHED | bits)
        if bits & 2:
            counts["method"] += 1        # 複数 intent は method > result > background で数える
        elif bits & 4:
            counts["result"] += 1
        elif bits & 1:
            counts["background"] += 1
        else:
            counts["no_intent"] += 1

    arr = np.array(out, dtype=np.uint8)
    VIZ_DIR.mkdir(parents=True, exist_ok=True)
    arr.tofile(VIZ_DIR / "edge_intent.bin")

    total = len(arr)
    known = total - counts["unfetched"]
    print(f"edges: {total:,} · citing paper fetched: {known:,} ({known / total:.1%})")
    print(f"  background {counts['background']:,} · method {counts['method']:,} · "
          f"result {counts['result']:,} · fetched-but-no-intent {counts['no_intent']:,}")
    if unknown:
        print(f"  UNKNOWN intent strings (not mapped, dropped): {unknown}")
    print(f"wrote {VIZ_DIR / 'edge_intent.bin'} ({arr.nbytes:,} bytes)")


if __name__ == "__main__":
    main()
