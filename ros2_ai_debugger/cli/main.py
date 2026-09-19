"""Standalone entry point (`ros2-ai`) and shared argument parsing for `ros2 ai`."""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from ros2_ai_debugger import __version__
from ros2_ai_debugger.cli import diagnose as diagnose_cmd


def add_subcommands(parser: argparse.ArgumentParser) -> None:
    """Attach `diagnose`, `doctor` and `version` to ``parser``."""
    sub = parser.add_subparsers(dest="verb", metavar="<command>")
    d = sub.add_parser(
        "diagnose", help="collect ROS 2 diagnostics and produce a diagnosis report",
        description="Read-only diagnosis of the running ROS 2 system. Rule-based checks always "
                    "run; AI analysis is opt-in (--local or --provider).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="examples:\n"
               "  ros2 ai diagnose                       rule-based diagnosis\n"
               "  ros2 ai diagnose --local               add analysis by a local Ollama model\n"
               "  ros2 ai diagnose --provider claude --dry-run    preview what would be sent\n"
               "  ros2 ai diagnose --output report.md    Markdown report (redacted)\n"
               "  ros2 ai diagnose --github              issue-ready report: github-report.md\n")
    diagnose_cmd.add_arguments(d)
    sub.add_parser("doctor", help="check that ros2-ai-debugger can work in this environment")
    sub.add_parser("version", help="print the ros2-ai-debugger version")


def run(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    """Dispatch a parsed namespace. Shared by `ros2 ai` and `ros2-ai`."""
    if args.verb == "version":
        print(f"ros2-ai-debugger {__version__}")
        return 0
    if args.verb == "doctor":
        from ros2_ai_debugger.cli.doctor import run_doctor

        return run_doctor()
    if args.verb == "diagnose":
        return diagnose_cmd.run_diagnose(args)
    parser.print_help()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="ros2-ai",
        description="AI-assisted diagnostics and troubleshooting for ROS 2 systems.",
    )
    add_subcommands(parser)
    try:
        return run(parser.parse_args(argv), parser)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
