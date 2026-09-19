# Security Policy

## Scope and design

ros2-ai-debugger is **read-only**: it must not modify a ROS system, run arbitrary commands, or expose secrets.
Anything that breaks these guarantees is a security bug, for example:

- a code path that publishes, sets parameters, or calls a state-changing service;
- a way to make a report or AI payload include API keys, arbitrary environment variables or file contents;
- a way for model output or ROS data (node names, log text) to cause command execution or bypass the
  read-only command allowlist;
- redaction bypasses for the patterns documented in `docs/privacy.md`.

Note that redaction is best effort and documented as such; missing an unusual secret format is a bug worth
reporting but not a guarantee violation.

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's private vulnerability reporting
("Security" tab, "Report a vulnerability") on the repository, or e-mail projecthumanoidx@gmail.com.
Include the version (`ros2 ai version`), your ROS distro, and steps to reproduce. Expect an acknowledgement
within about a week.

## Supported versions

Pre-1.0: only the latest release receives fixes.
