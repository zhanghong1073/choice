#!/usr/bin/env bash
set -e

# Prefer the Python interpreter that already has uvicorn installed.
if /Library/Frameworks/Python.framework/Versions/3.11/bin/python3 -c "import uvicorn" >/dev/null 2>&1; then
  PY="/Library/Frameworks/Python.framework/Versions/3.11/bin/python3"
elif python3 -c "import uvicorn" >/dev/null 2>&1; then
  PY="python3"
else
  echo "uvicorn not found in current Python. Run: python3 -m pip install -r requirements.txt"
  exit 1
fi

URL="http://127.0.0.1:8010/"

"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

# Wait briefly for server boot, then open browser.
for _ in {1..30}; do
  if curl -fsS "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done

open "$URL" >/dev/null 2>&1 || true
echo "Server is running at $URL"
echo "Press Ctrl+C to stop."

wait "$SERVER_PID"
