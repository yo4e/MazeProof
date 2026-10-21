# 依存と配布notice

アプリは固定バージョンのPython依存をインストールする。第三者実装のコード・binaryをこのリポジトリの独自MITライセンスとして再表示しない。自前のwheelには第三者binaryを同梱せず、package installerが各配布物を取得する。

| 依存 | 用途 | インストールした配布物のライセンス |
| --- | --- | --- |
| Pillow 13.0.0 | PNG/JPEG decode、EXIF、透過合成 | MIT-CMU。dist-info/licenses/LICENSE |
| NumPy 2.5.4 | ピクセル配列と投影 | BSD-3-Clause / 0BSD / MIT / Zlib / CC0-1.0、および同梱部品のnotice。dist-info/licenses/ |
| pypdfium2 5.14.0 | PDFiumのPython bindings | Apache-2.0 / BSD-3-Clause。dist-info/licenses/LICENSES/ |
| PDFium 156.0.8076.0 | 指定PDFページの描画 | BSD系と第三者notice。pypdfium2 dist-info/licenses/data/<platform>/BUILD_LICENSES/ |
| psutil 7.2.2 | workerのRSS監視 | BSD-3-Clause。dist-info/LICENSE |

PDFiumのbuildには画像decode、フォント、圧縮等の依存が含まれる。pypdfium2の配布物に含まれるLICENSES・BUILD_LICENSESを削除しない。将来standalone bundleへ再配布する場合は、対象プラットフォームのライセンス一式を含める必要がある。現在はstandalone bundleを作らない。

検証専用: Playwright 1.64.0はApache-2.0（ChromiumとNodeに別notice）、Ruff 0.14.1はMIT、Prettier 3.6.2はMIT。build/setuptools/jsonschema関連依存は開発・検証用。製品の実行時にブラウザ自動操作ライブラリは必要ない。

採用APIの一次資料: [Pillow Image API](https://pillow.readthedocs.io/en/stable/reference/Image.html)、[pypdfium2 Python API](https://pypdfium2.readthedocs.io/en/stable/python_api.html)、[pypdfium2 licensing](https://github.com/pypdfium2-team/pypdfium2#licensing)。実際のバージョンとライセンスはインストール済みwheelのmetadataとlicenseファイルでも確認した。
