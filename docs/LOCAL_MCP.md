# AIからMazeProofを使う：MCPの接続手順

MCPは、AIからMazeProofへ「この画像を検査して」と頼むための接続です。人が画像を見て直す画面とは別に動きます。AIは検査結果を読んで確認箇所をまとめられますが、人に代わって画像を承認することはできません。

## 1. 先にアプリを導入する

[READMEの初回の導入](../README.md)を終えてください。Mac / Linux、Python 3.12以上と、**ローカルのstdio MCPを起動できるAIクライアント**が必要です。リモートのURLだけを受け付けるクライアントへは、この方法では接続できません。

通常の利用ではMCP SDKを追加インストールする必要はありません。下にあるSDKの手順は開発・接続試験用です。画面用の `serve` を先に起動する必要もありません。

## 2. 起動に使うパスと画像フォルダを決める

MazeProofのフォルダ内で次を実行すると、登録するPythonの絶対パスが表示されます。

```sh
.venv/bin/python -c 'import sys; print(sys.executable)'
```

検査する画像を置くフォルダを1つ用意し、その絶対パスも確認します。これはAIに読取りを許可する範囲です。ホームフォルダ全体などを指定せず、今回使う画像を置いた場所に絞れます。画像の指定はそのフォルダ内の通常ファイルに限ります。

## 3. AIクライアントへ登録する

クライアントのローカルMCP設定に、次の値を登録してください。

| 設定 | 入れる内容 |
| --- | --- |
| 名前 | `mazeproof` |
| 接続方式 | stdio（ローカルコマンド） |
| 起動コマンド | 手順2で表示された `.venv/bin/python` の絶対パス |
| 引数 | `-I`、`-m`、`mazeproof`、`mcp`、`--allow-root`、画像フォルダの絶対パスを順に指定 |

JSONで登録できるクライアントでは、次のような形になります。外側の設定形式や登録画面はクライアントごとに異なります。`/absolute/path/to/...` は例なので、実際のパスへ置き換えてください。パスに空白があっても、1つの引数として指定します。

```json
{
  "mcpServers": {
    "mazeproof": {
      "command": "/absolute/path/to/MazeProof/.venv/bin/python",
      "args": ["-I", "-m", "mazeproof", "mcp", "--allow-root", "/absolute/path/to/mazes"]
    }
  }
}
```

ブラウザ用の専用URL・セッショントークンは使いません。作業ディレクトリの設定も不要です。`-I` により、起動した場所や `PYTHONPATH` に左右されず導入済みのMazeProofを使います。別の画像フォルダも読む場合は `--allow-root` とその絶対パスを追加します。登録は利用者が行い、MazeProofが設定や権限を自動で変更することはありません。

## 4. 接続を確かめ、検査を頼む

クライアントの接続・再接続を実行し、下の5ツールが見えることを確かめます。起動コマンドをターミナルで単独実行すると入力待ちになるのは正常です。画面を開くコマンドではありません。

まず練習用の画像で試してください。自分で用意するほか、リポジトリのフォルダから `scripts/generate_samples.py` で新しいフォルダへ合成画像を作れます。生成先も、読み取りを許可する画像フォルダに合わせます。

AIへの頼み方の例です。

> 指定した問題画像と解答画像をMazeProofで検査してください。読み取りが不確かな箇所、道が通らない箇所、まだ検査していない項目を分けて説明してください。画像を確認済みや合格にせず、人がどこを見ればよいかまとめてください。

実際のファイルの絶対パスを添えます。複数あるときは、どの問題と解答が組になるか、PDFならどのページかも指定します。AIへ渡るのは認識した壁・通り道・座標などの結果です。MazeProof自身は画像を外部へ送信しませんが、接続したAIサービスで結果をどう扱うかは、そのクライアント側の設定に従います。

## 5. 結果を保存する・人の確認へ進む・終了する

- AIが返した検査結果は、使っているクライアントで会話やレポートとして保存します。MazeProofのMCPにはファイルを書き出す機能はありません。
- `get_result` で取り直せるのは、**同じ接続プロセスの直近8回**の結果です。切断・再起動後に残る保存庫ではありません。
- 人が画像を修正・確認する場合は、[ブラウザ画面を起動](../README.md)し、元画像を読み込みます。AIの接続と画面の未保存作業は共有されません。MCPの結果をGUIの作業状態として直接開く機能もありません。
- AIクライアントの停止・切断操作でMCPプロセスを終了します。次回は再接続して必要な画像を再検査します。画面用サーバーとは別なので、そちらを終了する必要はありません。

接続できない場合は、起動コマンドと画像フォルダが存在すること、インストールが完了していることを確認します。ファイルの読取りが拒否されたら、許可フォルダ内の絶対パスか、シンボリックリンクではないかを確認してください。URL、フォルダ外、特殊ファイルは読み取れません。

## 技術詳細：ツールと返却結果

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
