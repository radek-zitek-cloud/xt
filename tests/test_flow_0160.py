"""v0.16.0, card #130: the Flow lane chart replaces the Log.

Each test names its criterion from the spec's "Done when" list and the terminal size it checks.
v0.17.0 (card #162) replaced criterion 14 (the final layout, the Inbox-height rule and the Team cap)
and "newest at the bottom" (criteria 3 and 9): Flow runs newest on top here, and the layout checks
are in test_tui_0170.py.
"""

import asyncio
import datetime as dt
import re
import time

import pytest
from rich.text import Text

from xt.alerts import Alerts
from xt.spawn import request_spawn
from xt.tui import flow as fl
from xt.tui.app import (FLOW, GLOBAL_KEYS, INBOX, PANE_KEYS, FlowPane, FlowPick, Help, LiveActions, XtTui,
                        band_heights, key_line)
from xt.tui.model import PANELS, Snapshot, build

from .conftest import add_member
from .test_batch_0160 import _team

SIX = ["human", "liaison", "lead", "pm", "qa", "builder"]


def _run(coro):
    return asyncio.run(coro)


def _members(ctx, retired=("scout",)):
    for name in ("pm", "qa", "builder", *retired):
        add_member(ctx, name)
    for name in retired:
        ctx.team.set_status(name, "retired")
    ctx.team.save()
    ctx.reload_team()


def _fixture(ctx, clock):
    """Two days of the six-lane team: one message of each glyph (the alert included), the system
    lines xt writes, an xt approval request, a retired agent's report, a message with no receiver."""
    _members(ctx)
    a = lambda *args, **kw: ctx.ledger.append(*args, **kw)["id"]
    m = {"goal": a("liaison", "lead", "goal", "Site check for #124")}
    m["task"] = a("lead", "pm", "task", "Read-only site check (curl -LfsS)", ref=m["goal"])
    m["scout"] = a("scout", "lead", "report", "scouted three station feeds")
    m["system"] = a("xt", "human", "system", "started pm (claude)")
    m["wake"] = a("xt", "qa", "wake", "scheduled wake-up (every 60m)")
    clock.advance(days=1)
    m["typed"] = a("human", "liaison", "report", "DNS fixed, ask QA to retry")
    m["friction"] = a("pm", "human", "friction", "settings refuse plain curl -s")
    m["done"] = a("pm", "lead", "done", "Site checked, all good", ref=m["task"])
    m["ask"] = a("lead", "liaison", "ask", "How should the site check finish?", ref=m["goal"])
    m["report"] = a("liaison", "human", "report", "v0.15.0 built, published and Accepted")
    m["nudge"] = a("xt", "lead", "nudge", "#9 has been open for an hour")
    m["note"] = a("qa", "qa", "note", "decided: retry tomorrow")
    request_spawn(ctx, "lead", "dora", "claude", None, "worker", None)  # xt writes the approval request
    m["approval"] = max(x["id"] for x in ctx.ledger.messages() if x["type"] == "approval")
    Alerts(ctx).raise_("blocked:qa", "qa is blocked (usually an approval prompt)")
    m["alert"] = max(x["id"] for x in ctx.ledger.messages() if x["type"] == "alert")
    m["nobody"] = a("builder", "", "note", "checkpoint: notes saved")
    return m


def _msg(ctx, mid):
    return next(x for x in ctx.ledger.messages() if x["id"] == mid)


def _pane(app) -> FlowPane:
    return app.panel(FLOW)


def _lines(pane) -> list[str]:
    return pane.render().plain.split("\n")


def _col(c: fl.Chart, name: str) -> int:
    return fl.TIME + c.where[name] * c.width


def _title(widget) -> str:
    return widget._border_title.plain


def _local(m) -> str:
    return dt.datetime.fromisoformat(m["ts"]).astimezone().strftime("%H:%M")


async def _pick(pilot, app, key):
    """f, then the pick `key` in the picker."""
    await pilot.press("f")
    await pilot.pause()
    assert isinstance(app.screen, FlowPick)
    options = app.screen.query_one("#flow-pick")
    options.highlighted = [k for k, _ in app.screen.picks].index(key)
    await pilot.press("enter")
    await pilot.pause()


