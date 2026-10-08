# ローカル構造コア検証記録

2026-10-08、Mac背景コマンドで実行。base main: `bee6c8f33891312fc1f42265615a37700d2d7205`。
開始確認時にopen PRは0件、ローカル変更なし。repo-local AGENTS/SKILLはなし。
構造コアのみのローカル作業で、push/PR/merge/release/権限変更は行っていない。

## 実行結果

```sh
python3 -m unittest discover -s tests -v
# 13 tests: OK (0.311秒、プロセス全体0.37秒)
```

- 3×2格子の全7辺組合せ128通り × 全順序付き端点30対 = 3,840ケース。独立DFS oracleでsimple path数を比較し、到達性・唯一性・別解witnessを確認。
- 250×250、62,500セルのHamiltonian snakeを検査し、unique/全域木を確認。再帰traversalを使わない。
- 壁追加による断線、壁除去による別解、route飛び/再訪/壁横断/終端ずれ、ペア壁・開口・寸法ずれを故障注入。
- 経路外cycle/孤立セルを含むunique例、回転不変性、未実施範囲、入力非変更、digest安定性、固定goldenを確認。
- 厳密JSON、duplicate keys、NaN/Infinity/float overflow、深い入力、未知項目、boolean/int混同、上限、内部例外を確認。拒否・障害後に部分PASS/証拠を残さない。

```sh
python3 -m venv /tmp/mazeproof-schema-qa
/tmp/mazeproof-schema-qa/bin/python -m pip install 'jsonschema==4.23.0'
/tmp/mazeproof-schema-qa/bin/python tests/check_schemas.py
# Draft 2020-12 schemas and 13 result scenarios: OK
```

jsonschemaは一時QA環境のみ。製品は標準ライブラリだけで動く。両schema自体の妥当性と、正常/不正/別解/ペア不一致/未対応/上限/内部障害を含む13結果を検証した。寸法依存のshape等はschemaに加えてsemantic validatorが必要。

```sh
PYTHONPYCACHEPREFIX=/tmp/mazeproof-pycache python3 -m compileall -q mazeproof tests
# OK
```

Markdown内部リンク、git diff --checkも成功。macOSの既定cacheへの書込みがsandboxで拒否されたため、一時cacheを指定して構文確認した。プロセスのRSS計測はsandboxで取得できず、メモリ上限の保証は行っていない。

## 残る範囲

画像/PDF認識、human confirmation、UI/CLI/MCP、renderedAgreement、transport/fileアクセス制限、workerによる強制timeout/メモリ制限、配布は未実装。画像入力はUNSUPPORTEDであり、構造PASSを完成品PASSとして使えない。
結果schemaは構造コアに対応するローカル契約。NEEDS_REVIEWは総合statusとして予約するが、認識adapterのフィールドはまだ固定していない。
ライセンス、fixtureの公開利用許諾、UI/配布方式、画像品質校正は保留。[ADR](adr/0001-structure-core.md)の人間ゲートを次のレビューで確認する。
