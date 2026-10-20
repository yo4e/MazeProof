# 一括検品の検証記録

2026-10-20、`7400107` 実装時点の記録。ローカルの `feat/local-image-workbench`、使い方ページ追加後の `46b7a93` から実装。この記録時点では公開・push・PR・mergeを行っていなかった。後続のGitHub保全と最新CIの確認先は[リポジトリの状態](REPOSITORY_STATUS.md)を参照。既存のChromeと作業中サーバーを操作せず、専用サーバーとヘッドレスChromiumで確認した。

## 実装した動線

- 使い方の「トップへ戻る」から実際に使える投入画面へ進む。元の作業タブは維持する。認証情報は同一originのタブ内セッションだけに渡し、使い方URLには含めない。
- 最大100件の問題画像と任意の解答を明示的に組み合わせる。PDFは行ごとのページ指定と行複製に対応する。
- 読み込み、一覧の絞り込み、各件の修正・承認、一覧への復帰、次の確認待ちへの移動。保存前・移動前に編集中のモデルを同期する。
- 現在の1件が終わってから一時停止し、未処理だけ再開する。1件のエラーで全体を止めず、差し替え・再試行できる。
- 原画像・修正・未処理分を `.mazeproof-batch` に保存し、全件を再認識して再開する。保存内の結果や承認は信用しない。JSON/HTMLの一覧レポートには未処理やエラーも残す。
- サーバーが古い4件以外を追い出す挙動を廃止。保持予算に達したら新規受付を拒否し、既存の編集・承認を保つ。
- 共通の `batch.inspect_item` を使う読取り専用MCP `inspect_batch`。エラーを行ごとに分離し、時間・返却量の予算に達した残りはID付きの `QUEUED` として返す。

## 確認結果

macOS arm64、Python 3.12.13、専用headless Chromium。合成fixtureのみ使用。

| 検査 | 実結果 |
| --- | --- |
| unittest | **52件成功**。従来46件＋一括の6件 |
| 既存の単一UI | **15シナリオ成功**、8.02秒 |
| 一括UI | **11シナリオ成功**、16.07秒 |
| 公式MCP SDKの実クライアント | **6項目成功**、7.39秒。SDK 2.3.0、実stdio、protocol 2025-06-18 |
| 結果schema | 13 core + 7 CLIシナリオ、5サンプル成功 |
| 静的検査 | Ruff、Prettier、JS構文、Python構文・内部リンク、git diff --check |
| 配布 | wheel/source archive生成。新規venvへwheelを導入し、ソース外のcwdで起動。静的asset6個、画像worker、承認PASS、一括復元後NEEDS_REVIEWを確認 |

時間はこの小さな合成入力を用いた1回の実測であり、任意サイズの迷路や人の確認時間の保証ではない。

一括UIの11シナリオ：

1. 使い方からトップへ移動しサンプルを読み込める。元のタブをリセットしない。
2. 8件を投入し、処理中に一時停止。完了1件・未処理7件をまとめて保存できる。
3. 問題のみ、問題・解答ペア、薄い壁による暫定違反、格子推定の曖昧さ、破損画像が混在しても区別する。
4. 解答上の未確認境界を解消して明示承認。5件目へ移動後も1件目の承認が残る。
5. 承認済みの壁を変更するとPASSを取り消す。移動・作業保存・一覧レポートに修正が反映される。
6. 保存データにPASSを注入しても復元直後は全件未処理。未処理レポートに古い結果を載せず、再認識後は修正を保持して確認待ちに戻る。
7. 破損画像を差し替えて続行できる。削除確認を取り消すと行が残る。
8. 同じPDFの問題1ページ・解答2ページの指定を保持する。
9. 最後の行を除いたあと、トップへ戻って新しく始められる。
10. 100件投入の最初に通信失敗を注入。99件を処理し、失敗行の再試行後に100件すべて確認待ちとなる。1件目を開き直せる。未承認の総合PASSは0件。
11. JS実行エラー・外部HTTP要求なし。390px幅でもページ全体の横はみ出しなし。

追加の単体試験は100件の混在（90確認待ち・10エラー）、重複ID/件数拒否、時間・返却量予算、保持上限でも古い承認を残すこと、同じ画像のGUI/MCPでchecks・evidence・digestが一致すること、許可root外・承認キー注入の拒否、検証方針変更時の承認取消を含む。

公式SDKクライアント試験は実サブプロセスとの初期化・5ツール発見から始め、構造PASSと画像確認待ちの区別、PNG/PDF・破損・root外・承認注入の混在バッチ、結果再取得、承認ツールの不在、100画像の検査、全入力のハッシュ不変まで確認した。通常アプリにSDK依存は追加していない。

## 再現と成果物

[README](../README.md)の開発環境で実行する。

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_schemas.py
.venv/bin/python tests/check_repository.py
.venv/bin/python -m ruff check mazeproof tests scripts
npm run check
.venv/bin/python scripts/e2e.py
.venv/bin/python scripts/batch_e2e.py
.venv/bin/python -m build --no-isolation
```

既存browserを使う場合は両UIスクリプトへ `--browser /absolute/path/to/chromium` を指定する。公式SDKの専用環境と実行方法は [LOCAL_MCP](LOCAL_MCP.md)。wheelを新規venvへ導入した後の確認は `scripts/check_install.py --python /absolute/path/to/new-venv/bin/python`。

ローカルの `.evidence/batch/result.json`、`pairing.png`、`mixed-list.png`、`mobile.png`、`hundred.png`、保存・復元ファイル、JSON/HTMLレポート、`.evidence/mcp-client/result.json`、`.evidence/batch-install.json` が証拠。Git対象外で、私的なMazeMa素材は含めていない。

## 制限・未検証

- 自動格子推定は正解保証ではない。今回の壁追加fixtureでも4列を2列に推定したケースがあった。unknownと確認待ちを維持し、原画像全体の照合・必要な格子修正を前提にする。
- UIは100件・原画像合計32MiB・作業ファイル128MiB。サーバーは128作業・推定保持量192MiBで新規受付を制限する。RSSの厳密なhard limitではなく、大きい画像を100件必ず保持できる保証もない。
- 自動保存、ファイル名による自動ペア化、全PDFページの自動投入、一括承認、専用の一括CLIは未対応。GUI新規バッチへの元構造JSONの行別追加も未対応。MCPでは参照JSONを行ごとに渡せる。
- PDFのベクター構造との独立照合、署名付き承認のMCPへの引渡しは未対応。MCPからGUI作業を直接開く機能はない。
- 公式SDKとの実接続は検証済み。特定GUIホストへの恒久登録、LLMを含む自由対話、実利用者による確認時間・見落としの比較は未実施。
- Windows、Safari/Firefox、Linux実機、上限近い大画像の全組合せは未検証。remote CIは設定のみで、未pushのため実行していない。
- ユーザーの既存サーバーは実行中の旧Pythonコードを保持する。新機能は新しく起動したサーバーで使う。既存画面の未保存作業を先に保存してから切り替える。
