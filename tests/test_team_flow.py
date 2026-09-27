import pytest

from xt import brief, goals
from xt.alerts import Alerts
from xt.context import Ctx
from xt.ledger import Ledger
from xt.paths import XtError
from xt.spawn import Approvals, decide, request_spawn, retire
from xt.team import Team
from xt.up import up
from xt.watch import Supervisor

from .conftest import add_member


def test_up_starts_supervisor_and_liaison_but_not_lead(ctx):
    lines = up(ctx)
    assert ctx.herdr.pane_runs and ctx.herdr.pane_runs[0][1].endswith("bin/xt watch")
    assert [s[0] for s in ctx.herdr.started] == ["liaison"]
    first = ctx.herdr.last_prompt("liaison")
    assert "You are **liaison**" in first and "PRECEDENCE" in first and "# xt protocol" in first
    assert any("starts when the first goal" in line for line in lines)


def test_lost_first_prompt_is_retried(ctx):
    ctx.herdr.stall["liaison"] = 1
    up(ctx)
    assert "You are **liaison**" in ctx.herdr.last_prompt("liaison")
    assert not any(k.startswith("noprompt:") for k in Alerts(ctx).active())


def test_first_prompt_that_never_lands_raises_an_alert(ctx):
    ctx.herdr.stall["liaison"] = 5
    ctx.herdr.status = lambda name: "idle"  # never seen working
    up(ctx)
    assert "noprompt:liaison" in Alerts(ctx).active()
    started = [m for m in ctx.ledger.messages() if m["type"] == "system" and "started liaison" in m["body"]]
    assert "NOT CONFIRMED" in started[-1]["body"]


def test_startup_dialog_is_answered_before_the_first_prompt(ctx):
    # codex's folder-trust dialog swallowed the liaison's first prompt in both real runs
    ctx.herdr.dialog_on_start = "  Folder access\n  Trust this folder? Codex can read, edit, and run files here"
    up(ctx)
    assert any(keys == ("enter",) for _, keys in ctx.herdr.keys)
    assert "You are **liaison**" in ctx.herdr.last_prompt("liaison")
    assert not Alerts(ctx).active()
    log = [m["body"] for m in ctx.ledger.messages() if m["type"] == "system"]
    assert any("answered codex's 'folder trust' dialog for liaison" in b for b in log)


def test_agent_blocked_at_startup_by_a_known_dialog_still_starts(ctx):
    # claude: herdr refuses with agent_not_ready while "Is this a project you created or one you
    # trust?" is up, with "No, exit" preselected, so xt must press down, then enter
    add_member(ctx, "carol")  # a claude agent
    ctx.herdr.block_on_start = "Quick safety check: Is this a project you created or one you trust?"
    request_spawn(ctx, "human", "carol", None, None, None, None)
    assert (ctx.herdr.live["carol"].pane_id, ("down", "enter")) in ctx.herdr.keys
    assert "You are **carol**" in ctx.herdr.last_prompt("carol")
    assert not ctx.herdr.closed and not Alerts(ctx).active()


def test_agent_blocked_by_an_unknown_dialog_is_closed_and_reported(ctx):
    add_member(ctx, "carol")
    ctx.herdr.block_on_start = "Some dialog xt has never seen"
    with pytest.raises(XtError, match="agent_not_ready"):
        request_spawn(ctx, "human", "carol", None, None, None, None)
    assert ctx.herdr.closed


def test_prompt_that_vanishes_without_a_known_dialog_is_caught(ctx):
    # herdr sees "working" (the harness starting up) but the prompt never reaches the transcript
    ctx.herdr.swallow["liaison"] = 1
    up(ctx)
    assert not Alerts(ctx).active()  # retried, and the second one landed
    assert sum(1 for n, _ in ctx.herdr.prompts if n == "liaison") == 1


def test_prompt_that_never_shows_up_raises_an_alert(ctx):
    ctx.herdr.swallow["liaison"] = 5
    up(ctx)
    assert "noprompt:liaison" in Alerts(ctx).active()


