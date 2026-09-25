"""共通の指標。"""
from __future__ import annotations
import numpy as np

def make_cd(g):
    year = g.year
    def cd_index(i: int, horizon: int | None) -> float | None:
        """Funk & Owen-Smith の CD 指数(コーパス内の引用のみ)。horizon は年数、None なら無期限。"""
        refs = set(g.upstream(i))
        citers_i = set(g.downstream(i))
        citers_refs = set()
        for r in refs: citers_refs.update(g.downstream(r))
        later = {j for j in citers_i | citers_refs if year[j] > year[i]}
        if horizon is not None:
            later = {j for j in later if year[j] <= year[i] + horizon}
        if not later: return None
        n_i = sum(1 for j in later if j in citers_i and j not in citers_refs)
        n_j = sum(1 for j in later if j in citers_i and j in citers_refs)
        n_k = sum(1 for j in later if j not in citers_i)
        return (n_i - n_j) / (n_i + n_j + n_k)
    return cd_index