# --- 1 lane order ----------------------------------------------------------------------------------


def test_1_lanes_in_roster_order_and_a_retired_lane_only_with_its_rows(ctx, clock):
    """160x40: human, liaison, lead, pm, qa, builder in that order; xt after human once it sent a
    shown message; a retired agent's lane dim, and only while its rows are shown."""
    _members(ctx)
    ctx.ledger.append("liaison", "lead", "goal", "Build it")
    ctx.ledger.append("lead", "builder", "task", "Build the thing")
    ctx.ledger.append("xt", "scout", "wake", "scheduled wake-up")  # a system line: hidden by default

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))  # Flow shares its band with Work (card #162)
            await pilot.pause()
            pane = _pane(app)
            c = pane.chart()
            assert [lane.name for lane in c.lanes] == SIX  # no xt, no scout: their rows are hidden
            head = _lines(pane)[0]
            assert [head.index(n) for n in SIX] == sorted(head.index(n) for n in SIX)
            assert head.startswith("time  human")
            await pilot.press("t")  # system lines shown: xt's wake-up to the retired scout
            await pilot.pause()
            c = pane.chart()
            assert [lane.name for lane in c.lanes] == ["human", "xt", *SIX[1:], "scout"]
            assert [lane.dim for lane in c.lanes] == [False] * 7 + [True]
            header = fl.header(c, pane.content_size.width)
            scout = header.plain.index("scout")
            assert any(s.start <= scout < s.end and str(s.style) == "bright_black" for s in header.spans)
            await pilot.press("t")
            await pilot.pause()
            assert "scout" not in [lane.name for lane in pane.chart().lanes]

    _run(run())


def _scout_then(ctx, n):
    """rc6 (QA's rc5 addendum): the retired scout's only message, then `n` newer reports."""
    _members(ctx)
    scout = ctx.ledger.append("scout", "lead", "report", "scouted three station feeds")["id"]
    for i in range(n):
        ctx.ledger.append("pm", "lead", "report", f"progress {i}")
    return scout


def _names(pane) -> list[str]:
    return [lane.name for lane in pane.chart().lanes]


def test_1_a_retired_lane_follows_the_rows_in_view_when_scrolling(ctx, clock):
    """100x30, QA's failing case: the scout's only row is outside the rows in view, so no scout
    lane; scrolled to the bottom (the oldest, card #162) it is in view and the dim lane appears; back
    to the newest it goes."""
    scout = _scout_then(ctx, 35)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            assert scout not in [x["id"] for x in pane.in_view()] and len(pane.in_view()) < len(pane.items)
            assert "scout" not in _names(pane) and "scout" not in _lines(pane)[0]
            await pilot.press("G")
            await pilot.pause()
            assert scout in [x["id"] for x in pane.in_view()]
            c = pane.chart()
            assert _names(pane)[-1] == "scout" and c.lanes[-1].dim and "scout" in _lines(pane)[0]
            await pilot.press("g")
            await pilot.pause()
            assert "scout" not in _names(pane)
            await pilot.press("G", *"k" * pane.view_height())  # k past the view: the scout row scrolls out
            await pilot.pause()
            assert scout not in [x["id"] for x in pane.in_view()] and "scout" not in _names(pane)

    _run(run())


def test_1_a_retired_lane_follows_the_filters(ctx, clock):
    """100x30: f on the scout, `/` on its text and t on its only (system) line each bring the lane
    in exactly while one of its rows is visible."""
    _scout_then(ctx, 35)
    ctx.ledger.append("xt", "scout", "wake", "scheduled wake-up")  # newest, a system line

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            assert "scout" not in _names(pane)
            await pilot.press("t")  # the wake-up to the scout is the newest row: in view
            await pilot.pause()
            assert _names(pane)[-1] == "scout"
            await pilot.press("t")
            await pilot.pause()
            assert "scout" not in _names(pane)
            await _pick(pilot, app, ("agent", "scout"))  # `f` still offers the retired scout
            assert _names(pane)[-1] == "scout" and len(pane.items) == 1
            await pilot.press("escape")
            await pilot.pause()
            assert "scout" not in _names(pane)
            await pilot.press("slash", *"station", "enter")
            await pilot.pause()
            assert _names(pane)[-1] == "scout" and len(pane.items) == 1
            await pilot.press("slash", *"progress 3", "enter")  # a filter without the scout's rows
            await pilot.pause()
            assert pane.items and "scout" not in _names(pane)

    _run(run())


