"""帯・サブ帯の名前を、前回ビルドから**所属論文の重なり**で引き継ぐ。

名前をキーワード署名(TF-IDF 上位語)で照合していた頃は、論文が少し増減する
だけで署名がずれ、再ビルドのたびに百件単位で名前が外れていた。名前が指して
いるのはキーワードではなくクラスタ(論文の集まり)なので、前回のどのクラスタと
中身が重なっているかで引き継ぐ。無人更新でも名前が保たれるようにするのが目的。

優先順位:
  1. 前回ビルドのクラスタと Jaccard が閾値以上 → その名前を引き継ぐ(1対1)
  2. viewer/band-names.json の署名に一致 → その名前(手で付けた名前の種)
  3. どちらも無い → キーワードから機械的に作る("A, B & C")
最後に band-names.json の "rename" {旧名: 新名} を適用する(手で改名したいとき用)。
名前は帯とサブ帯を通して重複させない(重複したら小さい方に識別語を足す)。
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NAMES_PATH = ROOT / "viewer" / "band-names.json"
MIN_JACCARD = 0.30      # これ未満は別のクラスタとみなして引き継がない


def _sig(o: dict, k: int) -> str:
    return "|".join((o.get("keywords") or [])[:k])


def _seed_tables() -> tuple[dict, dict, dict, dict, dict]:
    if not NAMES_PATH.exists():
        return {}, {}, {}, {}, {}
    data = json.loads(NAMES_PATH.read_text())

    def mk(entries: list[dict] | None) -> tuple[dict[str, str], dict[str, str]]:
        b5: dict[str, str] = {}
        b3: dict[str, str] = {}
        for e in entries or []:
            if e.get("sig5"):
                b5[e["sig5"]] = e["name"]
            elif e.get("sig"):
                b3[e["sig"]] = e["name"]
        return b5, b3

    band5, band3 = mk(data.get("bands"))
    sub5, sub3 = mk(data.get("subbands"))
    return band5, band3, sub5, sub3, data.get("rename") or {}


def _seed_name(o: dict, is_sub: bool, tables: tuple) -> str | None:
    band5, band3, sub5, sub3, _ = tables
    if is_sub:
        return (sub5.get(_sig(o, 5)) or sub3.get(_sig(o, 3))
                or band5.get(_sig(o, 5)) or band3.get(_sig(o, 3)))
    return band5.get(_sig(o, 5)) or band3.get(_sig(o, 3))


def _auto_name(o: dict) -> str:
    kws = [k for k in (o.get("keywords") or []) if k and not k.startswith("(")][:3]
    words = [k.replace("-", " ").title().replace(" ", "-") if "-" in k else k.title() for k in kws]
    if not words:
        return "Unnamed"
    if len(words) == 1:
        return words[0]
    return ", ".join(words[:-1]) + " & " + words[-1]


def _old_clusters(prev_meta: dict, tables: tuple) -> tuple[list[tuple[str, set[str]]], list[tuple[str, set[str]]]]:
    """前回ビルドの (名前, 所属DOI集合) を帯・サブ帯それぞれ返す。"""
    nodes = prev_meta.get("nodes") or []
    subs = prev_meta.get("subbands") or []
    bands = prev_meta.get("bands") or []
    sub_members: dict[int, set[str]] = defaultdict(set)
    for nd in nodes:
        s = nd.get("s", -1)
        if s is not None and s >= 0 and nd.get("d"):
            sub_members[s].add(nd["d"])
    old_subs = []
    for si, sb in enumerate(subs):
        name = sb.get("name") or _seed_name(sb, True, tables)
        if name and sub_members.get(si):
            old_subs.append((name, sub_members[si]))
    old_bands = []
    for bi, b in enumerate(bands):
        if b.get("community") is None:
            continue
        name = b.get("name") or _seed_name(b, False, tables)
        members: set[str] = set()
        for si in b.get("subbands") or []:
            members |= sub_members.get(si, set())
        if name and members:
            old_bands.append((name, members))
    return old_bands, old_subs


def _carry(new: list[tuple[int, set[str]]], old: list[tuple[str, set[str]]]) -> dict[int, str]:
    """Jaccard の高い順に 1対1 で名前を割り当てる。"""
    where: dict[str, list[int]] = defaultdict(list)     # DOI -> 旧クラスタ番号
    for oi, (_, members) in enumerate(old):
        for d in members:
            where[d].append(oi)
    pairs: list[tuple[float, int, int]] = []
    for ni, members in new:
        hits: Counter[int] = Counter()
        for d in members:
            for oi in where.get(d, ()):
                hits[oi] += 1
        for oi, inter in hits.items():
            jac = inter / (len(members) + len(old[oi][1]) - inter)
            if jac >= MIN_JACCARD:
                pairs.append((jac, ni, oi))
    pairs.sort(key=lambda t: (-t[0], t[1], t[2]))
    out: dict[int, str] = {}
    used_old: set[int] = set()
    for _, ni, oi in pairs:
        if ni in out or oi in used_old:
            continue
        out[ni] = old[oi][0]
        used_old.add(oi)
    return out


def assign_names(
    bands: list[dict],
    subbands: list[dict],
    band_members: dict[int, list[str]],
    sub_members: dict[int, list[str]],
    prev_meta: dict | None,
) -> dict[str, int]:
    """bands / subbands に "name" を書き込む。戻り値は由来ごとの件数。

    band_members は bands の添字 -> DOI のリスト、sub_members は subbands の添字 -> DOI。
    """
    tables = _seed_tables()
    rename = tables[4]
    old_bands, old_subs = _old_clusters(prev_meta, tables) if prev_meta else ([], [])
    carried_b = _carry([(i, set(m)) for i, m in band_members.items()], old_bands)
    carried_s = _carry([(i, set(m)) for i, m in sub_members.items()], old_subs)

    stats: Counter[str] = Counter()
    for is_sub, items, carried in ((False, bands, carried_b), (True, subbands, carried_s)):
        for i, o in enumerate(items):
            if not is_sub and o.get("community") is None:
                continue      # 孤立ノードの疑似バンドは名前を持たない
            if i in carried:
                o["name"], src = carried[i], "carried"
            else:
                seed = _seed_name(o, is_sub, tables)
                if seed:
                    o["name"], src = seed, "seed"
                else:
                    o["name"], src = _auto_name(o), "auto"
            o["name"] = rename.get(o["name"], o["name"])
            stats[src] += 1

    # 重複を解く: 大きい方が名前を保ち、小さい方に識別語を足す
    named = [o for o in bands if o.get("name")] + [o for o in subbands if o.get("name")]
    named.sort(key=lambda o: -(o.get("papers") or 0))
    taken: set[str] = set()
    for o in named:
        if o["name"] not in taken:
            taken.add(o["name"])
            continue
        base = o["name"]
        for kw in (o.get("keywords") or []):
            cand = f"{base} ({kw})"
            if cand not in taken:
                o["name"] = cand
                break
        else:
            n = 2
            while f"{base} {n}" in taken:
                n += 1
            o["name"] = f"{base} {n}"
        taken.add(o["name"])
        stats["deduped"] += 1
    return dict(stats)
