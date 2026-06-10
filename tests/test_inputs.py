"""Tests for the shared CLI input resolver (`chandra.inputs`).

This is the one input model behind all three subcommands, so these tests pin the invariants that make
them compose: explicit files/dirs (dirs recursed), else piped stdin, else an optional cwd fallback.
"""

import io
from pathlib import Path

from chandra import inputs


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"")
    return path


# --------------------------------------------------------------------------------
# expand_path

def test_expand_path_file_is_itself(tmp_path):
    f = _touch(tmp_path / "a.png")
    assert list(inputs.expand_path(f)) == [f]


def test_expand_path_passes_through_non_png_file(tmp_path):
    # A file given explicitly is yielded as-is, regardless of extension (no filtering of named files).
    f = _touch(tmp_path / "notes.txt")
    assert list(inputs.expand_path(f)) == [f]


def test_expand_path_directory_recurses_pngs_sorted(tmp_path):
    _touch(tmp_path / "b.png")
    _touch(tmp_path / "a.png")
    _touch(tmp_path / "sub" / "c.png")
    _touch(tmp_path / "skip.txt")
    got = list(inputs.expand_path(tmp_path))
    assert got == sorted(got)  # deterministic order
    assert {p.name for p in got} == {"a.png", "b.png", "c.png"}  # recursed, .txt excluded


# --------------------------------------------------------------------------------
# iter_image_paths: precedence

def test_explicit_takes_precedence_over_stdin(tmp_path, monkeypatch):
    f = _touch(tmp_path / "explicit.png")
    monkeypatch.setattr("sys.stdin", io.StringIO("ignored.png\n"))
    got = list(inputs.iter_image_paths([str(f)], use_stdin=True, default_cwd=True))
    assert got == [f]  # stdin and cwd are not consulted when explicit inputs are given


def test_stdin_when_use_stdin(tmp_path, monkeypatch):
    f1 = _touch(tmp_path / "x.png")
    f2 = _touch(tmp_path / "y.png")
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{f1}\n\n{f2}\n"))  # blank lines skipped
    got = list(inputs.iter_image_paths(None, use_stdin=True, default_cwd=False))
    assert got == [f1, f2]


def test_stdin_auto_detected_when_not_a_tty(tmp_path, monkeypatch):
    f = _touch(tmp_path / "piped.png")
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{f}\n"))  # StringIO.isatty() is False
    got = list(inputs.iter_image_paths(None, use_stdin=False, default_cwd=True))
    assert got == [f]  # piped stdin beats the cwd default


def test_stdin_lines_expand_directories(tmp_path, monkeypatch):
    _touch(tmp_path / "d" / "in.png")
    monkeypatch.setattr("sys.stdin", io.StringIO(f"{tmp_path / 'd'}\n"))
    got = list(inputs.iter_image_paths(None, use_stdin=True, default_cwd=False))
    assert [p.name for p in got] == ["in.png"]  # a directory on stdin is recursed too


def test_default_cwd_fallback(tmp_path, monkeypatch):
    _touch(tmp_path / "here.png")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)  # a terminal: nothing piped
    got = list(inputs.iter_image_paths(None, use_stdin=False, default_cwd=True))
    assert [p.name for p in got] == ["here.png"]


def test_no_input_no_default_is_empty(monkeypatch):
    # The show/inject guard: a terminal, nothing explicit, no cwd fallback -> no paths (caller errors).
    monkeypatch.setattr("sys.stdin.isatty", lambda: True)
    assert list(inputs.iter_image_paths(None, use_stdin=False, default_cwd=False)) == []
