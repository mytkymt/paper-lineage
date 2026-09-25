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

## 5. Schools and fields (C4 candidate) — 2026-09-25
- Founding window = 5 years from birth; founders = authors with ≥2 papers in it. Founders'
  share of the sub-field's papers by years since birth (median over 49 core sub-fields):
  y1 0.50, y2 0.56, y3 0.50, y4 0.43, **y5 0.25, y6 0.14, y8 0.05, y10 0.09, y15 0.00**.
  Years 0–4 are partly circular (founders are defined there); the drop after year 4 is not.
- Founder papers (top-3 per sub-field, 238): 10 citations from papers sharing no author arrive
  after a median 3 years (IQR 2–5); only 15% of a founder paper's first 20 citations are
  self-citations. HCI fields are communal almost from birth — the "school" phase is about five
  years and never dominates.
- The year-based take-off measure floors at the founding window (median 5 = the first year
  checked); report the curve, not the year.

## 6. Import / export typology (RQ3)
- Export share = 1 − in-corpus citations / OpenAlex cited_by_count, papers ≤2020 with ≥5 cites.
  Median 0.75 (IQR 0.66–0.82): three quarters of the citations HCI papers receive come from
  outside the 13 venues. Import (early external reference share) and export correlate ρ=0.46.
- High export (~0.9): Autonomous Vehicle Communication, Urban Mobility, Indoor Localization,
  Usability Methods, Search & Recommendation, Fisheye/Navigation, Groupware, CSCW Foundations —
  the classic and the sensing fields are read outside HCI. Low export (~0.5): E-textiles,
  Digital Fabrication, Printed Electronics, Chronic Care, Gender/Intimacy, Civic Participation,
  Race & Social Justice — HCI-internal conversations.

## 7. External ancestor layer (RQ3) — 2026-09-25
- Works outside the corpus cited ≥5 times by corpus papers: 62,543. Fetched 47,967 (77%) before
  the OpenAlex free daily budget ran out; `fetch_external` resumes where it stopped (an
  `OPENALEX_API_KEY` in the environment lifts the limit). Numbers below are on the 77%.
- OpenAlex leaves the venue empty for ~40% of these (ACM/IEEE conference papers, books).
  `fetch_external --containers` fills 15,281 of them from Crossref (ACM: one lookup per volume).
  Classification order: venue name → Crossref container → DOI prefix/conference token → title
  words. Result: 27,865 by venue name, 15,179 by container, 2,136 by title, 1,241 unclassified
  (3%); 1,367 dropped as reference noise (book reviews, paratext, mis-resolved sources) and 179
  as duplicate OpenAlex records of corpus papers.
- What the early papers of HCI sub-fields import (share of classified external references,
  decades 1990s / 2000s / 2010s): social science 19 / 18 / 20%; HCI journals and other HCI
  venues 15 / 15 / 13%; psychology 11 / 9 / 10%; graphics 8 / 3 / 4%; ML/AI 5 / 6 / 7%;
  CS general 4 / 5 / 5%; companion tracks (extended abstracts etc.) 2 / 5 / 4%; health 1 / 1 / 3%.
  In the 1980s graphics was 14% and social science 19%.
- Per sub-field (top external field of the early papers): GUI Toolkits, Gaze, Data Visualization,
  Digital Fabrication ← graphics (0.25–0.35); Pointing, Gamification ← psychology (0.20–0.25);
  Gender & Algorithmic Bias, Gig Work, Search & Recommendation, Chronic Care ← social science
  (0.27–0.38); Crowdsourcing, Explainable ML ← ML/AI (~0.18). Full table: external_origins.csv.
- Coverage caveat found on the way: 473 works whose Crossref container is a corpus venue's main
  proceedings are absent from the Semantic Scholar corpus (8,564 in-corpus citations, 1.4% of
  external citations; e.g. DiamondTouch UIST 2001, "Beyond Fitts' law" CHI 1997, the ESP game
  CHI 2004). Report as a limitation; consider backfilling from OpenAlex by venue.
- Remaining "other" (13%) is a long tail of journals (statistics, vision science, marketing,
  repositories); OpenAlex `primary_topic` (`fetch_external --topics`) would replace the rules.
