"""xt 0.10.0 batch: #89 desktop tools, #94 anchored daily schedules, and the rest of the batch."""

import datetime as dt
import io
import sys
import time

import pytest

from xt import cli
from xt.adapters import load_adapters
from xt.paths import XtError
from xt.spawn import Approvals, decide, request_spawn
from xt.team import Agent, check_at, next_due
from xt.watch import Supervisor

from .conftest import add_member


@pytest.fixture
def prague(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Prague")
    time.tzset()
    yield
    monkeypatch.delenv("TZ")
    time.tzset()


def local(*a):
    return time.mktime(dt.datetime(*a).timetuple())


# --- #89 desktop tools -------------------------------------------------------------------------


def test_codex_agents_start_without_the_computer_use_server(ctx):
    ad = load_adapters(ctx.paths)
    args = ad["codex"].start_args(None)
    assert "mcp_servers.cua_repl.enabled=false" in args and "features.computer_use=false" in args
    assert all('"' not in x and "{" not in x for x in args)  # typed into a shell by Herdr
    assert ad["codex"].desktop_tools == "blocked" and ad["pi"].desktop_tools == "none"
    assert ad["claude"].start_args(None)[:2] == ["--disallowedTools", "mcp__claude-in-chrome"]


def test_a_start_says_when_desktop_tools_arent_fully_blocked(ctx):
    add_member(ctx, "carol")  # claude: partial
    request_spawn(ctx, "human", "carol", None, None, None, None)
    request_spawn(ctx, "human", "liaison", None, None, None, None)  # codex: blocked
    notes = [m["body"] for m in ctx.ledger.messages() if "desktop and browser tools" in m["body"]]
    assert len(notes) == 1 and notes[0].startswith("carol:") and "not fully blocked" in notes[0]


# --- #94 daily schedules -----------------------------------------------------------------------


def pm(**kw):
    return Agent("pm", "pm", "codex", None, "lead", "active", wake_every="1d", **kw)


@pytest.mark.parametrize("approved,expected", [
    ((2026, 9, 27, 21, 50), (2026, 9, 28, 9, 0)),   # approved in the evening: next morning
    ((2026, 9, 28, 7, 0), (2026, 9, 28, 9, 0)),     # before the window: the same morning
    ((2026, 9, 28, 10, 21), (2026, 9, 29, 9, 0)),   # inside the window, after its start: tomorrow
])
def test_daily_schedules_wake_at_the_window_start(prague, approved, expected):
    assert next_due(pm(wake_between="09:00-17:00"), local(*approved)) == local(*expected)


def test_at_sets_the_time_and_is_checked(prague):
    assert next_due(pm(wake_between="09:00-17:00", wake_at="10:30"), local(2026, 9, 28, 9, 0)) == \
        local(2026, 9, 28, 10, 30)
    assert check_at("9:05", "1d", None) == "09:05"
    with pytest.raises(XtError, match="outside the schedule's window"):
        check_at("18:00", "1d", "09:00-17:00")
    with pytest.raises(XtError, match="daily or longer"):
        check_at("09:00", "60m", None)
    with pytest.raises(XtError, match="isn't a time"):
        check_at("9am", "1d", None)


def test_daily_time_holds_across_a_daylight_saving_change(prague):
    # Prague leaves summer time on 25 October 2026: that day is 25 hours long
    due = next_due(pm(wake_between="09:00-17:00"), local(2026, 10, 24, 9, 0))
    assert dt.datetime.fromtimestamp(due) == dt.datetime(2026, 10, 25, 9, 0)
    assert due - local(2026, 10, 24, 9, 0) == 25 * 3600


def test_sub_daily_schedules_keep_their_interval():
    a = Agent("scout", "scout", "codex", None, "lead", "active", wake_every="60m")
    assert next_due(a, 1000.0) == 1000.0 + 3600


def test_supervisor_wakes_a_daily_agent_once_a_day_at_the_window_start(ctx, prague):
    add_member(ctx, "pm")
    ctx.herdr.add("pm")
    ctx.team.set_schedule("pm", "1d", "daily duty", "09:00-17:00")
    ctx.team.save()
    ctx.reload_team()
    sup = Supervisor(ctx, out=lambda s: None)
    wakes = lambda: sum("daily duty" in t for _, t in ctx.herdr.prompts)
    sup.wake_scheduled(ctx.herdr.agents(), local(2026, 9, 27, 21, 50))  # approved in the evening
    for t in [(2026, 9, 27, 23, 0), (2026, 9, 28, 8, 59)]:
        sup.wake_scheduled(ctx.herdr.agents(), local(*t))
    assert wakes() == 0
    sup.wake_scheduled(ctx.herdr.agents(), local(2026, 9, 28, 9, 0))
    assert wakes() == 1
    ctx.herdr.live["pm"].status = "idle"
    sup.wake_scheduled(ctx.herdr.agents(), local(2026, 9, 28, 16, 0))  # not twice a day
    ctx.herdr.live["pm"].status = "working"  # busy at 09:00 the next day…
    sup.wake_scheduled(ctx.herdr.agents(), local(2026, 9, 29, 9, 0))
    ctx.herdr.live["pm"].status = "idle"  # …woken once it's free, still inside the window
    sup.wake_scheduled(ctx.herdr.agents(), local(2026, 9, 29, 11, 0))
    sup.wake_scheduled(ctx.herdr.agents(), local(2026, 9, 29, 12, 0))
    assert wakes() == 2


def test_schedule_with_at_goes_through_approval_and_shows_the_next_wake(ctx, monkeypatch, capsys, prague):
    add_member(ctx, "scout")
    ctx.herdr.add("lead")
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))

    class NoTty(io.StringIO):
        def isatty(self):
            return False

    monkeypatch.setattr(sys, "stdin", NoTty())
    p = cli.build_parser()
    with pytest.raises(XtError, match="outside"):
        cli.cmd_schedule(p.parse_args(["schedule", "scout", "1d", "--between", "09:00-17:00", "--at", "20:00",
                                       "--as", "lead"]))
    cli.cmd_schedule(p.parse_args(["schedule", "scout", "1d", "--between", "09:00-17:00", "--at", "10:30",
                                   "--as", "lead"]))
    (rid, req), = Approvals(ctx).pending().items()
    assert req["at"] == "10:30"
    appr = [m for m in ctx.ledger.messages() if m["type"] == "approval"][-1]
    assert "between 09:00-17:00 at 10:30" in appr["body"]
    decide(ctx, int(rid), approve=True)
    ctx.reload_team()
    assert ctx.team.agent("scout").wake_at == "10:30"
    Supervisor(ctx, out=lambda s: None).wake_scheduled(ctx.herdr.agents(), time.time())  # clock starts

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    capsys.readouterr()
    cli.cmd_status(p.parse_args(["status"]))
    assert "next wake" in capsys.readouterr().out


