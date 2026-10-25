"""
Command line for the generators.

    python -m scripts.datagen                     # every offline target
    python -m scripts.datagen deck_builder_cards  # just the named targets
    python -m scripts.datagen --check             # write nothing, exit 1 if anything is stale
    python -m scripts.datagen guides              # the Google Sheet import, which needs the network
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from api.client_db import client_output_dir
from scripts.datagen.runner import REPO_ROOT, Context, run
from scripts.datagen.targets import ALL_TARGETS, OFFLINE_TARGETS, by_name


def main(argv: list[str]) -> int:
    """
    Parse arguments, run the chosen targets, and print a report.

    Args:
        argv: Command line arguments, without the program name.

    Returns:
        0 on success. 1 when a target failed, or when `--check` found stale output.
    """
    parser = argparse.ArgumentParser(prog="python -m scripts.datagen", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("targets", nargs="*", help=f"targets to run (default: all offline). One of: {', '.join(t.NAME for t in ALL_TARGETS)}")
    parser.add_argument("--check", action="store_true", help="write nothing, and exit 1 if any output is stale")
    parser.add_argument("--refresh-art", action="store_true", help="re-encode existing images instead of only adding missing ones")
    parser.add_argument("--client", type=Path, default=None, help="extracted client folder (default: the configured one)")
    args = parser.parse_args(argv)

    try:
        targets = [by_name(name) for name in args.targets] if args.targets else OFFLINE_TARGETS
    except KeyError as exc:
        parser.error(f"unknown target {exc}")
    client_root = args.client or client_output_dir()
    if not (client_root / "db").is_dir():
        print(f"No extracted client at {client_root}. Extract it from Setup, or pass --client.", file=sys.stderr)
        return 1

    reports = run(targets, Context(client_root, refresh_art=args.refresh_art), check=args.check)

    stale = False
    for report in reports:
        state = "FAILED" if report.failed else (f"{len(report.changed)} file(s) {'stale' if args.check else 'written'}" if report.changed else "up to date")
        print(f"{report.name}: {report.summary} - {state}" if report.summary else f"{report.name}: {state}", flush=True)
        for path in report.changed[:10]:
            print(f"    {path.relative_to(REPO_ROOT) if path.is_relative_to(REPO_ROOT) else path}")
        if len(report.changed) > 10:
            print(f"    ... and {len(report.changed) - 10} more")
        for issue in report.issues:
            print(f"    [{issue.level}] {issue.message}")
        stale = stale or bool(report.changed)
    failed = any(report.failed for report in reports)
    return 1 if failed or (args.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
