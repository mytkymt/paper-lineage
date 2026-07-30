# Build a map for your own field

The pipeline is not HCI-specific — the venue list is the only thing that defines
the field. Swapping it rebuilds everything else (graph, main paths, bands,
layout) deterministically.

Prerequisites: Python 3.12+ with [uv](https://docs.astral.sh/uv/), ~1 GB disk
for raw data. A [Semantic Scholar API key](https://www.semanticscholar.org/product/api)
(`export S2_API_KEY=...`) is optional but strongly recommended — without it the
fetch stages throttle hard. Set a contact email for the OpenAlex polite pool in
`pipeline/src/paperlineage/openalex.py`.

## 1. List your venues and probe their exact names

Semantic Scholar matches on its own normalized venue strings, and guessing them
wrong silently returns 0 papers. So: replace the `VENUES` table in
[`pipeline/src/paperlineage/venues.py`](../pipeline/src/paperlineage/venues.py)
with your venues — one `Venue(key, s2_name, label, approx_total, probe_doi=...)`
per venue, where `s2_name` is your best guess and `probe_doi` is the DOI of any
one paper from that venue. Then check the guesses:

```bash
cd pipeline
uv run python -m paperlineage.probe_venues
```

For each venue it resolves the probe DOI, prints the `venue` string S2 actually
stores plus the bulk-search hit count, and flags `DIFF` where your guess was
wrong — paste the printed `actual` value back into `s2_name` until every row
reads `OK` with a plausible total.

Pick venues that cite each other — the map is built from **within-corpus**
citations, so a corpus of venues that don't interact produces a sparse map.
10–15 venues / 20k–50k papers is the scale this layout is tuned for.

Two gotchas the probe output helps with (details in
[data-sources.md](data-sources.md), Japanese):

- Venue names containing commas break the S2 bulk-search parameter (it's a
  comma-separated list); the pipeline strips commas automatically, but verify
  the probed count is non-zero.
- Venues that renamed or split (like CSCW → PACM HCI in 2017) need both names.

## 2. Run the pipeline

```bash
cd pipeline
uv run python -m paperlineage.fetch_corpus    # S2 metadata; resumable per venue
uv run python -m paperlineage.fetch_refs      # OpenAlex references; resumable per DOI
uv run python -m paperlineage.build_graph
uv run python -m paperlineage.spc
uv run python -m paperlineage.layout --mode community
```

For ~40k papers the fetches take tens of minutes; everything after runs in
seconds. Both fetch stages can be interrupted and rerun — they resume where
they stopped.

**Check what each stage prints** (see `.claude/skills/rebuild/SKILL.md` for the
full invariants):

- `build_graph` reports dropped edges (external / backward / same-year).
  Backward+cycle drops above ~1% mean the year data is broken.
- `spc` prints the global main path — it should read as a coherent thread
  through your field's history. If it looks random, stop and investigate.
- `layout` prints band keywords and the top-lab table — bands should read as
  recognizable sub-fields, labs as recognizable PIs.

Outputs land in `data/viz/` (a few binary arrays + `meta.json`), which is all
the viewer reads.

## 3. Serve

```bash
# from the repo root
python3 -m http.server 8137
# open http://localhost:8137/viewer/index.html
```

Update the title/counts in `viewer/index.html` and the corpus description in
`README.md` to match your field.

## 4. Name the bands (optional)

Fresh bands are labeled by their top keywords. Human-readable names live in
`viewer/band-names.json`: each entry is keyed by the band's keyword signature,
so stale names fall back to keywords instead of mislabeling. To name your
bands, paste the keyword lists that `layout` prints into any LLM (or write
names yourself) and fill the same JSON shape. Names are generated once and
committed — the viewer never calls an LLM at runtime for these.

## Notes

- The pipeline uses only public APIs within their terms (S2 bulk search,
  OpenAlex works), no scraping. Keep `mailto` set so OpenAlex keeps you in the
  polite pool.
- Raw fetched data stays in `data/` (git-ignored); only `data/viz/` is meant to
  be committed/deployed.
- Everything is seeded and deterministic: rerunning without input changes gives
  byte-identical outputs.
