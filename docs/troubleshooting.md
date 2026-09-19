# Troubleshooting

Start with `ros2 ai doctor`.

**`ros2: error: invalid choice: 'ai'`**
The `ros2` command (which runs on the system Python) cannot see the package. Install it with colcon and
`source install/setup.bash`, or `pip install` into the interpreter `ros2` uses. A virtualenv is invisible to
`ros2` unless you add it to `PYTHONPATH`. `ros2-ai` (standalone) works from a venv.

**`rclpy is not importable`**
Source ROS 2 first: `source /opt/ros/<distro>/setup.bash`. With a venv, create it with
`--system-site-packages`.

**"No ROS 2 nodes are visible" (R12)**
The tool sees an empty graph. Check `ROS_DOMAIN_ID`, `RMW_IMPLEMENTATION` and `ROS_LOCALHOST_ONLY` match the
robot's shell, and that multicast is not blocked. `ros2 node list` should list the nodes from the same shell.

**TF finding is a false alarm**
TF is sampled for `--listen-seconds` (default 2). Transforms published slower than that are missed; increase it.
Intentionally separate trees are also reported.

**"provider not configured" / AI skipped**
Set the API key environment variable (see `docs/providers.md`), or run without `--provider`. The rule-based
report is always produced.

**AI analysis skipped: "non-interactive session; pass --yes"**
Cloud sends need confirmation. Use `--dry-run` to review the payload, then `--yes`.

**Ollama: timed out / could not reach**
Run `ollama serve`, `ollama pull <model>`, and use `--model`. CPU-only machines can exceed the 300 s timeout
with large models.

**AI output was dropped ("Validation removed unsupported AI output")**
This is intended: the model referenced components not in the snapshot, or suggested a non-read-only command.

**Some collector failed**
See "Collection problems" in the report; other collectors still ran. Please open an issue with `ros2 ai doctor`
output.
