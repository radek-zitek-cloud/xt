import io
import sys

import pytest

from xt.cli import _who, build_parser
from xt.paths import XtError

from .conftest import REPO


class _Stdin(io.StringIO):
    def __init__(self, tty: bool):
        super().__init__()
        self._tty = tty

    def isatty(self):
        return self._tty


def test_as_human_requires_a_terminal(monkeypatch):
    p = build_parser()
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        _who(p.parse_args(["spawn", "x", "--as", "human"]))
    with pytest.raises(XtError, match="pass --as"):
        _who(p.parse_args(["status"]))
    assert _who(p.parse_args(["status", "--as", "carol"])) == "carol"
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=True))
    assert _who(p.parse_args(["spawn", "x", "--as", "human"])) == "human"
    assert _who(p.parse_args(["status"])) == "human"


def test_as_is_accepted_after_goal_subcommands():
    p = build_parser()
    a = p.parse_args(["goal", "new", "weather", "Build", "it", "--as", "liaison"])
    assert (a.goal_cmd, a.slug, a.title, a.as_) == ("new", "weather", ["Build", "it"], "liaison")
    a = p.parse_args(["goal", "dispatch", "weather", "--as", "liaison"])
    assert a.as_ == "liaison"


def test_brief_only_for_yourself_or_your_reports(ctx, monkeypatch, capsys):
    from xt import cli

    from .conftest import add_member

    add_member(ctx, "carol")
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(sys, "stdin", _Stdin(tty=False))
    p = build_parser()
    with pytest.raises(XtError, match="not lead's"):
        cli.cmd_brief(p.parse_args(["brief", "lead", "--as", "carol"]))
    cli.cmd_brief(p.parse_args(["brief", "--as", "carol"]))
    cli.cmd_brief(p.parse_args(["brief", "carol", "--as", "lead"]))
    assert "for carol" in capsys.readouterr().out


def test_send_defaults_to_report():
    a = build_parser().parse_args(["send", "lead", "--as", "carol", "hello", "there"])
    assert (a.to, a.type, a.body, a.as_) == ("lead", "report", ["hello", "there"], "carol")


def test_version_comes_from_pyproject(capsys):
    import tomllib

    from xt import __version__
    from xt.cli import main

    expected = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]["version"]
    assert __version__ == expected
    with pytest.raises(SystemExit):
        main(["--version"])
    assert capsys.readouterr().out.strip() == f"xt {expected}"
