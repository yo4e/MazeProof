# リポジトリの状態

2026-10-21更新。GitHub: [yo4e/MazeProof](https://github.com/yo4e/MazeProof)。

## 使うブランチ

| ブランチ | 位置付け |
| --- | --- |
| `main` | PR #5統合後の通常の導入先。構造JSON、画像GUI、一括検品、保存再開、読取り専用MCP、Mac起動ファイルを含む試用版 |
| `feat/local-image-workbench` | PR #5でmainに統合済みの履歴ブランチ。通常の導入はmainまたはv0.2.0から行う |

既存の3コミット（`ec61a46` 基本アプリ、`46b7a93` 使い方、`7400107` 一括検品）を履歴ごと保全して、PR #5をmainへ統合済み。統合の状態・時刻・コミットは[PR #5](https://github.com/yo4e/MazeProof/pull/5)で確認できる。

[導入手順](../README.md) · [mainとの差分](https://github.com/yo4e/MazeProof/compare/main...feat/local-image-workbench) · [PR一覧](https://github.com/yo4e/MazeProof/pulls)

以下はマージ済みの履歴ブランチ。削除・改名・履歴の書換えは行わず保持する。

| ブランチ | マージ済みPR |
| --- | --- |
| `docs/mazeproof-specification` | [#1 設計仕様](https://github.com/yo4e/MazeProof/pull/1) |
| `feat/structure-validation-core` | [#2 構造検証コア](https://github.com/yo4e/MazeProof/pull/2) |
| `chore/license-support-ci` | [#3 ライセンスとCI](https://github.com/yo4e/MazeProof/pull/3) |
| `feat/json-cli` | [#4 JSON CLI](https://github.com/yo4e/MazeProof/pull/4) |

## バージョンとタグ

パッケージ・画像エンジン・MCPサーバーの内部バージョンは `0.2.0`。2026-10-21に [v0.2.0](https://github.com/yo4e/MazeProof/releases/tag/v0.2.0) を試用版（GitHubのプレリリース）として公開した。対象は `14c67e325124414a807e8d5b875ff9184b2997cd`。デモの追加でこのタグや本体のバージョンは変更しない。

`preview/v0.2.0-batch.1` は過去の試用版であり、その後の修正や起動ファイルを含まない。タグは一度付けたコミットから動かさない。

通常のCIに加え、[静的デモ用workflow](../.github/workflows/demo.yml)で合成サンプル専用サイトを検証・配信する。デモ配信はmainの変更または明示的な手動実行が対象で、タグを変更しない。詳細は[デモの構成と検証方法](STATIC_DEMO.md)を参照。

## 検証状況の読み方

- [基本アプリ](WORKBENCH_VALIDATION.md)、[使い方](HELP_VALIDATION.md)、[一括検品](BATCH_VALIDATION.md)は、その実装時点の測定記録。文中の「未push」「remote CI未実施」は記録時点の状態である。
- 最新のリモート結果は[GitHub Actions](https://github.com/yo4e/MazeProof/actions/workflows/ci.yml)とPRのChecksを正本とする。**対象コミットSHA**と各jobの結果を確認する。過去のmainの成功や、実行中のjobを最新HEADの成功として扱わない。
- レビュー修正後のローカルでは61件のunittest、単一UI15・一括UI12・レビュー回帰UI9シナリオ、公式MCP SDKクライアント6項目、wheelの新規導入を確認済み。[修正内容と再現手順](REVIEW_FIX_VALIDATION.md)。
- 合成3件で、AIが実応答を読んで再検査し、人への確認箇所をまとめる限定的な実利用を確認した。任意のAIクライアントでの自由対話、恒久登録、実利用者の時短・見落としの比較は未検証・未計測。[今回の導入整備と検証](INSTALLATION_VALIDATION.md)。
- PDFは指定ページを描画した見た目の検査まで。ベクター構造との独立照合は未対応。未確認画像を自動でPASSにする機能はない。

画面・サーバーの更新前には、既存の未保存作業を保存する。GitHubへのpushだけで実行中のローカルPythonサーバーは更新されない。
