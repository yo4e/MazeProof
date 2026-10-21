# 使い方ページの検証記録

2026-10-20。初回試用で「確認待ち」「重ね表示」「条件付き PASS」の意味と次の操作が伝わりにくかったため、独立した `/help` ページを追加した。

## 変更

- 全画面共通のヘッダーに「使い方 別タブ ↗」を追加。`target="_blank"` と `rel="noopener noreferrer"` で検品中の画面を置き換えない。ヘルプにセッショントークンを渡さない。
- 投入、重ね表示、橙色境界の確認、モデル修正、明示承認、各判定の意味、保存・復元、問題だけ／問題と解答の両ケース、PDF の範囲を説明。
- 使い方はアプリ同梱の HTML/CSS のみ。JavaScript や API 呼出し、外部サービスへの依存はない。
- 判定コア、認識、承認条件、既存のボタン名は変更していない。作業画面の変更はヘルプ導線と、狭い画面でその導線を収めるヘッダー配置だけ。

## 確認結果

| 検証 | 結果 |
| --- | --- |
| unittest | 46 件成功。`/help` と `/help.css` の配信・Host 拒否・既存の安全ヘッダーも確認 |
| ヘッドレス UI | 15 シナリオ成功。従来 12 件に、別タブと未保存編集保持、ヘルプ内リンクと狭幅、問題だけでの文書通りの承認フローを追加 |
| 状態保持 | 修正済み・未保存のモデルでガイドを開閉し、canvas 内容・未承認状態・元画面の要求数が変わらないことを確認 |
| 承認の説明 | 問題だけで確認箇所 0 → 暫定チェックでも確認待ち → 明示チェックと承認で条件付き PASS、解答関連は未検査。ペアでは橙色境界解消が必要 |
| 表示 | 1440px 幅と 390px 幅のスクリーンショットを目視。320/390px 幅で横はみ出しなし。承認手順へのリンクと全ページ内リンクを確認 |
| 通信 | 別ポートのガイドにヘッドレスでアクセスし、外部要求 0、JavaScript エラー 0 |
| 配布 | wheel に HTML/CSS を同梱。別ディレクトリへ wheel をインストールしてソース外から起動し、全 5 静的 asset とサンプル認識・承認を確認。依存環境は既存 venv を利用 |
| 静的検査 | Prettier、JavaScript 構文、Ruff、Python 構文・文書内リンク、`git diff --check` 成功 |

試用中のユーザーの Chrome を操作・再読み込みせず、稼働中サーバーを停止しなかった。テストは別ポートと独立した headless Chromium を使用。素材は既存の合成 fixture のみ。

## 再現

開発用依存を導入した環境で、リポジトリ直下から:

```sh
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/e2e.py --browser /absolute/path/to/chrome-headless-shell
npm run check
.venv/bin/python -m ruff check mazeproof tests scripts
.venv/bin/python tests/check_repository.py
git diff --check
.venv/bin/python -m build --wheel --no-isolation
```

Playwright の対応ブラウザを標準位置に入れている場合、`--browser` は省略可能。今回の Mac は既存の Chromium headless shell を利用した。

wheel インストール先の Python を指定して `scripts/check_install.py --python /absolute/path/to/python` を実行すると、ソース外起動と同梱 asset を検証できる。

ローカルの `.evidence/` に `help-unittest.log`、`e2e.json`、`help-preview-check.json`、`help-install-check.json`、`help-preview.png`、`help-approval.png`、`help-preview-mobile.png` を保存した。Git 対象外。

## 稼働中の旧版への反映

新しい静的配信ルートを追加したため、旧サーバーには再起動が必要。現在の作業を「作業を保存」でダウンロードし、保存を確認してから旧サーバーを終了する。更新済みソースから `python -m mazeproof serve` で起動し、表示された専用 URL を開いて「保存した作業を開く」で復元する。復元後の再承認は従来通り必要。

今回の試用セッションには反映せず、別ポートでガイドを読むためのローカル確認サーバーを用意した。URL と PID はセッション固有のため最終報告へ記載する。

## 未検証

初めて使う人がチャットでの説明なしに完了できるか、確認時間が短縮されるかは、実利用での評価が必要。Safari/Firefox、実スマートフォンでの操作は今回確認していない。一括検品と AI 窓口の追加は [調査・提案](BATCH_REVIEW_PROPOSAL.md) のみで、実装していない。
