# CI の範囲と再現

GitHub Actions の [workflow](../.github/workflows/ci.yml) は全branchへのpushとpull_request（draftを含む）で実行する。mainへの反映は別のmerge判断であり、CIの成功だけで自動mergeしない。

Ubuntu上のPython 3.9 / 3.13で以下を独立に確認する。最低対応版と新しい版の差を確認するためのmatrixで、すべてのOS・Python版の互換性保証ではない。

1. `python -m unittest discover -s tests -v`：13テスト、独立DFS oracleの3,840ケース、62,500セル、故障注入、golden。
2. `python tests/check_schemas.py`：Draft 2020-12の両schemaと13結果シナリオ。
3. `python tests/check_repository.py`：Python構文とrepo内Markdownのローカルファイルリンク。外部URLや見出しanchorの疎通は対象外。
4. `git diff --check HEAD^ HEAD`：checkoutされたcommitの直前との差分の空白。PR実行ではGitHubのtest merge commitを検査する。

[requirements-ci.txt](../requirements-ci.txt)でQA依存と推移依存を固定する。製品の構造コアは標準ライブラリのみで動き、schema validatorは製品依存に追加しない。ローカル実行手順は [README](../README.md) に記載。

公式checkout/setup-python Actionsを確認済みのcommit SHAへ固定する。jobは5分上限、permissionsはcontents:read、checkout後の認証情報は保持しない。同じevent/refの古い実行だけを取消し、pushとPRの確認を互いに潰さない。成果物公開・release・deploy・自動mergeのstepはない。branch protectionなどの設定変更は行わない。

このCIは既存の構造検査を再現するもの。未実装の画像/PDF認識、human confirmation、UI/CLI/MCP、worker強制メモリ上限は検証しない。成功はそれらの品質保証や完成品画像のPASSを意味しない。
