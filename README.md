# paper-lineage

論文の引用ネットワークを **時系列(縦軸=時間)** で可視化し、「その論文が何の上に乗っているか」「その後どんな流れを作ったか」を1画面で読めるようにするツール。

Connected Papers 的な force-directed グラフではなく、**時間方向を必ず単調に描く DAG レイアウト**を主表現にする(引用は過去にしか向かない、という論文特有の制約を利用する)。

## ドキュメント

- [docs/scope.md](docs/scope.md) — 何を作るか / 作らないか、成功条件
- [docs/prior-art.md](docs/prior-art.md) — 既存ツール調査(Litmaps, Research Rabbit, CiteSpace ほか)と差分
- [docs/data-sources.md](docs/data-sources.md) — OpenAlex / Semantic Scholar / OpenCitations の使い分け
- [docs/dev-notes.md](docs/dev-notes.md) — 実装メモと決定ログ

## Status

2026-07-29: 構想段階。実装未着手。
