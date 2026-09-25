# Genealogy study — working notes (2026-09-25)

Corpus: 13-venue core, 36,264 papers, 372,218 in-corpus citations (extended: 20 venues, 44,232).
All numbers below are from `analysis/results/core/` unless marked *ext*.

## 1. Sub-field births (RQ1)
- 116 sub-fields (Louvain sub-bands). Birth = year the sub-field reached 5 papers or 2% of its
  eventual size. Distribution: 1980s 16, 1990s 21, 2000s 57, 2010s 22 (2015+: 1).
- Newest: RF & Radar Sensing (2015), Youth Online Safety (2014), Deceptive Advertising Patterns
  (2014), Digital Self-control (2013), Data Physicalization (2013), Moderation & Online Harassment
  (2012).
- Fading (share of papers in the last 5 years < 8%): Real-time Groupware (peak 1992), Fisheye &
  Scrolling (2008), Tabletop Collaboration (2009), Social Network Sites at Work (2011),
  Location-based Museum Play (2013), Smartphone Usage Logging (2016).

## 2. Founder papers (RQ2)
- Operationalisation: within the sub-field's earliest quartile, rank by citations received from
  the same sub-field (`founders2.csv`). Descendant-share saturates and is not discriminative.
- Examples: Tangible bits (1997) → Tangible Interaction; Skinput (2010) → Hand Input & Gesture
  Sensing; Research through design as a method (2007) → Speculative & Critical Design; Feminist HCI
  (2010) → Gender, Intimacy & Safety; A stage-based model of personal informatics (2010) →
  Self-tracking; The bubble cursor (2005) → Pointing; VizWiz (2010) → Visual Accessibility;
  Soylent (2010) → Crowdsourcing; SHARK2 (2004) → Text Entry; Shape-changing interfaces (2012) →
  Deformable & Soft Displays.
- External check: 52 of 71 lasting-impact award papers (UIST 2003–23, CSCW 2013–25, UbiComp
  2011–24, TEI 2007–16, MobileHCI, IUI) found in the corpus. 34/36 rank above the median of
  papers from the same sub-field and year; 15/25 of the first matched batch were in the top 10%
  of their sub-field by within-field citations, 8 were top-5. Awards are an independent,
  retrospective judgement of importance, so this is validation without human subjects.

## 3. Parents (RQ3)
- Early phase = first 10% of a sub-field's papers. Share of in-corpus references to the parent:
  Deformable & Soft Displays ← Tangible (0.30); Hand Input ← Touch (0.22); Data Visualization ←
  Fisheye/Navigation (0.21); Self-tracking ← Persuasive Health (0.20); E-textiles ← Tangible (0.19);
  Programming & Notebooks ← GUI Toolkits (0.18); Video Interfaces ← GUI Toolkits (0.18); Visual
  Accessibility ← Web Accessibility (0.18).
- 66–92% of early references go *outside* the 20-venue corpus. HCI sub-fields are born citing
  outward; the in-corpus parent is a minority of the ancestry.
- *ext*: some HCI sub-fields drew heavily on graphics at birth (UI toolkits 0.60, information
  navigation 0.51, real-time groupware 0.39, cloth/textiles 0.40 of early in-corpus refs).

## 4. Accumulation — the Kostakos question (RQ4)
- Co-word reproduction (title words, 5-year windows, Louvain on co-occurrence, Callon strategic
  diagram, motor = centrality & density above median): motor themes almost never persist to the
  next window — CHI: 0/1, 0/3, 0/4, 0/3, 1/3; all clusters: 0–2 of 7–10. This reproduces
  Kostakos (2015) on our data.
- Same windows, citation clusters computed independently per window (Louvain on the window's
  citation subgraph), persistence = ≥30% of a cluster's citations into the previous window land
  in one previous cluster: CHI 8/12, 13/17, 15/25, 5/18, 14/23; 13 venues 12/15, 16/21, 11/20,
  15/24, 12/18, 13/19. Roughly 55–80% of citation communities continue; co-word clusters ~0–20%.
  → The "no motor themes" result is a property of the lens (words), not of the field.
- Same-sub-field citation share ~0.50 since 2000 (0.61 in 1990). Mean reference age rose from
  2.1 years (1990) to ~6.0 (2023–26); median 2 → 4–5. Fields cite older work over time —
  accumulation, not churn.
- *ext*: graphics (SIGGRAPH/TOG) same-sub-field share 0.59–0.69 vs HCI 0.47–0.51; robotics (HRI)
  0.48–0.58; VR/AR 0.51–0.59. HCI is the least self-referential of the four, consistent with
  Reeves's "interdiscipline" reading — but its communities persist as much as anyone's.

## Caveats to carry into the paper
- Co-word uses title words, not author keywords (not available from public APIs). State it.
- Sub-band persistence measured on whole-period communities is tautological; the fair
  comparison is the per-window one above. Use only that.
- Lineage depth grows with year by construction; do not present raw depth as accumulation.
- 2026 reference lists are ~20% incomplete (indexing lag); cut the last year from time series.
- CD index is corpus-internal (75% of references are outside); report it as secondary.
