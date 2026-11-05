#!/usr/bin/env bash
# اگر ربات در حال اجرا نبود، دوباره اجرایش می‌کند.
cd "$(dirname "$0")/.."
mkdir -p logs

if ! pgrep -f "python.*-m app.main" > /dev/null 2>&1; then
  if [ ! -f .env ]; then
    echo "FAILED: .env not found"
    exit 1
  fi
  if [ ! -d .venv ]; then
    python3 -m venv .venv || { echo "FAILED: venv"; exit 1; }
    .venv/bin/pip install -q -r requirements.txt || { echo "FAILED: pip"; exit 1; }
  fi
  nohup .venv/bin/python -m app.main >> logs/stdout.log 2>&1 &
  disown 2>/dev/null || true
  sleep 2
  if pgrep -f "python.*-m app.main" > /dev/null 2>&1; then
    echo "RESTARTED"
  else
    echo "FAILED"
  fi
else
  echo "RUNNING"
fi
