"""v0.16.1, card #157: TUI fixes from the first live use of v0.16.0. Keys 0 and 4 and esc; arrows
and page keys in Team and Flow; the state dot in the state's colour; space folds in the Inbox; seen
New items folded under New for 7 days; clicks select without moving focus to Detail, and the
wheel scrolls Flow and Detail."""

import asyncio
import json

from rich.text import Text
from textual import events

from xt.tui import teampane
from xt.tui.app import DETAIL, FLOW, HINTS, INBOX, TEAM, WORK, Help, LiveActions, XtTui
from xt.tui.model import ANSWERED_FOLD, EARLIER_FOLD, FRICTION_FOLD, build
from xt.tui.thread import ThreadDetail

from .test_batch_0160 import _fixture, _shown, _team, _work_fixture, _xt_inbox
from .test_flow_0160 import _fixture as _flow_fixture


def _run(coro):
    return asyncio.run(coro)


def _app(ctx) -> XtTui:
    return XtTui(lambda: build(ctx), LiveActions(ctx))


async def _click(pilot, x: int, y: int) -> None:
    await pilot.click(offset=(x, y))
    await pilot.pause()


async def _wheel(pilot, widget, down: bool = True) -> None:
    await pilot._post_mouse_events([events.MouseScrollDown if down else events.MouseScrollUp], widget, (2, 2))
    await pilot.pause()


def _agent_at(app, name: str) -> tuple[int, int]:
    """Screen cell of `name`'s cell in the Team pane."""
    region = app.team.content_region
    for y, line in enumerate(str(app.team.render()).splitlines()):
        x = line.find(f" {name} ")
        if x > 0:
            return region.x + x + 1, region.y + y
    raise AssertionError(f"{name} is not in the Team pane")


def _option_at(panel, index: int) -> tuple[int, int]:
    region = panel.content_region
    return region.x + 2, region.y + index - panel.scroll_offset.y


def _flow_row_at(pane, index: int) -> tuple[int, int]:
    region = pane.content_region
    header = 1 if pane.chart() else 0
    return region.x + 20, region.y + header + index - pane.top


# --- 1 keys 0 and 4, esc back ------------------------------------------------------------------------


def test_1_zero_focuses_team_four_detail_and_esc_returns_to_the_pane_it_came_from(ctx, fake_home):
    _team(ctx, fake_home)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press("0")
            assert app.focused is app.team and app.last_panel == TEAM
            for key, pane in (("0", app.team), (str(INBOX), app.panel(INBOX)), (str(WORK), app.panel(WORK)),
                              (str(FLOW), app.panel(FLOW))):
                await pilot.press(key)
                await pilot.pause()
                assert app.focused is pane
                await pilot.press(str(DETAIL))
                await pilot.pause()
                assert app.focused.id == "detail"
                assert app.query_one("#detail").border_title == f"Detail─{pane.title}"
                await pilot.press("escape")
                await pilot.pause()
                assert app.focused is pane, key

    _run(run())


def test_1_the_key_line_and_the_help_list_0_to_4():
    assert TEAM == 0 and DETAIL == 4
    assert "0-4 panes" in HINTS
    keys = dict(Help.KEYS)
    assert keys["0-4"] == "jump to a pane: Team, Inbox, Work, Flow, Detail"
    assert "Team (0)" in keys
    assert not any("tab reaches" in what for _, what in Help.KEYS)

    async def run():
        from xt.tui.app import demo_snapshot

        app = XtTui(demo_snapshot)
        async with app.run_test(size=(100, 30)):
            assert "0-4 panes" in str(app.query_one("#hints").render())

    _run(run())


# --- 2 arrows and page keys ----------------------------------------------------------------------------


def test_2_up_and_down_move_in_team_like_j_and_k(ctx, fake_home):
    _team(ctx, fake_home)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press("0")
            order = [r.data["name"] for r in app.team.rows]
            assert app.team.selected == order[0]
            await pilot.press("down")
            assert app.team.selected == order[1]
            assert app.query_one("#detail-body").content.plain.startswith(order[1])
            await pilot.press("down", "up")
            assert app.team.selected == order[1]
            await pilot.press("up", "up")  # stops at the first
            assert app.team.selected == order[0]

    _run(run())