def test_1_a_retired_lane_follows_the_rows_in_view_when_resizing(ctx, clock):
    """100x30 → 160x60: a taller Flow brings the scout's row, and its lane, into view; back to
    100x30 it goes again."""
    _scout_then(ctx, 9)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            assert len(pane.in_view()) < 10 and "scout" not in _names(pane)
            await pilot.resize_terminal(160, 60)
            await pilot.pause()
            assert len(pane.in_view()) == 10 and _names(pane)[-1] == "scout"
            await pilot.resize_terminal(100, 30)
            await pilot.pause()
            assert "scout" not in _names(pane)

    _run(run())


# --- 2 arrows, 15 the alert --------------------------------------------------------------------------


ARROWS = {  # fixture key: sender, receiver, glyph, label
    "goal": ("liaison", "lead", "◆", "goal"), "task": ("lead", "pm", "▸", "task"),
    "done": ("pm", "lead", "◇", "done"), "report": ("liaison", "human", "✉", "report"),
    "ask": ("lead", "liaison", "⚑", "ask"), "approval": ("xt", "human", "⚑", "approval"),
    "friction": ("pm", "human", "✱", "friction"), "alert": ("xt", "human", "⚠", "alert"),
    "typed": ("human", "liaison", "○", "report"), "scout": ("scout", "lead", "✉", "report"),
}


def test_2_each_type_has_its_glyph_label_and_arrowhead_and_to_the_human_is_dotted(ctx, clock):
    """160x40: glyph and label at the sender's lane, the arrowhead at the receiver's pointing its
    way, `·` towards the human and `─` otherwise; a note to itself is its glyph and label only."""
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))  # Flow shares its band with Work (card #162)
            await pilot.pause()
            pane = _pane(app)
            c, width = pane.chart(), pane.content_size.width
            assert c is not None and {g for *_, g, _ in ARROWS.values()} | {"○"} >= set("◆▸◇✉⚑✱⚠○")
            for key, (src, dst, glyph, label) in ARROWS.items():
                line = fl.chart_row(_msg(ctx, m[key]), c, width).plain
                a, b = _col(c, src), _col(c, dst)
                assert line[a] == glyph, key
                assert line[b] == ("▶" if b > a else "◀"), key
                between = line[min(a, b) + 1:max(a, b)]
                assert label in between, key  # room for it at this width
                assert set(between.replace(label, "")) == ({"·"} if dst == "human" else {"─"}), key
                if b > a:  # the label next to the glyph, at the sender end
                    assert between.startswith("─" + label), key
                else:
                    assert between.endswith(label + ("·" if dst == "human" else "─")), key
            note = fl.chart_row(_msg(ctx, m["note"]), c, width).plain
            q = _col(c, "qa")
            assert note[q:q + 6] == "○ note" and not set("▶◀─·") & set(note[fl.TIME:fl.TIME + len(c.lanes) * c.width])
            # too little room for the label: glyph and arrowhead stay, the label goes
            tight = fl.Chart(c.lanes, fl.LANE_MIN, c.where)
            line = fl.chart_row(_msg(ctx, m["friction"]), tight, width).plain
            a, b = fl.TIME + c.where["pm"] * 9, fl.TIME
            assert line[a] == "✱" and line[b] == "◀"
            short = fl.chart_row(_msg(ctx, m["approval"]), tight, width).plain  # xt → human: 8 cells between
            assert short[fl.TIME + 9] == "⚑" and "approval" not in short[:fl.TIME + 9] and short[fl.TIME] == "◀"

    _run(run())