def test_goal_dispatch_starts_lead_lazily_with_goal_in_brief(ctx):
    up(ctx)
    ctx.herdr.live["liaison"].status = "idle"
    goals.new(ctx, "Forecast Team", "Build a forecast")
    with pytest.raises(XtError, match="only the liaison"):
        goals.dispatch(ctx, "lead", "forecast-team")
    out = goals.dispatch(ctx, "liaison", "forecast-team")
    assert "supervisor starts lead" in out and "lead" not in ctx.herdr.live
    Supervisor(ctx, out=lambda s: None).tick(now=0)  # the job runs outside the liaison's sandbox
    assert "lead" in ctx.herdr.live
    assert not Alerts(ctx).active()
    assert "Done: start lead" in ctx.herdr.last_prompt("liaison")
    assert (ctx.paths.goals / "forecast-team.md").exists()
    assert not (ctx.paths.drafts / "forecast-team.md").exists()
    first = ctx.herdr.last_prompt("lead")
    assert "goal → lead" in first and "Build a forecast" in first
    assert [i["type"] for i in ctx.ledger.open_items()] == ["goal"]


def test_spawn_needs_human_approval_by_default(ctx):
    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")
    out = request_spawn(ctx, "lead", "carol", "pi", None, "coder", None)
    assert "approval #" in out and "carol" not in ctx.herdr.live
    rid = int(next(iter(Approvals(ctx).pending())))
    decide(ctx, rid, approve=True)
    assert "carol" in ctx.herdr.live
    assert ctx.herdr.started[-1] == ("carol", "pi", ["-a"])
    assert ctx.team.agent("carol").reports_to == "lead"
    assert "approved" in ctx.herdr.last_prompt("lead")


def test_liaison_cannot_spawn_or_retire(ctx):
    (ctx.paths.roles / "researcher.md").write_text("# Role: researcher\n")
    with pytest.raises(XtError, match="liaison doesn't spawn"):
        request_spawn(ctx, "liaison", "researcher", "codex", None, "researcher", "lead")
    with pytest.raises(XtError, match="liaison doesn't retire"):
        retire(ctx, "liaison", "lead")


def test_spawn_refuses_missing_role(ctx):
    with pytest.raises(XtError, match="write the role brief"):
        request_spawn(ctx, "human", "carol", "claude", None, "nonexistent", "lead")


def test_retire_only_by_own_lead(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dave")
    ctx.herdr.add("carol")
    with pytest.raises(XtError, match="only lead"):
        retire(ctx, "dave", "carol")
    assert "retire job" in retire(ctx, "lead", "carol")
    assert "carol" in ctx.herdr.live
    ctx.herdr.add("lead")
    Supervisor(ctx, out=lambda s: None).tick(now=0)
    ctx.reload_team()
    assert "carol" not in ctx.herdr.live and not ctx.team.agent("carol").active


def test_agent_spawn_without_approval_goes_through_the_supervisor(ctx):
    ctx.team.doc["policy"]["spawn_approval"] = False
    ctx.team.save()
    ctx.reload_team()
    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")
    out = request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)
    assert "spawn job" in out and "carol" not in ctx.herdr.live
    Supervisor(ctx, out=lambda s: None).tick(now=0)
    assert "carol" in ctx.herdr.live
    assert "Done: spawn carol" in ctx.herdr.last_prompt("lead")


def test_brief_falls_back_to_the_supervisors_snapshot_when_herdr_is_unreachable(paths, clock):
    from xt.herdr import Herdr, LiveAgent

    paths.ensure_runtime()
    h = Herdr("test", snapshot=paths.state / "live.json")
    h.save_snapshot({"liaison": LiveAgent("liaison", "working", "w2:p1", "w2")}, "2026-09-26T17:41:00")

    def blocked(*a, **k):
        raise XtError("herdr failed (1): Operation not permitted")

    h._run = blocked
    assert h.agents()["liaison"].status == "working"
    c = Ctx(paths, Team.load(paths.team_toml), Ledger(paths, clock=clock), h)
    assert "liaison (liaison, codex, reports to human): working" in brief.build(c, "liaison")


