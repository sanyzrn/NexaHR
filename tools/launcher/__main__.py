"""نقطهٔ ورود: پنجره، یا همان کار در ترمینال.

حالتِ `--no-gui` تزئینی نیست. اگر Tk نصب نباشد (روی بعضی توزیع‌های لینوکس
`python3-tk` جدا بسته‌بندی می‌شود) راه‌انداز باید همچنان کار کند، و تستِ
سرتاسری هم بدونِ صفحه‌نمایش از همین مسیر رد می‌شود. هر دو حالت `Session` را
صدا می‌زنند، پس رفتارشان یکی است.
"""
from __future__ import annotations

import argparse
import sys
import time
import webbrowser

from .session import Session
from .steps import DEFAULT_BACKEND_PORT, DEFAULT_FRONTEND_PORT, Outcome, Step


def _print_log(source: str, line: str) -> None:
    print(f"{source:>9} | {line}", flush=True)


def _print_step(step: Step, outcome: Outcome | None) -> None:
    if outcome is None:
        print(f"\n== {step.title} ...", flush=True)
    else:
        mark = "OK " if outcome.ok else "[X]"
        print(f"   {mark} {outcome.summary}", flush=True)


def _print_remedy(outcome: Outcome | None) -> None:
    print("\n" + "=" * 60)
    if outcome is None:
        print("  NexaHR could not start.")
        return
    remedy = outcome.remedy
    print(f"  [X] {remedy.title if remedy else outcome.summary}")
    print("=" * 60)
    if remedy and remedy.body:
        print(f"\n{remedy.body}")
    for command in (remedy.commands if remedy else []):
        print(f"\n    {command}")
    if remedy and remedy.url:
        print(f"\n    {remedy.url}")
    print()


def _ask_password(prompt: str) -> str | None:
    import getpass

    print(f"\n{prompt}")
    try:
        return getpass.getpass("postgres password (blank to skip): ") or None
    except (EOFError, KeyboardInterrupt):
        return None


def run_headless(open_browser: bool = True) -> int:
    session = Session(log=_print_log, ask_password=_ask_password, on_step=_print_step)
    session.stop_on_exit()
    if not (session.prepare() and session.serve()):
        _print_remedy(session.failure)
        return 1

    print("\n" + "=" * 60)
    print("  NexaHR is running.\n")
    for label, url in session.links.all:
        print(f"  {label:<18} {url}")
    for note in session.ctx.notes:
        print(f"\n  note: {note}")
    print("\n  Demo sign-in: hr1 / sup1 / sup2 / dep1 / ceo1")
    print("  Password    : NexaHR@12345")
    print("\n  Press Ctrl+C to stop.")
    print("=" * 60 + "\n")

    if open_browser:
        webbrowser.open(session.links.local)

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nstopping…", flush=True)
    finally:
        session.stop()
    return 0


def run_check() -> int:
    """تشخیصِ بدونِ اجرا — برای وقتی که فقط می‌خواهیم بدانیم پورت‌ها چه وضعی دارند."""
    from . import ports as portlib
    from .environment import lan_address, locate, node_tool, python_tool

    paths = locate()
    print(f"root      {paths.root}")
    print(f"python    {python_tool().pretty} ({'ok' if python_tool().ok else 'too old'})")
    node = node_tool()
    print(f"node      {node.pretty} ({'ok' if node.ok else 'missing or too old'})")
    print(f"lan       {lan_address() or '(none)'}")
    for port in (DEFAULT_BACKEND_PORT, DEFAULT_FRONTEND_PORT):
        probe = portlib.probe(port)
        owner = portlib.owner_of(port) if probe.verdict is portlib.Verdict.IN_USE else None
        extra = f" — held by {owner.label}" if owner else ""
        ours = " (ours)" if owner and portlib.belongs_to(owner, paths.root) else ""
        print(f"port {port}  {probe.verdict.value}{extra}{ours}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tools.launcher", description="Start NexaHR for local development.")
    parser.add_argument("--no-gui", action="store_true", help="run in this terminal instead of a window")
    parser.add_argument("--check", action="store_true", help="report the environment and exit")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser when ready")
    args = parser.parse_args(argv)

    if args.check:
        return run_check()
    if args.no_gui:
        return run_headless(open_browser=not args.no_browser)

    try:
        from .ui import run
    except ImportError as exc:  # pragma: no cover - فقط وقتی Tk نصب نیست
        print(f"no graphical toolkit available ({exc}); falling back to the terminal.\n", file=sys.stderr)
        return run_headless(open_browser=not args.no_browser)
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
