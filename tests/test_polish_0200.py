"""v0.20.0, a polish release from a fresh-eyes review of 0.19.0 (cards #174-#180)."""

import json
import os
import sys

import pytest

from xt import cli, turns, usage
from xt.adapters import load_adapters
from xt.alerts import Alerts
from xt.spawn import request_spawn
from xt.watch import Supervisor

from .conftest import FakeHerdr
from .test_pi_0190 import DAMAGE, SlowPi, _no_wait, _Tty


@pytest.fixture
def pi_team(ctx, fake_home, monkeypatch):
    ctx.herdr = SlowPi(fake_home)
    (ctx.paths.roles / "worker.md").write_text("# Role: worker\n")
    ctx.team.upsert_agent("dave", "worker", "pi", None, "lead")
    ctx.team.save()
    ctx.reload_team()
    monkeypatch.setattr(usage, "_pi_windows", lambda ctx: {})  # never run a real `pi --list-models`
    return ctx


def _log(home, name="dave"):
    return home / ".pi/agent/sessions/--team--" / f"{name}.jsonl"


def _turn(home, tokens=1200, name="dave"):
    """One assistant message with usage, as pi writes it for a non-Anthropic provider."""
    rec = {"type": "message", "message": {"role": "assistant", "provider": "openrouter", "model": "moonshotai/kimi-k2.6",
                                          "usage": {"input": tokens - 200, "output": 200, "totalTokens": tokens},
                                          "timestamp": 1_790_000_000_000}}
    with open(_log(home, name), "a") as fh:
        fh.write(json.dumps(rec) + "\n")


