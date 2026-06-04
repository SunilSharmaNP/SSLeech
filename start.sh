#!/bin/bash
cd /usr/src/app
export PYTHONPATH="/usr/src/app:${PYTHONPATH}"
source /usr/src/app/.venv/bin/activate 2>/dev/null || true
python3 update.py && python3 -m bot
