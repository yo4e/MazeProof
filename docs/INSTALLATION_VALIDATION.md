# 導入整備と確認範囲

2026-10-21。PR #5の導入整備。使用中のサーバーと未保存作業を操作せず、別の検証用環境で確認する。正式リリースではない。

## リポジトリへ収録したもの

画像検品本体、一括検品、保存と再開、日本語ガイド、読取り専用MCPは、既に `feat/local-image-workbench` に含まれていた。今回追加したのは、個人の作業場所や起動中のURLに依存しないMac用の起動ファイルと、そのための起動オプション・画面入口、導入説明である。

- `MazeProof一括検品を開く.command` は自分の置かれたフォルダの `.venv/bin/python` を使う。環境変数や起動したディレクトリに依存しないよう `-I` で導入済みパッケージを実行する。
- `serve --batch` は一括入力画面から始める。`--open-browser` を指定したときだけ新しいタブを開く。通常の `serve` は従来どおりURLを表示するだけ。
- 起動のたびに空いているローカルポートと新しい接続用トークンを作る。起動済みサーバーの停止・再利用・設定変更はしない。ブラウザ起動に失敗しても手動でURLを開ける。
- ランチャーをソース配布物にも同梱。wheelには画面とMCPを同梱し、起動オプションを使える。個人向けのURLファイル、画像、作業保存物は公開物に含めない。
- READMEは人の画面の導入、保存先・終了・再開・更新と、AI接続を分けた。MCPの起動設定は個人のパスではなく置換例で示す。

## 確認方法

| 確認対象 | 方法・範囲 |
| --- | --- |
| 起動の安全性・移植性 | `tests/test_launcher.py` の4件。通常起動でブラウザを操作しないこと、明示指定時のURLと新規タブ要求、ブラウザ起動失敗の復帰、使用中ポート、未導入時の案内、日本語と空白を含む別フォルダでのランチャー引数を確認。実ブラウザ起動は置換して検査 |
| HTTPの一括入口 | `tests/test_server.py` で `/batch` の配信、Host制限と既存の保護を検査 |
| 実画面の一括入口 | `scripts/batch_e2e.py` に専用タブからの一括入力・実画像読み込みを追加。元の画面が維持されることも確認する。既存の100件・保存再開・承認取消・エラー復帰と合わせて実行 |
| 新規環境への配布 | wheel/source archiveを生成し、別のvenvへ導入。`scripts/check_install.py` がソース外のcwdから一括入口と静的ファイル7個を開き、画像処理・合成入力の承認・保存復元後の再確認を検査 |
| AI接続 | 既存のMCP単体試験と公式SDKクライアント試験。クライアント登録や権限の自動変更は行わない |
| 文書・公開物 | 内部リンク、構文、Ruff、JS・書式、差分の空白、配布物へのランチャー収録、個人の絶対パス・保存済みトークンが混入していないことを確認 |

上記のHTTP・画面・新規導入の一連の試験は、GitHub Actionsの各対象コミットで実行する。検証用の合成入力だけを使用し、人の作業を代理で承認するものではない。

## ローカルとCIを区別する

Mac上では追加した4テストと静的検査を確認した。新規venvへwheelと固定依存を導入し、ソース外の作業ディレクトリから `-I` で起動オプションとMCPの5ツールを確認した。合成画像と破損ファイルの混在を検査し、確認待ち1件・入力エラー1件、結果再取得の一致と原本不変を確認した。通常サンドボックスでの全unittest実行は、検証用HTTPサーバーのbindが `Operation not permitted` となり、関連8エラーで終了した。この失敗をアプリのテスト成功として扱わず、同じ操作をローカルで繰り返していない。既存の検品サーバーには接続・停止・再起動していない。

今回、Macの実ブラウザやデスクトップは操作しない。以前拒否されたヘッドレス起動も再試行しない。実ブラウザによるUIの確認とHTTPの全試験は、CIの専用Linux環境を使用する。OS上で起動ファイルをダブルクリックして既定ブラウザが開く操作そのものは、今回のMac実機では未確認。

最終コミットの成功・失敗は、[PR #5のChecks](https://github.com/yo4e/MazeProof/pull/5/checks)と[GitHub Actions](https://github.com/yo4e/MazeProof/actions/workflows/ci.yml)で対象SHAを照合する。main統合後も、merge commitに対するCIを別途確認する。実行中や別コミットの成功を流用しない。

## 再現

[READMEの開発環境](../README.md)を用意し、次を実行する。

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_repository.py
.venv/bin/python tests/check_schemas.py
.venv/bin/python -m ruff check mazeproof tests scripts
npm run check
bash -n MazeProof一括検品を開く.command
.venv/bin/python -m build --no-isolation
python3.12 -m venv .evidence/install-venv
.evidence/install-venv/bin/python -m pip install dist/*.whl
.venv/bin/python scripts/check_install.py --python "$PWD/.evidence/install-venv/bin/python"
.venv/bin/python scripts/batch_e2e.py
```

CIではPython 3.12 / 3.13の全テストとクリーン導入、別jobの単一・一括・レビュー回帰UI、公式MCP SDKとの接続を実行する。保存物・ログは `.evidence/` 以下でGitの対象外。

## AI実利用と性能評価について

10月21日の夜間には、合成した普通の迷路、赤線が途切れた迷路、壊れた画像の3件を、Codexが一時的なMCP接続で検査した。AIが返答を読んで、既知の合成条件に基づいて格子を指定し直し、再検査・結果再取得・人への確認事項の作成まで行った。画像の総合PASSと人の承認操作はともに0件。これはSDKの疎通だけではなく、限定した3件の実利用である。

ただし、特定クライアントへの恒久登録、任意画像の自由対話、人本人の検品時間や見落としの改善を確かめたものではない。実際の商品での認識精度や時短効果は未計測。今回の導入整備でも、この限界は変えていない。
