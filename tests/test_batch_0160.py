"""v0.16.0: #127 Inbox groups and friction read state; #132 rows cut at pane width, with ages."""

import asyncio
import io
import json
import sys

import pytest
from rich.text import Text

from xt import cli, inbox
from xt.alerts import Alerts
from xt.choices import render
from xt.dispatch import send
from xt.spawn import request_spawn
from xt.tui.app import LiveActions, XtTui
from xt.tui.model import PANELS, Row, Snapshot, age_text, build, fit

from .conftest import add_member

INBOX = PANELS.index("Inbox") + 1


def _run(coro):
    asyncio.run(coro)


def _friction(ctx, n, text="the sandbox refused a plain curl", sender="carol"):
    return [ctx.ledger.append(sender, "human", "friction", f"{text} ({i})")["id"] for i in range(n)]


def _fixture(ctx):
    """One open question, one alert, two new items (a goal done, a report), three unread and twelve
    seen friction items (the twelve predate the first run)."""
    add_member(ctx, "carol")
    ctx.herdr.add("liaison")
    seen = _friction(ctx, 12, "old friction")
    inbox.friction_marker(ctx)  # the first run on this ledger: the twelve count as seen
    from xt.goaldone import seen_upto

    seen_upto(ctx)
    q, _ = send(ctx, "liaison", "human", "ask", render("How should goal #9 finish?",
                                                       ["Close it :: done now", "Retry :: one more day",
                                                        "Drop it :: nothing ships"], 1))
    Alerts(ctx).raise_("blocked:carol", "carol is blocked (usually an approval prompt)")
    goal = ctx.ledger.append("liaison", "lead", "goal", "Site check for #124")["id"]
    done = ctx.ledger.append("lead", "liaison", "done", "Site checked, all good", ref=goal)["id"]
    report = ctx.ledger.append("liaison", "human", "report", "v0.15.0: all seven cards closed")["id"]
    unread = _friction(ctx, 3, "new friction")
    return {"q": q["id"], "goal": goal, "done": done, "report": report, "unread": unread, "seen": seen}


def _groups(rows):
    out, cur = {}, None
    for r in rows:
        if r.kind == "heading":
            cur = r.text.plain
            out[cur] = []
        else:
            out[cur].append(r)
    return out


def _as_human(monkeypatch, ctx, human=True):
    class Tty(io.StringIO):
        def isatty(self):
            return human

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))


def _xt_inbox(ctx, monkeypatch, capsys, human=True, *argv):
    _as_human(monkeypatch, ctx, human)
    cli.cmd_inbox(cli.build_parser().parse_args(["inbox", *argv]))
    return capsys.readouterr().out


def _marker(ctx):
    path = ctx.paths.state / "inbox_seen.json"
    return path.read_text() if path.exists() else None


# --- #127 Inbox groups and friction read state ----------------------------------------------------


def test_the_three_groups_in_order_with_the_seen_friction_folded(ctx):
    f = _fixture(ctx)
    g = _groups(build(ctx).panels["Inbox"])
    assert list(g) == ["NEEDS YOU", "NEW", "FRICTION"]
    assert [r.kind for r in g["NEEDS YOU"]] == ["question", "alert"]
    assert "3 options" in g["NEEDS YOU"][0].text.plain and g["NEEDS YOU"][0].text.plain.startswith("⚑ ")
    assert [(r.kind, r.data["id"]) for r in g["NEW"]] == [("message", f["report"]), ("done", f["goal"])]
    friction = g["FRICTION"]
    assert [r.data["id"] for r in friction if r.kind == "friction" and not r.data["seen"]] == f["unread"][::-1]
    fold = next(r for r in friction if r.kind == "fold")
    assert fold.text.plain == "(12 older, seen) ▸"
    folded = [r.data["id"] for r in friction if r.data.get("folded")]
    assert folded == f["seen"][::-1]  # newest first