def _status(ctx, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    return capsys.readouterr().out


# --- #174: a pi agent's context is readable, or xt says why not -----------------------------------


def test_174_a_log_whose_opening_was_lost_is_still_read(pi_team, fake_home):
    ctx = pi_team
    _no_wait(ctx)
    ctx.herdr.lost = DAMAGE  # the guard line and the opening are gone; the later parts are there
    request_spawn(ctx, "human", "dave", None, None, None, None)
    _turn(fake_home)
    r = usage.reading(ctx, "dave")
    assert r.known and r.used == 1200 and not r.missing
    adapter = load_adapters(ctx.paths)["pi"]
    assert [p for p, aux in turns.agent_logs(ctx, adapter, "dave", 0)] == [str(_log(fake_home))]


def test_174_a_log_of_another_agent_or_team_is_not_taken(pi_team, fake_home):
    ctx = pi_team
    d = _log(fake_home).parent
    d.mkdir(parents=True)
    other = "You are **erin**, an agent in the xt team \"t\". Always pass `--as erin` when you use xt."
    (d / "erin.jsonl").write_text(json.dumps({"message": {"role": "user", "content": other}}) + "\n")
    assert usage.find_session(ctx, load_adapters(ctx.paths)["pi"], "dave", None) is None


def test_174_no_logs_at_all_is_said(pi_team, monkeypatch):
    ctx = pi_team
    monkeypatch.setattr(SlowPi, "prompt", FakeHerdr.prompt)  # pi writes no log
    request_spawn(ctx, "human", "dave", None, None, None, None)
    r = usage.reading(ctx, "dave")
    assert r.missing and r.reason == "no pi session logs at ~/.pi/agent/sessions/*/*.jsonl, or xt can't read there"


def test_174_only_older_logs_is_said(pi_team, fake_home):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    started = usage.last_starts(ctx)["dave"]
    os.utime(_log(fake_home), (started - 3600, started - 3600))  # written before this start
    r = usage.reading(ctx, "dave")
    assert r.missing and r.reason.startswith("no pi session log written since dave started (the newest is from ")


def test_174_logs_without_the_first_prompt_are_counted(pi_team, fake_home):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    _log(fake_home).write_text(json.dumps({"type": "session"}) + "\n")  # pi wrote something else
    (_log(fake_home).parent / "x.jsonl").write_text("{}\n")
    r = usage.reading(ctx, "dave")
    assert r.missing and r.reason == "2 pi session logs written since dave started, none with its first prompt"


def test_174_the_status_line_says_which_of_context_and_usage_can_be_read():
    missing = usage.Reading(missing=True, reason="no pi session log written since dave started")
    assert usage.unreadable_line("dave", missing, True, 30) == (
        "dave: today's usage recorded; context can't be read (no pi session log written since dave started)")
    assert usage.unreadable_line("dave", missing, False, 30) == (
        "dave: nothing can be read: no context and no usage recorded today (no pi session log written since dave started)")
    no_usage_yet = usage.Reading(reason="no usage recorded yet")
    assert usage.unreadable_line("dave", no_usage_yet, False, 60) is None  # its first turn: expected
    assert usage.unreadable_line("dave", no_usage_yet, False, usage.GRACE).startswith("dave: nothing can be read")
    assert usage.unreadable_line("dave", usage.Reading(used=5, window=10), False, 60) is None


def test_174_status_shows_the_context_once_it_is_readable(pi_team, fake_home, monkeypatch, capsys):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    _turn(fake_home)
    out = _status(ctx, monkeypatch, capsys)
    assert "context:1k/?" in out and "can't be read" not in out


def _supervise(ctx, after):
    sup = Supervisor(ctx, out=lambda s: None)
    sup.check_context(ctx.herdr.agents(), usage.last_starts(ctx)["dave"] + after)
    return [m for m in ctx.ledger.messages() if m["type"] == "alert"]


def test_174_one_alert_after_the_first_turns_cleared_when_readable(pi_team, fake_home, monkeypatch):
    ctx = pi_team
    monkeypatch.setattr(SlowPi, "prompt", FakeHerdr.prompt)  # no log
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert _supervise(ctx, usage.GRACE - 1) == []  # its first turns: expected
    alerts = _supervise(ctx, usage.GRACE)
    assert len(alerts) == 1 and "context:dave" in Alerts(ctx).active()
    text = alerts[0]["body"]
    assert text.startswith("dave's context still can't be read 10 minutes after its start (no pi session logs at")
    assert "no usage is recorded either" in text and "look at its pane" in text and "How full is an agent's context?" in text
    assert len(_supervise(ctx, usage.GRACE + 60)) == 1  # not repeated
    Alerts(ctx).resolve("context:dave")  # the human cleared it
    assert len(_supervise(ctx, usage.GRACE + 120)) == 1  # still once for this start
    _log(fake_home).parent.mkdir(parents=True)  # the log appears
    first = {"message": {"role": "user", "content": "You are **dave**, an agent in the xt team \"t\"."}}
    _log(fake_home).write_text(json.dumps(first) + "\n")
    _turn(fake_home)
    Alerts(ctx).raise_("context:dave", "still open")
    _supervise(ctx, usage.GRACE + 180)
    assert "context:dave" not in Alerts(ctx).active()  # readable: cleared


def test_174_a_new_start_is_checked_anew_and_a_stopped_agent_clears(pi_team, monkeypatch):
    from xt.spawn import stop

    ctx = pi_team
    monkeypatch.setattr(SlowPi, "prompt", FakeHerdr.prompt)
    request_spawn(ctx, "human", "dave", None, None, None, None)
    _supervise(ctx, usage.GRACE)
    stop(ctx, "dave")
    Supervisor(ctx, out=lambda s: None).check_context(ctx.herdr.agents(), 0)
    assert "context:dave" not in Alerts(ctx).active()
    assert json.loads((ctx.paths.state / "context_alerts.json").read_text()) == {}
    ctx.ledger.clock.advance(hours=1)
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert len(_supervise(ctx, usage.GRACE)) == 2


def test_174_harnesses_without_a_log_format_raise_nothing(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)  # codex: logs found or not, it has a format
    toml = ctx.paths.harnesses / "codex.toml"
    toml.write_text(toml.read_text().replace('session_format = "codex"', 'session_format = ""'))
    sup = Supervisor(ctx, out=lambda s: None)
    sup.check_context(ctx.herdr.agents(), usage.last_starts(ctx)["liaison"] + usage.GRACE)
    assert not [k for k in Alerts(ctx).active() if k.startswith("context:")]


# --- #177: plainer wording -------------------------------------------------------------------------


def test_177_the_demo_inbox_shows_the_real_group_labels(ctx, fake_home, clock):
    from xt.tui.app import demo_snapshot
    from xt.tui.model import INBOX_HEADINGS, build

    from .test_tui_0170 import _acceptance

    _acceptance(ctx, fake_home, clock)  # all three groups in a real team's Inbox
    real = [r.text.plain for r in build(ctx).panels["Inbox"] if r.kind == "heading"]
    demo = [r.text.plain for r in demo_snapshot().panels["Inbox"] if r.kind == "heading"]
    assert demo == real == list(INBOX_HEADINGS) == ["NEEDS YOU", "NOTIFICATIONS", "FRICTION"]


def test_177_a_starting_agent_is_not_recorded_yet_and_an_old_one_is_unknown(ctx):
    from xt import versions

    now = ctx.ledger.clock()
    versions.mark_starting(ctx, "lead", now)
    v = versions.current(ctx, live_names={"lead", "liaison"}, supervisor_running=False, now=now)
    assert v.detail().splitlines()[1:] == ["lead: not recorded yet (first turn running)",
                                          "liaison: unknown (started before xt recorded versions)"]
    assert "\n  version not recorded yet (first turn running): lead" in v.line()
    assert "\n  version unknown (started before xt recorded versions): liaison" in v.line()
    later = now + versions.dt.timedelta(seconds=versions.STARTING_FOR)  # a start that never finished
    assert "lead: unknown" in versions.current(ctx, live_names={"lead"}, supervisor_running=False, now=later).detail()
    versions.record_agent_start(ctx, "lead", now)
    assert "lead" not in versions.load(ctx).get("starting", {})
    assert "not recorded" not in versions.current(ctx, live_names={"lead"}, supervisor_running=False, now=now).line()


def test_177_the_start_is_marked_before_the_first_prompt_is_built(ctx, monkeypatch):
    from xt import spawn, versions

    seen = []
    real = spawn.first_prompt

    def first_prompt(ctx, name):
        seen.append(dict(versions.load(ctx).get("starting", {})))
        return real(ctx, name)

    monkeypatch.setattr(spawn, "first_prompt", first_prompt)
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert "liaison" in seen[0]  # its first brief sees the start under way
    assert versions.load(ctx)["agents"]["liaison"]["version"] and "liaison" not in versions.load(ctx)["starting"]


def _xt_log(ctx, monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_log(cli.build_parser().parse_args(["log", *argv]))
    return capsys.readouterr().out


def _help(command):
    sub = next(a for a in cli.build_parser()._actions if getattr(a, "choices", None))
    return " ".join(sub.choices[command].format_help().split())


def test_177_log_id_of_a_missing_message_says_so_and_fails(ctx, monkeypatch, capsys):
    from xt.paths import XtError

    m = ctx.ledger.append("lead", "liaison", "report", "hello")
    with pytest.raises(XtError, match=r"^no such message: #999999$"):
        _xt_log(ctx, monkeypatch, capsys, "--id", "999999")
    assert _xt_log(ctx, monkeypatch, capsys, "--id", str(m["id"]), "--type", "task") == "(no messages)\n"
    assert f"#{m['id']} " in _xt_log(ctx, monkeypatch, capsys, "--id", str(m["id"]))


def test_177_tui_help_describes_the_demo_plainly():
    text = _help("tui")
    assert "made-up example data" in text and "spike" not in text


def test_177_approve_of_a_missing_id_names_it_once(ctx, monkeypatch, capsys):
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_approve(cli.build_parser().parse_args(["approve", "12345"]))
    assert capsys.readouterr().out == "no pending approval #12345\n"


# --- #178: xt log --events, and xt init without a terminal ---------------------------------------------


def test_178_log_events_prints_the_events_and_watch_still_works(ctx, monkeypatch, capsys):
    (ctx.paths.state / "watch.log").write_text("2026-09-26 12:00:00 delivered #1 to lead\n")
    assert _xt_log(ctx, monkeypatch, capsys, "--events") == _xt_log(ctx, monkeypatch, capsys, "--watch")
    assert "delivered #1 to lead" in _xt_log(ctx, monkeypatch, capsys, "--events")
    text = _help("log")
    assert "--events, --watch" in text and "printed once (it doesn't follow; --watch is the old name)" in text


def _fresh_clone(where):
    import shutil

    from xt.paths import Paths

    from .conftest import REPO

    where.mkdir(parents=True)
    for name in ("protocol.md", "roles", "harnesses"):
        src = REPO / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, where / name)
    return Paths(where)


@pytest.fixture
def no_terminal(monkeypatch):
    import io

    from xt import herdr, init

    monkeypatch.setattr(init, "prerequisites", lambda paths: (["git: ok"], []))
    monkeypatch.setattr(herdr, "sessions", lambda: {})
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))  # a pipe, not a terminal
    return init


