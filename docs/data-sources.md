# データソース

> 2026-07-29 に実測して方針を確定した。当初は「OpenAlex を主データソースにする」としていたが、
> **会議の判定には使えない**ことが分かったので役割分担を変えた。

## 役割分担(確定)

| 用途 | API | 理由 |
|---|---|---|
| **コーパス定義(どの会議の論文か)** | **Semantic Scholar Graph API** | venue が正規化されており、`publicationVenue.id` も安定。bulk search で venue 完全一致検索ができる。 |
| **引用グラフ(エッジ)・著者** | **OpenAlex** | `referenced_works` が完全。API キー不要、polite pool で 10 req/s・100k req/day。 |
| citation intent(色分け、後回し) | Semantic Scholar | intent(background / method / result)を返すのは S2 だけ。ただしレート制限が厳しい(下記)。 |

両者は **DOI で突き合わせる**。

## 実測でわかった落とし穴

### OpenAlex は ACM 会議論文の venue を持っていない

決定的だった実測:

```
CHI 2019 論文 (10.1145/3290605.3300719) の primary_location.source → null
source S4363607743 "CHI Conference on Human Factors in Computing Systems" の works_count → 637(全部 2022 年)
source S4306421131 "User Interface Software and Technology" の works_count → 22
```

UIST が 22 件ということはあり得ない。**OpenAlex の会議 source は分断・欠落しており、venue で絞るのは不可能。**
一方で `referenced_works` は正常なので、グラフのエッジ源としては問題ない。

### S2 bulk search の `venue` パラメータはカンマ区切りリスト

venue 名にコンマが含まれると、そこで分割されて 0 件になる。

```
"International Conference on Tangible, Embedded, and Embodied Interaction" → total=0
"International Conference on Tangible Embedded and Embodied Interaction"   → total=1995
```

引用符で囲んでも回避できない。**コンマを除去して渡す**(`Venue.search_venue`)。

### S2 は無認証だとすぐ 429

共有プールで実質 1 req/s 未満。bulk search(1000件/ページ)は許容範囲だが、
**per-paper で数万本を引くのは非現実的**。`s2.py` で 4 秒間隔 + 指数バックオフを入れている。
citation intent を全件に付けるなら API キーか S2 Datasets(bulk)が要る。

### 会議の分割(2017年前後)

- **CSCW** は 2017 以降 PACM HCI に移行 → `cscw` と `pacmhci` の両方が必要
- **UbiComp** は IMWUT に移行 → `ubicomp` と `imwut` の両方
- PACM HCI には EICS / ISS / CHI PLAY も混ざる。今は「HCI コーパス」としてまとめて扱う。

## 現在のコーパス(2026-07-29 実測)

| venue | 件数 | | venue | 件数 |
|---|---:|---|---|---:|
| CHI | 15,435 | | TEI | 1,995 |
| PACM HCI | 3,699 | | IMWUT | 1,861 |
| UIST | 3,261 | | UbiComp | 1,710 |
| DIS | 2,441 | | CHI PLAY | 1,240 |
| ASSETS | 2,198 | | MobileHCI | 937 |
| IUI | 2,108 | | TOCHI | 760 |
| CSCW | 2,019 | | **合計** | **39,664** |

想定より小さい。**全部描くのに何の無理もない規模。**

## 実装上の注意

- **キャッシュ / レジューム必須。** `fetch_corpus.py` は venue 単位、`fetch_refs.py` は DOI 単位で
  取得済みをスキップする。途中で落ちても続きから流せる。
- **年の欠損・不整合。** preprint と本刊で年が違う、年が無い、というケースがある。
  時系列が主表現なので、`build_graph.py` で年が無い/範囲外(1960–2027)のものは落とし、**落とした数を必ず出す**。
- **ID の正準化。** 内部では OpenAlex の短縮 ID(`W123…`)を正準にする。DOI は突き合わせ用。
- **API 規約。** スクレイピングはしない。OpenAlex は mailto 付きの polite pool を使う。
  S2 のキーを使う場合は `S2_API_KEY` 環境変数から読む(コミットしない)。