def test_2_home_end_and_the_page_keys_in_team(ctx, fake_home):
    _team(ctx, fake_home, extra_claude=9, extra_codex=6)  # 20 agents: capped at 100x24

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:  # every agent fits: a page is the whole team
            await pilot.press("0")
            order = [r.data["name"] for r in app.team.rows]
            await pilot.press("end")
            assert app.team.selected == order[-1]
            await pilot.press("home")
            assert app.team.selected == order[0]
            await pilot.press("pagedown")
            assert app.team.selected == order[-1]
            await pilot.press("pageup")
            assert app.team.selected == order[0]
        app = _app(ctx)
        async with app.run_test(size=(100, 24)) as pilot:  # capped: a page is the agent lines in view
            await pilot.press("0")
            await pilot.pause()
            assert app.team.limit is not None
            step = app.team.page_size()
            assert 1 <= step < len(order)
            await pilot.press("pagedown")
            assert app.team.selected == order[step]
            await pilot.press("pageup")
            assert app.team.selected == order[0]
            await pilot.press("end")
            assert app.team.selected == order[-1]
            assert any(f" {order[-1]} " in ln for ln in str(app.team.render()).splitlines())  # in view

    _run(run())


def test_2_up_and_down_move_in_flow_like_j_and_k(ctx, clock):
    _flow_fixture(ctx, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW))
            pane = app.panel(FLOW)
            msgs = pane.message_rows()
            assert pane.selected == msgs[-1]
            await pilot.press("up")
            assert pane.selected == msgs[-2] and not pane.follow
            await pilot.press("k")
            assert pane.selected == msgs[-3]
            await pilot.press("down", "j")
            assert pane.selected == msgs[-1] and pane.follow

    _run(run())


# --- 3 the state dot ----------------------------------------------------------------------------------


def _dot(cell) -> str:
    return next(str(s.style) for s in cell.spans if s.start == 0 and s.end == 1)


def _word_style(cell, state: str) -> str:
    at = cell.plain.index(f" {state} ") + 1
    return next(str(s.style) for s in cell.spans if s.start == at)


def test_3_the_dot_takes_the_states_named_colour_and_nothing_else_changes():
    expected = {"working": "yellow", "idle": "green", "done": "green", "blocked": "red"}
    for state, colour in expected.items():
        d = {"name": "carol", "model": "sonnet 5.5", "state": state, "running": True, "dot": "●",
             "used": 50_000, "window": 1_000_000}
        cell = teampane.cell(d, teampane.widths([d]), teampane.BAR_MAX)
        assert _dot(cell) == colour == _word_style(cell, state)
        styles = {str(s.style) for s in cell.spans if s.start > 0 and "meta" not in repr(s.style)}
        # the rest of the cell as in v0.16.0: bold name, dim model and tokens, cyan bar, the state word
        assert styles <= {"bold", "bright_black", "cyan", "", colour}
    for state in ("stopped", "retired"):
        d = {"name": "carol", "model": "sonnet 5.5", "state": state, "running": False, "dot": "○"}
        assert _dot(teampane.cell(d, teampane.widths([d]), teampane.BAR_MAX)) == "bright_black"


def test_3_the_team_panes_dots_follow_herdrs_states(ctx, fake_home):
    _team(ctx, fake_home)
    ctx.herdr.add("qa", "blocked")
    ctx.herdr.live.pop("pm")
    rows = {r.data["name"]: r for r in build(ctx).panels["Team"]}
    assert teampane.dot_style(rows["lead"].data) == "yellow"  # working
    assert teampane.dot_style(rows["builder"].data) == "green"  # idle
    assert teampane.dot_style(rows["qa"].data) == "red"  # blocked
    assert teampane.dot_style(rows["pm"].data) == "bright_black" and rows["pm"].data["dot"] == "○"  # not running
    lines = teampane.render(Text(""), "", [], [r.data for r in rows.values()], 160, ctx.ledger.clock())[0]
    lead = next(ln for ln in lines if " lead " in ln.plain)
    at = lead.plain.index("● lead")
    assert any(s.start == at and s.end == at + 1 and str(s.style) == "yellow" for s in lead.spans)