def test_the_fold_row_expands_and_folds_in_the_tui(ctx):
    f = _fixture(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            p = app.panel(INBOX)
            assert not any(r.data.get("folded") for r in p.rows)  # folded at first
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "fold")
            await pilot.press("enter")
            await pilot.pause()
            shown = [r.data["id"] for r in p.rows if r.data.get("folded")]
            assert shown == f["seen"][::-1]
            fold = next(i for i, r in enumerate(p.rows) if r.kind == "fold")
            assert "(12 older, seen) ▾" in str(p.get_option_at_index(fold).prompt)
            assert p.current.kind == "fold"
            await pilot.press("enter")
            await pilot.pause()
            assert not any(r.data.get("folded") for r in p.rows)

    _run(run())


def test_title_counts_equal_the_group_sizes_and_zero_is_left_out(ctx):
    _fixture(ctx)
    snap = build(ctx)
    g = _groups(snap.panels["Inbox"])
    unread = [r for r in g["FRICTION"] if r.kind == "friction" and not r.data["seen"]]
    assert snap.inbox_title == f"⚑ {len(g['NEEDS YOU'])} · ✉ {len(g['NEW'])} · ✱ {len(unread)}" == "⚑ 2 · ✉ 2 · ✱ 3"

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)):
            assert app.panel(INBOX).border_title == "[4]─Inbox─⚑ 2 · ✉ 2 · ✱ 3"

    _run(run())


def test_an_empty_group_and_its_count_are_not_shown(ctx):
    inbox.friction_marker(ctx)
    _friction(ctx, 2)
    snap = build(ctx)
    assert list(_groups(snap.panels["Inbox"])) == ["FRICTION"]
    assert snap.inbox_title == "✱ 2"
    empty = XtTui(lambda: Snapshot({}, Text("")))

    async def run():
        async with empty.run_test(size=(160, 40)):
            assert empty.panel(INBOX).border_title == "[4]─Inbox"

    _run(run())


def test_the_first_run_on_an_old_ledger_shows_no_unread_friction(ctx):
    _friction(ctx, 5)
    snap = build(ctx)
    g = _groups(snap.panels["Inbox"])
    assert not [r for r in g["FRICTION"] if r.kind == "friction" and not r.data["seen"]]
    assert g["FRICTION"][0].text.plain == "(5 older, seen) ▸" and "✱" not in snap.inbox_title


def test_the_supervisors_first_run_starts_the_friction_marker(ctx):
    from xt.watch import Supervisor

    _friction(ctx, 2)
    Supervisor(ctx, out=lambda s: None).notify_human(0)
    new = _friction(ctx, 1)
    rows = build(ctx).panels["Inbox"]
    assert [r.data["id"] for r in rows if r.kind == "friction" and not r.data["seen"]] == new


async def _scroll_through_inbox(pilot, app):
    """The Inbox pane is a few rows high in the current layout: move down to its last row."""
    await pilot.press(str(INBOX))
    await pilot.pause()
    for _ in range(len(app.panel(INBOX).rows)):
        await pilot.press("j")
        await pilot.pause()


def test_viewing_the_inbox_marks_the_friction_seen_for_the_next_start(ctx):
    f = _fixture(ctx)

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await _scroll_through_inbox(pilot, app)
            await pilot.press("1")  # leaving the Inbox
            await pilot.pause()

    _run(look())
    rows = build(ctx).panels["Inbox"]  # the next start
    assert not [r for r in rows if r.kind == "friction" and not r.data["seen"]]
    assert next(r for r in rows if r.kind == "fold").text.plain == "(15 older, seen) ▸"
    assert set(f["unread"]) <= inbox.friction_marker(ctx)[1]


def test_quitting_from_the_inbox_marks_the_friction_seen_too(ctx):
    _fixture(ctx)

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await _scroll_through_inbox(pilot, app)
            await pilot.press("q")

    _run(look())
    assert not [r for r in build(ctx).panels["Inbox"] if r.kind == "friction" and not r.data["seen"]]


def test_friction_below_the_panes_edge_stays_unread_after_a_look(ctx):
    f = _fixture(ctx)  # 11 Inbox rows; the pane shows 3 at 160x40

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            await pilot.pause()
            await pilot.press("1")

    _run(look())
    assert inbox.friction_marker(ctx)[1] == set()


