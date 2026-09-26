# Genealogy study — working notes (2026-09-25)

Corpus: 13-venue core, 36,264 papers, 372,218 in-corpus citations (extended: 20 venues, 44,232).
All numbers below are from `analysis/results/core/` unless marked *ext*.

## 1. Sub-field births (RQ1)
- 116 sub-fields (Louvain sub-bands). Birth (revised 2026-09-25) = first year whose 3-year window
  holds ≥3T papers and whose next 3-year window also does; T = 0.5% of that year's corpus, floored
  at 2 and capped at 5 (so T=2 around 1990, 5 from 2010). The 3-year window absorbs the gap years
  of biennial CSCW; the "next window too" condition removes one-off bursts. The earlier rule
  (5 papers or 2% of eventual size) was pulled up to 10–20 years too early by old papers that
  Louvain attaches to a later community (e.g. CAD papers in Digital Fabrication: 2004 → 2011).
  Distribution: 1980s 12, 1990s 17, 2000s 47, 2010s 40 (2015+: 15). `first_reach_year` in
  subfield_summary.csv keeps the old value.
- Newest: Deceptive Advertising Patterns, Bio-materials & Sustainable Making, Parkinson's &
  Mobility Support (2019); Race & Social Justice, Smart-home Privacy, Social VR & Presence (2017).
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
  share of the sub-field's papers by years since birth (median over ~100 core sub-fields, revised
  births): y0–y4 0.50, **y5 0.25, y6 0.20, y8 0.12, y10 0.08, y15 0.00**.
  Years 0–4 are partly circular (founders are defined there); the drop after year 4 is not.
  On its own this is a descriptive, expected result; it matters as the axis along which
  sub-fields differ (section 8), not as a headline.
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
- Works outside the corpus cited ≥5 times by corpus papers: 62,543 ids, 59,308 records returned
  (the rest are merged or deleted OpenAlex ids). Fetched over two days because of the OpenAlex free
  daily budget; `fetch_external` resumes where it stopped (an `OPENALEX_API_KEY` in the
  environment lifts the limit). Records fetched on the second day carry `primary_topic`.
- OpenAlex leaves the venue empty for ~40% of these (ACM/IEEE conference papers, books).
  `fetch_external --containers` fills 18,599 of them from Crossref (ACM: one lookup per volume).
  Classification order: OpenAlex primary_topic (where fetched) → venue name → Crossref container
  → DOI prefix/conference token → title words. Result: 10,994 by topic, 27,868 by venue name,
  15,182 by container, 2,136 by title, 1,242 unclassified (2%); 1,693 dropped as reference noise
  (book reviews, paratext, mis-resolved sources) and 193 as duplicate OpenAlex records of corpus
  papers. The decade shares below moved by at most one point when the last 23% arrived.
- What the early papers of HCI sub-fields import (share of classified external references,
  decades 1990s / 2000s / 2010s): social science 19 / 18 / 20%; HCI journals and other HCI
  venues 15 / 15 / 13%; psychology 11 / 9 / 10%; graphics 8 / 3 / 4%; ML/AI 5 / 6 / 7%;
  CS general 4 / 5 / 5%; companion tracks (extended abstracts etc.) 2 / 5 / 4%; health 1 / 1 / 3%.
  In the 1980s graphics was 14% and social science 19%.
- Per sub-field (top external field of the early papers): GUI Toolkits, Gaze, Data Visualization,
  Digital Fabrication ← graphics (0.25–0.35); Pointing, Gamification ← psychology (0.20–0.25);
  Gender & Algorithmic Bias, Gig Work, Search & Recommendation, Chronic Care ← social science
  (0.27–0.38); Crowdsourcing, Explainable ML ← ML/AI (~0.18). Full table: external_origins.csv.
