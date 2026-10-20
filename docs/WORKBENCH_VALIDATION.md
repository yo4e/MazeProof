# ローカルアプリの検証記録

2026-10-20。基準main: `a72a669b81f3a7c81b40dc2965071799d1253f4d`。既存checkoutの変更はなく、別checkoutで実装した。remote mainの再確認でも同じcommitだった。push、PR、merge、release、デプロイは行っていない。

## 実行環境

macOS 27.0.1、arm64、Python 3.12.13、Node 22.22.0。アプリ依存はrequirements-app.txtに固定。専用headless Chromiumで1440×1100と390×844のviewportを確認した。Macの画面占有・操作は行っていない。

## 確認結果

| 検査 | 結果 |
| --- | --- |
| unittest | **46件成功**。既存20件＋画像/PDF・承認・worker・MCP・HTTPの26件 |
| 既存コアの後方互換 | システムPython 3.9.6でも既存20件成功 |
| 結果schema | 13 core + 7 CLIシナリオ、5サンプル成功。認識未確認・承認済み結果も追加テストで検証 |
| 実UI | **12シナリオ成功**。ブラウザの実際のファイル入力・ボタン・canvas・downloadを使用 |
| 静的検査 | Ruff、JavaScript構文、Prettier、Python構文・内部リンク、git diff --check |
| 配布 | wheel/source archive生成、新しいvenvへwheelをインストール。ソース外のcwdから起動、全静的asset、別workerの画像認識、確認待ち→承認PASSを確認 |
| 通信 | UI一連操作に外部HTTP要求なし。Host/Origin/token拒否をAPIテストで確認 |

UIの12シナリオ:

1. PNGペア投入→確認待ち・承認不可。
2. 赤線で覆われた15境界を個別確認→条件付きPASS。
3. 作業、JSON/HTMLレポート、構造JSON、重ね画像PNGの保存。
4. 壁修正直後の承認取消→壁横断FAIL→undo/redo後も再承認が必要。
5. 解答を消してcanvas上で全セルをなぞり直す→承認PASS。
6. 再認識の入力エラー時に古いPASSを消し、元の作業を保持。
7. 再認識ダイアログの取消は作業を維持、実行後は承認をリセット。
8. 承認済み作業の復元も確認待ちに戻る。
9. 壊れた画像から復帰し、同じPDFの明示ページ1/2を投入。
10. 読込み取消後の遅れた結果は画面を置き換えず、次の投入が可能。
11. 390px幅でページ全体の横はみ出しがない。
12. JavaScriptエラー、外部HTTP要求がない。

追加の故障検査には1pxの赤線断線、分岐、斜め線、余分な赤い印、薄い・部分欠損の壁、JPEG、透過、EXIF/90°回転、描画と元JSONの差、PDF rotation/crop metadata、過大ページ/ページ数、文書JavaScript・添付の拒否、symlink/親ディレクトリ交換、FIFO、worker時間/RSS予算、API競合、承認revision不一致を含む。暗号化拒否のフラグ分岐はmockで確認し、実暗号化PDFの全方式を網羅していない。

## 認識の測定

`scripts/corpus_check.py`は独立にseed付きの壁配列を作り、3×4、10×8、25×20、壁幅1/3/5px、PNG/JPEG quality 90/40の**27ケース**を描画する。seedは `20261020 + width`。

- 正しい格子を与えた場合、全壁のtopology一致: **27/27**。
- 自動格子推定を含むモデル完全一致: **24/27**。3×4・1px壁の3ケースで不一致。手動格子の設定によって正しい壁を観測できる。
- 未承認の総合PASS: **0/27**。全ケースNEEDS_REVIEW。
- in-processで自動/指定格子の両方を処理し約0.7秒、ピークRSS約69〜70MiB。この計測はworker起動・ブラウザ・大画像を含まない。

これは合成コーパスの結果であり、一般画像での精度や誤りゼロを保証しない。自動承認は実装していない。画像に失われた壁の意図を復元できると主張しない。

## 再現

[README](../README.md)の環境構築後:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_schemas.py
.venv/bin/python tests/check_repository.py
.venv/bin/python -m ruff check mazeproof tests scripts
npm ci --ignore-scripts
npm run check
.venv/bin/python scripts/corpus_check.py
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/e2e.py
.venv/bin/python -m build --no-isolation
```

既存のブラウザbinaryを使うときは `scripts/e2e.py --browser /absolute/path/to/chromium`。画面は開かない。

wheelを別の新規venvへ入れたあと、`python scripts/check_install.py --python /absolute/path/to/new-venv/bin/python`で、ソース外起動とサンプルの確認・承認を再現できる。

ローカルの `.evidence/` に `unittest.log`、`e2e.json`、`corpus.json`、`install.json`、画面画像、保存した作業・レポートを残した。これらは合成素材のみで、Git対象外。原本を入力した場合も自動で公開される仕組みはない。

## 残る制約・未検証

- 任意の写真・斜め/曲線/立体迷路、deskew、透視補正は未対応。失敗した格子推定も編集開始用の仮格子として表示する。
- PDFは144dpiの見た目の検査。ベクター構造の抽出と独立照合、複数ペア一括検品は未実装。
- 個別MCPクライアントへの登録・人間との対話は未実施。stdio実clientによるhandshakeとtool呼出しは成功。
- Windows、Safari/Firefox、実スマートフォン、Linux実機のローカル試験は未実施。Linux/Python 3.13等のremote CI設定は更新したが、未pushのため実行していない。
- 20MP付近の全入力でのメモリ収容や所要時間を保証しない。512MiBはworkerのRSS監視で、瞬間的な超過をOSが防ぐhard sandboxではない。
- 人間が誤ったモデルを承認する可能性は残る。保存レポートは署名付き証明書ではなく、digestと実行条件付きの検証記録。

公開前のmaintainerによる品質範囲確認と、公開操作そのものは別の工程。本作業はローカルで使用・レビューできる候補として完了する。
