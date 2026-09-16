"""OpenOffensive — an autonomous, multi-agent AI pentester.

A root orchestrator delegates to specialist sub-agents that load skills, drive a
real HTTP tool layer against a target, and file validated findings — with a live
log you can watch. Agents run a scripted methodology out of the box, or reason
with a real model when one is configured.
"""

__version__ = "1.0.0"

from .config import Settings, load_settings
from .coordinator import Coordinator
from .models import Finding, ScanConfig, ScanResult
from .runner import run_scan

__all__ = [
    "Coordinator",
    "Finding",
    "ScanConfig",
    "ScanResult",
    "Settings",
    "load_settings",
    "run_scan",
    "__version__",
]
