#!/bin/bash
set -e
cd /usr/src/app

# Activate venv if it exists (SSLeech-style .venv), else use system Python (wzv3-style /wzvenv)
if [ -f "/usr/src/app/.venv/bin/activate" ]; then
    source /usr/src/app/.venv/bin/activate
fi

export PYTHONPATH="/usr/src/app:${PYTHONPATH}"
python3 update.py
exec python3 -m bot
