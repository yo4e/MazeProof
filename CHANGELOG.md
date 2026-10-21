# 変更履歴

## 操作体験デモ（本体 v0.2.0 とは別の静的サイト）

- 合成3例の原画像と重ね表示、拡大、決められた修正前後と結果・レポートの例、やり直し。
- 利用者画像の投入、自由編集、実画像の検査、人の承認は行わない。ローカル導入とAI接続を案内する。
- GitHub Pagesへ静的デモのみ配信。公開前の画面試験と公開URLの再検証を専用workflowで行う。

## 0.2.0 試用版 — 2026-10-21公開

PR #5でmainへ統合した画像検品版。[GitHub Release](https://github.com/yo4e/MazeProof/releases/tag/v0.2.0)は試用版として公開。タグは `14c67e325124414a807e8d5b875ff9184b2997cd` に固定。

- 矩形格子のPNG/JPEG、PDF指定ページを読み込み、壁・入口出口・赤い解答線を重ね表示するローカルGUI。
- 不確かな観測の確認、壁と解答の修正、明示承認、編集後の再検査。未承認画像は確認待ちを維持する。
- 問題と解答を明示的に組み合わせる一括検品。最大100件、停止・再試行・保存再開、JSON/HTMLの一覧レポート。
- 日本語の使い方ページとトップへの導線。
- 移植できるMac用起動ファイル。`serve --batch --open-browser` で新しい一括検品画面を起動。人の画面とAI接続を分けた導入・保存・再開の案内。
- allowed rootsを使う読取り専用stdio MCP。`inspect_batch` を含む5ツール、公式SDKとの実クライアント試験。
- 合成入力によるUI試験、故障注入、独立oracle、配布パッケージの導入確認。
- PR #5のレビュー指摘を修正。未同期undo後の承認失効、保存完了までの操作ロック、赤画素の二次元連結確認、取消・未受領読込みの回収。[修正と回帰検証](docs/REVIEW_FIX_VALIDATION.md)。

認識は原画像の完全な証明ではなく、承認後のPASSも人が確認したモデルに対する結果。合成3件で限定的なAI実利用を確認したが、任意のAIクライアントでの自由対話と人の検品時間短縮は未検証。

[導入・使い方](README.md) · [検証記録](docs/BATCH_VALIDATION.md) · [ブランチ・タグの方針](docs/REPOSITORY_STATUS.md)

## 以前の構造JSON版

構造JSONの検証コアとCLI、結果schema、別解witness、独立oracleと故障注入テスト。関連するマージ済みPRは [#2](https://github.com/yo4e/MazeProof/pull/2)、[#4](https://github.com/yo4e/MazeProof/pull/4)。
