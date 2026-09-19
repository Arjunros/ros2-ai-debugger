import pytest

from ros2_ai_debugger import __version__
from ros2_ai_debugger.cli.main import main


def test_version(capsys):
    assert main(["version"]) == 0
    assert __version__ in capsys.readouterr().out


def test_no_command_prints_help(capsys):
    assert main([]) == 0
    assert "usage" in capsys.readouterr().out


def test_help_exits_zero():
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0
