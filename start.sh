#!/bin/bash
set -e
source /usr/src/app/.venv/bin/activate
cd /usr/src/app
export PYTHONPATH="/usr/src/app:${PYTHONPATH}"
python3 update.py
exec python3 -m bot
