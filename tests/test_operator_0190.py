"""v0.19.0 card #166: a named operator sender and time-bound delegation."""

import io
import os
import stat
import subprocess
import sys

import pytest

from xt import cli, inbox, operators
from xt.paths import XtError
from xt.spawn import request_spawn
from xt.tui import flow
from xt.tui.model import build


class _Tty(io.StringIO):
    def isatty(self):
        return True


class _Pipe(io.StringIO):
    def isatty(self):
        return False


@pytest.fixture
def team(ctx, monkeypatch):
    """A running liaison and lead; xt commands run against this ctx. The test process stands in
    for the operator's harness process."""
    monkeypatch.setattr(cli, "find_root", lambda: ctx.paths.root)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(operators, "harness_of", lambda pid, proc="/proc": "claude")
    monkeypatch.setattr(operators, "agent_of", lambda pid, proc="/proc": None)
    monkeypatch.delenv(operators.TOKEN_ENV, raising=False)
    for n in ("liaison", "lead"):
        request_spawn(ctx, "human", n, None, None, None, None)
    return ctx


def human(monkeypatch, *argv):
    monkeypatch.setattr(sys, "stdin", _Tty())
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)


def agent(monkeypatch, *argv):
    """A command from a process that isn't the human's terminal (the operator, or an agent)."""
    monkeypatch.setattr(sys, "stdin", _Pipe())
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)


def register(ctx, monkeypatch, pid=None):
    human(monkeypatch, "operator", "add", "op", "--pid", str(pid or os.getpid()))
    token = operators.token_path(ctx.paths, "op").read_text().strip()
    monkeypatch.setenv(operators.TOKEN_ENV, token)
    return token


def _system(ctx):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system"]


# --- the sender ------------------------------------------------------------------------------------


def test_registration_writes_a_private_token_and_a_ledger_note(team, monkeypatch, capsys):
    register(team, monkeypatch)
    path = operators.token_path(team.paths, "op")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600 and stat.S_IMODE(path.parent.stat().st_mode) == 0o700
    rec = operators.load(team.paths)["operators"]["op"]
    assert rec["pid"] == os.getpid() and "token_sha256" in rec and path.read_text().strip() not in str(rec)
    assert any(b.startswith("human registered operator op") for b in _system(team))
    assert "token:" in capsys.readouterr().out


def test_registration_is_human_only_and_refuses_bad_targets(team, monkeypatch):
    with pytest.raises(XtError, match="only the human registers"):
        agent(monkeypatch, "operator", "add", "op", "--pid", str(os.getpid()), "--as", "lead")
    for name in ("lead", "human", "Bad"):
        with pytest.raises(XtError):
            human(monkeypatch, "operator", "add", name, "--pid", str(os.getpid()))
    with pytest.raises(XtError, match="no process"):
        human(monkeypatch, "operator", "add", "op", "--pid", "1")
    monkeypatch.setattr(operators, "harness_of", lambda pid, proc="/proc": None)
    with pytest.raises(XtError, match="not a harness"):
        human(monkeypatch, "operator", "add", "op", "--pid", str(os.getpid()))
    monkeypatch.setattr(operators, "harness_of", lambda pid, proc="/proc": "claude")
    monkeypatch.setattr(operators, "agent_of", lambda pid, proc="/proc": "lead")
    with pytest.raises(XtError, match="team agent lead"):
        human(monkeypatch, "operator", "add", "op", "--pid", str(os.getpid()))


def test_an_unregistered_name_is_refused(team, monkeypatch):
    with pytest.raises(XtError, match="not an active member"):
        agent(monkeypatch, "send", "liaison", "--as", "op", "hello")


def test_a_registered_operators_report_shows_as_its_own_sender(team, monkeypatch):
    register(team, monkeypatch)
    inbox.build(team, list(team.ledger.messages()))  # the human's first look sets the New marker
    agent(monkeypatch, "send", "liaison", "--as", "op", "staging", "check", "passed")
    m = list(team.ledger.messages())[-1]
    assert (m["from"], m["to"], m["type"]) == ("op", "liaison", "report")
    assert m["body"] == "staging check passed\n(sent by op, an operator, on the human's behalf)"
    assert operators.is_operator_message(m)
    assert ("op", "operator", True) in build(team).flow.roster  # its own Flow lane
    lanes = [ln.name for ln in flow.lanes(build(team).flow.roster, [m])]
    assert "op" in lanes
    new = [x for x, _ in inbox.build(team, list(team.ledger.messages())).new]
    assert m["id"] in [x["id"] for x in new]  # and in the human's Inbox
    from xt.dispatch import envelope

    assert "reply" not in envelope(team, m)  # nobody in the team messages an operator


