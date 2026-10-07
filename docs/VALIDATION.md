# 検証方針

## 独立性

本番 solver と生成器の共通バグを避ける。コアの bridge 判定とは独立に、極小グラフを対象とした simple-path DFS 全列挙 oracle をテスト用に用意し、経路数を 0/1/2以上で比較する。大きな入力をこの oracle へ渡さない。本番と oracle は traversal/唯一性ロジックを共有しない。極小の無向直交格子の辺組合せ・入口出口組合せを全列挙し、手で確かめた例も含める。

全域木ではないが入口出口間だけ unique のケース（経路外に cycle、孤立セル）を必須 fixture とする。未到達と multiple を混同しない。別解 witness は独立 route checker で合法性と相違を再検証する。

## 公開 synthetic corpus

MazeMa 商品、私的 PDF、Slack 添付画像をコピーしない。独立して作成した小格子と描画を使い、出典、作者、fixture license、seed、サイズ、壁モデル、route、変換、期待チェック、期待 assurance を manifest に記録する。生成器出力だけで golden を自動承認しない。
JSON の正解壁から PNG/JPEG、ベクター PDF、画像埋込 PDF、混在 PDF を作る計画だが、今回 fixture コードや実データは追加しない。

| 故障/条件 | 期待結果 |
| --- | --- |
| 唯一経路、合法な解答、一致するペア | exact JSON は PASS。画像は認識確認前 NEEDS_REVIEW、確認後条件付き PASS |
| 経路上の壁追加/断線 | reachability FAIL または routeValidity FAIL |
| 壁抜けで迂回路追加 | unique_required=true で FAIL、multiple と異なる2経路 witness |
| 行き止まり側だけ cycle | unique、全域木 false。unique_required で FAIL にしない |
| 壁横断、飛び、再訪、端点誤り | routeValidity FAIL、最初の違反位置 |
| 問題/解答の壁、開口、格子差 | 確定モデルなら mazeIdentity FAIL |
| 正しい JSON + 描画で壁一本欠落 | renderedAgreement FAIL。認識不確実なら NEEDS_REVIEW |
| 平行移動/回転/拡縮・crop ずれ | 記録された変換で照合、対応不確実なら NEEDS_REVIEW |
| 透過、アンチエイリアス、1px細壁、縮小 | topology 不安定なら NEEDS_REVIEW、元画像を勝手に修復しない |
| JPEG品質差、ブロックノイズ、リンギング、色にじみ、細壁消失 | threshold/scale 候補が異なるなら NEEDS_REVIEW。失われた壁を推測して PASS にしない |
| 赤線断線/分岐/太線/壁遮蔽 | route または同一性が未確定なら NEEDS_REVIEW |
| PDF clip/transform/transparent stroke/混在ページ | appearance 差分または NEEDS_REVIEW/UNSUPPORTED |
| 未指定PDFペア、暗号化、破損、巨大ページ | INVALID_INPUT/UNSUPPORTED/RESOURCE_LIMIT、PASSなし |

壁抜けを「自然な JPEG ノイズ」と消してはいけない。完成画像の欠陥と圧縮由来の不確実性の双方を保存し、人間が原資料を確認できるようにする。

## Golden と property checks

固定 corpus の canonical model、status、reasonCode、witness、未知境界、変換、assurance を snapshot とする。overlay は位置の許容差と目視で確認し、バイナリ画像差だけで判定しない。更新は差分理由と maintainer 承認が必要。
回転して座標を変換しても結果不変、壁追加は到達性を新規に作らない、合法 route の各辺は開いている、入力順や UI/CLI/MCP で判定不変を確認する。認識器を本番コアと独立に wall-level precision/recall と topology の完全一致で評価する。低 confidence ケースの review 率、誤 PASS 数を別に報告する。

## 安全性とリソース

malformed JSON、重複キー、偽拡張子、decode bomb、過大 dimensions、PDFページ数、timeout、worker memory、並列入力、symlink escape、path traversal、URL/SSRF、PDF active content、内部例外を fixture 化する。ネットワーク要求なし、入力変更なし、画像/個人pathのログ漏れなし、一時ファイル削除を確認する。途中終了は RESOURCE_LIMIT/ERROR とし、部分成功を PASS にしない。

## 出荷ゲート

対応範囲の curated corpus で誤った確定 PASS が 0、全反例が独立 checker を通る、未確認画像は総合 PASS にならない、未知/未対応を隠さない、golden と schema validation が全成功。これは corpus 上の受入基準であり、未知の画像に対する誤りゼロの保証ではない。
実測の認識品質・処理時間・メモリ・対象端末・依存versionを記録して上限と対応範囲を確定する。数値未計測の現在は品質保証済みと表示しない。