def test_friction_never_in_view_stays_unread(ctx):
    inbox.friction_marker(ctx)
    ids = _friction(ctx, 40)

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press(str(INBOX))
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()

    _run(look())
    seen = inbox.friction_marker(ctx)[1]
    assert seen and ids[-1] in seen  # the newest, at the top, were in view
    assert ids[0] not in seen  # the oldest were below the pane's bottom edge


def test_c_marks_one_friction_seen_at_once(ctx):
    f = _fixture(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            p = app.panel(INBOX)
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "friction")
            target = p.current.data["id"]
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            assert f"friction #{target} marked seen" in app.status
            assert target in inbox.friction_marker(ctx)[1]
            unread = [r.data["id"] for r in p.rows if r.kind == "friction" and not r.data["seen"]]
            assert target not in unread and len(unread) == 2
            assert "(13 older, seen)" in next(r.text.plain for r in p.all_rows if r.kind == "fold")
            assert app.panel(INBOX).border_title.endswith("✱ 2")

    _run(run())


def test_needs_you_stays_across_restarts_until_resolved(ctx):
    f = _fixture(ctx)
    request_spawn(ctx, "lead", "dora", "claude", None, "worker", None)

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            await pilot.pause()
            await pilot.press("q")

    for _ in range(2):  # two sessions, each looking at the Inbox
        _run(look())
    kinds = [r.kind for r in _groups(build(ctx).panels["Inbox"])["NEEDS YOU"]]
    assert kinds == ["question", "approval", "alert"]
    Alerts(ctx).resolve("blocked:carol")
    send(ctx, "liaison", "human", "done", "withdrawn", f["q"])
    kinds = [r.kind for r in _groups(build(ctx).panels["Inbox"])["NEEDS YOU"]]
    assert kinds == ["approval"]


def test_alert_rows_in_needs_you_show_the_warning_glyph(ctx):
    _fixture(ctx)
    alert = next(r for r in build(ctx).panels["Inbox"] if r.kind == "alert")
    assert alert.text.plain.startswith("⚠ carol is blocked")


def test_xt_inbox_prints_the_same_groups(ctx, monkeypatch, capsys):
    f = _fixture(ctx)
    out = _xt_inbox(ctx, monkeypatch, capsys, False)
    heads = [ln for ln in out.splitlines() if not ln.startswith(" ")]
    assert heads == ["Needs you:", "New since you last looked:", "Friction reported about xt or a harness:"]
    needs = out.split("Needs you:")[1].split("New since")[0]
    assert f"⚑ #{f['q']}" in needs and "3 options" in needs and "⚠ #" in needs and "carol is blocked" in needs
    new = out.split("New since you last looked:")[1].split("Friction")[0]
    assert new.index(f"✉ #{f['report']}") < new.index(f"✓ #{f['goal']}")  # newest first, as in the TUI
    friction = out.split("Friction reported about xt or a harness:")[1]
    assert [int(ln.split("#")[1].split()[0]) for ln in friction.splitlines() if "✱" in ln] == f["unread"][::-1]
    assert "(12 older, seen; xt inbox --seen lists them)" in friction


def test_an_agents_xt_inbox_changes_no_marker(ctx, monkeypatch, capsys):
    _fixture(ctx)
    before = _marker(ctx)
    for _ in range(2):
        out = _xt_inbox(ctx, monkeypatch, capsys, False)
        assert "new friction" in out and "New since" in out
    assert _marker(ctx) == before


def _first_run(ctx):
    """What the supervisor's first run on 0.16.0 does: both Inbox markers start at the log's end."""
    from xt.goaldone import seen_upto

    seen_upto(ctx)
    inbox.friction_marker(ctx)


def test_criterion_5a_the_humans_xt_inbox_marks_what_it_showed_seen(ctx, monkeypatch, capsys):
    _first_run(ctx)
    ids = _friction(ctx, 3)
    before = _marker(ctx)
    out = _xt_inbox(ctx, monkeypatch, capsys, False)  # an agent's listing: nothing changes
    assert all(f"✱ #{i} " in out for i in ids) and _marker(ctx) == before
    assert len([r for r in build(ctx).panels["Inbox"] if r.kind == "friction" and not r.data["seen"]]) == 3
    out = _xt_inbox(ctx, monkeypatch, capsys)  # the human's own listing shows them
    assert all(f"✱ #{i} " in out for i in ids)
    out = _xt_inbox(ctx, monkeypatch, capsys)  # the next listing: folded as seen
    assert "✱" not in out and "(3 older, seen;" in out
    rows = build(ctx).panels["Inbox"]
    assert next(r for r in rows if r.kind == "fold").text.plain == "(3 older, seen) ▸"
    assert not [r for r in rows if r.kind == "friction" and not r.data["seen"]]


