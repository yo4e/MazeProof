# MazeProof 設計仕様 v0.1

2026-10-07。実装開始前の仕様案。以下の「必須」は受入要件、「提案」は将来の実装時に検証する初期値を意味する。

## 1. 目的と範囲

自作迷路について、入口から出口への到達、別解、提出解答の合法性、問題版と解答版の迷路一致を検査する。生成器から独立した検証を行い、データが正しくても完成した描画で壁が欠ける問題を検出する。
外部の有料サービスやクラウドへの画像送信を必須にしない。

初期対応は矩形の直交格子、黒い壁と白い通路、一組の入口・出口。解答版は白黒の同じ迷路上に赤い単一路線を重ねた形式。任意手描き、曲線、立体、複数階層、扉や鍵、斜め移動の完全対応は保証しない。単なる画像 solver では完成品の正しさ全体を保証できない。

MVP は構造 JSON と PNG/JPEG の一組の問題・解答を対象にし、PDF は次の段階の必須拡張として扱う。PDF 未実装の間は入力を明示的に UNSUPPORTED とし、PNG と同等に対応済みとは表示しない。

## 2. 共通パイプライン

UI / CLI / ローカル MCP → 入力検査 → format adapter → 正規化モデル → 純粋な検証コア → 共通結果。
画像/PDF adapter は元資料、変換行列、候補格子、壁 overlay、不確実セル・境界を保持する。コアは画像処理を行わず、確定したグラフとルートだけを検査する。各 adapter の不確実性は判定と別フィールドで渡す。

完成品と JSON の両方がある場合は双方を検査し、完成品から認識した壁・開口と JSON を比較する。JSON の PASS を画像の PASS に転用しない。描画の壁抜けは差分位置を示す。画像だけの場合は認識されたモデルについての条件付き結論であることを表示する。

## 3. 正規化構造データ（提案契約）

schemaVersion は `mazeproof.maze/1`。座標は左上原点、整数の `row, col`。width/height は正整数。
壁は水平境界 `horizontalWalls[height+1][width]` と垂直境界 `verticalWalls[height][width+1]` の boolean 配列（true=壁）で一度だけ表す。セル中心間の直交隣接のみ通行可。外周開口を入口・出口に限定する。入口・出口はセル座標と外周 side（N/E/S/W）を持ち、異なる外周開口であること、指定境界に壁がないことを確認する。

route は入口セルから出口セルまでの順序付きセル座標配列。外周 side は端点契約で検証し、グラフに仮想の外部通路は追加しない。幅/高さ不一致、欠損、余分な未知フィールド、非 boolean 壁、範囲外座標、入口=出口、外周の未指定開口は INVALID_INPUT。JSON は UTF-8、重複キーを拒否し、NaN/Infinity を認めない。実装時は正式 JSON Schema と例を追加する。

解答は simple path（セル再訪なし）を初期契約とする。探索の全訪問履歴を解答として受け付けない。schema の破壊的変更は version を上げる。

## 4. 数学的検査

- 到達性：指定入口セルから出口セルへ BFS/DFS。未到達なら FAIL、経路があれば到達性 PASS。
- 別解：数えるのは入口出口間の **simple paths**。一経路を見つけただけで唯一解とはしない。提案アルゴリズムは、一経路 P を求め、P 上の全辺が無向グラフの bridge かを検査する。全辺 bridge なら唯一、非 bridge 辺があれば別経路の証拠を構成する。反例 witness を保存する。これにより指数的全経路列挙を避ける。
- 全域木：全セルの連結性と辺数 V−1 を別の任意診断として報告する。入口出口への経路から外れた cycle や孤立領域があっても入口出口間唯一性とは別問題。全域木を必須条件にしない。
- 解答：隣接セル差が Manhattan 距離 1、間の壁がない、再訪なし、入口開始・出口終了を個別確認。断線、斜め飛び、壁横断、終端不一致を位置付きで FAIL。最短であることは初期要件にしない。
- 問題/解答一致：正規化された dimensions、全壁、開口を比較し、解答線だけを除外。画像位置合わせの失敗を壁不一致と断定しない。入口出口位置も比較する。

uniqueness は `none / unique / multiple / unknown`。unique_required の既定は true とする提案。false の場合は multiple を診断として示し、合法な解答の PASS を許す。実行した policy を結果に必ず保存する。

## 5. PNG・JPEG/JPG 認識と人間ゲート

ファイル magic と実際の decode で型を確認する。JPEG の不可逆圧縮、ブロックノイズ、リンギング、色にじみ、細壁消失は原本の欠陥と認識誤りを区別できない場合がある。PNG も縮小、透過、アンチエイリアス、低解像度で同じ問題が起きる。

入力は EXIF orientation を適用し、透過は明示した白背景へ合成し、その操作を記録する。90度単位の回転は正規化し、任意角度の傾きは補正候補を示して確認。縦横別拡縮は格子推定の不確実性として扱う。原本は上書きしない。
細壁を縮小処理で消さない。格子境界の輝度/色と局所連続性を調べ、複数しきい値・解像度候補で壁 topology が変わる場合は NEEDS_REVIEW。単一の confidence 値だけで PASS を決めない。最小壁幅・通路幅・許容角度の具体値は synthetic corpus で校正し、未校正時は自動確定しない。

