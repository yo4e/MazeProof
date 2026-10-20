# リポジトリの状態

2026-10-20。GitHub: [yo4e/MazeProof](https://github.com/yo4e/MazeProof)。

## 使うブランチ

| ブランチ | 位置付け |
| --- | --- |
| `main` | 構造JSON検証コア・CLI。画像GUIを含む試用版は未マージ |
| `feat/local-image-workbench` | PNG/JPEG/PDF指定ページ、確認・修正GUI、一括検品、保存再開、読取り専用MCPの試用版。現在の導入手順はこのブランチのREADME |

作業ブランチ名は画像検品アプリ全体を表すため維持する。既存の3コミット（`ec61a46` 基本アプリ、`46b7a93` 使い方、`7400107` 一括検品）を履歴ごと保全する。mainへの反映はdraft PRでレビューしてから別途判断する。

[試用版のREADME](https://github.com/yo4e/MazeProof/blob/feat/local-image-workbench/README.md) · [mainとの差分](https://github.com/yo4e/MazeProof/compare/main...feat/local-image-workbench) · [PR一覧](https://github.com/yo4e/MazeProof/pulls)

以下はマージ済みの履歴ブランチ。削除・改名・履歴の書換えは行わず保持する。

| ブランチ | マージ済みPR |
| --- | --- |
| `docs/mazeproof-specification` | [#1 設計仕様](https://github.com/yo4e/MazeProof/pull/1) |
| `feat/structure-validation-core` | [#2 構造検証コア](https://github.com/yo4e/MazeProof/pull/2) |
| `chore/license-support-ci` | [#3 ライセンスとCI](https://github.com/yo4e/MazeProof/pull/3) |
| `feat/json-cli` | [#4 JSON CLI](https://github.com/yo4e/MazeProof/pull/4) |

## バージョンとタグ

パッケージ・画像エンジン・MCPサーバーの内部バージョンは `0.2.0`。これはコードの識別子であり、正式リリース済みを意味しない。

検証した試用版のスナップショットは `preview/v0.2.0-batch.1` の形式で識別する。`preview/` を付けてmainに未マージの試用版であることを示す。タグは一度付けたコミットから動かさず、追加修正は別のスナップショットとする。通常の `v0.2.0` タグやGitHub Releaseの公開は別の判断とする。

タグ追加前に確認したリポジトリのworkflowは検査用CIのみで、配布・デプロイ・Release作成処理はない。リポジトリwebhookの登録もない。タグpushではCIが起動するため、その結果も確認する。

## 検証状況の読み方

- [基本アプリ](WORKBENCH_VALIDATION.md)、[使い方](HELP_VALIDATION.md)、[一括検品](BATCH_VALIDATION.md)は、その実装時点の測定記録。文中の「未push」「remote CI未実施」は記録時点の状態である。
- 最新のリモート結果は[試用版のGitHub Actions](https://github.com/yo4e/MazeProof/actions/workflows/ci.yml?query=branch%3Afeat%2Flocal-image-workbench)とPRのChecksを正本とする。**対象コミットSHA**と各jobの結果を確認する。過去のmainの成功や、実行中のjobを最新HEADの成功として扱わない。
- ローカルでは52件のunittest、単一UI15・一括UI11シナリオ、公式MCP SDKクライアント6項目を確認済み。最終HEADでも同じ検査を実行する。
- **LLMを含む自由対話、特定GUI型MCPホストへの恒久登録、実利用者による検品時間・見落としの比較は未検証・未計測。** SDKの実接続試験が成功したことと区別する。
- PDFは指定ページを描画した見た目の検査まで。ベクター構造との独立照合は未対応。未確認画像を自動でPASSにする機能はない。

画面・サーバーの更新前には、既存の未保存作業を保存する。GitHubへのpushだけで実行中のローカルPythonサーバーは更新されない。
