"""Command-line interface: ``openoffensive <scan|serve|list|report|doctor>``.

Exit codes for ``scan`` (CI-friendly): 0 = clean, 1 = error, 2 = findings.
The real path needs Docker (and an LLM key for the agentic mode); ``doctor``
checks the environment and can pre-build the sandbox image.
"""

from __future__ import annotations

import argparse
import dataclasses
import queue
import sys
import threading
import uuid
from urllib.parse import urlparse

from . import __version__
from .config import Settings, load_settings
from .coordinator import Coordinator
from .demo_target import serve_in_thread
from .persistence import RunStore
from .runner import classify_target, run_scan

_GLYPH = {"system": "·", "phase": "▸", "think": "·", "skill": "◆", "tool": "→",
          "finding": "⚑", "graph": "○", "report": "★", "error": "✕"}
_LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "host.docker.internal")


def _is_local(target: str) -> bool:
    host = urlparse(target if "//" in target else "//" + target).hostname or ""
    return host in _LOCAL_HOSTS or host.endswith(".localhost")


def _settings_for(args: argparse.Namespace) -> Settings:
    s = load_settings()
    repl: dict = {}
    if getattr(args, "mode", None):
        repl["llm_mode"] = args.mode
    if getattr(args, "model", None):
        repl["model"] = args.model
    if getattr(args, "runs_dir", None):
        repl["runs_dir"] = args.runs_dir
    return dataclasses.replace(s, **repl) if repl else s


def _stream_and_run(coord: Coordinator, run_fn) -> None:
    """Run a scan in a thread while printing its live log to stdout."""
    sub = coord.subscribe()
    done = threading.Event()

    def _worker() -> None:
        try:
            run_fn()
        finally:
            done.set()

    threading.Thread(target=_worker, daemon=True).start()
    while not done.is_set() or not sub.empty():
        try:
            ev = sub.get(timeout=0.2)
        except queue.Empty:
            continue
        g = _GLYPH.get(ev.level, "·")
        print(f"  {g} {ev.agent:<18} {ev.message}")


def cmd_scan(args: argparse.Namespace) -> int:
    settings = _settings_for(args)
    store = RunStore(settings.runs_dir)
    scan_id = f"scan-{uuid.uuid4().hex[:8]}"

    demo_srv = None
    if args.target:
        target = args.target
        if classify_target(target) == "url":
            if "//" not in target:
                target = "http://" + target
            if not _is_local(target) and not args.authorized:
                print("Refusing to scan a non-local target without authorization.\n"
                      "Only scan systems you own or have explicit written permission to test.\n"
                      "Re-run with --authorized once you have confirmed you are in scope.",
                      file=sys.stderr)
                return 1
    else:
        # Start the bundled demo on all interfaces so the container can reach it
        # via host.docker.internal, then point the scan there.
        demo_srv, _ = serve_in_thread("0.0.0.0", 0)
        port = demo_srv.server_address[1]
        target = f"http://host.docker.internal:{port}"
        print(f"  (no target given — scanning the bundled demo app at {target})\n")

    coord = Coordinator(target)
    result_box: dict = {}

    def _run() -> None:
        result_box["res"] = run_scan(coord, settings=settings, scan_id=scan_id, store=store)

    try:
        _stream_and_run(coord, _run)
    finally:
        if demo_srv is not None:
            demo_srv.shutdown()
            demo_srv.server_close()

    res = result_box.get("res")
    if res is None:
        return 1
    print(f"\n  Report: {store.dir_for(scan_id) / 'report.md'}")
    print(f"  SARIF : {store.dir_for(scan_id) / 'findings.sarif'}")
    if res.status == "error":
        return 1
    return 2 if len(res.findings) > 0 else 0


def cmd_doctor(args: argparse.Namespace) -> int:
    from .sandbox import SANDBOX_DIR, docker_available, open_sandbox
    settings = load_settings()
    ok, reason = docker_available()
    print(f"docker daemon   : {'OK' if ok else 'UNAVAILABLE — ' + reason}")
    print(f"sandbox image   : {settings.sandbox_image}")
    print(f"ANTHROPIC_API_KEY: {'set' if settings.api_key_present else 'not set'}")
    print(f"mode            : {'llm (' + settings.model + ')' if (settings.llm_enabled and ok) else 'scripted'}")
    if not ok:
        print("\nDocker is required. Start the daemon, then re-run.", file=sys.stderr)
        return 1
    if args.build:
        print("\nbuilding the sandbox image (first time pulls Kali — slow)…")
        sb = open_sandbox("doctor", settings, emit=lambda level, msg: print("  " + msg))
        try:
            sb.ensure_image(dockerfile_dir=SANDBOX_DIR)
            print("image ready.")
        except Exception as e:  # noqa: BLE001
            print(f"image build/pull failed: {e}", file=sys.stderr)
            return 1
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from .server import main as serve_main
    serve_main(open_browser=not args.no_open)
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    settings = _settings_for(args)
    runs = RunStore(settings.runs_dir).list_runs()
    if not runs:
        print(f"No runs yet in {settings.runs_dir}/")
        return 0
    print(f"{'SCAN ID':<16} {'STATUS':<8} {'MODE':<9} {'FINDINGS':<9} TARGET")
    for r in runs:
        print(f"{r['scan_id']:<16} {r['status']:<8} {r['mode']:<9} "
              f"{r['total']:<9} {r['target']}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    settings = _settings_for(args)
    md = RunStore(settings.runs_dir).load_report(args.scan_id)
    if not md:
        print(f"No report for '{args.scan_id}' in {settings.runs_dir}/", file=sys.stderr)
        return 1
    print(md)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="openoffensive",
        description="OpenOffensive — a multi-agent AI pentester that runs in a Kali container.")
    p.add_argument("--version", action="version", version=f"openoffensive {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    sc = sub.add_parser("scan", help="run a scan (bundled demo, a git repo, a URL, or a dir)")
    sc.add_argument("target", nargs="?",
                    help="git repo URL, live URL/host, or local dir (default: bundled demo)")
    sc.add_argument("--mode", choices=["auto", "llm", "scripted"], help="override run mode")
    sc.add_argument("--model", help="override the model id (llm mode)")
    sc.add_argument("--runs-dir", dest="runs_dir", help="where to write run artifacts")
    sc.add_argument("--authorized", action="store_true",
                    help="confirm you are authorized to test a non-local URL target")
    sc.set_defaults(func=cmd_scan)

    dr = sub.add_parser("doctor", help="check Docker/LLM readiness; optionally build the image")
    dr.add_argument("--build", action="store_true", help="build/pull the sandbox image now")
    dr.set_defaults(func=cmd_doctor)

    sv = sub.add_parser("serve", help="start the live dashboard")
    sv.add_argument("--no-open", action="store_true", help="do not open a browser")
    sv.set_defaults(func=cmd_serve)

    ls = sub.add_parser("list", help="list persisted runs")
    ls.add_argument("--runs-dir", dest="runs_dir")
    ls.set_defaults(func=cmd_list)

    rp = sub.add_parser("report", help="print a run's markdown report")
    rp.add_argument("scan_id")
    rp.add_argument("--runs-dir", dest="runs_dir")
    rp.set_defaults(func=cmd_report)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    sys.exit(main())
