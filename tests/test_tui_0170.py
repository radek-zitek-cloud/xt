"""v0.17.0, card #162: TUI layout and consistency.

Three bands (Team and the Inbox side by side, Work or Flow in one pane, Detail at the bottom), pane
titles `[n] - Title - info`, a one-column Team pane with a `+N more` line, NOTIFICATIONS, a key line
per pane and newest on top everywhere. These checks replace #130's check 14 (the old final layout and
the Inbox-height rule), #128's Team cap and #130's "newest at the bottom".
"""

import asyncio
import json

import pytest

from xt.alerts import Alerts
from xt.dispatch import Queue, send
from xt.goaldone import seen_upto
from xt.tui import teampane
from xt.tui.app import (DETAIL, FLOW, GLOBAL_KEYS, INBOX, PANE_KEYS, TEAM, WORK, Help, LiveActions, XtTui,
                        band_heights, demo_snapshot)
from xt.tui.model import build

from .test_batch_0160 import _team, _title

SIZES = [(160, 40), (100, 30)]


def _run(coro):
    return asyncio.run(coro)


def _app(ctx) -> XtTui:
    return XtTui(lambda: build(ctx), LiveActions(ctx))


def _fresh_claude(ctx):
    """Both Claude windows read a minute ago (the `_team` fixture's 7d reading is stale)."""
    now = ctx.ledger.clock().timestamp()
    (ctx.paths.state / "claude_plan.json").write_text(json.dumps({
        "five_hour": {"used_percentage": 6.0, "resets_at": int(now + 3 * 3600), "observed_at": int(now - 60)},
        "seven_day": {"used_percentage": 10.0, "resets_at": int(now + 4 * 86400), "observed_at": int(now - 60)},
    }))


def _acceptance(ctx, home, clock, extra_claude=0, extra_codex=0):
    """Five agents on two harnesses (or more with the extras) and a little of everything: a goal with
    tasks, a question for the human, a report, unread friction and an alert."""
    _team(ctx, home, extra_claude, extra_codex)
    _fresh_claude(ctx)
    seen_upto(ctx)
    from xt import inbox

    inbox.friction_marker(ctx)
    ids = {}
    ids["goal"] = send(ctx, "liaison", "lead", "goal", "Weather report for the coast")[0]["id"]
    ids["t1"] = send(ctx, "lead", "pm", "task", "Find station data", ref=ids["goal"])[0]["id"]
    clock.advance(minutes=5)
    ids["t2"] = send(ctx, "lead", "builder", "task", "Build the daily report", ref=ids["goal"])[0]["id"]
    ids["done"] = send(ctx, "pm", "lead", "done", "212 stations in data/stations.csv", ref=ids["t1"])[0]["id"]
    clock.advance(minutes=5)
    ids["friction"] = ctx.ledger.append("qa", "human", "friction", "the sandbox refused a plain curl")["id"]
    ids["report"] = ctx.ledger.append("liaison", "human", "report", "Coast report: 2 of 3 tasks done")["id"]
    clock.advance(minutes=5)
    ids["q"] = send(ctx, "liaison", "human", "ask", "The coast adds a day: accept the new date?")[0]["id"]
    clock.advance(minutes=1)
    Alerts(ctx).raise_("blocked:qa", "qa is blocked (usually an approval prompt)")
    queue = Queue(ctx)  # delivered, as the supervisor would have: nothing stuck in the header
    queue.remove_many({i["id"] for i in queue.pending()})
    return ids


def _regions(app) -> dict:
    middle = next(p for p in (app.panel(WORK), app.panel(FLOW)) if p.display)
    return {"team": app.team.region, "inbox": app.panel(INBOX).region, "middle": middle.region,
            "detail": app.query_one("#detail").region, "hints": app.query_one("#hints").region}