def test_15_a_supervisor_alert_is_an_amber_warning_from_xt_into_the_human_lane(ctx, clock):
    """160x40: the alert's `⚠` and `alert` label in amber (not friction's colour), from the xt lane,
    dotted, with its arrowhead in the human lane; shown with system lines hidden."""
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))  # Flow shares its band with Work (card #162)
            await pilot.pause()
            pane = _pane(app)
            assert not pane.show_system and m["alert"] in [x["id"] for x in pane.items]
            c = pane.chart()
            row = fl.chart_row(_msg(ctx, m["alert"]), c, pane.content_size.width)
            a, b = _col(c, "xt"), _col(c, "human")
            assert row.plain[a] == "⚠" and row.plain[b] == "◀" and "alert" in row.plain[b:a]
            assert set(row.plain[b + 1:a].replace("alert", "")) == {"·"}

            def style_at(text, i):
                return " ".join(str(s.style) for s in text.spans if s.start <= i < s.end)

            friction = fl.chart_row(_msg(ctx, m["friction"]), c, pane.content_size.width)
            amber, other = style_at(row, a), style_at(friction, _col(c, "pm"))
            assert "yellow" in amber and amber != other
            assert any("alert" in ln and f"#{m['alert']} " in ln for ln in _lines(pane))

    _run(run())


# --- 3 time and days, 4 margin ------------------------------------------------------------------------


def test_3_rows_newest_on_top_a_day_change_inserts_a_separator_and_times_are_local(ctx, clock):
    """Card #162 reverses #130's order: the newest message is the top row and selected; the older
    day's separator sits over that day's rows (its newest first)."""
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW), "t")  # every row
            await pilot.pause()
            pane = _pane(app)
            ids = [x["id"] for x in pane.items]
            shown = [x["id"] for k, x in pane.rows if k == "msg"]
            assert shown == sorted(ids, reverse=True) and pane.message()["id"] == shown[0]  # newest on top, selected
            kinds = [k for k, _ in pane.rows]
            days = [x for k, x in pane.rows if k == "day"]
            first = fl.local(_msg(ctx, m["goal"])).date()
            assert days[-1] == first  # the separator over the first day's rows
            at = len(kinds) - 1 - kinds[::-1].index("day")
            assert pane.rows[at + 1][1]["id"] == m["wake"] and pane.rows[at - 1][1]["id"] == m["typed"]
            assert fl.separator(first, 60).plain == f"── {first:%b} {first.day} ──"
            for x in pane.items:
                assert fl.chart_row(x, pane.chart(), 158).plain[:6] == _local(x) + " "

    _run(run())


@pytest.mark.parametrize("size", [(160, 40), (100, 30)])
def test_4_margin_has_id_and_first_line_cut_only_when_needed_and_a_time_never_an_age(ctx, clock, size):
    m = _fixture(ctx, clock)
    long = ctx.ledger.append("lead", "qa", "report", "a long report " * 30 + "\nsecond line")["id"]

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(FLOW))  # Flow shares its band with Work (card #162)
            await pilot.pause()
            pane = _pane(app)
            c, width = pane.chart(), pane.content_size.width
            cut = 0
            for x in pane.items:
                line = fl.chart_row(x, c, width)
                assert line.cell_len <= width and re.match(r"\d\d:\d\d ", line.plain)
                whole = fl.chart_row(x, c, 10_000).plain
                assert whole.endswith(f"#{x['id']} {fl.first_line(x)}")  # nothing after it: no age column
                if len(whole) <= width:  # fits: whole, no `…`
                    assert line.plain == whole and "…" not in line.plain
                else:  # too long: cut at the pane edge with `…`
                    cut += 1
                    assert line.cell_len == width and line.plain.endswith("…") and whole.startswith(line.plain[:-1])
            assert cut >= 1 and long in [x["id"] for x in pane.items]
            assert "second line" not in fl.chart_row(_msg(ctx, long), c, 10_000).plain  # the first line only
            shown = [ln for ln in _lines(pane)[1:] if re.match(r"\d\d:\d\d ", ln)]
            assert shown and all(not re.search(r"\s(now|\d+[smhdw])$", ln.rstrip()) for ln in shown)

    _run(run())


