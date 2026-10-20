# MazeProof

迷路の問題画像と赤線入り解答を読み込み、壁・格子・入口出口を確認して検証するローカルアプリです。PNG / JPEG、PDF の指定ページ、構造 JSON を扱います。

**画像の認識と数学的な検証は別です。未承認の画像は必ず `NEEDS_REVIEW`。承認後の `PASS` も、確認したモデルに対する条件付きの結論です。**

## 起動する

Mac / Linux、Python **3.12 以上**が必要です。初回の依存インストールにはネット接続が必要ですが、起動後の画像処理はローカルで完結します。Node.js は通常の利用には不要です。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/mazeproof serve
```

ターミナルに表示された `http://127.0.0.1:.../#...` をブラウザで開きます。URL の後半はセッション用の秘密です。他人に共有しないでください。自動でブラウザを起動したり画面を切り替えたりはしません。終了はターミナルで `Ctrl+C`。

インストール後は好きなフォルダから `mazeproof serve` を起動できます。ソースから開発する場合は `pip install -e .`。固定ポートが必要なら `mazeproof serve --port 8765`。

## 検品の流れ

画面上部の **「使い方」** から、画像の選び方・重ね表示・承認・判定の意味・保存と再開を説明するガイドが別タブで開きます。検品中の状態はそのまま保たれます。[ガイドのソース](mazeproof/web/help.html)はアプリに同梱され、外部通信なしで読めます。

1. 問題画像と、任意の解答画像を選ぶ。PDF は問題と解答のページ番号をそれぞれ指定する。同じ PDF も選べます。「合成サンプルで試す」ならファイルは不要です。
2. 格子の行列数と外周位置を確認する。違う場合は「格子・切り出し・回転」で数値を直して再認識する。外周枠の座標は**壁の中心**です。
3. 原画像に重ねた壁を確認する。壁・通路の反転、入口出口の指定、赤線の描き直しができます。入口・出口を変えても外周の壁は自動変更しません。橙色の不確かな境界は個別に確認または修正します。
4. 「暫定チェック」で不正な開口、到達不能、別解、壁横断、問題と解答の壁差を確認する。必要なら修正し、元に戻す・やり直すを使う。
5. 全体を原画像と照合してチェックボックスを選び、「確認を承認して検証」。入力・格子・壁・入口出口・解答・検証方針が変わると承認は無効になります。
6. 「作業を保存」で原本と修正を一緒に保存する。レポート JSON / HTML、構造 JSON、表示中の重ね画像 PNG も書き出せます。作業を開き直すと再承認が必要です。

解答画像がなければ解答の合法性・問題解答の一致は `NOT_RUN`。元の構造 JSON を指定すれば、問題の描画から確認したモデルとの違いも検査します。`PASS` の文字だけでなく、未検査の範囲と確証水準を確認してください。

## 対応範囲と制限

- 矩形の直交格子、白い通路と黒い壁、外周の入口・出口が各1つ。赤線は単一の、セル中心を通る直交経路が対象です。
- 自動格子推定は候補です。内部の壁が少ない長い通路や余白・文字を含む画像では手動修正が必要です。写真、自由な手描き、曲線、斜めの迷路を自動復元する機能ではありません。
- 1ファイル25 MiB、描画後2,000万画素、最大250×250セル、1セル8画素以上。原画像の壁を消さないため、読込み時の自動縮小はしません。
- 画像デコード・認識は別プロセス。1組の認識予算30秒、各workerのRSS監視上限512 MiB。数学的コアは別途30秒の予算。RSSは短い間隔の監視であり、OSによる厳密な瞬間最大値保証ではありません。
- PDF は最大20ページ、明示した1組のみ、144dpiで描画。回転・CropBoxを記録します。**ベクター構造の抽出・描画との一致証明は未対応**です。暗号化、文書JavaScript、添付ファイルを持つ PDF は拒否します。他のアクションも実行せず、フォーム環境は初期化しません。
- 赤線が覆った壁は観測不能として扱い、問題画像から勝手に補いません。圧縮で失われた壁を復元できる保証はありません。
- 設定・画像・結果はブラウザとローカルサーバーのメモリに保持します。自動保存・クラウド送信・telemetry はありません。サーバー終了で失われるので、必要な作業は保存してください。作業ファイルとHTMLレポートは画像を含むため、共有範囲に注意してください。

