# HCI Research Trails

**Live: https://hci-research-trails.vercel.app**

An interactive map of HCI research — **about 39,000 papers and 380,000 citations
from 13 major venues (1981–2026)**, laid out along time on a single WebGL canvas.
A toggle adds seven neighbouring venues, taking it to about 47,000 papers.
Research areas appear as named horizontal bands; citations flow left to right.

![Overview](docs/media/overview.png)

## 1. Trace a paper's lineage

![A paper's lineage](docs/media/trail-paper.png)

- Click any paper: everything it builds on (upstream) and everything that later built
  on it (downstream) lights up.
- The side panel breaks the lineage down by research trend, with upstream:downstream
  ratio bars — click a trend to filter the view to it.
- **Local clusters** split the lineage by its own citation structure — UltraHaptics'
  descendants, for instance, resolve into branches like VR haptics, mid-air
  ultrasound, EMS and levitation.
- Right-click a paper for DOI and copy actions.
- **Lock view** freezes the highlight, so you can click through other papers and read
  each one's panel while the map keeps showing the lineage you are comparing against.
- How all of this is computed: [docs/lineage.md](docs/lineage.md).

## 2. Follow people

![People and their lab threads](docs/media/trail-person.png)

- Search names to add them to the legend (up to 15 people).
- Click them and their papers light up across the map, with same-lab citations (same
  last author at both ends) drawing the lab's thread through the decades.
- Focus one or several people: only their papers stay bright, and the panel shows each
  person's sub-fields and most cited work side by side.
- A toggle switches between "any authorship" and "last-author only".

## 3. Explore the field

![Sub-fields opening under zoom](docs/media/trail-field.png)

- 14 bands and 117 sub-fields, all named; labels appear as you zoom.
- Browse them all from the **Fields tree** (or search them by name): selecting a field
  highlights its papers and lists both its most cited work and everyone publishing in it.
- **Shift+scroll zooms topics without stretching time**; Alt+scroll zooms time only.
- Search any topic ("haptic", "fabrication") to see where and when it lives on the map,
  with related-term suggestions.
- Colour by people & labs, or by venue.

## Share what you are looking at

**Share** offers the plain link by default. Tick "Link to this view" and it also
carries the selected paper, the people and the camera — a particular lineage can be
sent to a co-author or cited in a talk.

## Tutorial

![Tour](docs/media/tour.gif)

The **Tutorial** link in the panel plays a walkthrough:
[docs/media/tutorial.mp4](docs/media/tutorial.mp4)

## Reading the map

- **x-axis = publication year.** Citations only ever flow left to right.
- **Bands = citation communities**, sized by paper count.
- **Bright routes = main paths** (edges weighted by search path count).
- **Dot size = citations.** Colour belongs to the people you have selected.

## Data notes

Corpus: CHI, PACM HCI, UIST, DIS, ASSETS, IUI, CSCW, TEI, IMWUT, UbiComp, CHI PLAY,
MobileHCI, TOCHI. A **Related venues** toggle adds HRI, IEEE VR, ISMAR, SIGGRAPH,
TOG, IJHCS and IEEE ToH — partially: only papers with at least one citation link to
the core corpus are included, and the UI marks them as such. About 75% of references point outside these venues and are excluded —
the UI states this wherever it limits what you see (an empty upstream list means the
paper cites work outside the corpus, not missing data). Band names are LLM-generated
once and committed; everything else is computed deterministically from citation data.

## Running locally

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
uv run python -m paperlineage.build_graph
uv run python -m paperlineage.spc
uv run python -m paperlineage.layout --mode community
```

Every stage is deterministic (fixed seeds) and reports everything it drops.

**Want this map for your own field?** The venue list is the only HCI-specific
part — see [docs/build-your-own.md](docs/build-your-own.md).

## Documentation

[How lineage is computed](docs/lineage.md) explains the algorithms;
[build a map for your own field](docs/build-your-own.md) covers adapting the
pipeline to another research area.
The repository / development name is `paper-lineage`.

## License

MIT
