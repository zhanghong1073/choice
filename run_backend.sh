#!/usr/bin/env bash
set -e
PY="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
if ! "$PY" -c "import uvicorn" >/dev/null 2>&1; then
  PY="python3"
fi
"$PY" -m uvicorn backend_api.main:app --host 127.0.0.1 --port 8000 --reload
