# ローカル MCP

Python環境へMazeProofをインストールしたあと、MCP clientに次の起動設定を登録する。実際の絶対パスへ置き換える。GUIの起動とは別プロセス。

```json
{
  "mcpServers": {
    "mazeproof": {
      "command": "/absolute/path/to/venv/bin/mazeproof",
      "args": ["mcp", "--allow-root", "/absolute/path/to/mazes"]
    }
  }
}
```

起動設定・新しい権限を利用者のMCP clientへ自動登録することはしない。`--allow-root` は複数指定可能。Mac/Linuxの通常のローカルディレクトリを指定する。必要以上に広いホームディレクトリなどを渡す必要はない。

| tool | 引数 | 結果 |
| --- | --- | --- |
| validate_structure | problem: JSON文字列, solution?: JSON文字列, unique_required?: bool | 既存の構造コアの結果 |
| inspect_file | path: 絶対パス, page?: 1からのPDFページ, geometry?: 格子, rotation?: 0/90/180/270 | 認識モデル、unknown、変換、未承認結果 |
| validate_pair | problem / solution: 絶対パス, problem_page? / solution_page?, unique_required? | 独立に認識したペアの未承認結果 |
| inspect_batch | items: ID・問題・任意の解答などを明示した配列（下記） | 各行の未承認結果、エラー、残りの未処理ID、件数 |
| get_result | requestId | 同じプロセス内の直近8件の結果 |

stdioは1行1JSON-RPC。protocolVersionは2025-06-18と2024-11-05。initialize、initialized notification、tools/list、tools/call、pingを扱う。stdoutはプロトコルだけに使う。画像byte列やファイル名は返却する観測から除外し、モデルと座標・digestを返す。生成・削除・外部ネットワーク・承認ツールはない。

認識結果のPASS/FAILは暫定の数学的検査。総合は `NEEDS_REVIEW` のままで、利用者の代わりに承認してはいけない。画像を確認・修正するにはGUIへ読み込む。MCPに保存済みレポートを渡しても、人間の承認として信頼する機能はない。

## 一括検品

`inspect_batch` へ次のような引数を渡す。ファイルの自動組み合わせはしない。

```json
{
  "items": [
    {"id": "maze-01", "problem": "/absolute/path/to/mazes/problem.png",
     "solution": "/absolute/path/to/mazes/answer.png", "unique_required": true},
    {"id": "maze-02", "problem": "/absolute/path/to/mazes/book.pdf",
     "problem_page": 3, "solution": "/absolute/path/to/mazes/book.pdf",
     "solution_page": 4}
  ]
}
```

各行の必須キーは `id`（重複なし、1〜128文字）、`problem`（絶対パス）。任意キーは `solution`、`problem_page` / `solution_page`、`problem_geometry` / `solution_geometry`、`problem_rotation` / `solution_rotation`、`reference`（元構造JSONの**文字列**、パスではない）、`unique_required`（既定true）。格子の形式はREADMEの `--settings` と同じ。PDFのページは明示する。新しい承認用キーを足しても受け付けない。

返却は従来通り `content[].text` のJSONで `{ "result": ... }`。一括結果は `schemaVersion: "mazeproof.batch-result/1"`、`requestId`、`counts`、入力順を保つ `items` を持つ。各行は元のIDと `state` を返す。

- `NEEDS_REVIEW`：`result` に既存の画像検査結果を持つ。暫定のPASS/FAILやunknown・反例・原本digestを含むが、人の承認ではない。
- `ERROR`：その行の `result` に入力不正・未対応・上限などの理由を持つ。他の行は続行する。
- `QUEUED`：時間・返却量の予算でまだ結果を返せなかった行。元のIDと入力を再送する。サーバーがバックグラウンドで処理を続けるジョブではない。

1呼出し1〜100件。行の間で60秒の予算を確認し、処理中の1件には既存の認識・コア予算を適用する。返却詳細の予算は8MiB（envelopeと未処理IDの小さな付加分を除く）。予算に達したら残りを `QUEUED` として返す。全件エラーの場合を除き総合は `NEEDS_REVIEW`。`isError: false` は「合格」ではない。取得結果は同じプロセスで `get_result` により再取得できる。キャッシュは一括・単一共通で直近8呼出し分。

GUIの `/api/batch-item` とMCPは `batch.inspect_item`・`Workspace` を共有する。GUIは人の途中操作に合わせて1件ずつ呼び、MCPは同じ処理を順に実行する。MCPは作業ファイルや画像を書き出さない。GUIで修正したい画像は明示的にGUIへ投入する。専用の一括CLIコマンドは未実装。

## 実クライアントでの再現

[公式MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) 2.3.0を専用QA環境に入れ、実際のstdioサブプロセスへ接続した。initialize、5ツールの発見、構造PASSと画像確認待ちの区別、混在バッチ、結果再取得、承認操作拒否、100件処理、原本不変を確認した。通常のアプリにはSDK依存を追加していない。

```sh
python3.12 -m venv .evidence/mcp-client-venv
.evidence/mcp-client-venv/bin/python -m pip install -r requirements-mcp-client.txt
.evidence/mcp-client-venv/bin/python scripts/mcp_client_check.py \
  --server-python "$PWD/.venv/bin/python"
```

証拠は `.evidence/mcp-client/result.json`。合成ファイルのみ使用する。GUI型MCPホストへの恒久登録、LLMを含む自由対話、人による操作時間評価は未実施。プロトコル参考: [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)。