# --- 4 and 5 space folds in the Inbox; seen New items under New ------------------------------------------


def _look_and_leave(ctx):
    """Open the TUI in the Inbox, then leave it: New and the friction on screen count as seen."""

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            await pilot.press(str(WORK))
            await pilot.pause()

    _run(run())


def test_5_seen_new_items_fold_under_new_after_a_restart(ctx):
    f = _fixture(ctx)
    _look_and_leave(ctx)
    marker_keys = set(json.loads((ctx.paths.state / "inbox_seen.json").read_text()))
    rows = build(ctx).panels["Inbox"]  # the next start
    new = [r for r in rows if r.kind in ("message", "done")]
    assert all(r.data.get("under") == EARLIER_FOLD and r.data.get("folded") for r in new)
    assert [(r.kind, r.data["id"]) for r in new] == [("message", f["report"]), ("done", f["goal"])]  # newest first
    fold = next(r for r in rows if r.key == EARLIER_FOLD)
    assert fold.text.plain == "(2 earlier, seen) ▸"
    heads = [r.text.plain for r in rows if r.kind == "heading"]
    assert heads == ["NEEDS YOU", "NEW", "FRICTION"]
    i = rows.index(fold)
    assert rows[i - 1].text.plain == "NEW"  # under New
    assert all(r.text.style == "" and {str(s.style) for s in r.text.spans} <= {"bright_black"} for r in new)  # dim
    assert "seen already" in new[0].detail().plain
    # nothing new is stored: the same marker keys as v0.16.0
    assert marker_keys <= {"upto", "friction_upto", "friction_seen"}
    assert set(json.loads((ctx.paths.state / "inbox_seen.json").read_text())) == marker_keys


def test_5_the_history_covers_seven_days(ctx, clock):
    _fixture(ctx)
    _look_and_leave(ctx)
    clock.advance(days=6, hours=23)
    assert "(2 earlier, seen) ▸" in [r.text.plain for r in build(ctx).panels["Inbox"]]
    clock.advance(hours=2)
    assert not [r for r in build(ctx).panels["Inbox"] if r.key == EARLIER_FOLD]
    assert not [r for r in build(ctx).panels["Inbox"] if r.data.get("under") == EARLIER_FOLD]


def test_5_xt_inbox_prints_what_it_did_before(ctx, monkeypatch, capsys):
    _fixture(ctx)
    _look_and_leave(ctx)
    out = _xt_inbox(ctx, monkeypatch, capsys, False)
    assert "earlier" not in out and "v0.15.0: all seven cards closed" not in out


def test_4_space_and_enter_open_and_fold_both_seen_folds(ctx):
    f = _fixture(ctx)
    _look_and_leave(ctx)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            p = app.panel(INBOX)
            assert app.focused is p
            for key, ids in ((EARLIER_FOLD, [f["report"], f["goal"]]), (FRICTION_FOLD, sorted(f["unread"] + f["seen"], reverse=True))):
                under = lambda: [r.data["id"] for r in p.rows if r.data.get("under") == key]
                assert under() == []
                p.highlighted = next(i for i, r in enumerate(p.rows) if r.key == key)
                await pilot.press("space")
                await pilot.pause()
                assert under() == ids, key
                assert "▾" in str(p.get_option_at_index(p.highlighted).prompt)
                await pilot.press("down")  # a row under the fold: space folds it and selects the fold row
                assert p.current.data.get("under") == key
                await pilot.press("space")
                await pilot.pause()
                assert under() == [] and p.current.key == key
                await pilot.press("enter")  # enter still opens it too
                await pilot.pause()
                assert under() == ids
                await pilot.press("enter")
                await pilot.pause()
                assert under() == []
                assert app.focused is p

    _run(run())


