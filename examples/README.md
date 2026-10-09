# 構造 JSON CLI サンプル

全サンプルは独立した2×2の合成格子。MazeMa商品や第三者データは使っていない。
このrepoの [MIT License](../LICENSE) を適用する。行・列は0始まり、trueは壁。

| ファイル | 内容と期待値 |
| --- | --- |
| [problem.json](problem.json) | 通路(0,0)→(0,1)→(1,1)、入口(0,0,N)、出口(1,1,S)。routeなし。単独では到達性・uniqueがPASS、解答検査はNOT_RUN |
| [solution.json](solution.json) | 同じ迷路と上記3セルの合法route。problemとペアでPASS、exit 0 |
| [multiple.json](multiple.json) | 下側にも(0,0)→(1,0)→(1,1)の通路を追加。別解があるため既定policyではFAIL、exit 1。--allow-multipleならPASS |
| [wall-crossing.json](wall-crossing.json) | 元の壁を残したまま下側ルートを解答として指定。index 1でROUTE_WALL_CROSSING、exit 1 |
| [invalid.json](invalid.json) | 正しいJSON構文だが必須フィールドが不足。INVALID_INPUT/OBJECT_FIELDS、exit 3 |

repo rootから：

```sh
python3 -m mazeproof examples/problem.json --solution examples/solution.json --format text
python3 -m mazeproof examples/multiple.json --format text
python3 -m mazeproof examples/wall-crossing.json --format text
python3 -m mazeproof examples/invalid.json
```

比較する問題と解答はともに完全なmaze schemaを使う。route-only JSONは受け付けない。
JSON stdoutは共通result schema。人間向けtextでもassurance、各check、未検査部分、違反位置を表示する。
入力の原本は変更しない。ファイルの読み取り失敗や引数不正も、結果JSONとexit 3で返す（--helpはexit 0）。