# --- #91 read-backs, #93 corrections ------------------------------------------------------------


def test_a_goal_is_dispatched_once_even_if_the_answer_comes_twice(ctx):
    from xt import goals

    goals.new(ctx, "weekly-digest", "Weekly digest")
    goals.dispatch(ctx, "liaison", "weekly-digest")
    with pytest.raises(XtError, match="already dispatched"):
        goals.dispatch(ctx, "liaison", "weekly-digest")
    assert sum(1 for m in ctx.ledger.messages() if m["type"] == "goal") == 1


def test_roles_carry_the_readback_and_correction_rules(paths):
    liaison = (paths.roles / "liaison.md").read_text()
    lead = (paths.roles / "lead.md").read_text()
    assert "as an xt question" in liaison and "dispatch once" in liaison
    assert "Correction from the human:" in liaison and "Correction from the human:" in lead
    assert "members/lead/lessons.md" in lead


# --- #95 restore after down ----------------------------------------------------------------------


def test_restart_all_after_down_restores_the_team_that_was_running(ctx, monkeypatch):
    from xt import up as up_mod
    from xt.spawn import stop
    from xt.up import down, restart

    monkeypatch.setattr(up_mod, "watch_pid", lambda c: None)
    add_member(ctx, "carol")
    add_member(ctx, "dora")
    for n in ("liaison", "lead", "carol", "dora"):
        request_spawn(ctx, "human", n, None, None, None, None)
    stop(ctx, "dora")  # stopped on purpose before the down: stays stopped
    down(ctx)
    assert ctx.herdr.live == {}
    out = restart(ctx, [], everyone=True)
    assert {"liaison", "lead", "carol"} <= set(ctx.herdr.live) and "dora" not in ctx.herdr.live
    assert any(line.startswith("restored: ") and "carol" in line and "before xt down" in line for line in out)
    down(ctx, keep_supervisor=True)
    (ctx.paths.state / "predown.json").unlink()
    out = restart(ctx, [], everyone=True)  # nothing recorded: say so
    assert any("restored: nobody" in line for line in out)


# --- #96 stopped agents, #97 Status pane ---------------------------------------------------------


def test_a_stopped_agent_shows_no_current_context(ctx, fake_home):
    from xt.spawn import stop
    from xt.tui.model import build

    from .test_context_usage import codex_session

    request_spawn(ctx, "human", "liaison", None, None, None, None)
    codex_session(fake_home, ctx, "liaison", 131000)
    stop(ctx, "liaison")
    row = next(r for r in build(ctx).panels["Team"] if r.data["name"] == "liaison")
    assert "—" in row.text.plain and "131k" not in row.text.plain
    assert "last session: context ~131k" in row.detail().plain


def test_status_pane_shows_only_what_matters(ctx):
    from xt.dispatch import send
    from xt.tui.model import build

    ctx.herdr.add("liaison")
    snap = build(ctx)
    assert "nothing waiting for you" in snap.header.plain and " 0 " not in snap.header.plain
    send(ctx, "liaison", "human", "ask", "Which story?")
    snap = build(ctx)
    line = snap.header  # the Team pane's header since v0.16.0 (card #128)
    assert "⚑ 1 needs you" in line.plain and "nothing waiting" not in line.plain
    assert any(span.style == "bold yellow" for span in line.spans)  # it stands out
    assert snap.spend == "today: no usage recorded yet"


def test_long_action_results_stay_on_one_line(ctx):
    """Since v0.16.0 (card #128) the result is a one-line toast: a long one is cut, not wrapped."""
    import asyncio

    from xt.tui.app import LiveActions, Toast, XtTui
    from xt.tui.model import build

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(100, 40)) as pilot:
            long = "started lead in workspace w8; " * 6 + "END"
            app.set_status(long)
            await pilot.pause()
            toast = app.query_one(Toast)
            assert toast.outer_size.height == 1 and str(toast.render()).startswith("started lead")
            assert app.status == long

    asyncio.run(run())
