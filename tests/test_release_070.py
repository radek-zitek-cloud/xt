"""xt 0.7.0: bare `xt approve`, `xt restart`, `xt friction`, harness/model shown everywhere."""

import io
import sys

import pytest

from xt import brief, cli
from xt.dispatch import send
from xt.spawn import Approvals, request_spawn
from xt.tui.model import build

from .conftest import add_member


@pytest.fixture
def human(monkeypatch, ctx):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    return cli.build_parser()


def test_bare_approve_lists_what_is_waiting(ctx, human, capsys):
    add_member(ctx, "lead", role="lead", reports_to="liaison")
    cli.cmd_approve(human.parse_args(["approve"]))
    assert "nothing is waiting" in capsys.readouterr().out
    (ctx.paths.roles / "researcher.md").write_text("# Role: researcher\n")
    request_spawn(ctx, "lead", "dora", "claude", "opus", "researcher", "lead")
    request_spawn(ctx, "lead", "erin", "codex", None, "researcher", "lead")
    cli.cmd_approve(human.parse_args(["approve"]))
    out = capsys.readouterr().out
    assert "spawn dora (researcher, claude/opus)" in out and "spawn erin (researcher, codex/default)" in out
    ids = " ".join(sorted(Approvals(ctx).pending(), key=int))
    assert f"all of them: xt approve {ids}" in out
    assert len(Approvals(ctx).pending()) == 2  # listing approves nothing


def test_restart_one_agent_and_the_whole_team(ctx, human, monkeypatch):
    from xt import up as up_mod

    add_member(ctx, "carol")
    for a in ("liaison", "carol"):
        request_spawn(ctx, "human", a, None, None, None, None)
    first = {n: a.workspace_id for n, a in ctx.herdr.live.items()}
    cli.cmd_restart(human.parse_args(["restart", "carol"]))
    assert ctx.herdr.live["carol"].workspace_id != first["carol"]  # a fresh session
    assert ctx.herdr.live["liaison"].workspace_id == first["liaison"]
    assert "You are **carol**" in ctx.herdr.last_prompt("carol")

    monkeypatch.setattr(up_mod, "watch_pid", lambda c: None)
    before = dict(ctx.herdr.live)
    cli.cmd_restart(human.parse_args(["restart", "--all"]))
    assert set(ctx.herdr.live) == set(before)  # the team comes back as it was
    assert all(ctx.herdr.live[n].workspace_id != before[n].workspace_id for n in before)
    with pytest.raises(cli.XtError, match="or pass --all"):
        cli.cmd_restart(human.parse_args(["restart"]))


def test_friction_reaches_the_humans_inbox_not_a_pane(ctx, human, capsys):
    add_member(ctx, "carol")
    ctx.herdr.add("liaison")
    msg, status = send(ctx, "carol", "human", "friction", "xt refused task --ref to a report; used a goal instead")
    assert msg["to"] == "human" and "Inbox" in status
    assert ctx.herdr.prompts == []  # nobody's pane got it
    cli.cmd_inbox(human.parse_args(["inbox"]))
    out = capsys.readouterr().out
    assert "Friction reported about xt or a harness:" in out and "xt refused task --ref" in out
    rows = build(ctx).panels["Inbox"]
    assert any(r.kind == "friction" and "carol" in r.text.plain for r in rows)


def test_harness_and_model_show_in_status_brief_and_team(ctx, human, capsys):
    add_member(ctx, "carol")  # claude, no model
    ctx.team.upsert_agent("dave", "worker", "pi", "kimi", "lead")
    ctx.team.save()
    ctx.reload_team()
    cli.cmd_status(human.parse_args(["status"]))
    out = capsys.readouterr().out
    assert "claude/default" in out and "pi/kimi" in out
    assert "dave (worker, pi/kimi, reports to lead" in brief.build(ctx, "lead")
    team = {r.data["name"]: r.text.plain for r in build(ctx).panels["Team"]}
    assert "pi/kimi" in team["dave"] and "claude/default" in team["carol"]
