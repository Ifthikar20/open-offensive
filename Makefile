# OpenOffensive — dev shortcuts
PY ?= python3

.PHONY: help install dev test doctor scan serve lint clean

help:
	@echo "make install       # pip install -e . (engine core; add the [llm] extra to run scans)"
	@echo "make dev           # pip install -e '.[llm,dev]'  (LLM + test deps)"
	@echo "make test          # run the pytest suite (no Docker needed — FakeSandbox + mocks)"
	@echo "make doctor        # check Docker/LLM readiness and build the Kali sandbox image"
	@echo "make scan TARGET=… # headless scan of TARGET (needs Docker + ANTHROPIC_API_KEY)"
	@echo "make serve TARGET=… # start the live dashboard for TARGET"
	@echo "make clean         # remove caches and local run artifacts"

install:
	$(PY) -m pip install -e .

dev:
	$(PY) -m pip install -e '.[llm,dev]'

test:
	$(PY) -m pytest

doctor:
	$(PY) -m openoffensive doctor --build

scan:
	$(PY) -m openoffensive scan $(TARGET)

serve:
	$(PY) -m openoffensive serve $(TARGET) --no-open

lint:
	$(PY) -m compileall -q openoffensive

clean:
	rm -rf runs .pytest_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
