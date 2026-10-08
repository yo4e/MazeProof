# 段階 BUILD_PLAN

初回の仕様策定では実装を行わなかった。2026-10-08、本人の続行依頼に基づき構造コアと合成テストをローカル実装中（[ADR 0001](adr/0001-structure-core.md)）。各段階は小さな PR とし、受入証拠を添えて順に進める。製品データを入手することを前提にしない。

## 0. 契約と技術選定

担当者は [SPEC](SPEC.md)、[検証方針](VALIDATION.md)、[未決事項](DECISIONS.md) を読み、言語/配布方式、JSON Schema、result Schema、上限、CLI exit code の ADR を作る。独立 synthetic fixtures のライセンスと生成 provenance を定める。
受入：正常/不正 JSON と全 status の例、入口/出口・route 座標の例が文書化され、UI/CLI/MCP で矛盾しない。
人間ゲート：maintainer が初期対応範囲、unique_required、入力上限、画像の条件付き PASS 文言を確認する。未回答の項目は DECISIONS に残し、依存する実装を先行しない。

## 1. 構造コアと CLI

純粋な parse/normalize/validate と graph solver、反例、route・同一性チェックを実装する。画像依存を入れない。独立 oracle と極小グラフ全列挙で数学的検査を確認する。
受入：唯一解・別解・未到達・壁横断・終端誤り・問題/解答壁差を期待 status と位置で返す。経路外 cycle は unique、全域木 false を同時に返せる。上限超過は RESOURCE_LIMIT、未要求チェックは NOT_RUN。CLI JSON が result schema を満たす。
人間ゲート：反例とテスト結果をレビューし、認識を追加する前にコア契約を固定する。

## 2. PNG/JPEG adapter と最小ローカル UI（MVP）

問題画像、赤線解答画像、入口出口指定、格子推定、wall/route overlay、unknown、修正・承認を実装する。完成品と JSON の比較も追加する。原本を保持し、しきい値や再サンプリングで topology が変わるケースを確認対象へ送る。
受入：対応範囲の synthetic clean PNG/JPEG ペアを確認して検証できる。圧縮ノイズ、リンギング、細壁欠落、透過、回転、赤線による遮蔽、ずれの corpus で未確認総合 PASS がゼロ。原本の意図を復元できない場合は NEEDS_REVIEW。確認後変更で承認が無効になる。
人間ゲート：fixture と画面 overlay を maintainer が目視し、認識可能な品質範囲を校正して README に公開する。自動認識率の高さだけを出荷判断にしない。

## 3. ローカル MCP

同じコア、adapter、schema を薄い stdio adapter から呼ぶ。allowed roots、read-only、payload 制限、worker timeout、privacy を実装し、未確認モデルを自動承認しない。
受入：UI/CLI/MCP へ同じ canonical input と policy を渡した時、requestId 等以外の status/checks/evidence が一致。path escape、URL、巨大入力、PDF active content への拒否が確認でき、原本が変更されない。
人間ゲート：実際のローカル MCP client で確認が必要なケースとエラー表示をレビューする。

## 4. PDF 拡張

採用エンジンの license/配布依存/コストを ADR で確定してから実装する。明示ページペア、bounded rendering、ベクター・raster・混在の区別、画像認識との共通化を行う。
受入：複数ページの指定ペアだけを検査し、回転/crop/clip/細線が結果に記録される。ベクター構造と実際の rendered appearance の不一致を検出、または NEEDS_REVIEW。ページ/画素/時間上限、暗号化/壊れた PDF は確定 PASS にならない。
人間ゲート：対応範囲、license notices、配布物を確認。PDF を正式対応と表示するのはこの受入後。

## 5. 公開候補の確認（別承認）

合成 fixture の provenance、依存 notices、privacy、結果の確証範囲、インストール手順、既知限界、golden regression を確認する。MazeMa に依存せず起動・検証できることを新規環境で確認する。
受入：VALIDATION の公開ゲートをすべて満たす。失敗/レビュー待ち/未対応を PASS と誤読しない表示になっている。
公開、release、merge、repo visibility 変更はこの計画の実行だけでは行わず、別の明示承認対象とする。

## 次の担当者の開始手順

1. 最新 main と適用 AGENTS/skills を確認し、今回の仕様案の未決事項をレビューする。
2. 段階 0 の ADR と schema のみの PR を作る。仕様変更は理由と影響する fixture を併記する。
3. 段階 1 から順に独立 oracle を先に用意し、故障注入の期待値を固定して実装する。
4. 各 PR に input provenance、実行コマンド、期待/実結果、失敗例、残る限界を書く。認識品質を数学的正しさの証拠として扱わない。