# --- 5 system lines, 6 filters --------------------------------------------------------------------------


def test_5_system_lines_hidden_by_default_t_shows_and_hides_them_approvals_and_alerts_always(ctx, clock):
    m = _fixture(ctx, clock)
    assert {x["type"] for x in ctx.ledger.messages() if x["from"] == "xt"} == {
        "system", "wake", "nudge", "approval", "alert"}  # what xt itself writes here

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))  # Flow shares its band with Work (card #162)
            await pilot.pause()
            pane = _pane(app)
            types = lambda: {x["type"] for x in pane.items}
            ids = lambda: {x["id"] for x in pane.items}
            assert not types() & {"system", "wake", "nudge"} and {m["approval"], m["alert"]} <= ids()
            assert "system hidden (t)" in pane.border_title
            await pilot.press("t")
            await pilot.pause()
            assert {"system", "wake", "nudge"} <= types() and {m["approval"], m["alert"]} <= ids()
            assert "system shown (t)" in pane.border_title
            await pilot.press("t")
            await pilot.pause()
            assert not types() & {"system", "wake", "nudge"} and {m["approval"], m["alert"]} <= ids()

    _run(run())


def test_6_f_filters_to_an_agent_or_a_goals_thread_and_esc_clears_it(ctx, clock):
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            everything = [x["id"] for x in pane.items]
            lanes = [lane.name for lane in pane.chart().lanes]
            await _pick(pilot, app, ("agent", "pm"))
            pm = [x["id"] for x in ctx.ledger.messages() if "pm" in (x["from"], x["to"]) and not fl.is_system(x)]
            assert [x["id"] for x in pane.items] == pm == [m["task"], m["friction"], m["done"]]
            assert "agent pm (f)" in pane.border_title and f"{len(pm)} of {len(pm)}" in pane.border_title
            # the team's lanes stay; the retired scout's goes with its rows (criterion 1)
            assert [lane.name for lane in pane.chart().lanes] == [n for n in lanes if n != "scout"]
            assert "scout" in lanes
            await pilot.press("escape")  # esc in Flow clears it
            await pilot.pause()
            assert [x["id"] for x in pane.items] == everything and "(f)" not in pane.border_title
            await _pick(pilot, app, ("goal", m["goal"]))
            assert [x["id"] for x in pane.items] == [m["goal"], m["task"], m["done"], m["ask"]]
            assert f"goal #{m['goal']} (f)" in pane.border_title
            await pilot.press("f")
            await pilot.pause()
            await pilot.press("escape")  # f, then esc: cleared
            await pilot.pause()
            assert pane.pick is None and [x["id"] for x in pane.items] == everything
            await _pick(pilot, app, ("agent", "qa"))
            await _pick(pilot, app, ("agent", "qa"))  # f again on the active filter: cleared
            assert pane.pick is None and [x["id"] for x in pane.items] == everything

    _run(run())


def test_slash_filters_flow_by_the_body_text(ctx, clock):
    """The Log's `/` filter keeps working in Flow, on the message text."""
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW), "slash", *"curl", "enter")
            await pilot.pause()
            pane = _pane(app)
            assert [x["id"] for x in pane.items] == [m["task"], m["friction"]] and "/curl" in pane.border_title
            await pilot.press("slash", "enter")
            await pilot.pause()
            assert len(pane.items) > 2 and "/" not in pane.border_title.split("(t)")[1]

    _run(run())


# --- 7 many agents, 8 narrow --------------------------------------------------------------------------


