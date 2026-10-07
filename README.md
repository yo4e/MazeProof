# MazeProof

自作迷路と解答を検査する、独立して公開可能なローカルアプリの設計リポジトリ。
人間向け UI、CLI、MCP が同じ検証コアと結果 schema を使い、構造データと完成品の PNG / JPEG（JPG）/ PDF を検査する。

**現在は仕様策定のみ。アプリ・認識器・MCP サーバーは未実装。**
画像からの認識とグラフ上の数学的判定を分離し、認識が不確かな完成品を無条件に PASS としない。

- [設計仕様](docs/SPEC.md)：対象範囲、データ契約、判定と確認フロー
- [段階 BUILD_PLAN](docs/BUILD_PLAN.md)：順序、受入条件、人間の確認ゲート
- [検証方針](docs/VALIDATION.md)：独立 solver、故障注入、golden tests
- [未決事項・依存候補](docs/DECISIONS.md)：技術選定、ライセンス、公開境界

MazeMa の非公開商品データをこの公開リポジトリへコピーしない。公開テストは独立した synthetic fixtures を使う。
名前は仮称。事前の簡易検索では目立つ同名アプリ・OSS は見つかっていないが、商標確認済みではない。