def _check_bands(app, w, h):
    """The three bands and the key line, inside the terminal, nothing overlapping."""
    r = _regions(app)
    assert r["team"].x == 0 and r["team"].y == 0  # top band: Team on the left...
    assert r["inbox"].x == r["team"].right and r["inbox"].y == 0 and r["inbox"].right == w  # ...the Inbox right
    assert r["inbox"].height == r["team"].height  # the same height
    assert r["middle"].x == 0 and r["middle"].y == r["team"].bottom and r["middle"].width == w
    assert r["detail"].x == 0 and r["detail"].y == r["middle"].bottom and r["detail"].width == w
    assert r["detail"].bottom == h - 1 and r["hints"].y == h - 1 and r["hints"].height == 1
    assert app.query_one("#detail").content_size.height >= 4  # Detail keeps its minimum rows
    assert app.query_one("#detail").outer_size.height < r["middle"].height  # shorter than the others
    assert app.query_one("#detail").outer_size.height < r["team"].height
    names = list(r)
    for i, a in enumerate(names):
        assert r[a].right <= w and r[a].bottom <= h, a
        for b in names[i + 1:]:
            assert not r[a].overlaps(r[b]), (a, b)


# --- the three bands --------------------------------------------------------------------------------


@pytest.mark.parametrize("size", SIZES)
def test_three_bands_with_five_agents_and_two_harnesses(ctx, fake_home, clock, size):
    _acceptance(ctx, fake_home, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.focused is app.panel(INBOX)  # the TUI still starts in the Inbox
            _check_bands(app, *size)
            assert app.team.hidden == 0 and len(app.team.rows) == 5  # every agent in view
            await pilot.press(str(FLOW))  # Flow takes Work's place, the bands stay
            await pilot.pause()
            _check_bands(app, *size)
            assert not app.panel(WORK).display and app.panel(FLOW).region == _regions(app)["middle"]

    _run(run())


@pytest.mark.parametrize("size", SIZES)
def test_the_demo_fixture_in_three_bands_with_a_claude_block_with_both_windows(size):
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            assert app.focused is app.panel(INBOX)
            _check_bands(app, *size)
            team = str(app.team.render())
            assert "CLAUDE" in team and "5h ▓" in team and "7d ▓" in team

    _run(run())


def test_band_heights_keep_detail_and_work_flow_their_minimum_when_the_terminal_allows():
    for total in range(15, 80):
        for team in range(3, 40):
            top, middle, detail = band_heights(total, team)
            assert top + middle + detail == total - 1 and min(top, middle, detail) >= 3
            assert top <= max(team, 5)
            if total >= 20:
                assert detail - 2 >= 4 and middle - 2 >= 4  # the minimum rows
                assert detail < middle  # Detail the shorter one
    assert band_heights(30, 14) == (14, 9, 6) and band_heights(40, 15) == (15, 16, 8)
    assert band_heights(30, 40) == (16, 7, 6) and band_heights(40, 40) == (22, 9, 8)  # a big team


# --- one column and +N more ----------------------------------------------------------------------------


def _hidden_names(app, ctx) -> list[str]:
    shown = {r.data["name"] for r in app.team.rows}
    return [a.name for a in ctx.team.agents() if a.kind != "human" and a.name not in shown]


@pytest.mark.parametrize("size,extra", [((100, 30), (5, 2)), ((160, 40), (5, 2)), ((160, 40), (9, 6))])
def test_a_big_team_shows_what_fits_and_a_plus_n_more_line(ctx, fake_home, clock, size, extra):
    """12 agents at 100x30 and 160x40 (all twelve fit there), 20 at 160x40."""
    _acceptance(ctx, fake_home, clock, *extra)
    agents = 5 + sum(extra)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            _check_bands(app, *size)
            team = app.team
            lines = str(team.render()).split("\n")
            assert len(lines) == team.content_size.height or team.hidden == 0
            assert all(len(ln) <= team.content_size.width for ln in lines)
            hidden = _hidden_names(app, ctx)
            if team.natural <= team.outer_size.height:
                assert team.hidden == 0 and not hidden and len(team.rows) == agents
                assert "more (widen the terminal)" not in lines[-1]
                return size, 0
            assert hidden and len(team.rows) + len(hidden) == agents
            # N counts the agents and harness lines out of view
            harness_lines = {k for _, k in team.lines(team.content_size.width) if k and k.startswith("harness:")}
            shown_harnesses = {k for k in harness_lines if any(ln.startswith(k.split(":")[1].upper())
                                                                  for ln in lines)}
            assert lines[-1] == f"+{len(hidden) + len(harness_lines - shown_harnesses)} more (widen the terminal)"
            assert team.hidden == len(hidden) + len(harness_lines - shown_harnesses)
            # the keys reach the agents in view only; the pane never scrolls
            await pilot.press("0", "end", "j", "down")
            await pilot.pause()
            assert team.selected == team.rows[-1].data["name"] and team.selected not in hidden
            assert str(team.render()).split("\n")[-1] == lines[-1]  # the same lines: nothing scrolled
            return size, team.hidden

    _, n = _run(run())
    assert (n > 0) == (size == (100, 30) or extra == (9, 6))  # all twelve fit at 160x40


def test_clip_counts_what_is_out_of_view():
    from rich.text import Text

    lines = [(Text("h"), teampane.HEADER), (Text("s"), None), (Text("-"), None),
             (Text("CLAUDE"), "harness:claude"), (Text("a"), "a"), (Text("b"), "b"), (Text("-"), None),
             (Text("CODEX"), "harness:codex"), (Text("c"), "c")]
    assert teampane.clip(lines, None) == (lines, 0) and teampane.clip(lines, 9) == (lines, 0)
    shown, n = teampane.clip(lines, 6)
    assert [t.plain for t, _ in shown] == ["h", "s", "-", "CLAUDE", "a", "+3 more (widen the terminal)"]
    assert n == 3  # b, the Codex line and c


# --- titles and the shared pane -----------------------------------------------------------------------


def test_every_title_is_n_title_info_and_2_and_3_swap_work_and_flow(ctx, fake_home, clock):
    _acceptance(ctx, fake_home, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            assert _title(app.team) == "[0] - Team"
            assert _title(app.panel(INBOX)) == "[1] - Inbox - ⚑ 2 · ✉ 1 · ✱ 1"
            work, flow = app.panel(WORK), app.panel(FLOW)
            assert _title(work) == "[2] - Work - 1 open · 0 done │ [3] - Flow"
            assert _title(app.query_one("#detail")) == "[4] - Detail - Inbox"
            dim = lambda w: [w._border_title.plain[s.start:s.end] for s in w._border_title.spans if "dim" in str(s.style)]
            assert "[3] - Flow" in dim(work) and not any("Work" in d for d in dim(work))  # Work active
            await pilot.press(str(WORK), "j", "j")
            await pilot.pause()
            work_sel = work.current.key
            await pilot.press(str(FLOW), "j", "j", "j")
            await pilot.pause()
            assert flow.display and not work.display and app.focused is flow
            title = _title(flow)
            assert title.startswith("[2] - Work │ [3] - Flow - ") and "system hidden (t)" in title
            assert "[2] - Work" in dim(flow) and not any("Flow" in d for d in dim(flow))  # Flow active
            flow_sel = flow.message()["id"]
            await pilot.press(str(WORK))
            await pilot.pause()
            assert work.display and work.current.key == work_sel  # each keeps its selection
            await pilot.press(str(FLOW))
            await pilot.pause()
            assert flow.message()["id"] == flow_sel and not flow.follow
            await pilot.press(str(DETAIL))
            await pilot.pause()
            assert _title(app.query_one("#detail")) == "[4] - Detail - Flow"

    _run(run())


# --- NOTIFICATIONS ---------------------------------------------------------------------------------------


def test_inbox_sections_read_needs_you_notifications_friction_and_unread_rows_are_bold(ctx, fake_home, clock):
    ids = _acceptance(ctx, fake_home, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            p = app.panel(INBOX)
            heads = [r.text.plain for r in p.rows if r.kind == "heading"]
            assert heads == ["NEEDS YOU", "NOTIFICATIONS", "FRICTION"]
            report = next(r for r in p.rows if r.kind == "message" and r.data["id"] == ids["report"])
            body = report.text.plain.index("#")
            assert any(s.start <= body < s.end and "bold" in str(s.style) for s in report.text.spans)
            assert "✉ 1" in _title(p)  # the unread count in the title

    _run(run())


# --- the key line --------------------------------------------------------------------------------------------


NAVIGATION = ("0-4", "j/k", "h ", "q ", "tab", "enter", "esc")


def test_the_key_line_follows_the_focused_pane_and_the_help_has_every_key(ctx, fake_home, clock):
    ids = _acceptance(ctx, fake_home, clock)
    ends = " · ".join(f"{k} {w}" for k, w in GLOBAL_KEYS)
    lines = {}

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            hints = lambda: str(app.query_one("#hints").render()).strip()
            p = app.panel(INBOX)
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "question")
            await pilot.pause()
            lines["inbox"] = hints()
            for key, name in ((str(TEAM), "team"), (str(WORK), "work"), (str(FLOW), "flow"), (str(DETAIL), "detail")):
                await pilot.press(key)
                await pilot.pause()
                lines[name] = hints()

    _run(run())
    assert lines["inbox"] == f"a/d approve/deny · s answer #{ids['q']} · c clear · space fold · {ends}"
    assert lines["team"] == f"u/U start · x/X stop · R retire · f jump · {ends}"
    assert lines["work"] == f"space fold · o open only · {ends}"
    assert lines["flow"] == f"t system · f filter · g/G newest/oldest · {ends}"
    assert lines["detail"] == ends
    for line in lines.values():
        assert not any(nav in line + " " for nav in NAVIGATION), line
    helped = " ".join(k for k, _ in Help.KEYS)
    for key in ("0-4", "tab", "shift+tab", "j / k", "enter", "esc", "h / ?", "q", "a / d", "c", "s", "S", "/",
                "v", "space", "o", "g / G", "t", "f", "u", "U", "x", "X", "R", "r", "pgup/pgdn", "2 / 3"):
        assert key in helped, key
    assert PANE_KEYS[INBOX][1][0] == "s"


# --- newest on top ----------------------------------------------------------------------------------------------


def test_newest_on_top_in_the_inbox_work_and_flow_and_the_top_row_follows(ctx, fake_home, clock):
    ids = _acceptance(ctx, fake_home, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            inbox, work, flow = app.panel(INBOX), app.panel(WORK), app.panel(FLOW)
            needs = [r for r in inbox.rows if r.kind in ("question", "approval", "alert")]
            assert [r.kind for r in needs] == ["alert", "question"]  # the alert is newer
            tasks = [r.data["id"] for r in work.rows if r.kind == "task"]
            assert tasks == [ids["t2"], ids["t1"]]  # tasks newest first under their goal
            # the top row selected: a newer row takes its place and the selection follows it
            assert inbox.highlighted == inbox.top_row()
            clock.advance(minutes=1)
            newer = send(ctx, "liaison", "human", "ask", "Which station list?")[0]["id"]
            await pilot.press("r")
            await pilot.pause()
            assert inbox.current.kind == "question" and inbox.current.data["id"] == newer
            assert inbox.highlighted == inbox.top_row()
            # off the top: the selection stays on its row
            await pilot.press("j")
            await pilot.pause()
            held = inbox.current.key
            clock.advance(minutes=1)
            send(ctx, "liaison", "human", "ask", "And the coast too?")
            await pilot.press("r")
            await pilot.pause()
            assert inbox.current.key == held and inbox.highlighted != inbox.top_row()
            # Work: the goal with the newest activity on top, followed
            await pilot.press(str(WORK))
            await pilot.pause()
            assert work.current.key == f"goal:{ids['goal']}"
            clock.advance(minutes=1)
            g2 = send(ctx, "liaison", "lead", "goal", "A newer goal")[0]["id"]
            await pilot.press("r")
            await pilot.pause()
            assert work.rows[0].key == f"goal:{g2}" and work.current.key == f"goal:{g2}"
            # Flow: the newest message is the top row; g the top, G the bottom
            await pilot.press(str(FLOW))
            await pilot.pause()
            top = [x for k, x in flow.rows if k == "msg"][0]
            assert top["id"] == max(x["id"] for x in flow.items) and flow.message() is top
            await pilot.press("G")
            await pilot.pause()
            assert flow.message()["id"] == min(x["id"] for x in flow.items)
            await pilot.press("g")
            await pilot.pause()
            assert flow.message() is top and flow.follow

    _run(run())
