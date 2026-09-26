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
OUT = ROOT / "analysis" / "results" / (os.environ.get("PL_TAG") or ("ext" if EXT else "core"))
# 会場集合の頑健性チェック用: PL_VENUES=chi,uist,... で、その会場の論文だけに絞る(辺・SPC・サブ帯も絞る)。
VENUES = {v for v in (os.environ.get("PL_VENUES") or "").split(",") if v}


class Graph:
    def __init__(self) -> None:
        self.meta = json.loads((VIZ / "meta.json").read_text())
        rows = [json.loads(l) for l in (GRAPH / "nodes.jsonl").open()]
        if VENUES:
            rows = [r for r in rows if r.get("venue_key") in VENUES]
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
            if a not in self.idx or b not in self.idx:
                continue          # 会場で絞ったときに外に出た辺
            src.append(self.idx[a]); dst.append(self.idx[b])
        self.cited = np.array(src, dtype=np.int64)    # 古い側
        self.citing = np.array(dst, dtype=np.int64)   # 新しい側
        spc = {}
        for l in (GRAPH / "spc.tsv").open():
            a, b, s = l.rstrip("\n").split("\t")
            if a in self.idx and b in self.idx:
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
        self.corpus_by_year = {int(y): int(c) for y, c in zip(*np.unique(self.year, return_counts=True))}

    def birth(self, members: np.ndarray) -> int:
        return birth_year(self.year[members], self.corpus_by_year)

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


def birth_year(years: np.ndarray, corpus_by_year: dict[int, int]) -> int:
    """立ち上がりの年: 3 年窓の本数が 3T 以上で、次の 3 年窓も 3T 以上になる最初の年。

    T はその年のコーパス規模の 0.5%(下限 2、上限 5)。1990 年ごろはコーパスが年 120 本
    なので T=2、2010 年以降は T=5。年ごとの本数で見ると隔年開催(2010 年までの CSCW)の
    空白年で切れるので 3 年窓の合計で見る。「次の窓も」の条件で一過性の山を除く。
    以前の「5 本または 2% に達した年」は、後年の帯に混ざった古い論文を拾って誕生が
    10 年早く出ることがあった。どの窓も条件を満たさない小さな帯は、最初の窓だけで判定する。
    """
    years = np.asarray(years); y0 = int(years.min())
    counts = np.bincount(years - y0)
    padded = np.concatenate([counts, np.zeros(4, dtype=counts.dtype)])
    def T(y: int) -> int:
        return int(max(2, min(5, np.ceil(0.005 * corpus_by_year.get(y, 0)))))
    for k in range(len(counts)):
        y = y0 + k
        if counts[k] and padded[k:k + 3].sum() >= 3 * T(y) and padded[k + 1:k + 4].sum() >= 3 * T(y + 1):
            return y
    for k in range(len(counts)):
        y = y0 + k
        if counts[k] and padded[k:k + 3].sum() >= 3 * T(y):
            return y
    return y0
