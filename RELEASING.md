# Releasing

1. Update the version in `setup.py`, `ros2_ai_debugger/__init__.py`, `package.xml`; add a section to `CHANGELOG.md`.
2. Make sure CI is green on `main`.
3. `git tag vX.Y.Z && git push origin vX.Y.Z`. The `Release` workflow checks the tag matches the package
   version, builds the sdist/wheel and creates the GitHub Release with the changelog section as notes.
4. PyPI (optional, manual): `pip install build twine && python -m build && twine upload dist/*`, with your own
   PyPI token. Consider PyPI trusted publishing instead of long-lived tokens.
5. ROS index (optional): `bloom-release` and a PR to `ros/rosdistro` so it can be installed with `apt`.
