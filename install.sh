#!/usr/bin/env bash
# Bootstrap cho Linux/macOS. Dùng: ./install.sh [lệnh osetup...]
cd "$(dirname "$0")" || exit 1
if ! command -v python3 >/dev/null; then
  echo "Cần Python 3. Linux: sudo apt-get install -y python3 | macOS: brew install python"; exit 1
fi
exec python3 -m osetup "$@"
