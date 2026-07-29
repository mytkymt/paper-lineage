# paper-lineage

分野まるごとの引用ネットワークを **時間軸に固定した単調レイアウト** で一度に描き、そこに浮かび上がる **太い流れ** を読むためのツール。

- 数十件を精読するのではなく、数万〜十万本を一度に出して**全体のトレンド感**を見る。
- Connected Papers 的な force-directed は時間方向を潰すので使わない。**引用は過去にしか向かない**という制約を、レイアウトの支柱にする。
- 浮かび上がった太い線が「1ラボ・ラストオーサーの系譜」なのか「分野として成立したトレンド」なのかまで見分ける。

## ドキュメント

- [docs/scope.md](docs/scope.md) — 何を作るか / 作らないか、成功条件
- [docs/algorithms.md](docs/algorithms.md) — レイアウト軸の候補、Main Path Analysis (SPC)、太さの帰属分析
- [docs/prior-art.md](docs/prior-art.md) — 既存ツール・先行手法の調査と差分
- [docs/data-sources.md](docs/data-sources.md) — OpenAlex / Semantic Scholar の使い分け
- [docs/dev-notes.md](docs/dev-notes.md) — 実装メモと決定ログ(新しい日付が上)

## Status

2026-07-29: 構想段階。実装未着手。
