# ADR 0002: ローカルの画像検品ワークベンチ

2026-10-20。ステータス: ローカル実装・検証済み、公開承認は別。

## 決定

Pythonの既存検証コアを保ち、Pillow + NumPy の画像adapter、PDFium の描画adapter、標準ライブラリHTTPサーバーと依存なしのHTML/CSS/JavaScript画面を組み合わせる。アプリ用環境はPython 3.12+。コアと旧JSON CLIの3.9互換は保つ。配布はPython wheelとsource archive。ブラウザは利用者が表示された専用URLを開く。

壁の観測は格子境界の中央64%で、輝度しきい値80/128/176の線上被覆を比較する。赤色の被覆、部分的な壁、しきい値間の不一致をunknownとして返す。自動格子推定は投影のピークと周期からの候補にすぎない。片方の軸に内部壁がない場合は他方のピッチで正方形セルを仮定し、GRID_ESTIMATE_UNCERTAINを表示する。手動の格子・切出しと人間の確認を必須にする。赤線は色maskの中心間接続をたどり、solverで断線を埋めない。

承認は画像digest、認識時の変換・格子・unknown、編集モデル・解決済み境界、構造参照JSON、policyを含むcanonical SHA-256に結び付ける。何か変われば承認を取り消す。人間の操作は「モデルを確認した」という申告であり、画像の完全な数学的証明でも電子署名でもない。

作業保存は原本byte列と設定・編集を含む。復元時にもう一度認識し、保存された承認は信頼しない。CLI/MCPは自動承認しない。GUIの承認をMCPへ移す永続署名鍵・資格情報ストアは導入しない。

## PDF

pypdfium2 5.14.0 / PDFium 156.0.8076.0を採用。指定ページの144dpiレンダリングを画像adapterへ渡す。ページ数、面積、暗号化、文書JavaScript、添付を先に検査し、form environmentを作らず、actionsを実行しない。ベクター、raster、混在のいずれも描画結果についてのみ認識する。ベクター構造抽出との一致は `vectorAgreement: NOT_RUN` と明示し、独立した構造証明とはしない。

PDFiumのライセンスはBSD系、pypdfium2はApache-2.0/BSD-3-Clause。ネイティブwheelに含まれる第三者ライセンスも保持する。[依存notice](../DEPENDENCIES.md)参照。

## 処理境界

- 127.0.0.1のみbind。正確なHost/Origin、毎回新しいbearer token、CSP、no-storeを適用。Web APIは任意のローカルパスを受け付けず、利用者が選んだbyte列だけを扱う。
- decoderは使い捨てspawnプロセス。30秒の認識予算をペアで共有し、RSSを20ms間隔で監視し512MiB超過を終了させる。coreは別の30秒予算。結果のmaxSeconds=60は両予算の合計。入力転送時間は含まない。
- MCPはPOSIX dir_fd/O_NOFOLLOWを使い、起動時に開いたallowed rootから各成分をたどる。root以下のsymlinkを拒否し、親ディレクトリのcheck/open競合を避ける。
- 入力は変更せず、ログに画像・パス・payloadを出さない。保存はブラウザdownloadまたは明示されたCLIの新規ファイルのみ。

## 残る範囲

任意角度のdeskew・透視補正、PDFベクター照合、複数ペアの一括検品、自動承認、署名付きMCPへの承認受渡し、ネイティブアプリbundleは今後の拡張。初期仕様の段階2〜4の全機能を無制限に正式対応と表示しない。公開・mainへのmerge・配布サイトへのreleaseはこの実装の範囲外。
