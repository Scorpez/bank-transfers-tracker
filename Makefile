# The four commands you need. Anything the README tells you to run lives here too,
# so the workflow is executable rather than only described.
.PHONY: setup test lint run clean

VENV ?= .venv
PY   := $(VENV)/bin/python

setup:                ## create a virtualenv and install the package with its dev extras
	python3 -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e ".[dev]" || $(PY) -m pip install -e .

test:                 ## run the full suite; needs no credentials and makes no network calls
	$(PY) -m pytest -q

lint:                 ## style only, never a substitute for the tests
	$(PY) -m ruff check . || true

run:                  ## the demo entry point
	$(PY) main.py --help

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__
