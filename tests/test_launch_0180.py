"""v0.18.0: warn when agents run without xt's launch settings (#165)."""

import os

import pytest

from xt import cli, launch
from xt.alerts import Alerts
from xt.spawn import request_spawn
from xt.up import restart, up
from xt.watch import Supervisor

from .conftest import add_member


def _proc(tmp_path, root, procs):
    """A fake /proc: one directory per process with comm, cmdline, environ and a cwd link.
    env None makes the environment unreadable."""
    proc = tmp_path / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    for pid, (argv, env, cwd) in procs.items():
        d = proc / str(pid)
        d.mkdir()
        (d / "comm").write_text(os.path.basename(argv[0])[:15] + "\n")
        (d / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        environ = d / "environ"
        environ.write_bytes(b"\0".join(f"{k}={v}".encode() for k, v in (env or {}).items()) + b"\0")
        if env is None:
            os.chmod(environ, 0)
        os.symlink(cwd or str(root), d / "cwd")
    return str(proc)


def _use(monkeypatch, proc):
    monkeypatch.setattr(launch, "scan", lambda root, p=None: launch.scan_proc(root, proc))


def _team(ctx):
    for name in ("carol", "dave"):
        add_member(ctx, name)
        request_spawn(ctx, "human", name, None, None, None, None)
        ctx.herdr.live[name].status = "idle"


def _restored(tmp_path, ctx, extra=None):
    """carol started by xt; dave resumed by the multiplexer without XT_AGENT."""
    root = ctx.paths.root
    procs = {101: (["/usr/bin/claude", "--settings", "x"], {"XT_AGENT": "carol", "HOME": "/h"}, None),
             102: (["/usr/bin/claude", "--resume"], {"HOME": "/h"}, None),
             103: (["/usr/bin/bash"], {"XT_AGENT": "dave"}, None),  # a shell, not the harness
             104: (["/usr/bin/claude"], {"XT_AGENT": "dave"}, "/elsewhere")}  # another team's dave
    procs.update(extra or {})
    return _proc(tmp_path, root, procs)


def _cli(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))

    def run(*argv):
        args = cli.build_parser().parse_args(list(argv))
        args.func(args)
        return capsys.readouterr().out

    return run


def _launch_alerts(ctx):
    return {k: a for k, a in Alerts(ctx).active().items() if k.startswith("launch:")}


def test_the_scan_finds_xt_agent_only_in_this_teams_harness_processes(tmp_path, ctx):
    s = launch.scan_proc(str(ctx.paths.root), _restored(tmp_path, ctx))
    assert s.names == {"carol"} and s.unreadable is None