def test_token_alone_or_process_alone_is_refused(team, monkeypatch):
    token = register(team, monkeypatch)
    monkeypatch.delenv(operators.TOKEN_ENV)
    with pytest.raises(XtError, match="missing its token"):
        agent(monkeypatch, "send", "liaison", "--as", "op", "x")  # the process alone
    monkeypatch.setenv(operators.TOKEN_ENV, "0" * 64)
    with pytest.raises(XtError, match="missing its token"):
        agent(monkeypatch, "send", "liaison", "--as", "op", "x")  # a wrong token
    other = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        register(team, monkeypatch, pid=other.pid)  # a process that isn't this one or an ancestor
        with pytest.raises(XtError, match="registered process"):
            agent(monkeypatch, "send", "liaison", "--as", "op", "x")  # the token alone
    finally:
        other.kill()
        other.wait()
    assert token != operators.token_path(team.paths, "op").read_text().strip()  # re-registering: new token
    assert not [m for m in team.ledger.messages() if m["from"] == "op"]


def test_an_operator_sends_reports_to_the_liaison_only(team, monkeypatch):
    register(team, monkeypatch)
    with pytest.raises(XtError, match="to the liaison only"):
        agent(monkeypatch, "send", "lead", "--as", "op", "x")
    with pytest.raises(XtError, match="sends reports .* never opens tasks"):  # v0.22.0: goals under drive (#200)
        agent(monkeypatch, "send", "liaison", "--as", "op", "--type", "task", "x")
    msg = team.ledger.append("liaison", "human", "ask", "Which one?")
    for argv in (["answer", str(msg["id"]), "1"], ["approve"]):  # v0.22.0: only under a drive grant (#200)
        with pytest.raises(XtError, match="operator op has no drive grant"):
            agent(monkeypatch, *argv, "--as", "op")
    for argv in (["done", str(msg["id"])], ["note", "x"],
                 ["friction", "x"], ["brief"], ["stop", "lead"], ["retire", "lead"], ["schedule", "lead", "1h"]):
        with pytest.raises(XtError, match="is an operator"):
            agent(monkeypatch, *argv, "--as", "op")


# --- delegation ------------------------------------------------------------------------------------


def test_a_grant_is_at_most_60_minutes_and_30_by_default(team, monkeypatch, capsys):
    register(team, monkeypatch)
    with pytest.raises(XtError, match="at most 60 minutes"):
        human(monkeypatch, "delegate", "op", "--for", "61m")
    with pytest.raises(XtError, match="at most 60 minutes"):
        human(monkeypatch, "delegate", "op", "--for", "2h")
    human(monkeypatch, "delegate", "op")
    g = operators.active_grant(team, "op")
    assert g["commands"] == ["restart", "reset", "spawn", "up"]
    assert (team.ledger.clock().fromisoformat(g["until"]) - team.ledger.clock()).total_seconds() == 1800
    human(monkeypatch, "delegate", "op", "--for", "60m")
    assert any(b.startswith("human delegated restart, reset, spawn, up to operator op until") for b in _system(team))
    with pytest.raises(XtError, match="not delegable: down"):
        human(monkeypatch, "delegate", "op", "--only", "restart,down")
    with pytest.raises(XtError, match="only the human grants"):
        agent(monkeypatch, "delegate", "op", "--as", "lead")


def test_with_a_grant_each_delegable_command_works_and_is_recorded(team, monkeypatch, capsys):
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op", "--for", "20m")
    until = operators._local(operators.active_grant(team, "op")["until"]).strftime("%H:%M")
    agent(monkeypatch, "restart", "lead", "--as", "op")
    assert "restarted lead" in capsys.readouterr().out
    agent(monkeypatch, "reset", "lead", "--when-idle", "--as", "op")
    agent(monkeypatch, "reset", "lead", "--cancel", "--as", "op")
    team.herdr.close_workspace(team.herdr.live["lead"].workspace_id)  # lead not running
    agent(monkeypatch, "spawn", "lead", "--as", "op")
    assert "lead" in team.herdr.live
    agent(monkeypatch, "up", "--as", "op")
    recorded = [b for b in _system(team) if b.startswith(f"op, delegated by human until {until}: xt ")]
    assert [r.split(": xt ", 1)[1] for r in recorded] == [
        "restart lead", "reset lead --when-idle", "reset lead --cancel", "spawn lead", "up"]


def test_a_failed_delegated_command_is_recorded_as_failed_not_as_run(team, monkeypatch):
    # rc3 live run: `spawn lead` on a running lead failed, yet the log said it ran
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op", "--for", "20m")
    with pytest.raises(XtError, match="lead is already running: spawn starts an agent that isn't running"):
        agent(monkeypatch, "spawn", "lead", "--as", "op")
    with pytest.raises(XtError, match="not an active agent: ghost"):
        agent(monkeypatch, "restart", "ghost", "--as", "op")
    recorded = [b for b in _system(team) if b.startswith("op, delegated by human")]
    assert len(recorded) == 2
    assert recorded[0].endswith("xt spawn lead (failed: lead is already running: spawn starts an agent that "
                                "isn't running (`xt restart lead` restarts a running one))")
    assert recorded[1].endswith("xt restart ghost (failed: not an active agent: ghost)")
    assert not [b for b in _system(team) if b.startswith("started lead")][1:]  # started once, at setup


