"""v0.19.0 card #169: per-agent Codex options, from an allowlist, shown where settings files are."""

import io
import sys

import pytest

from xt import brief, cli
from xt.adapters import CODEX_OPTIONS, codex_option_args
from xt.paths import XtError
from xt.spawn import request_spawn
from xt.tui.model import build

from .conftest import add_member

NET = "sandbox_workspace_write.network_access=true"


def _options(ctx, name, value):
    ctx.team._table(name)["codex_options"] = value
    ctx.team.save()
    ctx.reload_team()


def _notes(ctx, name):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system" and m["body"].startswith(f"{name}: ")]


class _Tty(io.StringIO):
    def isatty(self):
        return True


def _status(ctx, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    return capsys.readouterr().out


def test_the_allowlist_is_the_network_switch_alone():
    assert CODEX_OPTIONS == {"sandbox_workspace_write.network_access": ("true", "false")}


def test_an_agent_with_the_option_starts_with_the_matching_override(ctx, monkeypatch, capsys):
    _options(ctx, "liaison", [NET])  # liaison runs on codex in the test team
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    args = ctx.herdr.started[-1][2]
    i = args.index(NET)
    assert args[i - 1] == "-c"
    assert any(f"liaison: Codex options {NET} (network on: it can reach any host)" == n for n in _notes(ctx, "liaison"))
    out = _status(ctx, monkeypatch, capsys)
    # since 0.23.0 (#186) status and the brief fold the option into the caps row; the detail keeps it
    assert "    caps: write, deny, skills, creds advisory; deprecated codex network on" in out.splitlines()
    assert "  caps: write, deny, skills, creds advisory; deprecated codex network on" in brief.build(ctx, "lead")
    team = {r.data["name"]: r for r in build(ctx).panels["Team"]}
    assert "legacy codex network on (deprecated: xt capabilities liaison)" in team["liaison"].detail().plain


def test_network_off_is_accepted_too(ctx):
    _options(ctx, "liaison", ["sandbox_workspace_write.network_access=false"])
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert "sandbox_workspace_write.network_access=false" in ctx.herdr.started[-1][2]


def test_an_agent_without_the_key_is_unchanged(ctx, monkeypatch, capsys):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    args = ctx.herdr.started[-1][2]
    assert not any("sandbox_workspace_write" in x for x in args)
    assert not any("Codex options" in n for n in _notes(ctx, "liaison"))
    assert "codex options" not in _status(ctx, monkeypatch, capsys)
    assert "codex options" not in brief.build(ctx, "lead")


@pytest.mark.parametrize("bad", [
    "sandbox_workspace_write.writable_roots=/tmp",  # not on the list (decision 1)
    "sandbox_workspace_write.network_access=yes",  # not a value it takes
    "sandbox_workspace_write.network_access",  # no value
    "model=gpt",
])
def test_an_unknown_option_is_refused_at_start_with_the_allowed_list(ctx, bad):
    _options(ctx, "liaison", [bad])
    with pytest.raises(XtError) as e:
        request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert "isn't allowed" in str(e.value) and NET.replace("=true", "=true|false") in str(e.value)
    assert not ctx.herdr.started and not ctx.herdr.created  # refused before anything starts


def test_a_single_string_is_read_as_one_option(ctx):
    _options(ctx, "liaison", NET)
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert NET in ctx.herdr.started[-1][2]


def test_the_key_applies_to_codex_only(ctx):
    add_member(ctx, "carol")  # claude
    _options(ctx, "carol", [NET])
    with pytest.raises(XtError, match="applies to Codex agents only"):
        request_spawn(ctx, "human", "carol", None, None, None, None)
    with pytest.raises(XtError, match="applies to Codex agents only"):
        codex_option_args("dave", "pi", [NET])


def test_status_says_when_the_running_start_has_other_options(ctx, monkeypatch, capsys):
    request_spawn(ctx, "human", "liaison", None, None, None, None)  # started without
    _options(ctx, "liaison", [NET])  # the human adds the line afterwards
    out = _status(ctx, monkeypatch, capsys)
    assert "(running with none; `xt restart liaison` applies it)" in out


def test_harnesses_says_the_key_is_codex_only(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_root", lambda: ctx.paths.root)
    cli.cmd_harnesses(cli.build_parser().parse_args(["harnesses"]))
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "codex_options" in ln]
    assert len(lines) == 3  # claude, codex, pi
    assert sum("allowed: sandbox_workspace_write.network_access=true|false" in ln for ln in lines) == 1
    assert sum("not supported" in ln for ln in lines) == 2