@pytest.mark.parametrize("size", [(160, 40), (100, 30)])
def test_7_twelve_agents_every_message_has_a_row_and_collapsed_lanes_are_named(ctx, fake_home, size):
    _team(ctx, fake_home, extra_claude=5, extra_codex=2)  # 12 agents
    members = [a.name for a in ctx.team.agents() if a.kind != "human" and a.role not in ("liaison", "lead")]
    assert len(members) == 10
    for name in members:
        ctx.ledger.append("lead", name, "task", f"work for {name}")
        ctx.ledger.append(name, "lead", "done", f"{name} finished")
    ctx.ledger.append("liaison", "human", "report", "all ten done")
    total = len(list(ctx.ledger.messages()))

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(FLOW), "t")
            await pilot.pause()
            pane = _pane(app)
            assert len(pane.items) == total == len(pane.message_rows())  # every message has a row
            c, width = pane.chart(), pane.content_size.width
            assert c is not None and len(c.lanes) * c.width + fl.TIME + fl.MARGIN <= width
            if size[0] == 160:  # 13 lanes of 9 or more fit in 158 cells
                assert not c.collapsed and len(c.lanes) == 13
                return
            plus = c.lanes[-1]
            assert plus.name == f"+{len(plus.members)}" and len(plus.members) >= 1
            assert c.lanes[:3] == [fl.Lane("human"), fl.Lane("liaison"), fl.Lane("lead")]  # the chain stays
            hidden = plus.members[-1]
            task = next(x for x in pane.items if x["to"] == hidden)
            line = fl.chart_row(task, c, width).plain
            assert line[_col(c, "lead")] == "▸" and line[fl.TIME + (len(c.lanes) - 1) * c.width] == "▶"
            assert line[fl.TIME + len(c.lanes) * c.width:].lstrip().startswith(f"{hidden}: #{task['id']} ")
            assert all(fl.chart_row(x, c, width).cell_len <= width for x in pane.items)

    _run(run())


@pytest.mark.parametrize("size", [(60, 20), (40, 15)])
def test_8_a_narrow_terminal_lists_one_row_per_message_and_widening_brings_the_chart_back(ctx, clock, size):
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            assert pane.chart() is None  # list mode
            # nothing runs past the terminal: the key line is its last row, Detail ends above it (#162)
            detail = app.query_one("#detail")
            assert app.query_one("#hints").region.y == size[1] - 1 and detail.region.bottom == size[1] - 1
            assert pane.region.bottom == detail.region.y
            assert app.team.outer_size.height == band_heights(size[1], app.team.natural)[0]
            width = pane.content_size.width
            lines = pane.render().split("\n")
            assert all(ln.cell_len <= width for ln in lines)  # nothing spills
            rows = [ln.plain for ln in lines if re.match(r"\d\d:\d\d ", ln.plain)]
            assert rows and all(" → " in r for r in rows)
            x = _msg(ctx, m["ask"])
            full = fl.list_row(x, 400).plain
            assert full == f"{_local(x)} lead → liaison ⚑ #{x['id']} How should the site check finish?"
            # one row per message: every one of them, scrolled through
            seen = set()
            await pilot.press("g")
            for _ in range(len(pane.items) + 2):
                seen.add(pane.message()["id"])
                await pilot.press("j")
            assert seen == {x["id"] for x in pane.items}
            await pilot.press("g", "j", "j")
            chosen = pane.message()["id"]
            await pilot.resize_terminal(160, 40)
            await pilot.pause()
            assert pane.chart() is not None and pane.message()["id"] == chosen  # the selection kept

    _run(run())


# --- 9 moving, 10 scale, 11 robustness -----------------------------------------------------------------