NO_TERMINAL = ("no terminal: used the defaults for the questions not given as options "
               "(`--yes` does the same on purpose; `xt init --help` lists the options)")


def test_178_init_without_a_terminal_says_it_used_the_defaults(tmp_path, no_terminal):
    out = no_terminal.init(_fresh_clone(tmp_path / "piped"), None, None, None, None, None, yes=False, commit=False)
    assert out.count(NO_TERMINAL) == 1
    out = no_terminal.init(_fresh_clone(tmp_path / "yes"), None, None, None, None, None, yes=True, commit=False)
    assert NO_TERMINAL not in out  # asked for on purpose: nothing to say
    every = no_terminal.init(_fresh_clone(tmp_path / "all"), "t", "s", "codex", "codex", True, yes=False, commit=False)
    assert NO_TERMINAL not in every  # every question given as an option: nothing was defaulted
    assert "init" in _help("init") and "without a terminal xt uses them too, and says so" in _help("init")


def test_178_init_without_a_terminal_writes_what_yes_writes(tmp_path, no_terminal):
    piped, yes = _fresh_clone(tmp_path / "piped"), _fresh_clone(tmp_path / "yes")
    no_terminal.init(piped, "t", None, None, None, None, yes=False, commit=False)
    no_terminal.init(yes, "t", None, None, None, None, yes=True, commit=False)
    assert piped.team_toml.read_text() == yes.team_toml.read_text()


