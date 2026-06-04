#!/bin/bash
source /usr/src/app/.venv/bin/activate
cd /usr/src/app
export PYTHONPATH="/usr/src/app:${PYTHONPATH}"
python3 update.py && python3 -m bot
