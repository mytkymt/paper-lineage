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

## 現時点の読み

- 「引用グラフを時系列で描く」というアイデア自体は **既出**(CitNetExplorer, Litmaps)。ここだけでは新規性にならない。
- 新規性を主張できそうな部分は、
  1. **下流トレンドの"太さ"と分岐**を面積表現(F2)で見せること、
  2. **Related Work / citation intent から「著者自身の枠づけ」を復元**して、上流をトレンドの束として描くこと(F3)。
- 特に 2 は、citation intent(Semantic Scholar)や LLM による citation context 抽出の研究が 2025–2026 に出てきており、**ツールとして統合した例はまだ多くない**。ここが狙い目。

## 参考リンク

- Aaron Tay, "3 new tools to try for Literature mapping — Connected Papers, Inciteful and Litmaps" — https://aarontay.medium.com/3-new-tools-to-try-for-literature-mapping-connected-papers-inciteful-and-litmaps-a399f27622a
- List of Literature mapping tools (Aaron Tay) — http://musingsaboutlibrarianship.blogspot.com/p/list-of-innovative-literature-mapping.html
- UCL Library, citation network tools — https://library-guides.ucl.ac.uk/research-metrics/citation-network-tools
- Frontiers, "Leveraging Citation Networks to Visualize Scholarly Influence Over Time" — https://www.frontiersin.org/journals/research-metrics-and-analytics/articles/10.3389/frma.2017.00008/full
- Scientometrics (2026), "Deepening citation understanding in scientific literature via LLM-powered context extraction" — https://link.springer.com/article/10.1007/s11192-026-05637-7
- Connected Papers alternatives — https://alternativeto.net/software/connected-papers