def test_a_refused_delegated_command_is_not_recorded(team, monkeypatch):
    register(team, monkeypatch)
    with pytest.raises(XtError, match="no active delegation"):
        agent(monkeypatch, "restart", "lead", "--as", "op")
    assert not [b for b in _system(team) if b.startswith("op, delegated")]


def test_spawn_help_matches_what_it_does():
    helptext = cli.build_parser()._subparsers._group_actions[0].choices["spawn"].description
    assert "restarts it)" not in helptext and "if it isn't running" in helptext


def test_spawn_under_a_grant_is_for_an_existing_agent_as_it_is(team, monkeypatch):
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op")
    with pytest.raises(XtError, match="only start an existing agent"):
        agent(monkeypatch, "spawn", "newbie", "--harness", "codex", "--role", "lead", "--as", "op")
    with pytest.raises(XtError, match="as it is in team.toml"):
        agent(monkeypatch, "spawn", "lead", "--model", "x", "--as", "op")


def test_a_grant_can_be_limited(team, monkeypatch):
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op", "--only", "reset")
    with pytest.raises(XtError, match="covers reset, not restart"):
        agent(monkeypatch, "restart", "lead", "--as", "op")


@pytest.mark.parametrize("end", ["none", "expired", "revoked"])
def test_without_a_grant_after_expiry_or_revoke_commands_are_refused_as_today(team, monkeypatch, clock, end):
    register(team, monkeypatch)
    if end != "none":
        human(monkeypatch, "delegate", "op", "--for", "30m")
        if end == "expired":
            clock.advance(minutes=30)
        else:
            human(monkeypatch, "delegate", "--revoke")
    for argv in (["restart", "lead"], ["reset", "lead", "--when-idle"], ["spawn", "lead"], ["up"]):
        with pytest.raises(XtError, match="no active delegation"):
            agent(monkeypatch, *argv, "--as", "op")
    if end == "revoked":
        assert "human revoked the delegation to op" in _system(team)


def test_non_delegable_commands_are_refused_even_under_a_grant(team, monkeypatch):
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op", "--for", "60m")
    for argv, why in ((["down"], "is an operator"), (["restart", "--all"], "with --all"),
                      (["version", "use", "v0.18.0"], "is an operator"),
                      (["approve"], "answers, approvals and goals not included"),  # v0.22.0: drive only (#200)
                      (["operator", "add", "op2", "--pid", "1"], "is an operator"),
                      (["delegate", "op", "--for", "60m"], "is an operator")):
        with pytest.raises(XtError, match=why):
            agent(monkeypatch, *argv, "--as", "op")
    assert {"liaison", "lead"} <= set(team.herdr.live)  # nothing was stopped
    assert not [b for b in _system(team) if b.startswith("stopped ")]


def test_status_and_the_tui_header_show_an_active_grant(team, monkeypatch, capsys):
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op", "--for", "45m")
    until = operators._local(operators.active_grant(team, "op")["until"]).strftime("%H:%M")
    capsys.readouterr()
    human(monkeypatch, "status")
    assert f"delegation: delegated to op until {until}: restart, reset, spawn, up" in capsys.readouterr().out
    assert f"delegated to op until {until}" in build(team).header.plain


def test_the_as_human_guard_is_unchanged(team, monkeypatch):
    register(team, monkeypatch)
    human(monkeypatch, "delegate", "op", "--for", "60m")
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        agent(monkeypatch, "send", "liaison", "--as", "human", "x")  # token and process, still not the human
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        agent(monkeypatch, "restart", "lead", "--as", "human")


def test_an_agent_cannot_borrow_the_operators_name(team, monkeypatch):
    register(team, monkeypatch)
    monkeypatch.delenv(operators.TOKEN_ENV)  # an agent has neither the token in its env nor the process
    human(monkeypatch, "delegate", "op", "--for", "60m")
    with pytest.raises(XtError, match="this isn't operator op"):
        agent(monkeypatch, "restart", "lead", "--as", "op")


def test_operator_pid_prints_the_nearest_harness(monkeypatch, capsys):
    monkeypatch.setattr(operators, "harness_ancestor", lambda proc="/proc": (4242, "claude"))
    args = cli.build_parser().parse_args(["operator", "pid"])
    args.func(args)
    assert "4242 (claude)" in capsys.readouterr().out
