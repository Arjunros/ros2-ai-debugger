# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/), versioning: [SemVer](https://semver.org/).

## [0.1.0] - 2026-09-19

First public release (pre-1.0: interfaces may change).

### Added
- `ros2 ai diagnose`, `ros2 ai doctor`, `ros2 ai version` (also as standalone `ros2-ai`).
- Read-only collectors: nodes, topics with QoS, services, actions, TF, lifecycle state, ros2_control
  controllers, `/diagnostics`, `/rosout`, host CPU/memory/disk/network.
- 14 deterministic rules (R01-R14), including QoS incompatibility, disconnected TF trees, lifecycle
  and action-server checks, and expectation-based checks via `--config`.
- Optional AI analysis via Claude, OpenAI, Gemini and Ollama, with strict response validation
  (schema, grounded component names, read-only command allowlist).
- Privacy controls: opt-in AI, `--dry-run`, `--redact`, confirmation before cloud sends, secret scrubbing.
- Terminal, Markdown (GitHub-issue ready) and JSON reports; replay with `--from-snapshot`.
- Broken-robot demo (`examples/broken_robot_demo.py`) and deterministic golden-report tests.

### Verification
- ROS 2 Humble and Jazzy: colcon build, unit and live tests pass in CI.
- Cloud providers are tested against mocked transports only (Claude via the real SDK); not yet against live APIs.
- Ollama: request/response logic unit-tested; no live model run in CI.

[0.1.0]: https://github.com/Arjunros/ros2-ai-debugger/releases/tag/v0.1.0
