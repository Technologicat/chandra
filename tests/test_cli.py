"""Smoke tests for the `igmt` dispatcher and subcommand wiring."""

import pytest

from igmt import cli


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
    assert "igmt" in capsys.readouterr().out


def test_show_no_paths_is_usage_error():
    # `show`/`inject` require at least one PNG path; with none they report a usage error.
    assert cli.main(["show"]) == 2


def test_inject_no_paths_is_usage_error():
    assert cli.main(["inject"]) == 2


def test_dispatch_search_no_terms_is_usage_error():
    # search dispatches and, with no terms, reports a usage error (exit 2).
    assert cli.main(["search"]) == 2


def test_no_command_errors():
    # subparsers are required: invoking with no subcommand is a usage error (exit code 2).
    with pytest.raises(SystemExit) as exc:
        cli.main([])
    assert exc.value.code == 2
