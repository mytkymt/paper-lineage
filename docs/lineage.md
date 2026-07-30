# How lineage is computed

What happens when you click a paper, in the order it happens. Everything below is
deterministic — same corpus, same clicks, same result. Code:
[`viewer/main.js`](../viewer/main.js) (interactive parts) and
[`pipeline/src/paperlineage/`](../pipeline/src/paperlineage/) (precomputed parts).

## The citation graph

- **Corpus**: 38,791 papers from 13 HCI venues (1981–2026), fetched from Semantic
  Scholar; references resolved via OpenAlex and joined by DOI.
- Only citations with **both ends inside the corpus** are kept — 371,893 edges.
  About 75% of references point outside the 13 venues and are excluded; the UI
  says so wherever this limits what you see.
- Edges are forced into a **time-monotone DAG**: papers are totally ordered by
  `(year, id)`, and any edge pointing backward or within the same position is
  dropped (the build prints the drop counts; they stay well under 1%). This is
  why citations only ever flow left → right, and why every traversal below
  terminates.

## Upstream / downstream (the click)

Selecting a paper runs two breadth-first searches from it:

- **Upstream** — follow incoming citation edges backwards: everything the paper
  builds on, transitively.
- **Downstream** — follow outgoing edges forwards: everything that later built
  on it.

Both are bounded by the **Depth** slider (default 1 hop; "all" = unbounded —
safe because the graph is acyclic). The union of the two sets plus the paper
itself is the lineage; everything else dims.

## Trend breakdown (side panel)

Every paper belongs to one of 117 **sub-fields**, precomputed by two-level
Louvain community detection on the full citation graph (14 top-level bands,
nested sub-bands; fixed seed). The panel counts how many lineage papers fall in
each sub-field, split into upstream ↑ / downstream ↓, and draws the ratio bars
from those counts. Clicking a row filters the lineage to that sub-field — in
both directions at once.

## Local clusters

The global sub-fields describe the whole map; local clusters re-ask the question
for one lineage only. Computed automatically on every selection:

1. Take the subgraph induced by the lineage papers, **excluding edges that touch
   the selected paper** (the hub connects to everything by construction and
   would glue all clusters together).
2. Run Louvain on that subgraph (single pass over all 372k edges to extract it —
   a few tens of ms).
3. Keep clusters with ≥ 3 papers, up to 8; anything dropped is reported as
   "+N papers in M smaller clusters".
4. Label each cluster with its top TF-IDF title terms (IDF over the whole
   corpus). Optional LLM naming replaces these labels using your own API key,
   cached in your browser's localStorage.

## Lab threads

A citation is a **lab edge** when the same person is last author on both ends.
When you pin people (≤ 8), each edge is tested against the pinned set with a
per-person bitmask; the Scope toggle switches between "any authorship" and
"last-author only" for both points and lines.

## Edge brightness

Edge weights are **search path counts** (SPC / main path analysis): how many
source-to-sink paths in the DAG pass through each edge, computed by dynamic
programming in log space. Bright routes are the field's main paths, not just
high-degree nodes. Rendering accumulates all edges in an HDR buffer with log
tone-mapping, so density differences stay visible without thinning the data.
