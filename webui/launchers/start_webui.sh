#!/bin/sh
set -eu
cd "$(dirname "$0")/../.."
if [ -n "${NX_TOOLS_DIR:-}" ] && [ -x "$NX_TOOLS_DIR/runtime/bin/python3" ]; then
  exec "$NX_TOOLS_DIR/runtime/bin/python3" webui/launchers/start_webui.py "$@"
fi
exec python3 webui/launchers/start_webui.py "$@"
