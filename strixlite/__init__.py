"""Strix-Lite — a tiny, dependency-free demonstration of the Strix architecture.

A root orchestrator agent delegates to specialist sub-agents that load skills,
drive a real HTTP tool layer against a bundled vulnerable target, and file
findings — every step streamed as a live log. It is a teaching POC, not a
pentest tool; see the repo README.
"""

from .coordinator import Coordinator
from .runner import run_scan

__all__ = ["Coordinator", "run_scan"]
__version__ = "0.1.0"
