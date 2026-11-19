# Cheese Heist. Uses .venv if it exists, else the python on PATH.
# Needs Python 3.11-3.13 (pygame 2.6 has no wheels for 3.14 yet).
VENV_PY := $(firstword $(wildcard .venv/Scripts/python.exe .venv/bin/python) .venv/bin/python)
PYTHON ?= python
PY := $(if $(wildcard $(VENV_PY)),$(VENV_PY),$(PYTHON))
HEADLESS := SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy

.PHONY: setup deps test lint run demo bench match screens scenario experiments videos slides report docs check all

setup:
	$(PYTHON) -m venv .venv
	$(MAKE) deps

deps:  # separate make run so VENV_PY sees the new .venv
	$(VENV_PY) -m pip install -r requirements.txt

test:
	$(HEADLESS) $(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

run:
	$(PY) main.py

demo:  # algorithm demo screen (also F2 in the game)
	$(PY) main.py --demo

bench:
	$(PY) scripts/bench_search.py

match:
	$(PY) scripts/match.py --ladder --jerry normal --games 100

screens:
	$(HEADLESS) $(PY) scripts/screens.py

scenario:
	$(PY) scenario.py

experiments:
	$(PY) scripts/experiments.py

videos:
	$(PY) scripts/find_demo_seeds.py
	$(HEADLESS) $(PY) record.py

docs:
	$(PY) scripts/diagrams.py
	$(PY) scripts/build_docs.py

slides: docs
	$(PY) scripts/build_slides.py

report: docs
	$(PY) scripts/build_report.py

check:
	$(PY) scripts/check_consistency.py

# game checks, scenario, experiments, screenshots, videos, slides, report, consistency
all: test lint scenario screens experiments videos slides report check
