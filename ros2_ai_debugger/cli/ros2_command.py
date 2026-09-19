"""Thin adapter registering `ros2 ai` with the ros2cli command extension point.

Only this module imports ros2cli, so the rest of the package (and its tests)
work without a sourced ROS 2 environment.
"""
from ros2cli.command import CommandExtension

from ros2_ai_debugger.cli.main import add_subcommands, run


class AICommand(CommandExtension):
    """AI-assisted ROS 2 diagnostics."""

    def add_arguments(self, parser, cli_name):
        self._parser = parser
        add_subcommands(parser)

    def main(self, *, parser, args):
        return run(args, self._parser)
