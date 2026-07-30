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
- **Selection centering**: selecting a paper pans it to the center of the area left
  of the lineage panel — zoom must NOT change (`PL.cam.zx/zy` unchanged); drag or
  wheel mid-animation interrupts the pan. While the pane is hidden the pan is
  deferred and fires on visibilitychange.
- **Person focus (legend chip)**: hover/click only hits that person's papers (others are
  excluded, radius widened to 26px); their points render enlarged. **Co-authored papers
  must stay clickable and coloured under EVERY co-author's isolate**, not just the
  earliest-pinned one (slot assignment must prefer the isolated person's bit).
- **Search hover**: while search highlights are active, hover/click only hits matched
  papers; clearing the search restores normal picking.
- **Fields tree**: 14 band rows (pseudo "no-links" band excluded); band click expands
  subs AND selects (highlight + right-panel top-cited list); sub click narrows; re-click
  clears; map band/sub labels are clickable to the same action; while a field is
  selected hover/click hits only member papers; drilling into a paper switches to the
  normal lineage view; Esc order is tutorial overlay → menu → paper selection → field.
- **Field panel sections**: two collapsible `details.fold` blocks, each with an
  inner scroll area — "Most cited" (top 30, "… N more" line) and
  "Authors — click to pin a color (N)" listing ALL authors (no cap; ~9k rows on the
  biggest band renders in ~55ms); BOTH default closed on a fresh field selection;
  fold open/closed state survives only the re-render caused by a pin toggle.
  Author rows (and search People rows) pin/unpin ONLY — they must NOT open the
  author panel (15-limit alert unchanged).
- **Author panel** opens ONLY from the bottom legend: clicking a pinned person's
  chip isolates them AND shows their panel — paper count, year range, last-author
  count, lab-lineage links, Fields list (top 10 of N, click drills into the field),
  Papers list (scrollable, cap labeled). Re-clicking the chip clears the isolate
  and closes the panel; the "Other labs" chip isolates without a panel. Clicking a
  paper switches to the normal paper panel; Esc closes the author panel first and
  restores the field panel (folds closed) if a field was selected. Author chips
  inside the PAPER panel keep the old behaviour (pin + stay on the paper).
- **People search ranking**: exact whole-query name match first, then names
  containing every term, then partial matches; ties by paper count ("chun yu" puts
  Chun Yu on top, not the most-published partial match).
- **External links are plain anchors** (doi ↗ in the panel, Open DOI in the context
  menu): plain click opens a foreground tab; the browser-native Cmd/Ctrl+click is the
  supported way to open in background (JS cannot force it — a synthetic-click hack was
  tried and reverted).
- **Axis-split zoom**: Shift+scroll must leave the year axis unchanged; Alt+scroll must
  leave bands unchanged.
- **Toggles**: Scope (any/last) changes line spread; the "Color by" segmented control
  (People/Venue) swaps point colours and the legend.
- **Lineage lines checkbox** (Lineage group, default on): off hides the selected
  paper's lineage lines AND pinned people's lab lines in one switch — points stay
  highlighted/coloured either way; with lines off, isolate keeps ambient edges
  (must not blank the map) while still dimming/restricting points.
- **Tutorial overlay**: first load auto-opens the video muted; × closes for the
  session, "Don't show this again" sets localStorage `plTutorialNever` (no auto-open
  after reload); the "Tutorial" panel link reopens it with sound; the 13MB video
  gets its `src` only when the overlay opens (check Network on a flagged reload);
  Esc closes the overlay without touching the selection. It must NOT auto-open when
  the URL carries view state — a shared link would be hidden behind the video.
- **Share sheet** (the "Share" panel link): opens an overlay with the link, a Copy
  button and X / Bluesky / LinkedIn / Email targets built from `intent` URLs — no
  third-party scripts may ever be loaded here. The headline sentence describes the
  current state (paper title + year + venue, or the person, field or query).
  **The link is the clean site URL by default**; the "Link to this view" checkbox
  (unchecked on every open) switches it to the deep link. The address bar is never
  rewritten as you browse. Esc and a backdrop click close the sheet without
  touching the selection. `navigator.share` only: the "More…" button appears.
- **Deep links**: `?paper=<doi>` (`i<index>` only when a paper has no DOI),
  `?author=<name>`, `?band=`/`?sub=<field name>`, `?venue=<key>`, `?q=<query>`,
  `?pins=<names;…>` (written only when the pins differ from the default five) and
  `?v=cx,cy,zx,zy`. Identifiers are DOIs and names, never indices, because indices
  change on every rebuild — a shared link must not silently point at a different
  paper. Loading one restores the panel and applies the camera *after* the
  selection, so the shared framing wins over the auto-pan. An unknown DOI must say
  so in the stats line rather than open the wrong paper.
- **Panel footer** stays on one line: GitHub ↗ / Feedback ↗ / ▶ Tutorial / ⤴ Share.
  External links carry the ↗ text arrow; the two in-app actions carry inline SVG
  icons (`.ic`, 11px, `currentColor` so hover still lights them). Clicking the icon
  itself must open the overlay, not follow the anchor. Above the row, the maintainer
  line links the name itself (English homepage) — `Yamato Miyatake ↗ · Saitama
  University`.
- **Venue selection**: in venue colour mode, clicking a legend venue chip highlights
  that venue's papers (points only, no edges), lists its most-cited papers in the
  panel, and restricts hover/click to them; re-click or Esc clears; the chip shows an
  active state that clears with the selection.
- **Local clusters**: selecting a paper computes them automatically (no button) — ≤8
  local cluster rows with counts + TF-IDF labels, plus a "+N papers in M smaller
  clusters" line when anything is dropped; clicking a row filters BOTH directions (and
  clears any sub-band filter); re-click restores. Same lineage must give identical
  clusters every time.
- **Name clusters with AI**: prompts for an API key once (localStorage); names replace
  the TF-IDF labels; re-running on the same lineage must hit the localStorage cache
  (no network call — check the Network tab).
- **Right-click a paper** opens a small context menu (title · Open DOI · Copy DOI ·
  Copy title · Trace lineage when not selected) WITHOUT touching the selection; menu
  closes on action, outside click, wheel, or Esc (Esc closes ONLY the menu, keeping
  the selection); right-click on empty space shows the normal browser menu; papers
  without a DOI show "No DOI on record" instead of the DOI actions.
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
- Categorical colors: pinned people up to 15 + "Other" (product decision); isolate/labels
  are the required secondary encoding. Other categorical uses stay at max 8.
- UI copy is English and neutral: say "lab lineage", not "self-citation".
- Production serves the map at `/` only: `vercel.json` redirects `/viewer`,
  `/viewer/` and `/viewer/index.html` there, and `<link rel="canonical">` points at
  `/`. Those redirects match exact paths, so `/viewer/main.js` and
  `/viewer/band-names.json` still resolve — keep it that way. Local dev is
  unaffected (the static server ignores `vercel.json`); serve and open
  `/viewer/index.html` as before.
- The paper count in the `<title>`/description is deliberately rounded ("39,000"),
  so re-running the pipeline cannot silently make the static HTML wrong. Re-shooting
  `docs/media/` means rebuilding `docs/media/og-card.jpg` (1200×630) too.
