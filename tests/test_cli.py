"""Smoke tests for the `igmt` dispatcher and subcommand wiring."""

import pytest

from igmt import cli


def test_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "rosetta" in out
    assert "concordance" in out


def test_version_action(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "igmt" in capsys.readouterr().out


def test_dispatch_rosetta_stub():
    assert cli.main(["rosetta"]) == 0


def test_dispatch_concordance_stub():
    assert cli.main(["concordance"]) == 0


def test_no_command_errors():
    # subparsers are required: invoking with no subcommand is a usage error (exit code 2).
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