# --- 5b answered questions under Needs you ----------------------------------------------------------------


def test_5b_an_answer_given_in_the_tui_is_in_the_answered_fold_after_a_restart(ctx):
    f = _fixture(ctx)

    async def answer():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            p = app.panel(INBOX)
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "question")
            await pilot.press("s")
            await pilot.pause()
            await pilot.press("1", "ctrl+s")  # option 1, recorded as its full text
            await pilot.pause()
            assert not [r for r in p.rows if r.kind == "question"]

    _run(answer())
    # no new state: the marker keeps v0.16.0's keys
    assert set(json.loads((ctx.paths.state / "inbox_seen.json").read_text())) <= {"upto", "friction_upto",
                                                                                   "friction_seen"}

    async def restart():
        app = _app(ctx)  # a fresh TUI
        async with app.run_test(size=(160, 40)) as pilot:
            p = app.panel(INBOX)
            rows = p.all_rows
            heads = [r.text.plain for r in rows if r.kind == "heading"]
            assert heads[0] == "NEEDS YOU"
            fold = next(i for i, r in enumerate(rows) if r.key == ANSWERED_FOLD)
            assert rows[fold].text.plain == "(1 answered, last 7 days) ▸"
            assert rows.index(next(r for r in rows if r.text.plain == "NEW")) > fold  # under Needs you
            assert not [r for r in p.rows if r.kind == "answered"]  # folded at first
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.key == ANSWERED_FOLD)
            await pilot.press("space")
            await pilot.pause()
            shown = [r for r in p.rows if r.kind == "answered"]
            assert [r.data["id"] for r in shown] == [f["q"]]
            assert shown[0].text.plain.startswith(f"✓ #{f['q']} How should goal #9 finish? → 1: Close it")
            await pilot.press("down")
            text = "\n".join(_shown(app))
            assert "Options:" in text and "1. Close it — done now" in text  # the question with its options
            assert "your answer" in text and "Option 1: Close it — done now" in text
            assert isinstance(app.detail_view, ThreadDetail) and "◀ you are here" in text  # the thread
            await pilot.press("space")  # folds it again from a row under it
            await pilot.pause()
            assert not [r for r in p.rows if r.kind == "answered"] and p.current.key == ANSWERED_FOLD
            await pilot.press("enter")
            await pilot.pause()
            assert [r.kind for r in p.rows].count("answered") == 1

    _run(restart())


def test_5b_answers_newest_first_for_seven_days_and_open_questions_stay_in_needs_you(ctx, clock):
    from xt.dispatch import send
    from xt.tui.model import answer_text

    add = lambda text: send(ctx, "liaison", "human", "ask", text)[0]["id"]
    q1, q2, q3 = add("First question?"), add("Second question?"), add("Still open?")
    actions = LiveActions(ctx)
    actions.answer(q1, "yes, the first")
    clock.advance(days=1)
    actions.answer(q2, "no, the second")
    rows = build(ctx).panels["Inbox"]
    answered = [r for r in rows if r.kind == "answered"]
    assert [r.data["id"] for r in answered] == [q2, q1]  # newest answer first
    assert [r.data["id"] for r in rows if r.kind == "question"] == [q3]
    assert answered[0].text.plain.startswith(f"✓ #{q2} Second question? → no, the second")
    clock.advance(days=6, hours=1)  # q1's answer is over 7 days old
    assert [r.data["id"] for r in build(ctx).panels["Inbox"] if r.kind == "answered"] == [q2]
    assert answer_text("Option 2: Retry — one more day") == "2: Retry"
    assert answer_text("free text\nmore") == "free text"


def test_5b_xt_inbox_prints_what_it_did_before(ctx, monkeypatch, capsys):
    f = _fixture(ctx)
    LiveActions(ctx).answer(f["q"], "1")
    out = _xt_inbox(ctx, monkeypatch, capsys, False)
    assert "answered" not in out and "How should goal #9 finish?" not in out