def test_status_reports_an_agent_started_outside_xt_and_raises_one_alert(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    _use(monkeypatch, _restored(tmp_path, ctx))
    run = _cli(ctx, monkeypatch, capsys)
    out = run("status")
    assert ("WARNING: dave is running without xt's launch settings (restored by the multiplexer?): its "
            "model, permissions and connector blocks may be missing. Run `xt restart dave` (or `--all`).") in out
    assert "carol is running without" not in out
    run("status")
    alerts = _launch_alerts(ctx)
    assert list(alerts) == ["launch:dave"]  # one per agent, not one per look
    assert sum(1 for m in ctx.ledger.messages() if m["type"] == "alert" and "dave is running without" in m["body"]) == 1
    inbox = run("inbox")
    assert inbox.startswith("Needs you:") and "dave is running without xt's launch settings" in inbox


def test_an_agent_xt_started_raises_nothing(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    root = ctx.paths.root
    _use(monkeypatch, _proc(tmp_path, root, {
        1: (["/usr/bin/claude"], {"XT_AGENT": "carol"}, None),
        2: (["/usr/local/bin/codex"], {"XT_AGENT": "dave"}, None)}))
    out = _cli(ctx, monkeypatch, capsys)("status")
    assert "launch settings" not in out and _launch_alerts(ctx) == {}


def test_the_supervisor_alerts_once_and_the_team_pane_marks_the_agent(tmp_path, ctx, monkeypatch):
    _team(ctx)
    _use(monkeypatch, _restored(tmp_path, ctx))
    lines = []
    sup = Supervisor(ctx, out=lines.append)
    sup.check_launch(ctx.herdr.agents())
    sup.check_launch(ctx.herdr.agents())
    assert [line for line in lines if "launch settings" in line] == [lines[0]]
    assert lines[0].endswith("alert: dave runs without xt's launch settings")
    assert list(_launch_alerts(ctx)) == ["launch:dave"]

    from xt.tui import model

    rows = {r.key: r for r in model.build(ctx).panels["Team"]}
    assert rows["agent:dave"].data["unlaunched"] and not rows["agent:carol"].data["unlaunched"]
    assert rows["agent:dave"].text.plain.startswith("! dave")
    assert rows["agent:carol"].text.plain.startswith("● carol")
    detail = rows["agent:dave"].detail()
    assert "dave is running without xt's launch settings" in getattr(detail, "text", detail).plain


def test_the_supervisor_tick_runs_the_check(tmp_path, ctx, monkeypatch):
    _team(ctx)
    _use(monkeypatch, _restored(tmp_path, ctx))
    Supervisor(ctx, out=lambda _: None).tick(now=1000.0)
    assert list(_launch_alerts(ctx)) == ["launch:dave"]


def test_the_alert_clears_after_xt_restart(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    _use(monkeypatch, _restored(tmp_path, ctx))
    run = _cli(ctx, monkeypatch, capsys)
    run("status")
    assert "launch:dave" in _launch_alerts(ctx)
    restart(ctx, ["dave"])
    assert _launch_alerts(ctx) == {}  # xt started it
    # and the next look agrees: the new process has XT_AGENT
    _use(monkeypatch, _restored(tmp_path / "after", ctx, {105: (["/usr/bin/claude"], {"XT_AGENT": "dave"}, None)}))
    out = run("status")
    assert "launch settings" not in out and _launch_alerts(ctx) == {}


def test_an_alert_clears_when_the_agent_is_no_longer_running(tmp_path, ctx, monkeypatch):
    _team(ctx)
    _use(monkeypatch, _restored(tmp_path, ctx))
    sup = Supervisor(ctx, out=lambda _: None)
    sup.check_launch(ctx.herdr.agents())
    del ctx.herdr.live["dave"]  # closed outside xt: the missing-agent alert covers that
    sup.check_launch(ctx.herdr.agents())
    assert _launch_alerts(ctx) == {}


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads every file")
def test_an_unreadable_process_is_not_checked_never_a_match(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    root = ctx.paths.root
    _use(monkeypatch, _proc(tmp_path, root, {
        1: (["/usr/bin/claude"], {"XT_AGENT": "carol"}, None),
        2: (["/usr/bin/claude"], None, None)}))  # someone else's: its environment can't be read
    out = _cli(ctx, monkeypatch, capsys)("status")
    assert "launch settings: not checked (no permission to read process 2's environment)" in out
    assert "carol" not in out.split("launch settings: not checked")[0].splitlines()[-1]
    assert "WARNING" not in out and _launch_alerts(ctx) == {}


def test_no_proc_at_all_is_not_checked(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    _use(monkeypatch, str(tmp_path / "no-proc"))
    out = _cli(ctx, monkeypatch, capsys)("status")
    assert out.count("launch settings: not checked (can't list processes") == 2
    assert _launch_alerts(ctx) == {}


def _sandboxed(tmp_path, ctx):
    """A fake /proc as seen from a sandbox in its own PID namespace (rc2 staging, #2363): a few
    processes, none of them an agent's, and NSpid with two levels for this process."""
    proc = _proc(tmp_path, ctx.paths.root, {
        1: (["/usr/bin/bash"], {}, None), 5: (["/usr/bin/python3", "xt"], {}, None)})
    (tmp_path / "proc" / "self").mkdir()
    (tmp_path / "proc" / "self" / "status").write_text("Name:\tpython3\nNSpid:\t48211\t5\n")
    return proc


def test_from_a_sandbox_every_agent_is_not_checked_and_no_alert_changes(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    Alerts(ctx).raise_("launch:dave", launch.warning("dave"))  # raised earlier from a real look
    _use(monkeypatch, _sandboxed(tmp_path, ctx))
    run = _cli(ctx, monkeypatch, capsys)
    out = run("status")
    assert out.count("launch settings: not checked (xt runs in a PID namespace here (a sandbox?)") == 2
    assert "WARNING" not in out
    assert list(_launch_alerts(ctx)) == ["launch:dave"]  # neither raised nor cleared
    Supervisor(ctx, out=lambda _: None).check_launch(ctx.herdr.agents())
    assert list(_launch_alerts(ctx)) == ["launch:dave"]


def test_no_agent_process_visible_at_all_is_not_checked(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    # no namespace marker, but /proc shows no harness process in the team repo at all
    _use(monkeypatch, _proc(tmp_path, ctx.paths.root, {1: (["/usr/bin/bash"], {}, None)}))
    out = _cli(ctx, monkeypatch, capsys)("status")
    assert out.count("launch settings: not checked (no agent process is visible from here (a sandbox?))") == 2
    assert _launch_alerts(ctx) == {}


def test_the_restored_case_still_warns_when_only_some_processes_have_xt_agent(tmp_path, ctx, monkeypatch, capsys):
    _team(ctx)
    # both restored: their processes are visible, neither has XT_AGENT
    _use(monkeypatch, _proc(tmp_path, ctx.paths.root, {
        1: (["/usr/bin/claude", "--resume"], {}, None), 2: (["/usr/bin/claude", "--resume"], {}, None)}))
    out = _cli(ctx, monkeypatch, capsys)("status")
    assert "WARNING: carol is running without" in out and "WARNING: dave is running without" in out
    assert set(_launch_alerts(ctx)) == {"launch:carol", "launch:dave"}


def test_the_namespace_marker_is_read_from_nspid(tmp_path):
    d = tmp_path / "self"
    d.mkdir(parents=True)
    (d / "status").write_text("Name:\tx\nNSpid:\t812\n")
    assert launch.isolated(str(tmp_path)) is False
    (d / "status").write_text("Name:\tx\nNSpid:\t812\t3\n")
    assert launch.isolated(str(tmp_path)) is True
    assert launch.isolated(str(tmp_path / "missing")) is False


def test_from_a_sandbox_the_supervisor_is_not_checked_unless_it_saved_live_state(ctx, monkeypatch, capsys):
    import json

    monkeypatch.setattr(launch, "isolated", lambda proc=None: True)
    run = _cli(ctx, monkeypatch, capsys)
    out = run("status")
    assert "the supervisor: not checked (this shell runs in a PID namespace" in out
    assert "supervisor isn't running" not in out
    (ctx.paths.state / "live.json").write_text(json.dumps({"ts": ctx.ledger.clock().isoformat(), "agents": {}}))
    out = run("status")
    assert "supervisor" not in out.split("team usage today")[1]  # it ticked seconds ago: running


def test_status_says_plainly_when_the_supervisor_is_not_running(ctx, monkeypatch, capsys):
    monkeypatch.setattr(launch, "isolated", lambda proc=None: False)
    run = _cli(ctx, monkeypatch, capsys)
    assert ("the supervisor isn't running: no messages are delivered, no alerts raised and nobody is "
            "woken until it runs. `xt up` starts it.") in run("status")
    (ctx.paths.state / "watch.pid").write_text(str(os.getpid()))
    assert "supervisor isn't running" not in run("status")


def test_up_warns_about_agents_running_without_the_settings(tmp_path, ctx, monkeypatch):
    _team(ctx)
    # the liaison `xt up` starts is xt's own, with XT_AGENT
    _use(monkeypatch, _restored(tmp_path, ctx, {106: (["/usr/bin/codex"], {"XT_AGENT": "liaison"}, None)}))
    out = up(ctx)
    assert any(line.startswith("WARNING: dave is running without xt's launch settings") for line in out)
    assert not any("carol is running without" in line for line in out)
    assert list(_launch_alerts(ctx)) == ["launch:dave"]
