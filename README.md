# HCI Research Trails

(リポジトリ/開発名は paper-lineage)

分野まるごとの引用ネットワークを **時間軸に固定した単調レイアウト** で一度に描き、そこに浮かび上がる **太い流れ** を読むためのツール。

- 数十件を精読するのではなく、数万本を一度に出して**全体のトレンド感**を見る。
- Connected Papers 的な force-directed は時間方向を潰すので使わない。**引用は過去にしか向かない**という制約を、レイアウトの支柱にする。
- 浮かび上がった太い線が「1ラボ・ラストオーサーの系譜」なのか「分野として成立したトレンド」なのかまで見分ける。

現在のコーパスは HCI 主要会議 13 venue = 約 4 万本(CHI / PACM HCI / UIST / DIS / ASSETS / IUI / CSCW / TEI / IMWUT / UbiComp / CHI PLAY / MobileHCI / TOCHI)。

## 使い方

データ取得からレイアウト計算まではオフラインの Python パイプライン、表示は静的な WebGL ページ。

```bash
cd pipeline
uv run python -m paperlineage.fetch_corpus    # 1. S2 から venue 単位でコーパスを取る (~10分)
uv run python -m paperlineage.fetch_refs      # 2. OpenAlex から引用エッジと著者を取る (~40分)
uv run python -m paperlineage.build_graph     # 3. コーパス内引用 DAG を組む(サイクル除去込み)
uv run python -m paperlineage.spc             # 4. Main Path Analysis (SPC) でエッジに重みを付ける
uv run python -m paperlineage.bundles         # 5. 太い束を取り出し、帰属(ラボ系譜 or 分野)を判定
uv run python -m paperlineage.layout          # 6. 時間単調レイアウトの座標を前計算
```

1 と 2 は取得済みをスキップするので、途中で止めても再実行すれば続きから流れる。

表示:

```bash
python3 -m http.server 8137
```

でリポジトリのルートを配信し、`http://localhost:8137/viewer/index.html` を開く。

## ドキュメント

- [docs/scope.md](docs/scope.md) — 何を作るか / 作らないか、成功条件
- [docs/algorithms.md](docs/algorithms.md) — レイアウト軸の候補、Main Path Analysis (SPC)、太さの帰属分析
- [docs/prior-art.md](docs/prior-art.md) — 既存ツール・先行手法の調査と差分
- [docs/data-sources.md](docs/data-sources.md) — S2 / OpenAlex の役割分担と実測した落とし穴
- [docs/dev-notes.md](docs/dev-notes.md) — 実装メモと決定ログ(新しい日付が上)
