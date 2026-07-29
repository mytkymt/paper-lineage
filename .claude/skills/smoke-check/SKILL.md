---
name: smoke-check
description: Post-change smoke checklist for the paper-lineage viewer. Use before committing viewer changes or after regenerating data/viz.
---

# Viewer smoke check

## 1. Parse (catches stray braces from string-patching — has bitten twice)

```bash
node -e "new (require('vm').Script)(require('fs').readFileSync('viewer/main.js','utf8')); console.log('parse OK')"
```

## 2. Serve and load

```bash
python3 -m http.server 8137   # from repo root
```

Open `/viewer/index.html`. Stats line must show paper/citation counts (not "Loading…"),
console must be clean.

## 3. Interactions (each one has broken at least once)

- **Search**: a paper query shows Related terms chips + paper list; a person query
  ("ishii") shows People rows with `papers · lineage N` / `no lineage`.
- **Pin/unpin**: click a person row → appears in legend; × in legend removes; 9th pin
  alerts instead of silently failing.
- **Isolate**: click a legend chip → other chips get `.off` **and points dim too**;
  re-click clears. Re-query the chip after each click (legend re-renders).
- **Lineage**: select a paper → panel shows authors (last author marked ◂) and
  "N of M references are inside this corpus". Zero in-corpus refs must show the
  corpus-boundary explanation, never a bare empty list.
- **Trend filter**: clicking a trend row keeps BOTH upstream and downstream of that
  sub-field; clicking a different row switches (must not AND to empty); re-click restores.
- **Hover during selection** only hits lineage nodes; clicking empty space clears
  selection and restores the camera.
- **Person focus (legend chip)**: hover/click only hits that person's papers (others are
  excluded, radius widened to 26px); their points render enlarged.
- **Axis-split zoom**: Shift+scroll must leave the year axis unchanged; Alt+scroll must
  leave bands unchanged.
- **Toggles**: Scope (any/last) changes line spread; Color venue/people swaps legend.
- **Color: Citation intent**: legend shows background/method/result counts **plus a
  coverage line** ("intents fetched for N of M citations"); with no `edge_intent.bin`
  the option is disabled and labeled "(no data)", never silently identical.
- **Re-cluster this lineage**: button in the lineage panel produces ≤8 local cluster
  rows with counts + TF-IDF labels, plus a "+N papers in M smaller clusters" line when
  anything is dropped; clicking a row filters BOTH directions (and clears any sub-band
  filter); re-click restores. Same lineage must give identical clusters every time.
- **Name clusters with AI**: prompts for an API key once (localStorage); names replace
  the TF-IDF labels; re-running on the same lineage must hit the localStorage cache
  (no network call — check the Network tab).
- Esc clears selection.

## 3.5 Testing pitfalls (each cost real time)

- **Module caching**: the pane caches `main.js` aggressively. `index.html` loads it as
  `main.js?v=N` — bump N on every edit, or you will debug stale code against fresh disk.
- **Hidden pane**: while the browser pane is hidden, `clientWidth/Height` can be 0 and
  rAF never fires. `render()` guards zero-size and `visibilitychange` reschedules, but
  **pick() tests are meaningless while hidden** (all coordinates degenerate) — take a
  screenshot first to force a visible frame, then test.
- **Re-query legend chips after every click** — the legend re-renders, detaching old nodes.
- `window.PL` exposes `pick`, `meta`, `nodeSlot()`, `isolated()`, `pinned()`,
  `screenPos(i)` for closure-internal verification.
- A "colored dot near a person's line" is not necessarily their paper — verify with
  `PL.meta.nodes[i]` before concluding a pick bug (CoDine looked like an Ishii dot;
  it is Adrian Cheok's).

## 4. Invariants

- Coordinate system is top-left origin everywhere (shader flips y; screenToNorm is the
  only inverse). Vertical pan/zoom/hover inverting means this broke.
- Edges accumulate in the HDR buffer + log tone map — never thin the data to fix density.
- Any display cap (top-N lists, highlight cap) must be labeled in the UI, never silent.
- Categorical colors: max 8 + "Other"; isolate/labels are the required secondary encoding.
- UI copy is English and neutral: say "lab lineage", not "self-citation".
