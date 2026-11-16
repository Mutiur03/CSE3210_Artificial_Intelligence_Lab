#!/usr/bin/env sh
# Start Cheese Heist. Extra arguments go to main.py (e.g. --seed 5 --size 27).
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then PY=.venv/bin/python
elif [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
else PY=python3; fi
exec "$PY" main.py "$@"
