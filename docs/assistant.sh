#!/usr/bin/env bash
# osetup — cài TRỢ LÝ chạy ngầm (Linux/macOS). Gỡ: python3 ~/.osetup-assistant/app/osetup_main.py assistant uninstall
set -e
REPO="${OSETUP_REPO:-Ciro4c/o_setup}"
ROOT="$HOME/.osetup-assistant/app"
[ "$REPO" = "OWNER/REPO" ] && { echo "Chua biet repo. Dat: OSETUP_REPO=ten-chu/ten-repo"; exit 1; }
command -v python3 >/dev/null || { echo "Cần Python 3."; exit 1; }
curl -s -X POST http://127.0.0.1:47890/uninstall-stop -d '{}' >/dev/null 2>&1 || true
sleep 1; rm -rf "$ROOT"; mkdir -p "$ROOT"
curl -fsSL "https://github.com/$REPO/archive/HEAD.tar.gz" | tar xz -C "$ROOT" --strip-components=1
OWNER="$(echo "${REPO%%/*}" | tr 'A-Z' 'a-z')"
ORIG=(--origin "https://${OWNER}.github.io"); [ -n "${OSETUP_ORIGIN:-}" ] && ORIG+=(--origin "$OSETUP_ORIGIN")
python3 "$ROOT/osetup_main.py" assistant install "${ORIG[@]}"
