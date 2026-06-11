"""Smoke tests for the `chandra` dispatcher and subcommand wiring."""

import io

import pytest

from chandra import cli, pngchunks


def test_help_lists_subcommands(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "search" in out
    assert "show" in out
    assert "inject" in out
    assert "eject" in out


def test_version_action(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert "chandra" in capsys.readouterr().out


def test_show_no_paths_prints_usage(capsys, monkeypatch):
    # `show`/`inject` require at least one PNG path; with none (and no pipe) they print a short usage
    # (exit 2). Simulate a terminal so the resolver doesn't try to read paths from captured stdin.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert cli.main(["show"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "chandra show" in err


def test_inject_no_paths_prints_usage(capsys, monkeypatch):
    # A bare `chandra inject` must never default to modifying files in the cwd — it prints usage.
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert cli.main(["inject"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "chandra inject" in err


def test_search_no_terms_prints_usage(capsys):
    assert cli.main(["search"]) == 2
    err = capsys.readouterr().err
    assert "usage:" in err and "chandra search" in err


def test_show_reads_paths_from_stdin(tmp_path, capsys, monkeypatch):
    # The composability win: `search … | chandra show` — show consumes paths piped on stdin.
    # A PNG with no ComfyUI `prompt` chunk makes show report a per-file error naming the path,
    # which proves the path came in via stdin (no positional args were given).
    png = tmp_path / "plain.png"
    ihdr = pngchunks.Chunk(b"IHDR", (8).to_bytes(4, "big") + (8).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")
    pngchunks.write_file(png, [ihdr, pngchunks.Chunk(b"IEND", b"")])
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{png}\n"))
    rc = cli.main(["show"])
    assert rc == 1  # processed the file, but it has no ComfyUI prompt chunk
    assert str(png) in capsys.readouterr().err


def test_bare_chandra_lists_commands(capsys):
    # Bare `chandra` is friendly: it prints the help, which lists the commands, and exits 0.
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "search" in out and "show" in out and "inject" in out and "eject" in out
