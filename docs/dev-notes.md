# dev-notes — paper-lineage

## 2026-07-29 プロジェクト開始

- Vault(Obsidian)側でのアイデア出しから、リポジトリを分離して開始。`~/Repo/paper-lineage`。
- 発端: Connected Papers は時系列ソートができない(フィルタのみ)。論文の引用は時間について単方向なので、これを時系列 DAG として描けば「乗っているトレンド」と「作ったトレンド」が読めるはず、という着想。
- 軽い既存調査の結果 → `prior-art.md`。**時系列レイアウト自体は Litmaps / CitNetExplorer に既出**。差分は F2(トレンドの太さ・分岐)と F3(Related Work / citation intent からの枠づけ復元)に置く。
- スタック未決定。第一候補は Next.js + TypeScript + D3(既存の elapsed-time-tracker と揃う)。ただし**レイアウトの検証が先**で、フレームワーク選定は後回しでよい。

### 次にやること(優先順)

1. **Litmaps と Research Rabbit を自分の論文で実際に触る。** ここで「もう十分読める」となったら作る意味が薄れるので、最初にやる。CitNetExplorer のレイアウトも画像だけでも見る。
2. OpenAlex API で seed 論文 1本の上流2ホップ・下流2ホップを取ってきて JSON に落とす、だけのスクリプトを書く。UI なし。
3. その JSON を、縦軸=年 / 横軸=年 の両方でざっくり描いてみて、**どちらが読めるか**を目で判断する。ここが本体。
4. 下流の間引き基準を決める(各年上位 K? パス数?)。
5. Semantic Scholar の citation intent を足して、上流エッジを background / method で色分けしてみる(F3 の 2 段階目)。

### 決めていないこと

- プロジェクト名。`paper-lineage` は仮。まだ何もコミットしていないので変更は容易。
- 時間軸の向き(縦 / 横)。→ 3 で決める。
- 公開するか(自分用ツールで止めるか、Web で出すか)。出すなら API レート制限とキャッシュの設計が変わる。
