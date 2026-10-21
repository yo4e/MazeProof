#!/bin/bash
# Run the installed copy next to this launcher. No saved URL, port or token.
set -eu
mazeproof_dir="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
mazeproof_python="$mazeproof_dir/.venv/bin/python"

if [ ! -x "$mazeproof_python" ] || ! "$mazeproof_python" -I -c 'import mazeproof.server' >/dev/null 2>&1; then
  printf '%s\n' 'MazeProofの初回準備がまだ完了していません。' \
    'このファイルと同じフォルダのREADMEにある「初回の導入」を実行してください。' \
    'Python 3.12以上で .venv を作り、.venv/bin/python -m pip install . を実行します。'
  if [ -t 0 ]; then
    read -r -p 'Enterキーで閉じます。' _mazeproof_reply
  fi
  exit 1
fi

exec "$mazeproof_python" -I -m mazeproof serve --batch --open-browser "$@"