def test_9_j_k_g_G_and_following_and_enter_shows_the_message_in_detail(ctx, clock):
    """Card #162: newest on top. The top row is followed; j moves to older messages and stops
    following; g is the newest (top), G the oldest (bottom)."""
    m = _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            order = lambda: [x["id"] for x in reversed(pane.items)]  # the rows, top to bottom
            assert pane.follow and pane.message()["id"] == order()[0] and pane.top == 0
            await pilot.press("j")
            assert not pane.follow and pane.message()["id"] == order()[1]
            new = ctx.ledger.append("lead", "qa", "task", "a new task while I read")["id"]
            await pilot.press("r")
            await pilot.pause()
            assert pane.message()["id"] == order()[2] and order()[0] == new  # not following: stays put
            await pilot.press("g")
            assert pane.follow and pane.message()["id"] == new and pane.top == 0
            newer = ctx.ledger.append("qa", "lead", "report", "on it")["id"]
            await pilot.press("r")
            await pilot.pause()
            assert pane.message()["id"] == newer and _lines(pane)[1].find(f"#{newer} ") > 0  # on top, followed
            await pilot.press("G")
            await pilot.pause()
            assert pane.message()["id"] == order()[-1] and not pane.follow
            await pilot.press("k", "k")
            await pilot.pause()
            assert pane.message()["id"] == order()[-3]
            await pilot.press("pageup")
            await pilot.pause()
            page = pane.view_height() - 1
            at = max(0, len(order()) - 3 - page)
            assert pane.message()["id"] == order()[at]
            await pilot.press("pagedown")
            await pilot.pause()
            assert pane.message()["id"] == order()[min(len(order()) - 1, at + page)]
            await pilot.press("j", "j", "j")  # past the bottom: stays on the oldest
            await pilot.pause()
            assert pane.message()["id"] == order()[-1]
            pane.selected = next(i for i, (k, x) in enumerate(pane.rows) if k == "msg" and x["id"] == m["done"])
            pane.follow = False
            pane.place()
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused.id == "detail" and _title(app.query_one("#detail")) == "[4] - Detail - Flow"
            view = app.detail_view
            assert view.selected == m["done"] and [x["id"] for x in view.thread][:2] == [m["goal"], m["task"]]
            assert "Site checked, all good" in view.plain
            await pilot.press("escape")
            await pilot.pause()
            assert app.focused is pane and pane.message()["id"] == m["done"]

    _run(run())


def test_10_a_5000_message_ledger_opens_and_each_key_is_handled_without_a_stall(ctx, clock, capsys):
    """Pilot at 160x40 on a 5,000-message ledger: the measured times are printed for the QA verdict."""
    _members(ctx, retired=())
    kinds = [("liaison", "lead", "goal"), ("lead", "pm", "task"), ("pm", "lead", "done"),
             ("qa", "human", "friction"), ("xt", "human", "system"), ("builder", "lead", "report")]
    for i in range(5000):
        src, dst, kind = kinds[i % len(kinds)]
        ctx.ledger.append(src, dst, kind, f"message {i}")
        if i % 500 == 0:
            clock.advance(hours=6)
    assert len(list(ctx.ledger.messages())) == 5000
    times = {}

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        start = time.perf_counter()
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            times["open"] = time.perf_counter() - start
            pane = _pane(app)
            assert len(pane.items) > 4000
            for key in ("j", "j", "k", "pagedown", "pagedown", "pageup", "G", "g", "t", "t", "r"):
                t0 = time.perf_counter()
                await pilot.press(key)
                await pilot.pause()
                times[key] = max(times.get(key, 0), time.perf_counter() - t0)
            assert pane.message()["id"] == pane.items[-1]["id"]  # g: the newest, on top

    _run(run())
    with capsys.disabled():
        print("\n#130 criterion 10 (5,000 messages, 160x40): " +
              ", ".join(f"{k} {v * 1000:.0f} ms" for k, v in times.items()))
    assert times["open"] < 10 and max(v for k, v in times.items() if k != "open") < 1.0


