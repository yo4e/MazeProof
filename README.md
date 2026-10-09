# MazeProof

自作迷路と解答を検査する、独立したローカルアプリを開発するリポジトリ。
人間向け UI、CLI、MCP が同じ検証コアと結果 schema を使い、構造データと完成品の PNG / JPEG（JPG）/ PDF を検査する。

**構造 JSON の検証コアと CLI を実装済み。画像認識・UI・MCP サーバーは未実装。**
画像からの認識とグラフ上の数学的判定を分離し、認識が不確かな完成品を無条件に PASS としない。

- [設計仕様](docs/SPEC.md)：対象範囲、データ契約、判定と確認フロー
- [段階 BUILD_PLAN](docs/BUILD_PLAN.md)：順序、受入条件、人間の確認ゲート
- [検証方針](docs/VALIDATION.md)：独立 solver、故障注入、golden tests
- [未決事項・依存候補](docs/DECISIONS.md)：技術選定、ライセンス、公開境界

MazeMa の非公開商品データをこの公開リポジトリへコピーしない。公開テストは独立した synthetic fixtures を使う。
名前は仮称。事前の簡易検索では目立つ同名アプリ・OSS は見つかっていないが、商標確認済みではない。

## CLI で JSON を検証する

Python 3.9+、外部の実行時依存なし。repo root で次を実行すると、問題と解答を読み取り専用で検査し、共通schemaのJSON結果をstdoutへ返す。

```sh
python3 -m mazeproof examples/problem.json --solution examples/solution.json
```

期待結果は `PASS`、exit code 0。人間向けの要約は `--format text`、使い方は `--help` で表示する。

```sh
python3 -m mazeproof examples/multiple.json --format text
python3 -m mazeproof examples/wall-crossing.json --format text
python3 -m mazeproof examples/invalid.json
```

それぞれ別解 `FAIL` / exit 1、壁横断 `FAIL` / exit 1、不正入力 `INVALID_INPUT` / exit 3。
`--allow-multiple` は唯一解の要件だけを外す。到達性・提出された解答の合法性は引き続き検査する。
`--solution` を省略すると問題JSON内の任意routeを検査し、routeがなければ解答検査は `NOT_RUN`。
別解答ファイルはroute付きの完全な迷路JSONを渡し、問題側にはrouteを入れない。

| exit code | 意味 |
| --- | --- |
| 0 | 構造データと実行policyの範囲でPASS |
| 1 | 確定した構造データ上の条件違反（FAIL） |
| 2 | NEEDS_REVIEW用の予約値。画像認識が未実装の現段階では発生しない |
| 3 | 不正入力・未対応・上限超過・内部/ファイルエラー |

PASSは完成品画像や解答未提出部分の保証ではない。JSONのscopeとNOT_RUNも確認する。
入力はローカルの通常ファイルのみ、1ファイル25 MiB以下。URL・FIFO・デバイス・ディレクトリ・ネットワーク共有形式は受け付けない。
stdin入力、インストール用package、画像/PDF認識、UI/MCPは後続段階。[サンプル説明](examples/README.md)も参照。

## ローカル構造コアの確認

Python 3.9+、実行時の外部依存なし。repo rootから実行する。

```sh
python3 -m unittest discover -s tests -v
```

```python
from mazeproof import validate_structure

# JSON text/bytesのみ受付。ファイルは呼出側が明示的に読み取る。
result = validate_structure(problem_json, solution_json, unique_required=True)
```

solution_jsonを省略すると、問題JSON内の任意routeを検証する。routeがなければ解答検査はNOT_RUN。
PASSは入力された構造とpolicyに限定され、完成画像の保証ではない。
PNG/JPEG/PDFは現在UNSUPPORTED。UI/MCPおよびworkerの強制メモリ・時間制限は後続段階。

[構造コアADR](docs/adr/0001-structure-core.md)、[入力schema](schemas/maze.schema.json)、[結果schema](schemas/result.schema.json)、[合成fixtureの由来](tests/fixtures/PROVENANCE.md)を参照。
[ローカル検証記録](docs/CORE_VALIDATION.md)に実行コマンド・結果・制約を記載。

## CI と貢献前の確認

push と pull request ごとに、GitHub Actions が Python 3.9 / 3.13 で検査する。
独立 oracle・故障注入・golden・CLI回帰を含む20テスト、JSON Schemaと13コア/7 CLI結果シナリオ、5サンプル、Python構文、内部Markdownリンク、変更の空白を確認する。
CI用の依存は製品の実行時依存ではない。同じ検査をローカルで再現するには repo root で次を実行する。

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-ci.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python tests/check_schemas.py
.venv/bin/python tests/check_repository.py
git diff --check
```

CIは対応した構造データの回帰検査であり、画像認識品質やworkerの強制リソース制限を保証するものではない。
[CIの範囲と設定](docs/CI.md)を参照。

## ライセンスとコーヒー

MazeProof のコード・文書・独立した合成fixtureは [MIT License](LICENSE) で利用できる。
役に立ったら、[コーヒーを奢ってね ☕](https://ko-fi.com/yo4e)。支援は任意です。
