# CLAUDE.md — paper-lineage

Field-scale, time-monotone citation map for HCI (13 venues, ~39k papers). See README.md
for the idea; **docs-dev/dev-notes.md (newest entries on top) for every decision and its
reason** — read it before changing layout, colours, or lineage semantics.
`docs-dev/` is local-only (git-ignored): the public repo is English-only, the Japanese
decision log stays here.

## Working here

- **Pipeline**: offline Python in `pipeline/` — use the `rebuild` skill for stage order,
  what to rerun, and output invariants. Data dirs (`data/`) are git-ignored and reproducible.
- **Viewer**: static WebGL2 in `viewer/` (no build step). Serve repo root on :8137.
  Verify changes with the `smoke-check` skill before committing.

## Conventions (all have a reason in dev-notes)

- **Determinism**: fixed seeds everywhere; same inputs ⇒ identical outputs.
- **No silent truncation**: dropped edges, display caps, merged clusters — always surface
  the count in output or UI.
- **Empty lineage = corpus boundary, not missing data** — the UI must say so explicitly.
- **Colour**: position already encodes time+topic, so colour encodes *who* (pinned people /
  lab lineage). Pinned-people palette allows up to 15 + "Other" (a deliberate product
  decision); at that width the secondary encoding (isolate, legend labels) is mandatory,
  not optional. Other categorical uses stay at max 8.
- **Coordinates**: normalized top-left origin end-to-end; `screenToNorm()` is the only
  screen→data inverse. Canvas needs explicit CSS `width/height` (replaced element).
- **Language & tone**: UI copy in English, neutral phrasing — "lab lineage", never
  "self-citation". Everything committed (docs/, README) is English; Japanese notes go
  to the untracked docs-dev/.
- When patching `viewer/main.js` by string replacement, keep spans minimal and re-run the
  parse check — over-wide spans have deleted neighbouring listeners twice.