def test_11_an_unknown_type_an_unknown_agent_and_no_receiver_do_not_crash_the_pane():
    now = dt.datetime(2026, 9, 30, 10, 0, tzinfo=dt.timezone.utc)
    ts = now.isoformat()
    msgs = [{"id": 1, "ts": ts, "from": "lead", "to": "pm", "type": "mystery", "body": "a new type"},
            {"id": 2, "ts": ts, "from": "ghost", "to": "lead", "type": "report", "body": "who am I"},
            {"id": 3, "ts": ts, "from": "pm", "to": "", "type": "note", "body": "no receiver"},
            {"id": 4, "ts": ts, "from": "pm", "type": "report", "body": "no `to` at all"},
            {"id": 5, "from": "lead", "to": "pm", "type": "task"},  # no time, no body
            {"id": 6, "ts": "not a time", "from": "", "to": "lead", "type": "task", "body": "no sender"}]
    data = fl.Data(msgs, [("liaison", "liaison", True), ("lead", "lead", True), ("pm", "worker", True)],
                   lambda m: Text(str(m)), now)
    snap = lambda: Snapshot({"Inbox": [], "Work": []}, Text("t"), flow=data)

    async def run(size):
        app = XtTui(snap)
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            pane = _pane(app)
            assert len(pane.items) == 6
            text = pane.render().plain
            if pane.chart():
                c = pane.chart()
                assert [lane.name for lane in c.lanes][-1] == "ghost" and c.lanes[-1].dim
                row = {x["id"]: fl.chart_row(x, c, pane.content_size.width).plain for x in msgs}
                assert "• mystery" in row[1] or "•─mystery" in row[1]
                assert "○ note" in row[3] and "✉ report" in row[4]  # drawn in the sender's own lane
                assert row[5].startswith("--:-- ") and row[6].startswith("--:-- ")
            else:
                rows = [fl.list_row(x, pane.content_size.width).plain for x in msgs]
                assert rows[1].startswith("12:00 ghost → lead ✉") or "ghost → lead" in rows[1]
                assert "pm → — ○ #3" in rows[2] and "? → lead" in rows[5] and "pm → — " in text
            for key in ("g", "j", "j", "j", "j", "j", "enter"):
                await pilot.press(key)
            await pilot.pause()
            assert app.focused.id == "detail"

    for size in ((160, 40), (40, 15)):
        _run(run(size))


# --- 12 the Log is gone ----------------------------------------------------------------------------------


def test_12_the_log_pane_and_its_key_are_gone_and_xt_log_still_prints_the_ledger(ctx, clock, monkeypatch,
                                                                                  capsys):
    from xt import cli

    m = _fixture(ctx, clock)
    keys = [pair for pairs in PANE_KEYS.values() for pair in pairs] + GLOBAL_KEYS
    assert PANELS == ("Inbox", "Work", "Flow") and not any("Log" in k or "Log" in w for k, w in keys)
    assert not any("Log" in k or "Log" in w for k, w in Help.KEYS)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press("3")
            await pilot.pause()
            assert app.focused is _pane(app) and app.focused.title == "Flow"
            assert "Log" not in _title(app.focused)
            assert not [w for w in app.query("*") if getattr(w, "title", None) == "Log"]
            await pilot.press("4")  # no Log: since #157 the detail pane
            assert app.focused.id == "detail"

    _run(run())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_log(cli.build_parser().parse_args(["log", "--limit", "50"]))
    out = capsys.readouterr().out
    assert f"#{m['goal']}" in out and "Site check for #124" in out and f"#{m['system']}" in out


# --- 14 the final layout: replaced by card #162 (tests/test_tui_0170.py) -----------------------------


def test_the_key_line_keeps_every_key_and_drops_words_from_the_end_first():
    pairs = [("h", "help"), ("q", "quit"), ("1-3", "panes"), ("j/k", "move")]
    assert key_line(pairs, [("tab", "Team")], 80) == "h help · q quit · 1-3 panes · j/k move · tab Team"
    assert key_line(pairs, [("tab", "Team")], 30) == "h help · q quit · 1-3 · j/k"
    assert key_line(pairs, [], 14) == "h · q · 1-3 · j/k"


def test_the_key_line_lists_t_f_and_g_G_while_flow_has_focus(ctx, clock):
    _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))
            await pilot.pause()
            line = str(app.query_one("#hints").render())
            assert line.startswith("t system · f filter · g/G newest/oldest")
            await pilot.press(str(INBOX))
            await pilot.pause()
            line = str(app.query_one("#hints").render())
            assert "f " not in line and "g/G" not in line and "t system" not in line  # Flow's own keys only in Flow
            keys = dict(Help.KEYS)
            assert keys["g / G"] and keys["t"].startswith("show or hide system lines")

    _run(run())


def test_flow_is_read_only(ctx, clock):
    """No key in Flow sends or changes anything: the ledger is the same after every Flow key."""
    _fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))
            before = ctx.ledger.last_id()
            for key in ("j", "k", "g", "G", "pageup", "pagedown", "t", "t", "escape"):
                await pilot.press(key)
            await pilot.pause()
            assert ctx.ledger.last_id() == before

    _run(run())
