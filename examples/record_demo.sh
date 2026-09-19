#!/usr/bin/env bash
# Scripted terminal demo of ros2-ai-debugger, meant to be recorded:
#
#   asciinema rec --cols 100 --rows 36 -c "examples/record_demo.sh" demo.cast
#   asciinema upload demo.cast
#   # or a GIF:  agg demo.cast demo.gif      (https://github.com/asciinema/agg)
#
# Prerequisites: ROS 2 sourced, ros2-ai-debugger installed (colcon or pip), and the repo checked out
# (the demo robot lives in examples/). Nothing is sent over the network; no API key is needed.
#
# Options (environment variables):
#   DEMO_FAST=1        no typing delays or pauses (for testing the script itself)
#   ROS_DOMAIN_ID=N    domain used for the demo (default 42, isolated from your real robots)
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export ROS_DOMAIN_ID="${ROS_DOMAIN_ID:-42}"
FAST="${DEMO_FAST:-0}"

if ! command -v ros2 >/dev/null; then
  echo "ros2 not found: source /opt/ros/<distro>/setup.bash first" >&2; exit 1
fi
if ros2 ai version >/dev/null 2>&1; then
  AI="ros2 ai"
elif command -v ros2-ai >/dev/null; then
  AI="ros2-ai"   # standalone entry point (e.g. pip install into a venv)
else
  echo "ros2-ai-debugger is not installed (see README: Installation)" >&2; exit 1
fi

pause() { [ "$FAST" = 1 ] || sleep "$1"; }

type_cmd() {  # print a command as if typed, then run it
  printf '\033[1;32m$\033[0m '
  if [ "$FAST" = 1 ]; then printf '%s' "$1"; else
    for ((i = 0; i < ${#1}; i++)); do printf '%s' "${1:i:1}"; sleep 0.035; done
  fi
  printf '\n'; pause 0.4
  eval "$1"
}

say() { printf '\n\033[1;36m# %s\033[0m\n' "$1"; pause 1.2; }

python3 "$HERE/broken_robot_demo.py" >/dev/null 2>&1 &
DEMO_PID=$!
trap 'kill "$DEMO_PID" 2>/dev/null; wait "$DEMO_PID" 2>/dev/null' EXIT
clear 2>/dev/null || true

say "A fake robot is running. Something is wrong with it, but what?"
pause 3.5   # let DDS discovery settle while the caption is on screen
type_cmd "ros2 node list"
pause 2

say "One command collects the ROS 2 graph (read-only) and diagnoses it"
say "(output trimmed to the first three findings for the recording)"
type_cmd "$AI diagnose --listen-seconds 3 --no-color | awk '/^FINDING #4/{exit} {print}'"
pause 5

say "Every finding separates OBSERVED facts from INFERRED causes"
say "Want a second opinion from an LLM? First see exactly what would be sent:"
type_cmd "$AI diagnose --provider claude --dry-run --listen-seconds 2 2>/dev/null | head -9"
pause 4

say "Share a redacted, issue-ready report"
type_cmd "cd \"\$(mktemp -d)\" && $AI diagnose --github --listen-seconds 2 && head -12 github-report.md"
pause 4
say "ros2-ai-debugger: read-only, evidence-based, works without any AI provider"
pause 3