- Coverage caveats found on the way: TOCHI is nearly absent from the Semantic Scholar corpus for
  2004–2013 (174 TOCHI works cited ≥5 times sit in the external layer), CHI 1994 is half missing
  (19 works), and a few hundred other main-track works are absent (DiamondTouch UIST 2001, "Beyond
  Fitts' law" CHI 1997, the ESP game CHI 2004). CHI's yearly counts otherwise match the actual
  proceedings. Backfill TOCHI and CHI 1994 before the paper; report the rest as a limitation.
- Venue boundary check (core papers' 1.5M references): 24.9% land in the corpus, 7.2% in
  HCI-labelled venues outside it, 25.0% in other fields, 42.9% in works cited fewer than 5 times
  (not fetched). Of references to HCI-labelled venues, the corpus holds 77.5%; the rest go to CHI
  Extended Abstracts (excluded on purpose), interactions, Human-Computer Interaction, Personal and
  Ubiquitous Computing, TOCHI (the gap above), the CSCW journal, Computers in Human Behavior, IDC,
  IJHCI, Interacting with Computers, Presence, TACCESS, IEEE Pervasive, BIT and AutomotiveUI.
  The core set is "SIGCHI-run venues with full coverage in the source" but that rule is not applied
  in full (IDC, AutomotiveUI, C&C, ETRA, VRST, ISS, EICS, GROUP are missing); decide, then show the
  main results on CHI-only / core / full-SIGCHI / extended sets.
- Remaining "other" (13%) is a long tail of journals (statistics, vision science, marketing,
  repositories); OpenAlex `primary_topic` (`fetch_external --topics`) would replace the rules.


## 8. Modes of origin: emergent vs. built (candidate C4) — 2026-09-25
- Three concentration measures on the founding window (birth to birth+4), 113 core sub-fields:
  *flag concentration* = share of later in-sub citations to founding-window papers that go to
  one paper (median 0.18, IQR 0.12–0.27); *group concentration* = share of founding papers by
  the largest co-author component (median 0.20, IQR 0.15–0.29); *external trigger* = share of
  founding papers citing the same external work. A "flag paper" is declared only when flag
  concentration ≥0.25 and ≥2× the runner-up: 19 sub-fields (Gaze 0.70, Computers are social
  actors 0.59, Interactive machine learning 0.43, VizWiz 0.38, Tangible bits 0.30, ...).
  Whether flag papers are agenda papers or artefacts must be checked by reading them.
- The two axes are independent (ρ = −0.15). Four modes, examples:
  one group + flag (Explainable ML, Voice agents, Gaze, Visual Accessibility);
  one group, no flag (Wikipedia & Open Source 0.63 one group, Digital Fabrication 0.41,
  Sustainable HCI 0.36, Gamification 0.39);
  many groups + flag (Feminist HCI, Pointing/Fitts, Text Entry, Hand Input);
  many groups, no flag (GUI Toolkits, Touch, Self-tracking, Gig Work, Social Media & Mental Health).
- Rank correlations (no test yet): group concentration × eventual size −0.28; flag concentration
  × size +0.28; flag concentration × founders' share at year 6 −0.39 (a flag paper brings
  outsiders in rather than closing the field); export share weakly related (+0.24 with flag).
- Digital Fabrication: born 2011 (not 2004); founding window 2011–15 has 49 papers in 21 groups,
  largest (HPI) 0.41, no flag paper (WirePrint 0.06; Interactive fabrication, FreeD, MixFab share).
  Tangible: born 1995, 61 founding papers, 39 groups, largest 0.20, flag Tangible bits 0.30.
- Next: permutation test for the correlations; read the 19 flag papers and label agenda vs.
  artefact vs. study; compare modes on longevity and award density.

## 9. Corpus v2 (2026-09-26): every SIGCHI-sponsored venue
- The core now follows one rule: conferences ACM SIGCHI sponsors or co-sponsors plus SIGCHI's
  journals, companion tracks excluded. 17 venues added (IDC, C&C, AutomotiveUI, ETRA, VRST, ISS,
  EICS, GROUP, ICMI, UMAP, RecSys, IMX, ISWC, COMPASS, CUI, SCF, HRI); ASSETS moved to the linked
  layer; TOCHI 2004–2013 recovered via its second Semantic Scholar name. Core 53,909 papers,
  450,037 citations, 17 fields, 137 sub-fields; 7,620 papers (14%) have no in-corpus citation
  link (RecSys, UMAP, ICMI and ETRA connect weakly to the rest). All numbers above sections 1–8
  were computed on the 13-venue corpus; this section records what moved.
- Stable: co-word motor themes still almost never persist (CHI 0/1, 0/3, 0/4, 0/3, 1/2; core
  1/3, 0/3, 0/3, 0/2, 1/1, 0/2) while per-window citation clusters do (CHI 8/12, 13/17, 15/25,
  6/18, 15/23; core 10/16, 15/20, 18/26, 21/28, 13/23, 14/24). Founders' share y0–4 0.50, y5
  0.22, y6 0.20, y8 0.13, y10 0.05. Awards: 53/71 identified, 34/39 above the same-year
  same-sub-field median. Export median 0.76 (IQR 0.69–0.84), ρ(import, export) 0.56; the
  recommender sub-fields are the most exported (0.92–0.95).
- Moved: early external references now show more ML/AI (2000s 11%, 2010s 13%, was 6–7%) because
  RecSys, UMAP and ICMI import it; social science 17–20% and psychology 11–12% unchanged. The
  origin-mode correlation between group concentration and eventual size fell to −0.05 (was
  −0.28); flag concentration × founders' share at y6 stays at −0.42.
- Waves (title+abstract keywords, abstracts for 31,170 of 53,909 papers; cohesion = lift over
  same-year non-wave papers; founding-window references ≥60):
  LLMs 2022: 17.5% of 2025 papers, 60 sub-fields, lift 14, newcomers 0.54 vs 0.49.
  VR 2016: 9.6% (2019), 27 sub-fields, lift 35, newcomers 0.62 vs 0.50 (VRST now in the core).
  WWW 1994: 7.4% (1998), lift 11, newcomers 0.74 vs 0.66, 7% of peak after ten years.
  Smartphones 2008: 6.8% (2020), lift 39 but self-reference 0.01 (the word arrives late).
  Social media 2007: 5.9% (2022), lift 44, newcomers 0.50 vs 0.61.
  Deep learning 2015: 5.8% (2023), 19 sub-fields, lift 33, newcomers 0.65 vs 0.49.
  Voice assistants 2016: 4.3%, lift 129 (the most self-contained wave).
  MTurk 2008: 3.1%, self-reference 0.30, lift 66, newcomers 0.37 vs 0.60.
  Personal fabrication 2012: 3.8% (2022), lift 43, still at its peak after ten years.
  Kinect 2011: 1.0% (2012), lift 22. Tabletop 2005: 3.6% (2010), newcomers 0.32 vs 0.61.
  Two shapes persist across corpora: platform waves (WWW, smartphones, LLMs) are large, spread
  across many sub-fields, bring newcomers and dissolve into everything; instrument waves (MTurk,
  voice, Kinect, tabletop) stay small, cohesive and incumbent-led.
- Trigger bursts now recover "Attention Is All You Need" (burst 2019) and Latent Diffusion (2023)
  besides Kinect pose recognition (2011), D3 (2012), ImageNet (2015), GloVe/word2vec (2016–17),
  BERT (2019). GPT-3 itself is barely visible: OpenAlex rarely resolves references to arXiv.
- To do for the paper: venue-set robustness (CHI-only / old core 13 / core 29 / all 36), the
  citation-rewiring null model for cluster persistence, wave definitions that do not depend on
  when a word became common (smartphones), and a decision on the 14% isolated papers.

## 10. Isolated papers (decision, 2026-09-26)
- 7,612 core papers (14.1%) have no citation link inside the corpus. 37% of them have no
  reference list at all in OpenAlex (indexing gap, concentrated in 2026: 884 of 3,584 papers of
  that year are isolated); the rest cite only outside the corpus. By venue: HRI 38%, ICMI 40%,
  GROUP 38%, VRST 34%, C&C 33%, IDC 25%, ETRA 20%, UbiComp 17%, IUI 16%, RecSys 14%, CHI 6%.
- Decision: keep them in the corpus (they are peer-reviewed papers of the venues) and in the
  denominators of paper-count measures (wave shares, venue sizes), but they take no part in any
  citation-based measure by construction (persistence, founders, parents, cohesion, accumulation).
  State the 14% and the indexing gap in the paper; do not drop them silently. The weekly refresh
  re-fetches empty reference lists, so the 2026 share will fall.

## 11. Null model for cluster persistence (2026-09-26)
- Rewiring: within each cited-paper year, the cited endpoints of all edges are shuffled. This keeps
  every paper's number of references, every paper's in-corpus citation count and the reference-age
  distribution; only *which* paper cites *which* is destroyed. Same per-window Louvain and the
  same 30% rule as section 4, core corpus, 5 replicates (`null_persist.py`).
- Observed (core, window to next): 10/16, 15/20, 18/26, 21/28, 13/23, 14/24 (0.52–0.75).
- Rewired: 0/18, 0/26, 0/31, 0/32, 0/20, 0/32 (rep 1); 1/20, 0/24, 0/34, 0/26, 0/20, 0/30 (rep 2);
  reps 3–5 all 0 of 18–33. The measure is not driven by degree or age structure: on a graph with
  the same volume of citations to the previous window, no cluster continues.
- Consequence for the paper: the co-word/citation contrast in section 4 is a contrast between
  lenses, and the citation lens is not trivially persistent.

## 12. Venue-set robustness (2026-09-26)
Same scripts on four venue sets (`robustness.py`; results/{chi,core13,core29,all36}/):
chi = CHI alone (14,531 papers); core13 = the pre-September core (CHI, PACM HCI, UIST, DIS,
ASSETS, IUI, CSCW, TEI, IMWUT, UbiComp, CHI PLAY, MobileHCI, TOCHI, cut from the extended build);
core29 = all SIGCHI-sponsored venues; all36 = core29 plus the seven linked venues.

| set | sub-fields | founders y2 / y6 / y8 | export median | citation clusters persisting, window by window | co-word motor persisting |
|---|---|---|---|---|---|
| chi | 93 | 0.54 / 0.19 / 0.09 | 0.88 | 4/4 8/12 13/17 15/25 6/18 15/23 | 0/0 0/1 0/3 0/4 0/3 1/2 |
| core13 | 129 | 0.57 / 0.22 / 0.11 | 0.76 | 12/15 14/21 13/22 16/22 12/18 12/20 | 0/2 1/3 0/4 0/3 0/2 0/2 |
| core29 | 128 | 0.50 / 0.20 / 0.14 | 0.76 | 10/16 15/20 18/26 21/28 13/23 14/24 | 1/3 0/3 0/3 0/2 1/1 0/2 |
| all36 | 149 | 0.55 / 0.17 / 0.12 | 0.78 | 16/19 18/26 22/31 20/29 15/22 15/21 | 0/3 0/4 0/3 1/1 0/2 1/1 |

| set | LLM peak / lift / newcomers | VR peak / lift | MTurk peak / lift | WWW peak / lift |
|---|---|---|---|---|
| chi | 21.6% / 10.8 / 0.62 | 10.8% / 41.9 | 6.3% / 51.2 | 7.4% / — |
| core13 | 18.6% / 14.1 / 0.53 | 8.8% / 33.7 | 4.0% / 60.0 | 8.6% / 10.4 |
| core29 | 17.5% / 9.8 / 0.53 | 9.6% / 35.0 | 3.1% / 66.1 | 7.4% / 10.8 |
| all36 | 16.8% / 13.4 / 0.55 | 14.4% / 25.7 | 2.8% / 72.5 | 6.5% / 22.5 |

- Every claim keeps its direction and rough size across the four sets: citation clusters persist
  in 50–85% of cases while co-word motor themes persist in 0–1 of 1–4; founders hold ~0.5 of a
  sub-field's papers for four years and ~0.2 by year six; three quarters of citations come from
  outside the set (0.88 for CHI alone, as expected for a single venue); LLMs are the largest wave
  in every set (17–22% of the latest year) and the least cohesive of the recent waves, MTurk the
  most cohesive, VR in between. The only set-sensitive number is VR's size, which grows when the
  VR venues are added (all36 14.4%), as it should.
- Wave start years are now data-driven (first year the wave holds ≥0.5% of the set for two
  years); see waves.csv `start` vs `start_manual`.

## 13. Exploratory hypotheses and what survived scrutiny (2026-09-26)
Seven candidate "surprises" were tested (analysis/explore/hypotheses_*.py), then the survivors
were re-tested with controls (explore/critique.py; log in results/core/critique_log.txt).
- Dropped: lasting-impact awards fall evenly inside/after founding windows (16 vs 21); CD5
  declines monotonically 1990→2020 (+0.11 → −0.02), i.e. the general Park et al. trend.
- Weakened: "LLMs displaced the hardware side of CHI". Keyword counts confirm input/haptics/
  gesture fell 14.5% → 9.7% of CHI (2019→2025) and games 8.7% → 5.2% while social computing,
  health and accessibility held or rose. But the band shares show the decline predates LLMs
  (Input & Interaction Techniques 12.3% → 9.3% → 6.7% over 2015–17 / 2019–21 / 2023–25; Gaze
  4.3 → 3.4 → 1.7; the AI band already doubled 5.1% → 10.4% before 2022), and part of it is
  migration to UIST/ISS/ETRA (input techniques outside CHI ×1.24 vs CHI ×1.03). Honest form:
  CHI's AI turn began around 2017 and the interaction-technique share has halved since 2015;
  LLMs continued rather than caused it.
- Survived with a caveat: "boundary-crossing papers are cited less inside HCI". Within year ×
  sub-field and controlling for reference-list length (CHI 2005–2018, n=4,811), moving the
  external-reference share from 0.6 to 0.9 multiplies citations from HCI by 0.63 and total
  OpenAlex citations by 0.85 (within-cell quartiles: ×0.65 vs ×0.90). The effect disappears
  when the number of in-corpus references is controlled, so the mechanism is embeddedness
  (papers with few HCI references are less discoverable through HCI citation chains) rather
  than an evaluative penalty; report as the former.
- Survived: two wave-riding lineages. With the control group "prolific in the earlier window
  but not a founder" and permutation intervals (strict LLM keywords): tabletop founders →
  fabrication 5.7× and VR 2.9× (both outside the null interval) but → deep learning 0.0×, voice
  0.5×, LLM 0.9×; crowdsourcing founders → deep learning 5.1×, voice 4.2×, LLM 3.6× but →
  fabrication 0.0×, VR 0.4×; smartphones → deep learning 11.8×; wearables → voice 4.1×; deep
  learning → LLM 2.3× [0.5–1.6]; voice → LLM 3.4× [0.6–1.5]; VR → LLM 0.8× [0.7–1.3] (n=259);
  fabrication → LLM 1.3× [0.6–1.5]. The lineages have always been separate; LLMs are a
  data-lineage wave, not the first wave one lineage skipped.
- Moderate: founders' newcomer share relative to all prolific authors of the same window fell
  1.17 (1990s) → 0.99 (2000s) → 0.77 (2010s): field founding moved from outsiders to insiders.
- Abstract coverage is 100% for CHI 2019+ but 7–18% before 2016, so keyword-based topic counts
  are only comparable from 2019 on; wave membership for older waves relies on titles.
- Venue check (2026-09-26, later): the embeddedness effect is not a CHI artefact. Same
  specification on all 29 core venues with venue FE (n=16,294): HCI-internal citations ×0.62,
  total ×0.84 for external share 0.6→0.9; on the 28 non-CHI venues ×0.62 / ×0.84; per venue the
  internal multiplier runs 0.38 (PACM HCI) to 0.86 (RecSys) and is below 1 everywhere; RecSys is
  the one venue whose outward-citing papers gain total citations (×1.31). The two lineages also
  survive with CHI papers removed (explore/critique_without_chi.py): tabletop → fabrication
  4.9×, → VR 2.5×, → LLM 1.0×; crowdsourcing → LLM 3.6×; deep learning → LLM 3.4×; voice → LLM
  3.3×; VR → LLM 1.0× [0.5–1.6]; fabrication → LLM 1.1×.

## 14. Contribution types of the two lineages (LLM-labelled, 2026-09-27)
- Sample: papers by lineage founders 2010–2025 with abstracts, stratified by year (hardware
  lineage 776, data lineage 868) plus 493 other core papers; labelled by Claude from title and
  abstract with the Wobbrock & Kientz (2016) types and two substrate flags (physical device or
  material; data-driven model, ML, language model, agent, recommender or crowd computation).
  Rubric and samples in data/contrib (not committed); aggregate in results/core/contrib_types.csv.
  79% of labels marked high confidence.
- Method differs, but modestly: artifact 0.57 vs 0.42, empirical 0.33 vs 0.46 (build-type share
  0.61 vs 0.47; other papers 0.53). Substrate differs strongly: physical 0.68 vs 0.21,
  computational 0.14 vs 0.51 (others 0.31 / 0.34). Guessing a paper's lineage from "physical=1"
  is right 74% of the time; from "type=artifact" 57% (chance 50%). Both lineages have a large
  "neither" share (0.24 / 0.36): studies of people with no device and no model.
- So the divide is primarily one of substrate, with a secondary tilt in method; the keyword
  proxy in section 13 understated the method difference. Say "substrate first, method second",
  not "not method". Stable across 2010–16 vs 2017–25.
- Data-quality note from the labelling: a few Semantic Scholar abstracts belong to a different
  paper than the title (e.g. one MediaEval entry); workshop proposals appear in IDC/C&C.
- Sensitivity of the lineage table (explore/lineage_sensitivity.py; results/core/
  lineage_sensitivity.csv): under founders ≥3 papers, windows of 4 or 6 years, and narrow
  keyword sets, the within-lineage cells stay above 1 (tabletop → fabrication 2.5–6.2×, → VR
  1.7–2.9×; crowdsourcing → deep learning 2.9–5.5×, → voice 2.9–7.0×, → LLM 3.3–4.2×; voice →
  LLM 3.1–3.9×; deep learning → LLM 1.0–2.9×) and the cross-lineage cells stay at or below 1
  (tabletop → deep learning 0–0.9×, → LLM 0–1.1×; crowdsourcing → VR 0–0.5×; VR → LLM 0.8–1.1×;
  fabrication → LLM 0.7–1.7×). The ≥3-paper setting thins several cells to n≈10–16, where a few
  within-lineage cells drop to 0; the two large cells (VR → LLM n=125–343, voice → LLM n=59–201)
  are stable in every setting.
