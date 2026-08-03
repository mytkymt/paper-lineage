# How lineage is computed

What happens when you click a paper, in the order it happens. Everything below is
deterministic — same corpus, same clicks, same result. Code:
[`viewer/main.js`](../viewer/main.js) (interactive parts) and
[`pipeline/src/paperlineage/`](../pipeline/src/paperlineage/) (precomputed parts).

## The citation graph

- **Corpus**: about 39,000 papers from 13 HCI venues (1981–2026), fetched from Semantic
  Scholar; references resolved via OpenAlex and joined by DOI.
- Records that are containers rather than papers are dropped before anything else:
  proceedings volumes, companion/adjunct volumes, Extended Abstracts volumes and
  "Session details:" dividers (about 900 entries). A venue search returns these as
  ordinary hits, and their citation counts are enormous — the 2017 CHI proceedings
  record alone showed 2,217 — so leaving them in put meaningless bright dots on the
  map. The test is the start of the title only; nothing is inferred from content.
- Only citations with **both ends inside the corpus** are kept — roughly 380,000 edges.
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

Both are bounded by the **Depth** slider (default 2 hops; "all" = unbounded —
safe because the graph is acyclic). The union of the two sets plus the paper
itself is the lineage; everything else dims.

## Reading a year column

Within one year, each venue sits at its own x, and papers from the same venue
and year share that x exactly — they are not spread around it, so venues read as
clean columns and the gap between years stays visible. The columns are evenly
spaced in the order the venues usually happen (TEI, IUI, CHI, … UIST, CSCW,
TOCHI). The spacing is even rather than proportional to the calendar because
most HCI conferences fall between September and November, which would crowd them
into an unreadable clump; what the axis carries is the order, not the date. The
layout is identical in every year and fully deterministic.

## Trend breakdown (side panel)

Every paper belongs to one of 117 **sub-fields**, precomputed by two-level
Louvain community detection ([Blondel et al., 2008](https://doi.org/10.1088/1742-5468/2008/10/P10008))
on the full citation graph (14 top-level bands, nested sub-bands; fixed seed —
plain Louvain is order-sensitive, so node order and seeds are pinned to keep the
partition reproducible). The panel counts how many lineage papers fall in
each sub-field, split into upstream ← / downstream → (the arrows match the map,
where time runs left to right), and draws the ratio bars
from those counts. Clicking a row filters the lineage to that sub-field — in
both directions at once.

## Local clusters

The global sub-fields describe the whole map; local clusters re-ask the question
for one lineage only. Computed automatically on every selection:

1. Take the subgraph induced by the lineage papers, **excluding edges that touch
   the selected paper** (the hub connects to everything by construction and
   would glue all clusters together).
2. Run Louvain ([Blondel et al., 2008](https://doi.org/10.1088/1742-5468/2008/10/P10008))
   on that subgraph (a single pass over the whole edge list to extract it — a few tens
   of ms).
3. Keep clusters with ≥ 3 papers, up to 8; anything dropped is reported as
   "+N papers in M smaller clusters".
4. Label each cluster with its top TF-IDF title terms
   ([Spärck Jones, 1972](https://doi.org/10.1108/eb026526); IDF over the whole
   corpus). Optional LLM naming replaces these labels using your own API key,
   cached in your browser's localStorage.

## Lab threads

A citation is a **lab edge** when the same person is last author on both ends —
the person cited work they themselves led. The panel reports the **depth** of that
line (the longest chain of such citations, computed by dynamic programming over the
DAG) rather than a raw link count: 58% of people who have any lab edge have a chain
of just two papers, while a sustained line runs 10+ generations.
When you pin people (up to 15), each edge is tested against the pinned set with a
per-person bitmask; the Scope toggle switches between "any authorship" and
"last-author only" for both points and lines. Focusing people narrows the map to
that subset — the same bitmask goes to the shader, so any number of them can be
lit at once. A focused person's papers keep their colour inside a lineage view as
well, where direction is still readable from position. **Lines** (in Appearance) turns every
citation line off, leaving the points as the only encoding — the lineage still
reads as upstream to the left and downstream to the right.

## Edge brightness

Edge weights are **search path counts** (SPC / main path analysis): how many
source-to-sink paths in the DAG pass through each edge, computed by dynamic
programming in log space. Main path analysis is due to
[Hummon & Doreian (1989)](https://doi.org/10.1016/0378-8733(89)90017-8); the SPC
weight is [Batagelj (2003)](https://arxiv.org/abs/cs/0309023). Bright routes are the field's main paths, not just
high-degree nodes. Rendering accumulates all edges in an HDR buffer with log
tone-mapping, so density differences stay visible without thinning the data.

## References

- V. Blondel, J.-L. Guillaume, R. Lambiotte, E. Lefebvre (2008).
  *Fast unfolding of communities in large networks.* J. Stat. Mech.
  [doi:10.1088/1742-5468/2008/10/P10008](https://doi.org/10.1088/1742-5468/2008/10/P10008)
- N. P. Hummon, P. Doreian (1989). *Connectivity in a citation network: The
  development of DNA theory.* Social Networks 11(1).
  [doi:10.1016/0378-8733(89)90017-8](https://doi.org/10.1016/0378-8733(89)90017-8)
- V. Batagelj (2003). *Efficient algorithms for citation network analysis.*
  [arXiv:cs/0309023](https://arxiv.org/abs/cs/0309023)
- K. Spärck Jones (1972). *A statistical interpretation of term specificity and
  its application in retrieval.* Journal of Documentation 28(1).
  [doi:10.1108/eb026526](https://doi.org/10.1108/eb026526)
