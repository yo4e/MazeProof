# MazeProof

自作迷路と解答を検査する、独立して公開可能なローカルアプリの設計リポジトリ。
人間向け UI、CLI、MCP が同じ検証コアと結果 schema を使い、構造データと完成品の PNG / JPEG（JPG）/ PDF を検査する。

**ローカル構造検証コアを実装中。画像認識・UI・CLI・MCP サーバーは未実装。**
画像からの認識とグラフ上の数学的判定を分離し、認識が不確かな完成品を無条件に PASS としない。

- [設計仕様](docs/SPEC.md)：対象範囲、データ契約、判定と確認フロー
- [段階 BUILD_PLAN](docs/BUILD_PLAN.md)：順序、受入条件、人間の確認ゲート
- [検証方針](docs/VALIDATION.md)：独立 solver、故障注入、golden tests
- [未決事項・依存候補](docs/DECISIONS.md)：技術選定、ライセンス、公開境界

MazeMa の非公開商品データをこの公開リポジトリへコピーしない。公開テストは独立した synthetic fixtures を使う。
名前は仮称。事前の簡易検索では目立つ同名アプリ・OSS は見つかっていないが、商標確認済みではない。

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
PNG/JPEG/PDFは現在UNSUPPORTED。CLI/UI/MCPおよびworkerの強制メモリ・時間制限は後続段階。

[構造コアADR](docs/adr/0001-structure-core.md)、[入力schema](schemas/maze.schema.json)、[結果schema](schemas/result.schema.json)、[合成fixtureの由来](tests/fixtures/PROVENANCE.md)を参照。
[ローカル検証記録](docs/CORE_VALIDATION.md)に実行コマンド・結果・制約を記載。ライセンス選定は引き続き保留。
