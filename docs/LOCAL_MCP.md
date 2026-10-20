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
| get_result | requestId | 同じプロセス内の直近8件の結果 |

stdioは1行1JSON-RPC。protocolVersionは2025-06-18と2024-11-05。initialize、initialized notification、tools/list、tools/call、pingを扱う。stdoutはプロトコルだけに使う。画像byte列やファイル名は返却する観測から除外し、モデルと座標・digestを返す。生成・削除・外部ネットワーク・承認ツールはない。

認識結果のPASS/FAILは暫定の数学的検査。総合は `NEEDS_REVIEW` のままで、利用者の代わりに承認してはいけない。画像を確認・修正するにはGUIへ読み込む。MCPに保存済みレポートを渡しても、人間の承認として信頼する機能はない。

検証はローカルstdio JSON-RPC clientでhandshakeから実tool呼出しまで行う。特定のGUI型MCP clientへの登録・対話試験は別途必要。プロトコル参考: [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports)。