赤線は色 mask と線の連続性から route 候補へ変換する。線が壁を覆う、分岐、途切れ、端点が不明、格子へ一意に対応しない場合は NEEDS_REVIEW。問題版の壁を先に認識する。ただし解答版の赤線の下にある壁を勝手に問題版から補って「同一迷路」と証明しない。観測不能な壁は unknown とし、構造データとの照合や人間確認を要求する。

UI は原画像に壁・開口・赤線 route・unknown の overlay を重ね、ズームと問題/解答切替を提供する。入口/出口は候補提示後ユーザーが指定/確認できる。必要なら格子と壁を修正し、修正・確認したモデルの digest と変換設定を保存する。入力、crop、変換、壁、入口出口が変われば確認を無効化する。
人間の確認は認識モデルの承認であり、元画像の数学的証明ではない。UI/CLI/MCP に同じ `human_confirmed` の確証範囲を示す。MCP は確認情報がないまま自動承認しない。

## 6. PDF 拡張

選択ページを独立処理し、問題 page と解答 page を明示指定する。複数ページを偶数/奇数で自動ペアにしない。ページ寸法、crop、回転、座標系と変換を結果へ記録する。
ベクター PDF は path/stroke/fill/transform/clip から壁を取り出せる候補だが、見た目との一致もレンダリングして検査する。raster PDF は画像抽出または bounded rendering 後に raster 認識する。混在 PDF、clip、細線、透明度、重なり、フォント依存が未対応なら NEEDS_REVIEW/UNSUPPORTED。ベクターであることだけで確実とみなさない。暗号化・パスワード・壊れた PDF は初期非対応。

## 7. 共通結果 schema（提案）

`schemaVersion: mazeproof.result/1`、requestId、engineVersion、inputDigests、pagePairs、policy、limits、transforms、recognition、checks、overallStatus、issues、evidence を必須とする。checks は reachability、uniqueness、routeValidity、mazeIdentity、renderedAgreement を持ち、各々 status、reasonCode、対象座標、適用資料、assurance を返す。未要求/資料なしは NOT_RUN と理由を返す。
assurance は `exact_structure / recognized_unconfirmed / human_confirmed`。同一性と描画一致は比較対象がなければ NOT_RUN。overall に検査済み範囲と未検査範囲を併記し、単独問題の PASS が解答の正しさを意味しないようにする。

| status | 意味 |
| --- | --- |
| PASS | 要求された全チェックが完了し、そのモデルと policy で成立。画像は承認済みモデルに対する条件付き PASS と明示 |
| FAIL | 確定モデル上で要求条件違反があり、反例または差分を提示可能 |
| NEEDS_REVIEW | 認識/対応付け/入力選択が不確か。暫定コア結果が PASS/FAIL でも総合の確定判定にしない |
| INVALID_INPUT | schema 不正、型偽装、ページ指定不正、禁止された入力 |
| UNSUPPORTED | 未対応 format/style/暗号化等 |
| RESOURCE_LIMIT | サイズ、時間、メモリ等の上限超過。部分探索から結論を出さない |
| ERROR | 内部障害。FAIL と混同しない |

総合は入力拒否/上限/内部障害を先に表示し、認識が未確定なら NEEDS_REVIEW、確定後に FAIL または PASS。暫定の違反は issue として保存する。エラー後に古い PASS を表示しない。
CLI は同じ JSON を返し、提案 exit code は PASS=0、FAIL=1、NEEDS_REVIEW=2、入力/未対応/上限/内部エラー=3。人間向け要約は JSON の意味を変えない。

## 8. ローカル MCP・安全性・privacy

初期 transport は stdio。提案 tools は `validate_structure`、`inspect_file`（overlay と認識候補）、`validate_pair`、`get_result`。read-only で生成、修正、削除、外部送信ツールを設けない。overlay はメモリまたは期限付き専用一時領域に生成し、入力は変更しない。UI の確認操作が作った digest 付きモデルを再検証できる契約にする。tool 説明と正式 schema は実装段階で確定する。

起動時にユーザーが指定した allowed root 内の regular file または bounded payload のみ受付。realpath 後の root 境界検査、symlink escape/TOCTOU 対策、拡張子と magic、ページ指定、長さを検査する。任意 URL、HTTP fetch、file URL、ネットワーク共有を拒否し SSRF を防ぐ。shell、eval、任意コード、PDF JavaScript、外部参照、添付ファイル起動を禁止。入力内の文章は指示として実行しない。

上限初期案：1 file 25 MiB、decoded 20 megapixels/page、格子 250×250、PDF 20 pages、1 request 5 explicit pairs、全処理 30 秒、worker memory 512 MiB、並列 request 1。全ページ情報読み取りにもページ上限を適用し、decode/render/グラフ構築前に可能な限り制限する。上限は実測して低性能端末でも強制できる値に調整し、実行値を結果に残す。
入力・結果・overlay はローカル処理、telemetry 既定 off、原文/画像/path をログに出さない。セッション終了で一時資料を削除し、保存/export はユーザーの明示操作。公開 fixture/report に MazeMa の商品データを含めない。将来 Web 版は別 privacy 設計と明示承認が必要。
