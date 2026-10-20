# CI の範囲

`push` と `pull_request` で Python 3.12 / 3.13 の検証を実行する設定。実行権限は `contents: read` のみ。checkout/setup-python actionはcommit SHA固定。

- 独立oracle、全列挙、故障注入を含む構造コアと従来JSON CLI
- 画像/PDFのdecode・認識・承認・取消・保存復元・構造参照との比較
- workerの時間/RSS上限、MCP stdio handshake、allowed-root逸脱とsymlink拒否
- loopback HTTPのHost/Origin/token検査、競合、エラー復帰
- 結果schema、サンプル、Python構文・内部リンク、Ruff、JavaScript構文、Prettier
- 別jobで専用headless Chromiumを使ったUI一連操作

ローカル手順は[README](../README.md)参照。UI証拠は`.evidence/`へ保存し、リポジトリやCI artifactへ自動公開しない。製品データはテストに使わない。

これは設定された検査範囲の説明であり、この変更のremote CI実行済みを意味しない。Windows、全ブラウザ、任意画像に対する品質保証ではない。
