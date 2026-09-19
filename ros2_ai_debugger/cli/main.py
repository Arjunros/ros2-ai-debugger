"""Standalone entry point (`ros2-ai`) and shared argument parsing."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ros2_ai_debugger import __version__


def add_subcommands(parser: argparse.ArgumentParser) -> None:
    """Attach the `version` (and, later, `diagnose`/`doctor`) subcommands."""
    sub = parser.add_subparsers(dest="verb", metavar="<command>")
    sub.add_parser("version", help="print the ros2-ai-debugger version")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Dispatch a parsed namespace. Shared by `ros2 ai` and `ros2-ai`."""
    if args.verb == "version":
        print(f"ros2-ai-debugger {__version__}")
        return 0
    parser.print_help()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ros2-ai",
        description="AI-assisted diagnostics and troubleshooting for ROS 2 systems.",
    )
    add_subcommands(parser)
    return run(parser.parse_args(argv), parser)


if __name__ == "__main__":
    sys.exit(main())
