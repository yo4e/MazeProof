# ADR 0001: ローカル構造検証コア（レビュー前の実装判断）

2026-10-08。本人の「ひまなときに進めておいてー」を受け、構造コアと合成テストまでローカル実装する判断を記録する。main や公開物へ反映する判断ではない。

- Python 3.9+ の標準ライブラリのみを使用。現在の Mac で動かせ、画像ライブラリやOSS solverを導入せず純粋なコアを検証できる。最終 UI/配布の言語選定は保留。
- API は `validate_structure(problem, solution=None, unique_required=True)`。payload は UTF-8 JSON bytes/text のみ。ファイルアクセス・ネットワーク・shell は行わない。
- 壁配列と端点契約を SPEC の通り採用し、入力 shape は JSON Schema、寸法依存の行列形状・境界・開口・座標は semantic validator で厳密検査する。両者が必要。schema 単独では maze の意味的妥当性を保証しない。
- unique_required=true を既定とし、simple path を検査。same-cell entrance/exit は別開口でも拒否。問題内 route と別解答 route の同時指定は曖昧なので INVALID_INPUT。別解答を指定する場合は完全な同一迷路と route が必要。
- 到達 BFS と iterative bridge 判定は O(V+E)。別解は経路の非bridge辺を一本除いた BFS で構成する。全域木は独立の診断。route の再訪を拒否する。
- 別解答の route は問題の壁・端点に対して検査し、解答側で壁を消した不正解を通さない。寸法の違うペアは同一性 FAIL、route は INCOMPATIBLE_DIMENSIONS / NOT_RUN。
- 共通結果は SPEC の必須項目と scope を持つ。構造-only の assurance は exact_structure。資料なしチェックは NOT_RUN。画像とPDF magicは UNSUPPORTED。NEEDS_REVIEW は schema に予約し、画像 adapter 未実装のコアでは発生しない。
- 25 MiB/input、250×250、30秒の協調deadlineを使用。route長は62,500以下。JSON decode 前にbytes上限を検査する。deadlineはparse前後とgraph処理で確認するが、JSON decode自体を中断するworkerや512 MiB上限は未実装。サービス境界へ公開する前にworker強制制限が必要。
- malformed/重複キー/非finite/未知項目は INVALID_INPUT。途中障害や上限超過では部分チェック・証拠を破棄し、総合PASSを残さない。例外の入力文字列を結果に含めない。
- CLI exit code の提案は継続（0/1/2/3）。今回CLI/UI/MCPは追加しない。ファイルパスや認識モデルの契約を先取りしない。
- ライセンス・fixture利用許諾は保留。テスト素材は今回独立作成し、MazeMaデータや第三者コードを転用していない。LICENSEや公開許諾は追加しない。

## 後続の更新

構造コアは別途本人の承認で PR #2 から main へマージ済み。さらに本人のMIT採用指示により、上記のライセンス・fixture許諾の保留は解消した（[現行判断](../DECISIONS.md)）。以下の技術的未決事項は継続する。

## 次の人間ゲート

API/schema、unique policy、端点・route source、上限をこのローカル差分でレビューする。画像認識、UI、MCP、配布は未決。段階0の公開向け受入が完了したとは扱わず、構造コア検証をその判断材料とする。