def test_criterion_5a_friction_the_humans_listing_did_not_show_stays_unread(ctx, monkeypatch, capsys):
    inbox.friction_marker(ctx)
    ids = _friction(ctx, 3)
    out = _xt_inbox(ctx, monkeypatch, capsys, True, "--limit", "1")  # shows only the newest
    assert f"✱ #{ids[2]} " in out and f"#{ids[0]} " not in out and "… 2 more" in out
    unread = [r.data["id"] for r in build(ctx).panels["Inbox"] if r.kind == "friction" and not r.data["seen"]]
    assert unread == [ids[1], ids[0]]
    out = _xt_inbox(ctx, monkeypatch, capsys, True, "--seen")
    assert "(1 older, seen)" in out and f"#{ids[2]} " in out.split("(1 older, seen)")[1]


def test_an_empty_inbox_says_so(ctx, monkeypatch, capsys):
    assert _xt_inbox(ctx, monkeypatch, capsys, False).strip() == "Nothing for you."


def test_the_marker_keeps_the_done_marker_and_drops_the_oldest_ids(ctx, monkeypatch):
    from xt import goaldone

    goaldone.mark_seen(ctx, 7)
    upto, _ = inbox.friction_marker(ctx)
    monkeypatch.setattr(inbox, "KEEP_SEEN", 3)
    inbox.mark_friction_seen(ctx, [upto + 1, upto + 2, upto + 4, upto + 5, upto + 6])
    d = json.loads(_marker(ctx))
    assert d["upto"] == 7 and d["friction_upto"] == upto + 2 and d["friction_seen"] == [upto + 4, upto + 5, upto + 6]
    goaldone.mark_seen(ctx, 9)
    assert json.loads(_marker(ctx))["friction_seen"] == [upto + 4, upto + 5, upto + 6]


@pytest.mark.parametrize("size", [(160, 40), (100, 30)])
def test_no_row_spills_outside_its_pane(ctx, size):
    _fixture(ctx)
    ctx.ledger.append("liaison", "human", "report", "漢字のテスト " * 40)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(INBOX))
            await pilot.pause()
            for n in range(1, len(PANELS) + 1):
                p = app.panel(n)
                for i in range(p.option_count):
                    assert p.get_option_at_index(i).prompt.cell_len <= p.content_size.width, (n, i)

    _run(run())


# --- #132 rows cut at pane width, with ages -------------------------------------------------------


@pytest.mark.parametrize("secs, shown", [
    (3, "now"), (9, "now"), (10, "10s"), (45, "45s"), (59, "59s"), (60, "1m"), (14 * 60, "14m"),
    (59 * 60 + 59, "59m"), (3600, "1h"), (3 * 3600, "3h"), (23 * 3600 + 59 * 60, "23h"), (86400, "1d"),
    (2 * 86400, "2d"), (59 * 86400, "59d"), (60 * 86400, "8w"), (63 * 86400, "9w"),
])
def test_the_age_rule_boundaries(secs, shown):
    assert age_text(secs) == shown


def test_rows_age_with_the_refresh(ctx, clock):
    """The TUI reads the last 30 days, so weeks show only through the rule itself (above)."""
    inbox.friction_marker(ctx)
    _friction(ctx, 1)
    ages = lambda: [r.age for r in build(ctx).panels["Inbox"] if r.kind == "friction"]
    for step, shown in [(dict(seconds=9), "now"), (dict(seconds=1), "10s"), (dict(seconds=50), "1m"),
                        (dict(hours=23, minutes=59), "1d"), (dict(days=28), "29d")]:
        clock.advance(**step)
        assert ages() == [shown]


