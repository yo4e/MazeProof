# 未決事項と設計記録

## 固定した方向

ローカルで独立検証、共通コア、構造JSONを厳密基準、完成品も検査、認識と証明を分離、画像確認ゲート、synthetic 公開 fixture。実装・依存導入・公開設定変更は今回の対象外。
2026-10-07 の調査時点で repo は空。README/AGENTS/関連する repo-local SKILL は存在しなかった。PR 比較用に内容なしの main 初期コミットを作成し、仕様は PR でレビューする。

## 未決と決める時期

| 項目 | 候補/確認内容 | 決定時期 |
| --- | --- | --- |
| 言語・配布 | Python の画像処理親和性、TypeScript の UI/MCP、単一言語/worker 分離の配布負担を比較 | 段階0 |
| UI | ローカルブラウザUIかdesktop。loopbackの場合の認証/Origin対策も設計 | 段階0 |
| JSON/result schema | 本仕様の壁配列・端点・status・exit code を正式schemaと例で固定 | 段階0 |
| policy | unique_required=true と simple path 契約の利用者適合性 | 段階0 |
| 認識品質 | 最小壁幅、格子推定、しきい値、JPEG品質、角度、確認文言。自動PASSは初期導入しない | 段階2 |
| 上限 | SPECの初期案を実測し、decode/render前の制限とworker強制終了を確認 | 各adapter導入前 |
| PDF engine | PDFium系/Poppler等のlicense、バイナリ配布、sandbox、vector extractionの実装費を比較。MuPDF系を含め選定前に条件確認 | 段階4前 |
| 公開license | MazeProof自身とfixtureのlicense、依存notice、商標/name確認 | 公開候補前 |
| 自動確認 | supported profileで自動承認を将来許すかは別ADR。現時点は画像認識モデルの人間確認が必要 | MVP後 |

## OSS 候補（採用未決、未動作検証）

2026-10-07 に以下の実 LICENSE 本文を GitHub から確認。ライセンスが許容可能でもアルゴリズムや認識品質を保証しない。丸ごと採用せず、固定commit、依存全体、notice、配布条件、故障注入結果を評価してから判断する。

| 候補 | 実LICENSE | 参考価値と注意 |
| --- | --- | --- |
| [jtris/maze-solver](https://github.com/jtris/maze-solver) | [MIT](https://github.com/jtris/maze-solver/blob/main/LICENSE)、copyright 2023 triskj0 | OpenCV系の画像solver候補。縮小で細壁が消える可能性を評価。解けることと画像の正しさ/唯一性は別 |
| [mikepound/mazesolving](https://github.com/mikepound/mazesolving) | [Unlicense](https://github.com/mikepound/mazesolving/blob/master/LICENSE) | 白黒、上入口/下出口等の制約が候補調査で報告されている。適用範囲は採用前にコードとfixtureで再確認 |
| [MorvanZhou/mmaze](https://github.com/MorvanZhou/mmaze) | [MIT](https://github.com/MorvanZhou/mmaze/blob/main/LICENSE)、copyright 2022 MorvanZhou | 構造生成/solve/描画の比較候補。生成と検証の共通ロジックを独立oracleにしない |

MIT のコピー/重要部分採用時は著作権・許諾表示を保持する。Unlicense の本文も配布の provenance として保持する方針。PDF engine、画像decode、OpenCV、UI/MCP依存はまだ選定・license確認していない。候補一覧は導入承認ではない。外部有料サービスは不要とする。

## 記録の公開境界

要件は依頼者から提供された会話要約に基づく。私的会話の全文・添付・商品データは転載しない。MazeMa の非公開素材を試験する将来作業は非公開環境で別途許可を得る。公開版には独立 synthetic data と集計した検証方針のみ置く。
名前の事前簡易検索結果は依頼者の引継ぎ情報であり、商標・法的クリアランスの証拠ではない。