def test_supervisor_alerts_on_crash_and_blocked(ctx, clock):
    add_member(ctx, "carol")
    request_spawn(ctx, "human", "carol", None, None, None, None)
    sup = Supervisor(ctx, out=lambda s: None)
    del ctx.herdr.live["carol"]  # crashed
    sup.tick(now=0)
    assert any(k == "missing:carol" for k in Alerts(ctx).active())
    ctx.herdr.add("carol", status="blocked")
    sup.tick(now=1)
    active = Alerts(ctx).active()
    assert "blocked:carol" in active and "missing:carol" not in active


def test_lead_missing_with_open_goal_alerts_once(ctx):
    ctx.ledger.append("liaison", "lead", "goal", "a goal")  # dispatched, but the lead never started
    sup = Supervisor(ctx, out=lambda s: None)
    for t in range(5):
        sup.tick(now=t)
    alerts = [m for m in ctx.ledger.messages() if m["type"] == "alert"]
    assert len(alerts) == 1 and "missing:lead" in Alerts(ctx).active()
    ctx.herdr.add("lead")
    sup.tick(now=10)
    assert "missing:lead" not in Alerts(ctx).active()


def test_heartbeat_nudges_idle_owner_then_alerts(ctx, clock):
    add_member(ctx, "carol")
    ctx.herdr.add("carol")
    ctx.ledger.append("lead", "carol", "task", "stuck task")
    sup = Supervisor(ctx, out=lambda s: None)
    for i in range(2):
        ctx.herdr.live["carol"].status = "idle"
        clock.advance(minutes=20)
        sup.tick(now=1000 * (i + 1))
        assert "Heartbeat" in ctx.herdr.last_prompt("carol")
    ctx.herdr.live["carol"].status = "idle"
    clock.advance(minutes=20)
    sup.tick(now=3000)
    assert any(k.startswith("silent:") for k in Alerts(ctx).active())


def test_heartbeat_skips_recent_reporter(ctx, clock):
    add_member(ctx, "carol")
    ctx.herdr.add("carol")
    t = ctx.ledger.append("lead", "carol", "task", "long task")
    ctx.ledger.append("carol", "lead", "report", "waiting on data", ref=t["id"])
    Supervisor(ctx, out=lambda s: None).tick(now=1000)
    assert ctx.herdr.prompts == []


def test_brief_for_member_shows_only_its_work(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dave")
    ctx.ledger.append("lead", "carol", "task", "carol's task")
    ctx.ledger.append("lead", "dave", "task", "dave's task")
    b = brief.build(ctx, "carol")
    assert "carol's task" in b and "dave's task" not in b
    assert "dave's task" in brief.build(ctx, "lead")


def test_approval_message_carries_its_real_id_and_the_liaison_sees_it(ctx):
    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")
    request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)
    request_spawn(ctx, "lead", "dora", "claude", None, "coder", None)
    ids = sorted(Approvals(ctx).pending(), key=int)
    msgs = {str(m["id"]): m for m in ctx.ledger.messages() if m["type"] == "approval"}
    for rid in ids:
        assert f"xt approve {rid}" in msgs[rid]["body"] and "<id>" not in msgs[rid]["body"]
    b = brief.build(ctx, "liaison")
    assert "Waiting on the human (2 approvals" in b and f"xt approve {' '.join(ids)}" in b
    assert "Waiting on the human" not in brief.build(ctx, "lead")


def test_approve_several_ids_at_once(ctx, monkeypatch, capsys):
    import io
    import sys

    from xt import cli

    class Tty(io.StringIO):
        def isatty(self):
            return True

    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")
    request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)
    request_spawn(ctx, "lead", "dora", "claude", None, "coder", None)
    ids = [int(i) for i in Approvals(ctx).pending()]
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(sys, "stdin", Tty())
    cli.cmd_approve(cli.build_parser().parse_args(["approve", *map(str, ids)]), True)
    assert {"carol", "dora"} <= set(ctx.herdr.live) and not Approvals(ctx).pending()


