# HCI Research Trails

**Live: https://hci-research-trails.vercel.app**

A field-scale, time-monotone citation map. Instead of exploring a few dozen papers around
one seed, it draws an entire field at once — currently **38,791 papers and 371,893
citations across 13 HCI venues (1981–2026)** — and lets you read the *trails*: the trends
a paper builds on, the trends it created, and the threads individual labs have been
weaving through the field for decades.

(The repository / development name is `paper-lineage`.)

## Why another literature map?

Tools like Connected Papers use similarity-based force-directed layouts, which collapse
the time dimension. But citations have a property no other network has: **they only ever
point backwards in time**. This tool makes that constraint the backbone of the layout —
time is a fixed axis, and every citation flows left to right. What emerges are horizontal
bands of research communities and the visible threads running through them.

- **Time-monotone layout** — x is publication year, always. Communities (Louvain over the
  citation graph) get horizontal bands proportional to their size; sub-fields nest inside.
- **Main-path weighting** — edge brightness uses SPC (search path count), so the trunk
  routes of knowledge flow glow through the haze of 370k citations.
- **Lineage tracing** — click a paper to see everything it (transitively) draws on and
  everything that later built on it, with a breakdown of which trends each side belongs
  to, and on-demand re-clustering of the lineage's own internal branches.
- **People as first-class citizens** — search a person, pin them to a colour, and see
  their papers and their lab's own citation thread (same last author at both ends)
  drawn across the decades.
- **Everything is precomputed and static** — the viewer is a single WebGL2 page reading
  ~15 MB of binary layout data. No server, no API keys, no tracking.

## Running locally

The viewer is static; the pipeline is offline Python.

```bash
# Serve the repo root and open /viewer/index.html
python3 -m http.server 8137
```

Committed data in `data/viz/` is enough to run the viewer. To rebuild the data from the
public APIs (Semantic Scholar for the corpus, OpenAlex for citations):

```bash
cd pipeline
uv run python -m paperlineage.fetch_corpus    # ~10 min, resumable
uv run python -m paperlineage.fetch_refs      # ~40 min, resumable
uv run python -m paperlineage.build_graph     # cycle-free citation DAG
uv run python -m paperlineage.spc             # main-path (SPC) edge weights
uv run python -m paperlineage.layout --mode community   # bands, labels, binary outputs
```

Every stage is deterministic (fixed seeds) and prints what it dropped — nothing is
truncated silently.

## Corpus

CHI, PACM HCI, UIST, DIS, ASSETS, IUI, CSCW, TEI, IMWUT, UbiComp, CHI PLAY, MobileHCI,
TOCHI. Citations that point outside these venues (~75% of all references) are excluded,
and the UI says so wherever it matters — an empty upstream list means the paper cites
work outside the corpus, not missing data.

## Documentation

Design notes and decision logs are in Japanese under `docs/`:

- [docs/scope.md](docs/scope.md) — what this is and is not
- [docs/algorithms.md](docs/algorithms.md) — layout candidates, SPC, attribution
- [docs/prior-art.md](docs/prior-art.md) — existing tools and how this differs
- [docs/data-sources.md](docs/data-sources.md) — S2 / OpenAlex split and pitfalls
- [docs/dev-notes.md](docs/dev-notes.md) — dated decision log (newest first)

## License

MIT
