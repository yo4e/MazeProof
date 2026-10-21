# リポジトリの状態

2026-10-21更新。GitHub: [yo4e/MazeProof](https://github.com/yo4e/MazeProof)。

## 使うブランチ

| ブランチ | 位置付け |
| --- | --- |
| `main` | 本体、操作体験デモ、最新の公開文書を含む開発・配信元。通常の利用はReleaseの導入セットから始める |
| `feat/local-image-workbench` | PR #5でmainに統合済み。既存のローカル検品環境に対応する作業ブランチとして残している |
| `feat/static-demo` | PR #6でmainに統合済み。デモのローカル作業場所に対応するブランチとして残している。公開デモの配信元はmain |

既存の3コミット（`ec61a46` 基本アプリ、`46b7a93` 使い方、`7400107` 一括検品）を履歴ごと保全して、PR #5をmainへ統合済み。操作体験デモはPR #6で追加した。統合の状態・時刻・コミットは[PR #5](https://github.com/yo4e/MazeProof/pull/5)・[PR #6](https://github.com/yo4e/MazeProof/pull/6)で確認できる。文書整備などの一時作業ブランチは、完了後に整理する。

[導入手順](../README.md) · [mainとの差分](https://github.com/yo4e/MazeProof/compare/main...feat/local-image-workbench) · [PR一覧](https://github.com/yo4e/MazeProof/pulls)

以下の4ブランチは、2026-10-21にリモートから削除済み。全コミットがmainの履歴に含まれ、固有の未マージ変更がないこと、配信元や使用中の作業場所ではないことを確認して整理した。削除前の先端と履歴の控えも保全した。変更内容と統合履歴は各PRから参照でき、必要な場合はPRのRestore branchで復元できる。タグやReleaseは削除・移動していない。

| ブランチ | マージ済みPR |
| --- | --- |
| `docs/mazeproof-specification` | [#1 設計仕様](https://github.com/yo4e/MazeProof/pull/1) |
| `feat/structure-validation-core` | [#2 構造検証コア](https://github.com/yo4e/MazeProof/pull/2) |
| `chore/license-support-ci` | [#3 ライセンスとCI](https://github.com/yo4e/MazeProof/pull/3) |
| `feat/json-cli` | [#4 JSON CLI](https://github.com/yo4e/MazeProof/pull/4) |

## バージョンとタグ

パッケージ・画像エンジン・MCPサーバーの内部バージョンは `0.2.0`。2026-10-21に [v0.2.0](https://github.com/yo4e/MazeProof/releases/tag/v0.2.0) を公開し、同日にプレリリース指定を外して通常リリース・Latestとした。対象は `14c67e325124414a807e8d5b875ff9184b2997cd` のまま。デモ・文書の更新や配布物の追加によって、このタグや本体コードは変更していない。

配布物は `MazeProof-0.2.0-mac-linux.zip`（日本語ガイド・wheel・Mac起動ファイル・ソース）、`mazeproof-0.2.0-py3-none-any.whl`、`mazeproof-0.2.0.tar.gz`、`SHA256SUMS.txt` の4点。GitHub Releaseへ添付しており、Pythonを別途導入して使う。詳しい選び方と導入方法は[README](../README.md)を参照。既存の配布ファイルは文書更新のたびに差し替えず、タグ内の元文書は作成当時の記録として保持する。

`preview/v0.2.0-batch.1` は過去の試用版であり、その後の修正や起動ファイルを含まない。タグは一度付けたコミットから動かさない。

通常のCIに加え、[静的デモ用workflow](../.github/workflows/demo.yml)で合成サンプル専用サイトを検証・配信する。デモ配信はmainの変更または明示的な手動実行が対象で、タグを変更しない。詳細は[デモの構成と検証方法](STATIC_DEMO.md)を参照。

## 検証状況の読み方

- [基本アプリ](WORKBENCH_VALIDATION.md)、[使い方](HELP_VALIDATION.md)、[一括検品](BATCH_VALIDATION.md)は、その実装時点の測定記録。文中の「未push」「remote CI未実施」は記録時点の状態である。
- [導入整備](INSTALLATION_VALIDATION.md)などの「正式リリースではない」も当時の作業範囲を示す。通常リリースへの切替後も、過去の検証結果や未検証事項を書き換えていない。配布物追加時にはMacの別々の新規環境でwheelとソースを導入し、CLI・PNG/JPEG/PDF処理・MCP実起動、原本不変、未確認画像が合格にならないことを確認した。公開ファイル4点の再ダウンロードとSHA-256一致も確認済み。HTTP・画面操作は[同じタグ対象の既存CI](https://github.com/yo4e/MazeProof/actions/runs/39535807890)で確認しており、配布物追加時にMacの実ブラウザやダブルクリック起動を再検証したものではない。
- 最新のリモート結果は[GitHub Actions](https://github.com/yo4e/MazeProof/actions/workflows/ci.yml)とPRのChecksを正本とする。**対象コミットSHA**と各jobの結果を確認する。過去のmainの成功や、実行中のjobを最新HEADの成功として扱わない。
- レビュー修正後のローカルでは61件のunittest、単一UI15・一括UI12・レビュー回帰UI9シナリオ、公式MCP SDKクライアント6項目、wheelの新規導入を確認済み。[修正内容と再現手順](REVIEW_FIX_VALIDATION.md)。
- 合成3件で、AIが実応答を読んで再検査し、人への確認箇所をまとめる限定的な実利用を確認した。任意のAIクライアントでの自由対話、恒久登録、実利用者の時短・見落としの比較は未検証・未計測。[今回の導入整備と検証](INSTALLATION_VALIDATION.md)。
- PDFは指定ページを描画した見た目の検査まで。ベクター構造との独立照合は未対応。未確認画像を自動でPASSにする機能はない。

画面・サーバーの更新前には、既存の未保存作業を保存する。GitHubへのpushだけで実行中のローカルPythonサーバーは更新されない。
