#!/usr/bin/env bash
# اجرای ربات در پس‌زمینه + نگه‌داشتن لاگ
set -e
cd "$(dirname "$0")/.."

mkdir -p logs

if [ ! -f .env ]; then
  echo "FAILED: .env not found (از .env.example یک نسخه بسازید)" >&2
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

nohup .venv/bin/python -m app.main >> logs/stdout.log 2>&1 &
echo "STARTED pid=$!"
