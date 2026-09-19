## What and why

## Checklist
- [ ] Tests added/updated (`pytest`); golden files regenerated deliberately if reports changed
- [ ] `ruff check .` passes
- [ ] Read-only: no publishing, parameter sets, process control or arbitrary commands
- [ ] New rules use only data present in the snapshot; inferences are in `possible_causes`
- [ ] Recommended commands pass `is_read_only_command`
- [ ] New collected fields considered for redaction (`docs/privacy.md`)
- [ ] Tested on ROS 2 distro: <!-- humble / jazzy / ... -->; I did not claim support for untested distros
