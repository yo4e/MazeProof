# CI の範囲

`push` と `pull_request` で Python 3.12 / 3.13 の検証を実行する設定。実行権限は `contents: read` のみ。checkout/setup-python actionはcommit SHA固定。

- 独立oracle、全列挙、故障注入を含む構造コアと従来JSON CLI
- 画像/PDFのdecode・認識・承認・取消・保存復元・構造参照との比較
- workerの時間/RSS上限、MCP stdio handshake、allowed-root逸脱とsymlink拒否
- loopback HTTPのHost/Origin/token検査、競合、エラー復帰
- 起動ファイルのパス移植性、ブラウザ起動の明示指定と失敗時の復帰
- wheel/source archiveの生成と新規仮想環境への導入、ソース外からの一括入口・画像処理・保存復元
- 結果schema、サンプル、Python構文・内部リンク、Ruff、JavaScript構文、Prettier
- 別jobで専用headless Chromiumを使った単一・一括UI一連操作（100件、停止・保存再開、承認取消、エラー復帰）
- レビュー回帰UI（未同期undo、遅延・失敗する保存、受付後の取消、受領確認の応答欠落）
- 分離したQA環境の公式MCP Python SDKから実stdioサーバーへ接続する一括検品試験

ローカル手順は[README](../README.md)参照。UI証拠は`.evidence/`へ保存し、リポジトリやCI artifactへ自動公開しない。製品データはテストに使わない。

これは設定された検査範囲の説明。実行結果は[GitHub Actions](https://github.com/yo4e/MazeProof/actions/workflows/ci.yml)またはPRのChecksで、対象のコミットSHAとともに確認する。`success` / `failure` / 未実行・実行中を分け、以前のmainの成功を新しいHEADの成功として扱わない。ブランチと試用版タグの位置付けは[リポジトリの状態](REPOSITORY_STATUS.md)を参照。Windows、全ブラウザ、任意画像に対する品質保証ではない。
