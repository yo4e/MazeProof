# JSON CLI 実装・検証記録

2026-10-10 JST、背景コマンドで実施。開始時 main は `cfc5c4efa78bf9fd65f9ef814605323976ff7ec2`（PR #3マージ済み）。open Issue/PRなし、既存ローカル変更なし、repo-local AGENTS/SKILLなし。
今回のpush・公開・PR許可は確認できていないため、ローカル保存まで。remote CI実行・merge・deploy・課金・権限変更は行わない。

## 実装判断

`python3 -m mazeproof PROBLEM --solution SOLUTION` を最小の実用入口とする。packageのインストール不要、標準ライブラリのみ。CLIはbounded file readと結果表示のadapterであり、数学的検査は既存コアをそのまま使う。正常なCLI/core結果はrequestId以外が一致することを回帰検証する。

stdoutは既定で共通result schemaのJSON。`--format text` はassurance、各check、違反位置、未検査範囲を表示。既定はunique_required、`--allow-multiple`はその要件だけを外す。exit 0/1/2/3はSPECの契約を採用する。NEEDS_REVIEW=2は将来の認識adapter用に予約し、現段階では発生しない。

問題内routeと別解答routeの同時指定は既存コア同様に拒否。解答ファイルはroute付きの完全な迷路JSON。ファイルの読取り失敗や引数不正もschema結果とexit 3にし、入力内容・private path・例外本文をログへ出さない。helpは通常のexit 0。

入力は明示したローカル通常ファイル、25 MiB/input上限。open後fstatで実体を確認し、最大上限+1byteまで読み取る。POSIXではO_NONBLOCKによりFIFOに接続して待たず拒否する。URL・ネットワーク共有形式・device・directoryは拒否。原本書換なし。CLIはMCP用のallowed-root sandboxではなく、symlink先やmounted filesystemまで完全に隔離する機能はない。

## 検証範囲

既存CIのunit discoveryに7 CLI回帰テストを追加（合計20）。schema検査も13コア結果に7 CLI subprocess結果と5サンプルを加える。Python構文/内部リンク/差分空白を確認し、actionlintも成功。

ローカルで以下のCI相当コマンドを実行：

```sh
python3 -m unittest discover -s tests -v
/tmp/mazeproof-schema-qa/bin/python tests/check_schemas.py
python3 tests/check_repository.py
/tmp/mazeproof-actionlint/actionlint -shellcheck= .github/workflows/ci.yml
git diff --check
```

20テストには既存の独立oracle 3,840ケース・62,500セル・故障注入を含む。CLIは正常、別解、壁横断、不正入力、policy変更、text scope、core一致、入力非変更、引数/help、missing/URL/FIFO/巨大ファイル、未対応magic、内部例外、出力失敗を検査する。

4種類の公開用合成サンプルを実コマンドで確認：ペアPASS/exit0、別解FAIL/exit1、壁横断FAIL/exit1、必須項目不足INVALID_INPUT/exit3。結果の意味は [サンプル](../examples/README.md) に記録。

## 未実施と引継ぎ

remote保存/対象headのCIは未実施。親が今回のpush・draft PR許可を確認してからremote保存し、Python3.9/3.13の対象head CIを確認する。mergeは別承認。
stdin、package配布、画像/PDF認識、UI/MCP、worker強制timeout/メモリ上限は未実装。構造PASSを完成画像PASSとして使わない。通常ファイルI/OやJSONdecodeを強制中断する仕組みも未実装。
