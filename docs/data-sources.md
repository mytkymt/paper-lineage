# データソース

## 使い分け(方針)

| API | 使う場面 | 認証 | 備考 |
|---|---|---|---|
| **OpenAlex** | グラフ構造の骨格(references / cited_by、メタデータ、会場、概念タグ、OA リンク) | 不要(polite pool 用に mailto を付ける) | カバレッジが広く、`cited_by_api_url` で被引用を辿れる。**主データソース。** |
| **Semantic Scholar Graph API** | citation context と intent(background / method / result)、influential citation flag、SPECTER2 embedding | API key 推奨(無しだと厳しめのレート制限) | **F3 の 2 段階目の中核。** OpenAlex にはこの情報がない。 |
| **Crossref** | DOI 正規化、メタデータの穴埋め | 不要 | |
| **OpenCitations** | 引用関係のクロスチェック | 不要 | 補助 |
| **arXiv / PMC / OA link** | Related Work 全文(F3 の 3 段階目) | 不要 | OA のものだけ。取れないものは諦める設計にする。 |

## 実装上の注意

- **キャッシュ必須。** 同じ論文で何度も試すので、API レスポンスをローカル(ファイル or SQLite)にキャッシュする。レート制限に当たっても再現できることを success criteria に入れてある。
- **下流の爆発。** 被引用数の多い論文は `cited_by` が数千〜数万。全部取らない。取得段階で「各年 上位 K 件(被引用数順)」など打ち切り、**打ち切ったことを UI に明示する**(黙って切ると「全部見た」と誤読される)。
- **ID の正規化。** DOI / OpenAlex ID / S2 corpusId / arXiv ID が混ざるので、内部の正準 ID を最初に決める(OpenAlex ID を正準にする案が有力)。
- **年の欠損・不整合。** 出版年が preprint と proceedings で違う、年が無い、といったケースがある。時系列が主表現なので、**年の決め方(preprint 優先か publication 優先か)を明示的に決めて、UI で切り替えられるとよい。**
- **API 規約。** スクレイピングはしない。OpenAlex は mailto を付けて polite pool を使う。S2 の key は `.env` に置く(コミットしない)。
