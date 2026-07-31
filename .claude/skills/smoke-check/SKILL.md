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
- **Pin/unpin**: click a person row → appears in legend; × in legend removes; a 16th
  pin alerts instead of silently failing. **Removing someone must not recolour anyone
  else** — slots are kept as tombstones, so the remaining chips keep their exact
  colours (only trailing empties are reclaimed).
- **Author colouring is one rule everywhere**: a name or swatch takes its real colour
  only when that person is selected. The hover tooltip colours selected authors inline,
  the paper panel's author chips colour only selected ones, and the search/field author
  swatches keep the hue but sit under a `saturate(.3)` filter (`i.dim`) until selected.
- **Focus**: nothing on the map is coloured until you pick someone. Legend chips start
  desaturated — the dot keeps the person's hue under a CSS `saturate(.3)` filter so you
  can tell what colour they will get — with muted text; clicking one gives it `.sel`,
  full colour and a bright label, **and only then do that person's points and lab lines
  take colour**.
  Re-click clears. Click several chips to focus several people. Re-query the chip after
  each click (legend re-renders).
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
- **Person focus** is a multi-select. A legend chip, a search People row, a field-panel
  author row and an author chip in the paper panel all do the same thing: ensure the
  person is pinned, then toggle them in the focus set (**unpinning is the legend × only**).
  Hover/click hits only focused people's papers and their points render enlarged; the
  widened 26px radius applies only when exactly one person is focused, since several make
  the target field dense. **Co-authored papers must stay clickable and coloured under
  EVERY co-author's focus** (slot assignment prefers the focused bits, lowest among them).
- **Search hover**: while search highlights are active, hover/click only hits matched
  papers; clearing the search restores normal picking.
- **Fields tree**: 14 band rows (pseudo "no-links" band excluded); band click expands
  subs AND selects (highlight + right-panel top-cited list); sub click narrows; re-click
  clears; map band/sub labels are clickable to the same action; while a field is
  selected hover/click hits only member papers; drilling into a paper switches to the
  normal lineage view.
- **Band labels stay visible while a panel is open** — they shift left of the right
  panel (`right: 352px`) instead of being hidden, so you can still see which band you
  are in and click through to it. Below 900px they are hidden as before.
- **Field panel sections**: two collapsible `details.fold` blocks, each with an
  inner scroll area — "Most cited" (top 30, "… N more" line) and
  "Authors — click to pin a color (N)" listing ALL authors (no cap; ~9k rows on the
  biggest band renders in ~55ms); BOTH default closed on a fresh field selection;
  fold open/closed state survives only the re-render caused by a pin toggle.
  Author rows focus the person (see below); the 15-limit alert is unchanged.
- **Author panel** stacks every focused person: the first is laid out as before
  every person is a card that collapses at their name (dot + name + × to drop), the
  first open by default and the rest closed; the title reads "N people" past one and
  the meta line carries "clear all". Inside a card: paper count, year range,
  first/last-author counts, lab-lineage links, Fields (top 10 of N) and a scrollable
  Papers list. The "Other labs" chip focuses without contributing a card. Fold state
  survives adding a person.
- **The focus set is persistent state.** Selecting a paper, a field or running a
  search only *suspends* its display — the set survives, the legend keeps those chips
  in full colour, and Esc brings it back. Esc order is share sheet → context menu →
  paper → field → focus. **No author click ever drops a paper or field selection** —
  from the paper panel, the legend or a field's author list they are added in the
  background, and the search highlight is the only thing that gives way. Removing
  someone from the legend while a paper is open must keep the paper too: refresh the
  results list with `runSearchList`, never the full `runSearch` (which resets
  `selected` and used to wipe the lineage).
- **Paper-panel author chips cycle add → remove.** An uncoloured name pins and
  focuses that person; clicking a name that is already coloured drops them from the
  legend entirely, since the paper panel has no × of its own.
- **Focused colours survive a lineage/field/search view**: those papers keep their own
  colour instead of the upstream/downstream/match colour (direction still reads from
  position) and are drawn slightly larger. Watch for stale dimming — `applyPinned()`
  must re-run whenever the display flips between focused and suspended, or
  non-focused points stay greyed.
- **People search ranking**: exact whole-query name match first, then names
  containing every term, then partial matches; ties by paper count ("chun yu" puts
  Chun Yu on top, not the most-published partial match).
- **Search → focus**: clicking a People row drops the yellow match highlight and switches
  the map to the focused people, while the results list stays so more people can be added.
  Typing a new query suspends the focus display (yellow comes back) without losing the
  set, so people found under different queries accumulate.
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
  highlighted/coloured either way; with lines off, focus keeps ambient edges
  (must not blank the map) while still dimming/restricting points.
- **Tutorial overlay** never opens by itself — only the "Tutorial" panel link opens
  it, with sound. The 13MB video gets its `src` only when the overlay opens (check
  the Network tab on a fresh load: nothing until you click). Esc and × close the
  overlay without touching the selection.
- **Share sheet** (the "Share" panel link): opens an overlay with the link, a Copy
  button and X / Bluesky / LinkedIn / Email targets built from `intent` URLs — no
  third-party scripts may ever be loaded here. The headline sentence describes the
  current state (paper title + year + venue, or the person, field or query).
  **The link is the clean site URL by default**; the "Link to this view" checkbox
  (unchecked on every open) switches it to the deep link. The address bar is never
  rewritten as you browse. Esc and a backdrop click close the sheet without
  touching the selection. `navigator.share` only: the "More…" button appears.
- **Deep links**: `?paper=<doi>` (`i<index>` only when a paper has no DOI),
  `?authors=<names;…>` (the focus set, written alongside whatever else is selected;
  the older single `?author=` is still accepted), `?band=`/`?sub=<field name>`, `?venue=<key>`, `?q=<query>`,
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
- `window.PL` exposes `pick`, `meta`, `nodeSlot()`, `focused()`, `focusOn()`, `pinned()`,
  `screenPos(i)` for closure-internal verification.
- A "colored dot near a person's line" is not necessarily their paper — verify with
  `PL.meta.nodes[i]` before concluding a pick bug (CoDine looked like an Ishii dot;
  it is Adrian Cheok's).

## 4. Invariants

- Coordinate system is top-left origin everywhere (shader flips y; screenToNorm is the
  only inverse). Vertical pan/zoom/hover inverting means this broke.
- Edges accumulate in the HDR buffer + log tone map — never thin the data to fix density.
- Any display cap (top-N lists, highlight cap) must be labeled in the UI, never silent.
- Categorical colors: pinned people up to 15 + "Other" (product decision); focus/labels
  are the required secondary encoding. Pinning alone must never colour anything — a
  colour on the map always means that person is selected. Other categorical uses stay at max 8.
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
