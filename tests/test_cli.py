"""Smoke tests for the `chandra` dispatcher and subcommand wiring."""

import pytest

from chandra import cli


def test_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "search" in out
    assert "show" in out
    assert "inject" in out


def test_version_action(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "chandra" in capsys.readouterr().out


def test_show_no_paths_prints_usage(capsys):
    # `show`/`inject` require at least one PNG path; with none they print a short usage (exit 2).
    assert cli.main(["show"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "chandra show" in err


def test_inject_no_paths_prints_usage(capsys):
    assert cli.main(["inject"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "chandra inject" in err


def test_search_no_terms_prints_usage(capsys):
    assert cli.main(["search"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "chandra search" in err


def test_bare_chandra_lists_commands(capsys):
    # Bare `chandra` is friendly: it prints the help, which lists the commands, and exits 0.
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "search" in out and "show" in out and "inject" in out