def test_down_stops_everyone_cleanly_and_up_raises_no_false_alerts(ctx, monkeypatch):
    from xt import up as up_mod
    from xt.alerts import Alerts
    from xt.up import down

    add_member(ctx, "carol")
    up(ctx)  # supervisor pane + liaison
    request_spawn(ctx, "human", "carol", None, None, None, None)
    assert {"liaison", "carol"} <= set(ctx.herdr.live)
    monkeypatch.setattr(up_mod, "watch_pid", lambda c: None)  # no real supervisor process in tests
    out = down(ctx)
    assert ctx.herdr.live == {}
    assert any("closed the supervisor's workspace" in line for line in out)
    Supervisor(ctx, out=lambda s: None).tick(now=0)  # what the next supervisor sees
    assert not any(k.startswith("missing:") for k in Alerts(ctx).active())


def test_tui_X_stops_every_running_agent(ctx):
    import asyncio

    from xt.tui.app import Confirm, LiveActions, XtTui
    from xt.tui.model import build

    add_member(ctx, "carol")
    for a in ("liaison", "carol"):
        ctx.herdr.add(a)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("2", "X")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert ctx.herdr.live == {}

    asyncio.run(run())


def test_scheduled_wakeups(ctx, monkeypatch):
    import io
    import sys

    from xt import cli
    from xt.paths import XtError as E

    add_member(ctx, "scout")
    ctx.herdr.add("scout")
    ctx.herdr.add("lead")
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))

    class NoTty(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", NoTty())
    p = cli.build_parser()
    with pytest.raises(E, match="only lead"):
        cli.cmd_schedule(p.parse_args(["schedule", "scout", "30m", "--as", "liaison"]))
    with pytest.raises(E, match="isn't like"):
        cli.cmd_schedule(p.parse_args(["schedule", "scout", "soon", "--as", "lead"]))
    with pytest.raises(E, match="shortest schedule an agent may request is 15m"):
        cli.cmd_schedule(p.parse_args(["schedule", "scout", "5m", "--as", "lead"]))
    cli.cmd_schedule(p.parse_args(["schedule", "scout", "30m", "--message", "check the feeds", "--as", "lead"]))
    ctx.reload_team()
    assert ctx.team.agent("scout").wake_every is None  # waits for the human
    (rid, req), = Approvals(ctx).pending().items()
    assert req["kind"] == "schedule"
    appr = [m for m in ctx.ledger.messages() if m["type"] == "approval"][-1]
    assert "wake scout every 30m" in appr["body"] and f"xt approve {rid}" in appr["body"]
    assert "wake scout every 30m" in brief.build(ctx, "liaison")
    decide(ctx, int(rid), approve=True)
    ctx.reload_team()
    assert ctx.team.agent("scout").wake_every == "30m"
    assert "now woken every 30m" in ctx.herdr.last_prompt("lead")
    assert "woken every 30m" in brief.build(ctx, "lead")

    sup = Supervisor(ctx, out=lambda s: None)
    sup.tick(now=10_000)  # first sight: the clock starts, nobody is woken
    assert not any("check the feeds" in t for _, t in ctx.herdr.prompts)
    sup.tick(now=10_000 + 29 * 60)  # not due yet
    assert not any("check the feeds" in t for _, t in ctx.herdr.prompts)
    ctx.herdr.live["scout"].status = "working"
    sup.tick(now=10_000 + 31 * 60)  # due, but busy: wait
    assert not any("check the feeds" in t for _, t in ctx.herdr.prompts)
    ctx.herdr.live["scout"].status = "idle"
    sup.tick(now=10_000 + 32 * 60)  # due and idle: wake
    wake = ctx.herdr.last_prompt("scout")
    assert "wake from:xt" in wake and "check the feeds" in wake
    ctx.herdr.live["scout"].status = "idle"
    sup.tick(now=10_000 + 40 * 60)  # just woken: not again until 30 minutes later
    assert sum("check the feeds" in t for _, t in ctx.herdr.prompts) == 1

    cli.cmd_schedule(p.parse_args(["schedule", "scout", "off", "--as", "lead"]))
    ctx.reload_team()
    assert ctx.team.agent("scout").wake_every is None
    ctx.herdr.live["scout"].status = "idle"
    sup.tick(now=10_000 + 200 * 60)
    assert sum("check the feeds" in t for _, t in ctx.herdr.prompts) == 1
