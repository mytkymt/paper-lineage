# 既存ツール調査 — 2026-07-29(軽い一次調査)

> 注意: 以下は web 検索ベースの一次調査であり、**各ツールを実際に触って確認した結果ではない**。実装判断の前に、少なくとも Litmaps と Research Rabbit は自分の論文で試すこと(→ dev-notes.md の TODO)。

## 時系列を扱っているツール

| ツール | 時系列の扱い | paper-lineage との差分(仮説) |
|---|---|---|
| **Litmaps** | 論文を「古い=左 / 新しい=右」に並べる時系列レイアウトを持つ。Connected Papers 的な見た目と時系列を組み合わせた、と紹介されている。**現時点で一番近い既存ツール。** | Litmaps は「seed から関連論文を探し続ける(monitoring / discovery)」が主目的。paper-lineage は **1本の論文の上流・下流の系譜を読む**ことが目的で、trend の太さ(F2)と Related Work の枠づけ(F3)を狙う点が違う、という仮説。**実際に触って確認が必要。** |
| **Research Rabbit** | timeline ビューがあり、論文の時間的つながりを見せる | discovery / collection 志向。引用フローの太さは見せない。 |
| **CiteSpace** | time slicing・burst detection を持つ古参の計量書誌ツール | 分野レベルの俯瞰(数千〜数万論文)向け。1論文の系譜を読む UX ではない。デスクトップ Java、学習コストが高い。 |
| **CitNetExplorer** | 引用ネットワークを時系列レイアウトで描く(まさに縦軸=年) | Web of Science 前提・要ライセンス、UI が古い。**レイアウトの参考としては最も近い。要調査。** |
| **Connected Papers** | 類似度ベース force-directed。年は**色**でのみ表現 | ユーザー本人の指摘通り、時系列ソートはできない |
| **Inciteful / Citation Gecko** | 引用ネットワーク探索。時系列は主表現ではない | |

## 手法側の先行研究(2026-07-29 追記)

「太いラインを取り出す」は、可視化ツールではなく**計量書誌学の手法**として既に確立している。

- **Main Path Analysis** — Hummon & Doreian (1989) が提案。引用ネットワーク(DAG)の主要な知識流路を取り出す。Batagelj (2003) が SPC を追加。Pajek / CitNetExplorer に実装がある。→ `algorithms.md`
- **サイクルのある引用ネットワークへの拡張** — JASIST 2019。実データのサイクル混入に対処する変種。
- **Semantic main path network analysis**(2023)— citation context 解析を main path に組み合わせ、分野の「進化のバックボーン」を取り出す。**F3 の狙いにかなり近い先行研究。要精読。**

つまり **手法は既にある**。paper-lineage の勝負どころは手法の発明ではなく、

- それを**分野まるごとのスケールで、時間単調レイアウトの上に載せて、インタラクティブに見せる**こと(既存の main path 研究は静的な図を論文に載せて終わり)、
- 太さの**出どころ(ラボの自己参照 vs 分野トレンド)を判別**して見せること。

## 現時点の読み

- 「引用グラフを時系列で描く」は既出(CitNetExplorer, Litmaps)。「太い流れを取り出す」も既出(main path analysis)。**個々の要素に新規性はない。**
- 差分になりうるのは:
  1. **スケール + インタラクション** — 数万〜十万本を一度に描き、その中で流れを探索できるツールは見当たらない(要確認)。既存の main path 研究は数百〜数千規模の静的図。
  2. **太さの帰属分析** — その流れが1ラボの系譜か複数グループのトレンドかを分けて見せる。**ここは先行が見つかっていない。一番の狙い目。**
  3. citation intent による色分けは、あれば良いが差分にはならない。

> **未検証**: 1 と 2 について「見当たらない」は軽い検索の結果であり、網羅的な調査ではない。特に InfoVis / VAST 系に類似システムがある可能性が高い。**実装前に IEEE VIS・CHI の可視化系を検索すること。**

## 参考リンク

- Aaron Tay, "3 new tools to try for Literature mapping — Connected Papers, Inciteful and Litmaps" — https://aarontay.medium.com/3-new-tools-to-try-for-literature-mapping-connected-papers-inciteful-and-litmaps-a399f27622a
- List of Literature mapping tools (Aaron Tay) — http://musingsaboutlibrarianship.blogspot.com/p/list-of-innovative-literature-mapping.html
- UCL Library, citation network tools — https://library-guides.ucl.ac.uk/research-metrics/citation-network-tools
- Frontiers, "Leveraging Citation Networks to Visualize Scholarly Influence Over Time" — https://www.frontiersin.org/journals/research-metrics-and-analytics/articles/10.3389/frma.2017.00008/full
- Scientometrics (2026), "Deepening citation understanding in scientific literature via LLM-powered context extraction" — https://link.springer.com/article/10.1007/s11192-026-05637-7
- Connected Papers alternatives — https://alternativeto.net/software/connected-papers
- Main path analysis(概説)— https://en.wikipedia.org/wiki/Main_path_analysis
- Main path analysis on cyclic citation networks (JASIST 2019) — https://dl.acm.org/doi/abs/10.1002/asi.24258
- Extracting the evolutionary backbone of scientific domains: semantic main path network analysis (2023) — https://www.sciencedirect.com/science/article/abs/pii/S1751157723000068
- OpenAlex snapshot / bulk download — https://docs.openalex.org/download-all-data/openalex-snapshot
