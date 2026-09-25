"""系譜分析の共通ローダ。data/graph(コア)または data/graph-ext を読み、
時間単調 DAG・帯/サブ帯の所属・SPC 重みを numpy で返す。

meta.json(viewer 用)は帯とサブ帯の所属と名前を持ち、nodes.jsonl は著者と
OpenAlex ID を持つので、両方を DOI で突き合わせる。
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXT = os.environ.get("PL_DATASET") == "ext"
GRAPH = ROOT / "data" / ("graph-ext" if EXT else "graph")
VIZ = ROOT / "data" / ("viz-ext" if EXT else "viz")
OUT = ROOT / "analysis" / "out" / ("ext" if EXT else "core")


class Graph:
    def __init__(self) -> None:
        self.meta = json.loads((VIZ / "meta.json").read_text())
        rows = [json.loads(l) for l in (GRAPH / "nodes.jsonl").open()]
        self.idx = {r["id"]: i for i, r in enumerate(rows)}
        self.rows = rows
        self.n = len(rows)
        self.year = np.array([r["year"] for r in rows], dtype=np.int32)
        self.venue = [r.get("venue_key") for r in rows]
        self.title = [r.get("title") or "" for r in rows]
        self.doi = [r.get("doi") for r in rows]
        self.cited_by = np.array([r.get("cited_by_count") or 0 for r in rows])
        self.authors = [r.get("authors") or [] for r in rows]
        # edges.tsv: cited(古い) \t citing(新しい)
        src, dst, w = [], [], {}
        for l in (GRAPH / "edges.tsv").open():
            a, b = l.rstrip("\n").split("\t")
            src.append(self.idx[a]); dst.append(self.idx[b])
        self.cited = np.array(src, dtype=np.int64)    # 古い側
        self.citing = np.array(dst, dtype=np.int64)   # 新しい側
        spc = {}
        for l in (GRAPH / "spc.tsv").open():
            a, b, s = l.rstrip("\n").split("\t")
            spc[(self.idx[a], self.idx[b])] = float(s)
        self.spc = np.array([spc.get((a, b), 0.0) for a, b in zip(self.cited, self.citing)])
        # 帯・サブ帯(meta.json は DOI 順不同なので DOI で結ぶ)
        by_doi = {nd["d"]: nd for nd in self.meta["nodes"] if nd.get("d")}
        self.sub = np.full(self.n, -1, dtype=np.int64)
        for i, d in enumerate(self.doi):
            nd = by_doi.get(d)
            if nd is not None:
                self.sub[i] = nd.get("s", -1)
        subs = self.meta["subbands"]
        self.sub_band = np.array([sb["band"] for sb in subs], dtype=np.int64)
        self.band = np.where(self.sub >= 0, self.sub_band[np.clip(self.sub, 0, None)], -1)
        self.sub_name = [sb.get("name") or "|".join(sb.get("keywords") or []) for sb in subs]
        self.band_name = [b.get("name") or "|".join(b.get("keywords") or []) for b in self.meta["bands"]]
        # 隣接(CSR)
        self.out_start, self.out_idx = _csr(self.cited, self.citing, self.n)   # cited -> citing(下流)
        self.in_start, self.in_idx = _csr(self.citing, self.cited, self.n)     # citing -> cited(上流)
        # トポロジカル順: (year, id) 全順序で DAG なので年順で十分
        self.topo = np.argsort(self.year, kind="stable")

    def downstream(self, i: int) -> list[int]:
        return self.out_idx[self.out_start[i]:self.out_start[i + 1]].tolist()

    def upstream(self, i: int) -> list[int]:
        return self.in_idx[self.in_start[i]:self.in_start[i + 1]].tolist()


def _csr(a: np.ndarray, b: np.ndarray, n: int):
    order = np.argsort(a, kind="stable")
    counts = np.bincount(a, minlength=n)
    start = np.zeros(n + 1, dtype=np.int64)
    start[1:] = np.cumsum(counts)
    return start, b[order]


def load() -> Graph:
    OUT.mkdir(parents=True, exist_ok=True)
    return Graph()
