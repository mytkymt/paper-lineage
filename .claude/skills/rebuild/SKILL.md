---
name: rebuild
description: Rebuild the paper-lineage data pipeline (corpus → graph → SPC → layout) and refresh viewer data. Use after pipeline code changes, venue/corpus changes, or when data/viz is stale.
---

# Rebuild the pipeline

Run stages from `pipeline/` with `uv run python -m paperlineage.<stage>`. Only rerun from the
earliest stage whose inputs changed — later stages are cheap, earlier ones hit rate-limited APIs.

| Stage | Command | Rerun when | Cost |
|---|---|---|---|
| 1 | `fetch_corpus` | venues.py changed | ~10 min (S2, resumes per venue) |
| 2 | `fetch_refs` | corpus changed | ~40 min (OpenAlex, resumes per DOI) |
| 3 | `build_graph` | works.jsonl changed | seconds |
| 4 | `spc` | graph changed | seconds |
| 5 | `bundles` | spc changed (optional analysis) | seconds |
| 6 | `layout --mode community` | graph/spc changed, or any label/meta change in layout.py | ~9 s |

Most edits (labels, keywords, bands, lab/author tables) only need stage 6.

## Invariants — check the printed output

- `build_graph` prints dropped-edge counts (external / backward / same-year). **Backward+cycle
  drops must stay well under 1%** of refs; a jump means the year data or ordering broke.
- `spc` prints the global main path. Skim it — it must still read as a coherent 44-year thread.
  If it looks random, the DAG ordering is broken; do not proceed to layout.
- `layout` prints band/sub-band summaries and the lab table. Band keywords should read as
  HCI sub-fields; top labs should be recognisable PIs.
- Everything is deterministic (fixed seeds). Same inputs ⇒ byte-identical outputs; if a diff
  appears without an input change, something is wrong.

After stage 6, verify in the browser with the `smoke-check` skill.
