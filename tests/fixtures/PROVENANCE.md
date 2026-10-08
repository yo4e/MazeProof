# Synthetic fixture provenance

2026-10-08、MazeProofのローカル検証作業で新規に作成。
MazeMa商品、Slack添付、第三者repoのコード/画像は使用していない。
本人のMIT採用指示により、これら独立合成fixtureにもrepo rootの [MIT License](../../LICENSE) を適用する。

- `unique-2x2.json`: 手で構成した2×2格子。通路辺 (0,1),(1,3)、入口(0,0,N)、出口(1,1,S)、解答0→1→3。セル2は孤立。入口出口間はuniqueだが全域木ではない。
- `unique-2x2.result.json`: 上記のexact_structure結果。requestIdのみ省略したgolden。checkedはreachability/uniqueness/routeValidity、mazeIdentity/renderedAgreementはNOT_RUN。更新時は意味の変更をレビューする。
- 動的fixture: `tests/test_core.py` の `maze` が格子辺から壁配列を構成する。seedなしの全列挙は3×2の7辺×全順序付き端点対=3,840ケース。独立DFS oracleは辺集合上で全simple pathsを数える。
- 故障注入: 壁追加、壁除去、解答断線/再訪/壁横断/終端ずれ、ペア壁・寸法・開口ずれ、JSON不正、上限、内部例外。期待値はテストに明示し、goldenを本番結果だけで自動承認しない。