# --- 6 mouse --------------------------------------------------------------------------------------------


def test_6_a_click_on_a_team_agent_selects_it_and_focuses_team(ctx, fake_home):
    _team(ctx, fake_home)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            assert app.focused is app.panel(INBOX)
            await _click(pilot, *_agent_at(app, "qa"))
            assert app.focused is app.team and app.team.selected == "qa"
            assert app.query_one("#detail-body").content.plain.startswith("qa")
            await _click(pilot, *_agent_at(app, "lead"))
            assert app.team.selected == "lead" and app.focused is app.team
            await pilot.press("enter")
            assert app.focused.id == "detail"

    _run(run())


def test_6_a_click_on_a_flow_row_selects_it_and_focuses_flow(ctx, clock):
    m = _flow_fixture(ctx, clock)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            pane = app.panel(FLOW)
            target = next(i for i in pane.message_rows()[:-1] if pane.top <= i and pane.rows[i][1]["id"] == m["done"])
            await _click(pilot, *_flow_row_at(pane, target))
            assert app.focused is pane and pane.selected == target and not pane.follow
            assert f"#{m['done']}" in app.query_one("#detail-body").content.plain.split("\n")[0]
            await pilot.press(str(DETAIL))
            assert app.focused.id == "detail"

    _run(run())


def test_6_a_click_in_the_inbox_or_work_keeps_focus_there_while_detail_updates(ctx, clock):
    from xt.goaldone import seen_upto

    f = _work_fixture(ctx, clock)
    seen_upto(ctx)  # the first run: the reports below are New
    ctx.ledger.append("liaison", "human", "report", "first report")
    ctx.ledger.append("liaison", "human", "report", "second report")

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            p = app.panel(INBOX)
            second = next(i for i, r in enumerate(p.rows) if "first report" in r.text.plain)
            await _click(pilot, *_option_at(p, second))
            assert app.focused is p and p.highlighted == second
            assert "first report" in app.query_one("#detail-body").content.plain
            w = app.panel(WORK)
            row = next(i for i, r in enumerate(w.rows) if r.key == f"task:{f['t_done']}")
            await _click(pilot, *_option_at(w, row))
            assert app.focused is w and w.highlighted == row
            assert "finished part" in app.query_one("#detail-body").content.plain
            await pilot.press("enter")
            assert app.focused.id == "detail"
            await pilot.press("escape", "4")
            assert app.focused.id == "detail"

    _run(run())


def test_6_the_wheel_scrolls_flow_and_the_selection_stays_in_view(ctx, clock):
    for i in range(60):
        ctx.ledger.append("lead", "liaison", "report", f"progress {i}")

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            pane = app.panel(FLOW)
            bottom = pane.top
            assert pane.follow and bottom > 0
            await _wheel(pilot, pane, down=False)
            assert pane.top == bottom - pane.WHEEL_ROWS and not pane.follow
            assert pane.top <= pane.selected < pane.top + pane.view_height()
            assert app.focused is app.panel(INBOX)  # the wheel doesn't move focus
            await _wheel(pilot, pane, down=True)
            assert pane.top == bottom

    _run(run())


def test_6_the_wheel_scrolls_a_long_thread_in_detail(ctx, clock):
    g = ctx.ledger.append("liaison", "lead", "goal", "A goal with a long thread")["id"]
    for i in range(40):
        ctx.ledger.append("lead", "liaison", "report", f"step {i}", ref=g)

    async def run():
        app = _app(ctx)
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(FLOW), "g")  # the goal, oldest: the thread's later rows are hidden
            await pilot.pause()
            assert isinstance(app.detail_view, ThreadDetail)
            body = lambda: "\n".join(_shown(app))
            before = body()
            assert "later rows hidden" in before
            await _wheel(pilot, app.query_one("#detail"), down=True)
            assert body() != before and app.detail_view.offset is not None  # the thread moved
            assert app.focused is app.panel(FLOW)  # the wheel doesn't move focus

    _run(run())