検証した品質範囲と未検証事項は [検証記録](docs/WORKBENCH_VALIDATION.md) を参照してください。

## CLI

既存の構造 JSON 検証は維持しています。コアと従来CLIだけなら Python 3.9+、外部依存なしでソースから動きます。

```sh
python3 -m mazeproof examples/problem.json --solution examples/solution.json
python3 -m mazeproof examples/multiple.json --format text
```

画像検査と編集用作業ファイルの生成は、アプリ用環境で実行します。CLI から人間の承認は行いません。

```sh
mazeproof inspect problem.png --solution solution.jpg --save-project work.mazeproof
mazeproof inspect book.pdf --problem-page 1 --solution book.pdf --solution-page 2
mazeproof inspect problem.png --reference examples/problem.json
```

`--settings settings.json` は `{"problem":{"geometry":{"x0":24,"y0":24,"x1":312,"y1":312,"cols":4,"rows":4},"rotation":0}}` の形式です。解答側は `solution` キーで独立に指定できます。保存先の既存ファイルは上書きしません。

| 終了コード | 意味 |
| --- | --- |
| 0 | 構造モデルの PASS |
| 1 | 確定モデルで条件違反 |
| 2 | 認識モデルの確認待ち |
| 3 | 入力不正・未対応・上限・内部エラー |

`--allow-multiple` は唯一解の要件だけを外します。到達性と提出解答の合法性は引き続き検査します。

## ローカル MCP

```sh
mazeproof mcp --allow-root /absolute/path/to/your/mazes
```

stdio MCP の `validate_structure`、`inspect_file`、`validate_pair`、`get_result` を提供します。ファイル指定は絶対パス、起動時に許可したディレクトリ内の通常ファイルだけ。URL・symlink・FIFO・ディレクトリ外を拒否します。書込み・外部送信・自動承認ツールはありません。画像の結果は常に確認待ちです。[設定と契約](docs/LOCAL_MCP.md) を参照。

## 開発と検証

```sh
.venv/bin/python -m pip install -e . -r requirements-ci.txt -r requirements-dev.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_schemas.py
.venv/bin/python tests/check_repository.py
.venv/bin/python -m ruff check mazeproof tests scripts
npm ci --ignore-scripts
npm run check
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/e2e.py
.venv/bin/python -m build --no-isolation
git diff --check
```

UIテストは専用のヘッドレスブラウザで実行し、画面を占有しません。スクリーンショット・合成入力・テスト結果はGit対象外の `.evidence/` に保存します。サンプルだけを作るなら `python scripts/generate_samples.py /path/to/new-folder`。

- [設計仕様](docs/SPEC.md) / [段階計画](docs/BUILD_PLAN.md)
- [構造コアADR](docs/adr/0001-structure-core.md) / [ローカルアプリADR](docs/adr/0002-local-workbench.md)
- [入力schema](schemas/maze.schema.json) / [結果schema](schemas/result.schema.json)
- [独立検証方針](docs/VALIDATION.md) / [合成fixtureの由来](tests/fixtures/PROVENANCE.md)
- [依存notice](docs/DEPENDENCIES.md) / [CI](docs/CI.md)

MazeMa の非公開商品・私的画像は公開fixtureに使いません。アプリ・文書・独立合成fixtureは [MIT License](LICENSE)。支援は任意です：[コーヒーを奢ってね ☕](https://ko-fi.com/yo4e)。