def _long_short(ctx):
    inbox.friction_marker(ctx)
    long_id = ctx.ledger.append("carol", "human", "friction", "long " + "word " * 80 + "END")["id"]
    short_id = ctx.ledger.append("carol", "human", "friction", "short line")["id"]
    return long_id, short_id


def _prompt(app, row_id) -> Text:
    p = app.panel(INBOX)
    i = next(i for i, r in enumerate(p.rows) if r.data.get("id") == row_id and r.kind == "friction")
    return p.get_option_at_index(i).prompt


@pytest.mark.parametrize("size", [(160, 40), (100, 30)])
def test_a_long_line_fills_the_row_to_the_pane_edge_and_a_short_one_is_not_cut(ctx, size):
    long_id, short_id = _long_short(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            width = app.panel(INBOX).content_size.width
            long, short = _prompt(app, long_id), _prompt(app, short_id)
            assert long.cell_len == width and long.plain.endswith("… now")
            assert "END" not in long.plain
            assert short.cell_len == width and "…" not in short.plain and short.plain.endswith(" now")
            assert short.plain.startswith(f"✱ #{short_id} carol: short line ")

    _run(run())


def test_a_resize_re_cuts_the_rows(ctx):
    long_id, _ = _long_short(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            wide = _prompt(app, long_id)
            await pilot.resize_terminal(100, 30)
            await pilot.pause()
            narrow = _prompt(app, long_id)
            width = app.panel(INBOX).content_size.width
            assert narrow.cell_len == width < wide.cell_len
            assert narrow.plain.endswith("… now")

    _run(run())


def test_wide_characters_are_cut_by_cell_width():
    text = Text("✱ #1 carol: " + "漢字" * 60)
    for width in (40, 41, 57):
        line = fit(text, "3h", width)
        assert line.cell_len == width and line.plain.endswith(" 3h") and "…" in line.plain
    assert fit(Text("漢字"), "", 10).cell_len == 4  # short: untouched, no …


def test_the_age_never_overwrites_the_text():
    line = fit(Text("x" * 30), "12m", 20)
    assert line.plain == "x" * 15 + "… 12m"
    assert fit(Text("abc"), "12m", 4).plain == "abc"  # too narrow for both: the text wins
    assert fit(Text("abcdef"), "now", 12).plain == "abcdef   now"


def test_goal_rows_show_the_age_of_their_newest_activity(ctx, clock):
    g = ctx.ledger.append("liaison", "lead", "goal", "Build it")["id"]
    clock.advance(hours=3)
    t = ctx.ledger.append("lead", "carol", "task", "part one", ref=g)["id"]
    clock.advance(minutes=20)
    ctx.ledger.append("carol", "lead", "report", "halfway", ref=t)
    clock.advance(minutes=5)
    snap = build(ctx)
    goal = next(r for r in snap.panels["Goals"] if r.kind == "goal")
    task = next(r for r in snap.panels["Tasks"] if r.kind == "task")
    assert goal.age == "5m" and task.age == "25m"


def test_team_and_supervisor_rows_carry_no_age(ctx):
    from xt.watch import Supervisor

    Supervisor(ctx, out=lambda s: None).say("woke scout (every 60m)")
    snap = build(ctx)
    assert all(r.age == "" for r in snap.panels["Team"] + snap.panels["Supervisor"])
    assert snap.panels["Supervisor"][0].text.plain[2] == ":"  # its clock time instead


def test_the_focused_panels_title_is_reversed_and_follows_focus(ctx):
    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            style = lambda n: app.panel(n).styles.border_title_style
            assert style(1).reverse and not style(INBOX).reverse
            await pilot.press(str(INBOX))
            await pilot.pause()
            assert style(INBOX).reverse and not style(1).reverse

    _run(run())


def test_group_headings_are_skipped_by_the_cursor(ctx):
    _fixture(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            p = app.panel(INBOX)
            assert p.current.kind == "question" and p.border_subtitle.startswith("1 of ")
            await pilot.press("k")
            assert p.current.kind == "question"  # nothing selectable above
            await pilot.press("j", "j")
            await pilot.pause()
            assert p.current.kind == "message"  # past the NEW heading

    _run(run())
