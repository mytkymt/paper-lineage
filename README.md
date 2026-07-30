# HCI Research Trails

**Live: https://hci-research-trails.vercel.app**

A research field is a story told across decades — but we usually read it one paper at a
time. HCI Research Trails draws the whole story at once: **45 years of human–computer
interaction research (38,791 papers, 371,893 citations, 13 major venues)** on a single
map, laid out along time. Research areas appear as horizontal bands, and the trails
running through them are ideas being passed from paper to paper, year after year.

There are three kinds of trails to follow.

## 1. A paper's trail — where an idea came from, and what it became

Click any paper. Everything it built on lights up to the left; everything that later
built on it fans out to the right, with a breakdown of which research trends each side
belongs to.

Try *Tangible Bits* (1997): it draws on 14 papers in the corpus and has **5,124
descendants** — you can watch one CHI paper turn into tangible interaction, then
shape-changing interfaces, e-textiles, and digital fabrication over 25 years. Or take
*UltraHaptics* (2013) and hit **Re-cluster**: its 708 descendants split into seven
distinct branches — VR haptic feedback, mid-air ultrasound, electrical muscle
stimulation, acoustic levitation, swarm-robot haptics — a map of every direction one
idea scattered into.

## 2. A person's trail — a lab's thread through the decades

Search a name, pin it to a colour. That person's papers surface across the map, and the
citations that stay within their group (same last author at both ends) are drawn as a
continuous thread — a lab's own storyline inside the field.

Pin Hiroshi Ishii and a single orange thread runs through the tangible-interaction band
from 1997 to 2022. Pin up to eight people — advisors, collaborators, or a field's key
figures — and compare how their trails run parallel, cross, or diverge. A toggle switches
between "everything they co-authored" and "their lab's own line".

## 3. The field's trail — watching research areas be born

Zoom out and the bands tell the macro story: when games research became its own
community, when accessibility grew from a corner into a major area, when the AI band
suddenly thickens. Zoom in (Shift+scroll expands topics without stretching time) and each
band opens into named sub-fields — the sensing band alone splits into activity
recognition, gaze, text entry, on-body sensing, and more.

Band and sub-field names are generated once by an LLM from the underlying clusters and
committed to the repo; everything else on the map is computed deterministically from
citation data alone.

## Reading the map

- **x-axis = publication year.** Citations only ever flow left to right.
- **Bands = citation communities** (Louvain), sized by paper count, named.
- **Bright routes = main paths** — edges weighted by how much of the field's knowledge
  flow passes through them (search path count).
- **Dot size = citations.** Colours belong to the people you pin.

## Honest edges

The corpus is 13 HCI venues: CHI, PACM HCI, UIST, DIS, ASSETS, IUI, CSCW, TEI, IMWUT,
UbiComp, CHI PLAY, MobileHCI, TOCHI. About 75% of all references point *outside* these
venues (psychology, ML, systems, books) and are excluded — the UI says so explicitly
whenever it limits what you see. An empty upstream list means "this paper cites work
outside HCI's venues", never "no data". Display caps are always labeled.

## Running locally

The viewer is a static WebGL2 page; the pipeline is offline Python.

```bash
# Serve the repo root, then open /viewer/index.html
python3 -m http.server 8137
```

The committed `data/viz/` is all the viewer needs. To rebuild from the public APIs
(Semantic Scholar for the corpus, OpenAlex for citations):

```bash
cd pipeline
uv run python -m paperlineage.fetch_corpus    # ~10 min, resumable
uv run python -m paperlineage.fetch_refs      # ~40 min, resumable
uv run python -m paperlineage.build_graph     # cycle-free citation DAG
uv run python -m paperlineage.spc             # main-path edge weights
uv run python -m paperlineage.layout --mode community
```

Every stage is deterministic (fixed seeds) and reports everything it drops.

## Documentation

Design notes and the decision log live in Japanese under `docs/` —
[scope](docs/scope.md), [algorithms](docs/algorithms.md), [prior art](docs/prior-art.md),
[data sources](docs/data-sources.md), [dev notes](docs/dev-notes.md) (newest first).
The repository / development name is `paper-lineage`.

## License

MIT
