# Contributing

Thanks for helping! This project aims to be a trustworthy diagnostic tool, so correctness and honesty about
uncertainty matter more than feature count.

## Setup

```bash
python3 -m venv --system-site-packages .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest                       # no ROS needed
source /opt/ros/<distro>/setup.bash && pytest -m ros   # live tests
```

## Ground rules

1. **Read-only.** No change to a running system: no publishing, parameter sets, process control, arbitrary
   commands. The only service calls allowed are queries listed in `docs/architecture.md`.
2. **No invented diagnostics.** A rule must rest on data present in the snapshot. Put inferences in
   `possible_causes`, never in `observed`.
3. **Core works without AI.** Nothing outside `providers/` may require an LLM or the network.
4. **Privacy.** New collected fields must be considered for redaction; never add arbitrary env vars or file contents.
5. **Recommended commands** must pass `utils/commands.py::is_read_only_command`.
6. Only `collectors/rclpy_backend.py` imports rclpy; only `cli/ros2_command.py` imports ros2cli.

## Pull requests

- Small, focused commits; describe the *why*. Follow [Conventional Commits](https://www.conventionalcommits.org/) if you like.
- Add or update tests: unit tests for logic, a fixture or golden file for report changes
  (regenerate goldens deliberately and review the diff).
- PEP 8, type hints, docstrings on public functions; line length 120 (`ruff check .`).
- State which ROS distro you tested on. Do not claim support for a distro you did not run.

## Adding things

See "Extending" in `docs/architecture.md` (collectors, rules, providers, distros).

## Versioning

[Semantic Versioning](https://semver.org). Report JSON has `schema_version`; breaking changes bump it.
