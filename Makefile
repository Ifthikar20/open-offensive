# OpenOffensive — dev shortcuts
PY ?= python3

.PHONY: help install dev test doctor scan serve lint clean

help:
	@echo "make install   # pip install -e . (scripted mode; no Python deps, but Docker is required)"
	@echo "make dev       # pip install -e '.[llm,dev]'  (LLM + test deps)"
	@echo "make test      # run the pytest suite (no Docker needed — FakeSandbox + mocks)"
	@echo "make doctor    # check Docker/LLM readiness and build the Kali sandbox image"
	@echo "make scan      # headless scan of the bundled demo target (needs Docker)"
	@echo "make serve     # start the live dashboard"
	@echo "make clean     # remove caches and local run artifacts"

install:
	$(PY) -m pip install -e .

dev:
	$(PY) -m pip install -e '.[llm,dev]'

test:
	$(PY) -m pytest

doctor:
	$(PY) -m openoffensive doctor --build

scan:
	$(PY) -m openoffensive scan

serve:
	$(PY) -m openoffensive serve --no-open

lint:
	$(PY) -m compileall -q openoffensive

clean:
	rm -rf runs .pytest_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
