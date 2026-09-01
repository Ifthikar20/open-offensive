# OpenOffensive — dev shortcuts
PY ?= python3

.PHONY: help install dev test scan serve lint clean

help:
	@echo "make install   # pip install -e . (scripted mode, zero deps)"
	@echo "make dev       # pip install -e '.[llm,dev]'  (LLM + test deps)"
	@echo "make test      # run the pytest suite"
	@echo "make scan      # headless scan of the bundled demo target"
	@echo "make serve     # start the live dashboard"
	@echo "make clean     # remove caches and local run artifacts"

install:
	$(PY) -m pip install -e .

dev:
	$(PY) -m pip install -e '.[llm,dev]'

test:
	$(PY) -m pytest

scan:
	$(PY) -m openoffensive scan --watch

serve:
	$(PY) -m openoffensive serve --no-open

lint:
	$(PY) -m compileall -q openoffensive

clean:
	rm -rf runs .pytest_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
