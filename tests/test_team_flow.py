import pytest

from xt import brief, goals
from xt.alerts import Alerts
from xt.paths import XtError
from xt.spawn import Approvals, decide, request_spawn, retire
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


def test_goal_dispatch_starts_lead_lazily_with_goal_in_brief(ctx):
    up(ctx)
    ctx.herdr.live["liaison"].status = "idle"
    goals.new(ctx, "Forecast Team", "Build a forecast")
    with pytest.raises(XtError, match="only the liaison"):
        goals.dispatch(ctx, "lead", "forecast-team")
    out = goals.dispatch(ctx, "liaison", "forecast-team")
    assert "started lead" in out
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


def test_spawn_refuses_missing_role(ctx):
    with pytest.raises(XtError, match="write the role brief"):
        request_spawn(ctx, "human", "carol", "claude", None, "nonexistent", "lead")


def test_retire_only_by_own_lead(ctx):
    add_member(ctx, "carol")
    ctx.herdr.add("carol")
    with pytest.raises(XtError, match="only lead"):
        retire(ctx, "liaison", "carol")
    retire(ctx, "lead", "carol")
    assert "carol" not in ctx.herdr.live and not ctx.team.agent("carol").active


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