# --- #176: TUI help, detail cue and Flow key names (Pilot at four sizes) ------------------------------

SIZES = [(120, 40), (100, 30), (80, 24), (60, 20)]


def _lines(widget):
    from textual.geometry import Region

    return [s.text for s in widget.render_lines(Region(0, 0, widget.size.width, widget.size.height))]


@pytest.mark.parametrize("size", SIZES)
def test_176_every_keys_line_is_whole_and_the_close_hint_shows(size):
    from xt.tui.app import Help, XtTui, demo_snapshot

    from .test_tui_0170 import _run

    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=size) as pilot:
            await pilot.press("h")
            await pilot.pause()
            box = app.screen.query_one("#help")
            assert 0 <= box.region.x and box.region.right <= size[0] and box.region.bottom <= size[1]
            assert box.border_subtitle == Help.HINT and box.region.width - 4 >= len(Help.HINT)
            body = app.screen.query_one("#help-body")
            assert body.size.width <= box.content_region.width
            lines = _lines(body)
            assert all(len(line.rstrip()) <= body.size.width for line in lines)
            text = " ".join(" ".join(lines).split())
            for key, what in Help.KEYS:  # each entry whole, its words in order across its wrapped lines
                assert " ".join(f"{key} {what}".split()) in text, (size, key)
            for _ in range(len(lines)):  # j reaches the last line
                await pilot.press("j")
            await pilot.pause()
            assert box.scroll_y == box.max_scroll_y  # taller than 80% of every size here: before, cut off
            await pilot.press("escape")
            await pilot.pause()
            assert not app.screen.query("#help")

    _run(run())


@pytest.mark.parametrize("size", SIZES)
def test_176_hidden_detail_lines_get_a_cue_and_the_key_line_lists_j_k(ctx, fake_home, clock, size):
    from xt.tui.app import DETAIL, GLOBAL_KEYS, TEAM

    from .test_tui_0170 import _acceptance, _app, _run

    _acceptance(ctx, fake_home, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(TEAM))
            for _ in range(12):
                await pilot.press("k")  # up to the Team header: versions and today's usage, long
            await pilot.press(str(DETAIL))
            await pilot.pause()
            await pilot.pause()
            pane = app.query_one("#detail")
            hints = str(app.query_one("#hints").render()).strip()
            assert hints.startswith("j/k scroll · " + " · ".join(f"{k} {w}" for k, w in GLOBAL_KEYS)[:20]), hints
            below = round(pane.max_scroll_y - pane.scroll_y)
            if below:
                assert pane.border_subtitle == f"▾ {below} more (j/k)"
                for _ in range(below):
                    await pilot.press("j")
                await pilot.pause()
                assert pane.scroll_y == pane.max_scroll_y
                assert pane.border_subtitle == f"▴ {round(pane.scroll_y)} above (k)"
            else:
                assert pane.border_subtitle == ""
            return below

    hidden = _run(run())
    assert hidden or size == (120, 40), size  # the smaller sizes hide lines of the Team header's detail


def test_176_flow_names_f_focus_and_slash_filter(ctx, fake_home, clock):
    from xt.tui.app import FLOW, GLOBAL_KEYS, PANE_KEYS, FlowPick, Help

    from .test_tui_0170 import _acceptance, _app, _run

    _acceptance(ctx, fake_home, clock)
    assert ("f", "focus") in PANE_KEYS[FLOW] and ("/", "filter") in GLOBAL_KEYS
    keys = [k for k, _ in Help.KEYS]
    flow = dict(Help.KEYS[keys.index(f"Flow ({FLOW})"):keys.index("Team (0)")])  # Flow's own section
    assert flow["f"].startswith("focus: only one agent's messages or one goal's thread")
    assert flow["/"] == "filter: only messages with this text"
    assert dict(Help.KEYS[:keys.index("Inbox (1)")])["/"].startswith("filter the focused pane")

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            line = str(app.query_one("#hints").render())
            assert line.startswith("t system · f focus · g/G newest/oldest") and "/ filter" in line
            await pilot.press("f")
            await pilot.pause()
            assert isinstance(app.screen, FlowPick) and app.screen.query_one(".pick").border_title == "Focus Flow on"

    _run(run())
