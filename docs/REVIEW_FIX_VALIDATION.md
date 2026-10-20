# PR #5 レビュー指摘の修正と検証

2026-10-20。[対象レビュー](https://github.com/yo4e/MazeProof/pull/5#issuecomment-6285086290) の4件は、修正前の `98a4527` で再現した。以前のCI・UI検査には以下の境界条件が不足していた。今回は修正と回帰テストを追加した。mainへのマージ・正式リリースは含まない。

## 修正

| 指摘 | 原因と変更 |
| --- | --- |
| F1 編集→未同期undoで承認復活 | モデルが承認時と同一ならサーバーは編集を検出できなかった。画面に承認失効状態を保持し、undoでは戻さず、検査リクエストの `revokeApproval` で原子的に失効させる。失敗時は失効状態を保持し、成功応答後にだけ解除する。新しい承認には明示操作が必要。 |
| F2 保存待ちの編集が未保存扱いでなくなる | 前半の再検査だけで解除していた操作ロックを、後半のexport完了まで維持。保存中の編集・undo・reset・一括画面への移動を抑止する。失敗後は操作を戻し、未保存状態を残す。 |
| F3 非連結の赤線が確実な経路になる | 軸方向の被覆率に加えて、候補境界領域と盤面内の赤画素の8近傍連結を確認する。行ごとの連続区間を追跡し、全画素分のPythonキューやラベル画像を作らない。断線を補間せず、候補経路を残したまま `RED_ROUTE_UNCERTAIN` として人の確認を要求する。 |
| F4 受付後取消の結果が保持枠に残る | 読込み要求ID、受領確認、明示取消、未受領結果の60秒リースを導入。取消・受領確認は画像処理中にも実行できる小さなメタデータ操作。未受領の結果も保持予算に算入するが、取消または期限切れで回収し、既存の編集済み作業は追い出さない。 |

F1は承認手順の不整合であり、元と異なるモデルの誤PASSを再現したものではない。F3も修正前から総合結果は `NEEDS_REVIEW` だったが、赤線の追加確認が要求されない問題を修正した。

## 回帰テスト

`tests/test_review_regressions.py` の9件:

- 同一digestへのundo後も失効し、明示再承認でだけPASSになること。HTTPのevaluate/exportと入力型の拒否も確認。
- 3×3二値マスク全512通りを独立した画素探索と比較し、連結判定を確認。
- レビューのずらした断線fixtureと転置版を実workerへ投入し、routeUncertain・routeReviewed・pending・総合確認待ちを確認。
- 受付前取消、認識中の取消、結果受領前の取消、受領確認の応答欠落、同じ取消の再送。
- 受付済みHTTP接続の切断と、明示取消が届かない場合のリース回収。期限は専用時計の注入で進め、実時間の長い待機を避ける。
- 検証用の小さな保持上限で次の入力が回復し、以前の承認済み作業が残ること。認証・Originの既存防御と制御要求の1KiB上限も維持する。

`scripts/review_e2e.py` の実UI9シナリオ:

- 承認→編集→即undo→再検査、作業保存、JSONレポート、HTMLレポートの4経路で確認待ち。
- 本物のexport応答を遅延させ、保存中の操作を抑止。保存後の新しい変更では実ページ再読込み時にも未保存警告が出る。
- export失敗後の未保存状態、操作復帰、正しい再保存。
- サーバーが受け付けた後の取消、結果が生成された後の取消、受領確認が確定して応答だけ失われた場合の回収。いずれも次の投入が成功。

`scripts/batch_e2e.py` には、未同期undo→一覧復帰→一括保存でPASSを再利用しない試験を追加した。

## 実行結果と再現

Mac、Python 3.12.13、アプリの固定依存（Pillow 13.0.0、NumPy 2.5.4、pypdfium2 5.14.0、psutil 7.2.2）、Playwright 1.64.0、専用headless Chromiumで確認。

| 検査 | 結果 |
| --- | --- |
| 全unittest | 61件成功。追加9件を含む |
| 単一UI | 15シナリオ成功 |
| 一括UI | 12シナリオ成功。100画像の実読込みと未承認PASSゼロを含む |
| レビュー回帰UI | 9シナリオ成功 |
| 公式MCP SDKクライアント | 6項目成功。100画像、PNG/PDF混在、未承認PASSゼロ、入力不変を含む |
| 配布 | wheel/source archive生成。新規venvへwheelを導入し、ソース外で起動・読込み・承認・一括復元を確認 |
| schema・構文・リンク・静的検査 | 成功 |

```sh
python -m unittest discover -s tests -v
python tests/check_schemas.py
python tests/check_repository.py
python -m ruff check mazeproof tests scripts
npm run check
python scripts/e2e.py
python scripts/batch_e2e.py
python scripts/review_e2e.py
```

Chromiumの実行ファイルを指定する場合はUIスクリプトに `--browser /absolute/path/to/chromium` を付ける。必要なQA依存と公式MCPクライアントの手順は [README](../README.md) と [一括検品の検証記録](BATCH_VALIDATION.md) を参照。`review_e2e.py` もCIのHeadless workflowへ追加した。リモートの成否は [Actions](https://github.com/yo4e/MazeProof/actions/workflows/ci.yml?query=branch%3Afeat%2Flocal-image-workbench) とPR Checksの対象SHAで確認する。

ローカルのログと保存物は `.evidence/review-regressions/`。公開テスト素材は合成画像のみ。既存の作業サーバー・Chrome・デスクトップには操作を加えていない。

## 処理上の制約

- 取消は結果の採用と保持を止める。すでに動いている認識workerは既存の時間予算内で終了するため、直後の再投入が一時的にBUSYになる場合は少し待って再試行する。
- 明示取消が届かなければ、未受領結果は60秒後の回収処理で解放する。受領済みの利用中作業は時間だけで消さない。
- 内部のGUI用HTTPでは新規読込みに `X-MazeProof-Import` を付け、表示前に `import-claim` を行う。アプリとサーバーは同じ版で使う。CLI/MCPの公開ツール契約と保存ファイルschemaは変更していない。
- 二次元の連結確認は任意画像の完全認識保証ではない。細線・ノイズなどで確認要求が増える場合もあり、人による原画像との照合が必要。
- 起動中の旧サーバーはpushだけでは更新されない。未保存作業を保存したうえで、別途、新しい版を導入・起動する。
