# The four commands you need. Anything the README tells you to run lives here too,
# so the workflow is executable rather than only described.
.PHONY: setup test lint run diagrams clean

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

diagrams:             ## regenerate docs/diagrams/*.svg from their .d2 sources
	@command -v d2 >/dev/null 2>&1 || { echo "d2 is not installed: https://d2lang.com/tour/install"; exit 1; }
	@for f in docs/diagrams/*.d2; do \
		d2 --theme 0 --dark-theme 200 --pad 24 "$$f" "$${f%.d2}.svg" || exit 1; \
	done

run:                  ## the demo entry point
	$(PY) main.py --help

clean:
	rm -rf $(VENV) .pytest_cache **/__pycache__
