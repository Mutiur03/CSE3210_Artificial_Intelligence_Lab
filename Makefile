# Cheese Heist. Uses .venv if it exists, else the python on PATH.
# Needs Python 3.11-3.13 (pygame 2.6 has no wheels for 3.14 yet).
VENV_PY := $(firstword $(wildcard .venv/Scripts/python.exe .venv/bin/python) .venv/bin/python)
PYTHON ?= python
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))

.PHONY: setup deps test lint run bench match screens

setup:
	$(PYTHON) -m venv .venv
	$(MAKE) deps

deps:  # separate make run so VENV_PY sees the new .venv
	$(VENV_PY) -m pip install -r requirements.txt

test:
	SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy $(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

run:
	$(PY) main.py

bench:
	$(PY) scripts/bench_search.py

match:
	$(PY) scripts/match.py --ladder --jerry normal --games 100

screens:
	$(PY) scripts/screens.py
