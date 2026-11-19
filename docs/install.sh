#!/usr/bin/env bash
# osetup — cài nhanh 1 dòng lệnh (Linux/macOS):
#   curl -fsSL https://<user>.github.io/<repo>/install.sh | OSETUP_ARGS='install student -y' bash
set -e
REPO="${OSETUP_REPO:-Ciro4c/o_setup}"
DIR="${HOME}/.osetup/app"
command -v python3 >/dev/null || { echo "Cần Python 3. Linux: sudo apt-get install -y python3 | macOS: brew install python"; exit 1; }
rm -rf "$DIR"; mkdir -p "$DIR"
echo "Đang tải osetup từ github.com/$REPO ..."
curl -fsSL "https://github.com/$REPO/archive/HEAD.tar.gz" | tar xz -C "$DIR" --strip-components=1
cd "$DIR"
# shellcheck disable=SC2086
exec python3 -m osetup ${OSETUP_ARGS:-menu}
