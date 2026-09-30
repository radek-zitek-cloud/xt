"""v0.16.0: #127 Inbox groups and friction read state; #132 rows cut at pane width, with ages;
#128 Team pane; #129 Work outline; #131 Detail thread and the Supervisor pop-up."""

import asyncio
import io
import json
import re
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
WORK = PANELS.index("Work") + 1
FLOW = PANELS.index("Flow") + 1


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
            assert app.panel(INBOX).border_title == f"[{INBOX}]─Inbox─⚑ 2 · ✉ 2 · ✱ 3"

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
            assert empty.panel(INBOX).border_title == f"[{INBOX}]─Inbox"

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
            await pilot.press(str(WORK))  # leaving the Inbox
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
    f = _fixture(ctx)
    more = _friction(ctx, 20, "more friction")  # 31 Inbox rows; the pane shows about 11 at 160x40

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            await pilot.pause()
            await pilot.press(str(WORK))

    _run(look())
    seen = inbox.friction_marker(ctx)[1]
    assert more[-1] in seen  # the newest, at the top of the group
    assert not seen & set(f["unread"]) and more[0] not in seen  # below the pane's bottom edge


def test_friction_never_in_view_stays_unread(ctx):
    inbox.friction_marker(ctx)
    ids = _friction(ctx, 40)

    async def look():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(100, 30)) as pilot:
            await pilot.press(str(INBOX))
            await pilot.pause()
            await pilot.press(str(WORK))
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
            for n in (INBOX, WORK):
                p = app.panel(n)
                for i in range(p.option_count):
                    assert p.get_option_at_index(i).prompt.cell_len <= p.content_size.width, (n, i)
            flow = app.panel(FLOW)  # Flow draws its own rows (card #130)
            assert all(ln.cell_len <= flow.content_size.width for ln in flow.render().split("\n"))

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
    goal = next(r for r in snap.panels["Work"] if r.kind == "goal")
    task = next(r for r in snap.panels["Work"] if r.kind == "task")
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
            assert style(INBOX).reverse and not style(WORK).reverse  # the Inbox first (card #130)
            await pilot.press(str(WORK))
            await pilot.pause()
            assert style(WORK).reverse and not style(INBOX).reverse
            await pilot.press(str(FLOW))
            await pilot.pause()
            assert style(FLOW).reverse and not style(WORK).reverse

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


# --- #128 Team pane replaces Status and Team -------------------------------------------------------

CLAUDE_MEMBERS = [("pm", "claude-sonnet-5-5"), ("builder", "claude-opus-5-5"), ("qa", None)]


def _codex_session(home, ctx, name, used, model="gpt-5.2-codex", window=258000):
    """A Codex session log whose turn_context names the real model (`default` in team.toml)."""
    from .test_context_usage import _prompt

    d = home / ".codex/sessions/2026/09/28"
    d.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "session_meta", "payload": {"cwd": str(ctx.paths.root), "source": "vscode"}},
             {"type": "response_item", "payload": {"role": "user", "content": [{"text": _prompt(ctx, name)}]}}]
    if model:
        lines.append({"type": "turn_context", "payload": {"model": model}})
    lines.append({"timestamp": "2026-09-28T08:00:00Z", "type": "event_msg",
                  "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": used},
                                                              "last_token_usage": {"total_tokens": used},
                                                              "model_context_window": window}}})
    (d / f"rollout-{name}-m.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")


def _windows(ctx):
    """Real usage windows: Codex's 7d from its logs, Claude's 5h; Claude's 7d reading is stale (missing)."""
    now = ctx.ledger.clock().timestamp()
    ctx.paths.state.mkdir(parents=True, exist_ok=True)
    (ctx.paths.state / "allowance.json").write_text(json.dumps({"codex": {
        "primary": {"used_percent": 64.0, "window_minutes": 10080, "resets_at": int(now + 3 * 86400)}}}))
    (ctx.paths.state / "claude_plan.json").write_text(json.dumps({
        "five_hour": {"used_percentage": 6.0, "resets_at": int(now + 3 * 3600), "observed_at": int(now - 120)},
        "seven_day": {"used_percentage": 10.0, "resets_at": int(now + 4 * 86400), "observed_at": int(now - 5 * 3600)},
    }))


def _team(ctx, home, extra_claude=0, extra_codex=0):
    """Five agents on two harnesses: liaison and lead on Codex (`default`, one with a session log
    naming its model), pm, builder and qa on Claude (qa on `default` with no session log)."""
    from .test_context_usage import claude_session

    for name, model in CLAUDE_MEMBERS + [(f"c{i}", "claude-sonnet-5-5") for i in range(extra_claude)]:
        (ctx.paths.roles / "worker.md").write_text("# Role: worker\n")
        ctx.team.upsert_agent(name, "worker", "claude", model, "lead")
    for i in range(extra_codex):
        ctx.team.upsert_agent(f"x{i}", "worker", "codex", None, "lead")
    ctx.team.save()
    ctx.reload_team()
    for a in ctx.team.agents():
        if a.kind != "human":
            ctx.herdr.add(a.name, "working" if a.name == "lead" else "idle")
    _codex_session(home, ctx, "lead", 181_000)
    claude_session(home, ctx, "pm", model="claude-sonnet-5-5")
    claude_session(home, ctx, "builder", model="claude-opus-5-5")
    _windows(ctx)


def _pane(app):
    return [ln.rstrip() for ln in str(app.team.render()).splitlines()]


def _lines(ctx, width):
    from xt.tui import teampane

    snap = build(ctx)
    lines, _ = teampane.render(snap.header, snap.spend, snap.harnesses, [r.data for r in snap.panels["Team"]],
                               width, ctx.ledger.clock())
    return lines


def test_short_models_drop_the_vendor_and_default_becomes_the_real_model():
    from xt.tui.teampane import short_model, shown_model

    assert short_model("claude-sonnet-5-5") == "sonnet 5.5"
    assert short_model("claude-opus-5-5") == "opus 5.5"
    assert short_model("claude-haiku-4-5-20251001") == "haiku 4.5"
    assert short_model("anthropic/claude-opus-4-8") == "opus 4.8"
    assert short_model("gpt-5.2-codex") == "gpt-5.2-codex" and short_model("kimi") == "kimi"
    assert shown_model("default", "gpt-5.2-codex") == "gpt-5.2-codex"
    assert shown_model(None, "claude-opus-5-5") == "opus 5.5"
    assert shown_model("default", None) == "default"
    assert shown_model("claude-sonnet-5-5", "claude-opus-5-5") == "sonnet 5.5"  # configured wins


def test_codex_default_shows_the_model_from_its_own_session_log(ctx, fake_home):
    _team(ctx, fake_home)
    team = {r.data["name"]: r.data for r in build(ctx).panels["Team"]}
    assert team["lead"]["model"] == "gpt-5.2-codex"  # `default` in team.toml, turn_context in the log
    assert team["liaison"]["model"] == "default"  # no session log to read it from
    assert team["qa"]["model"] == "default"
    assert team["pm"]["model"] == "sonnet 5.5" and team["builder"]["model"] == "opus 5.5"


def test_the_codex_model_is_found_in_the_head_when_the_tail_has_none(ctx, fake_home, monkeypatch):
    from xt import usage

    _team(ctx, fake_home)
    monkeypatch.setattr(usage, "codex_model", lambda lines, real=usage.codex_model:
                        None if len(lines) == 4 and '"token_count"' in lines[0] else real(lines))
    assert usage.reading(ctx, "lead").model == "gpt-5.2-codex"


def test_status_and_team_panes_are_gone_and_team_shows_header_blocks_and_agents(ctx, fake_home):
    _team(ctx, fake_home)
    _first_run(ctx)
    send(ctx, "liaison", "human", "ask", "Which story?")
    ctx.ledger.append("liaison", "human", "report", "halfway")
    send(ctx, "liaison", "lead", "goal", "Build it")
    assert "Team" not in PANELS and not any("Status" in p for p in PANELS)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            assert not app.query("#topbar") and app.team.border_title == "Team"
            titles = [app.panel(n).title for n in range(1, len(PANELS) + 1)]
            assert titles == list(PANELS) and "Team" not in titles
            lines = _pane(app)
            head = lines[0]
            assert head.startswith("t · xt ") and "5 running" in head and "1 goal open" in head
            assert "⚑ 1 needs you" in head and "✉ 1 new" in head and head.endswith("today: no usage recorded yet")
            blocks = lines[1]
            assert blocks.startswith("CLAUDE  5h ▓") and "6% resets 15:00" in blocks
            assert "7d" not in blocks.split("CODEX")[0]  # Claude's stale 7d reading: no blank bar
            assert "CODEX  7d ▓▓▓▓▓▓░░░░  64% resets Tue" in blocks
            agents = lines[2:]
            assert len(agents) == 2  # five agents, two lines
            text = "\n".join(agents)
            for name in ("liaison", "lead", "pm", "builder", "qa"):
                assert f" {name} " in text
            assert "claude/" not in text and "codex/" not in text
            # Claude's block on the left, Codex's under its own heading on the right
            assert agents[0].index("pm") < blocks.index("CODEX") <= agents[0].index("liaison")
            assert " lead " in agents[1][blocks.index("CODEX"):]

    _run(run())


def test_agent_columns_line_up_and_bars_match_tokens_and_window(ctx, fake_home):
    from xt.tui import teampane

    _team(ctx, fake_home)
    lines = [ln.plain for ln in _lines(ctx, 158)[2:]]
    assert len(lines) == 2
    starts = [[i for i, ch in enumerate(ln) if ch == "▕"] for ln in lines]
    assert len(starts[0]) == 3 and set(starts[1]) <= set(starts[0])  # bars line up, whatever the model
    # after models of different lengths the state words still line up: sonnet 5.5 over opus 5.5 in
    # the first column, default over gpt-5.2-codex in the Codex column
    assert lines[0].index(" idle ") == lines[1].index(" idle ")
    liaison, lead = lines[0].index("● liaison"), lines[1].index("● lead")
    assert liaison == lead and lines[0].index(" idle ", liaison) == lines[1].index(" working ", lead)
    team = {r.data["name"]: r.data for r in build(ctx).panels["Team"]}
    lead = team["lead"]  # ~181k of 258k
    assert teampane.context_pct(lead) == pytest.approx(100 * 181_000 / 258_000)
    row = next(ln for ln in lines if " lead " in ln)
    cell = row[row.index("● lead"):]
    assert "~181k ▕" in cell and cell.split("▏")[1].split()[0] == "70%"
    bar = cell.split("▕")[1].split("▏")[0]
    assert bar == teampane.context_bar(181 / 258, len(bar)) and bar.count("█") == int(181 / 258 * len(bar))
    pm = next(ln for ln in lines if " pm " in ln)
    assert "41k ▕" in pm and "4%" in pm.split(" pm ")[1].split("▏")[1]  # 41k of 1M
    qa = next(ln for ln in lines if " qa " in ln)
    assert " — ▕" in qa  # no reading: no bar, no percentage


def test_a_twelve_agent_team_takes_four_lines_at_160_and_fits_at_100(ctx, fake_home):
    _team(ctx, fake_home, extra_claude=5, extra_codex=2)  # 8 on Claude, 4 on Codex
    assert len([r for r in build(ctx).panels["Team"]]) == 12

    async def run(size):
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            lines = _pane(app)
            width = app.team.content_size.width
            assert all(len(ln) <= width for ln in lines)
            assert app.team.outer_size.height == len(lines) + 2  # no empty space: content plus the frame
            laid_out = [ln.plain for ln in _lines(ctx, width) if "▕" in ln.plain]
            assert sum(ln.count("▕") for ln in laid_out) == 12  # every agent laid out
            return len(laid_out), [ln for ln in lines if "▕" in ln], app.panel(INBOX).content_size.height

    lines, shown, _ = asyncio.run(run((160, 40)))
    assert lines == 4 and len(shown) == 4  # all shown
    lines, shown, inbox_rows = asyncio.run(run((100, 30)))
    # two columns, Claude's block over Codex's; capped at 100x30 so the Inbox keeps 5 rows (card #130)
    assert lines == 6 and len(shown) < 6 and inbox_rows >= 5


def test_the_team_panes_height_follows_the_agent_count(ctx, fake_home):
    async def height():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            return app.team.outer_size.height

    _team(ctx, fake_home)
    five = asyncio.run(height())
    ctx.team.upsert_agent("c9", "worker", "claude", "claude-sonnet-5-5", "lead")
    ctx.team.upsert_agent("c8", "worker", "claude", "claude-sonnet-5-5", "lead")
    ctx.team.save()
    assert asyncio.run(height()) == five + 1  # 5 Claude agents in two columns: three lines


def test_the_toast_shows_an_actions_result_and_goes_on_its_own(ctx, fake_home, monkeypatch):
    from xt.tui.app import Toast

    assert Toast.SECONDS == 10.0  # about ten seconds in real use; shortened here
    monkeypatch.setattr(Toast, "SECONDS", 0.3)
    _team(ctx, fake_home)
    Alerts(ctx).raise_("blocked:pm", "pm is blocked (usually an approval prompt)")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            p = app.panel(INBOX)
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "alert")
            await pilot.pause()
            await pilot.press("c")
            await pilot.pause()
            toast = app.query_one(Toast)
            assert toast.display and "alert cleared" in str(toast.render())
            assert toast.size.height == 1
            assert not any("alert cleared" in ln for ln in _pane(app))  # never part of Team
            await pilot.pause(0.6)
            assert not toast.display  # gone without a key press
            assert not any("alert cleared" in ln for ln in _pane(app))

    _run(run())


def test_the_header_keeps_the_version_notices(ctx, fake_home):
    from xt import versions
    from xt.tui.model import version_text

    V = versions.Versions
    assert version_text(V("0.16.0", "", "0.16.0", "0.16.0")).plain == "xt 0.16.0 (latest)"
    assert version_text(V("0.17.0", "", "0.16.0", "0.16.0")).plain == "xt 0.16.0 (0.17.0 published)"
    assert version_text(V(None, "", "0.16.0", "0.16.0")).plain == "xt 0.16.0 (published ?)"
    old = version_text(V("0.16.0", "", "0.16.0", "0.15.0", {"lead": "0.16.0"}))
    assert old.plain == "xt 0.16.0 (latest) · running mixed: restart to update"
    assert version_text(V("0.15.0", "", "0.16.0rc2", None, {"lead": None})).plain == \
        "xt 0.16.0-rc2 (published 0.15.0) · running unknown"


def test_the_header_names_what_is_stuck_and_when_nothing_waits(ctx, clock):
    ctx.herdr.add("liaison")
    assert "nothing waiting for you" in build(ctx).header.plain
    from xt.dispatch import Queue

    msg = ctx.ledger.append("liaison", "lead", "report", "hello")
    Queue(ctx).add(msg["id"], "lead", "busy")
    clock.advance(minutes=2)
    assert "1 queued over a minute" in build(ctx).header.plain


def test_keys_follow_the_panes_that_exist(ctx, fake_home):
    from xt.tui.app import HINTS, Help

    _team(ctx, fake_home)
    assert "1-3 panes" in HINTS and "1-4" not in HINTS and "tab Team" in HINTS  # #131: no Supervisor pane
    keys = dict(Help.KEYS)
    assert keys["1-3"] == "jump to a pane: Inbox, Work, Flow"  # card #130: Flow in place of the Log

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            for n, title in enumerate(PANELS, start=1):
                await pilot.press(str(n))
                await pilot.pause()
                assert app.focused.title == title
            await pilot.press("4")  # no fourth pane since card #131: nothing happens
            assert app.focused.title == "Flow"
            await pilot.press("tab")  # past Flow, the last pane: Team, at the top
            await pilot.pause()
            assert app.focused is app.team and app.team.current.data["name"] == "pm"
            await pilot.press("j")
            await pilot.pause()
            assert app.team.current.data["name"] == "builder"
            assert app.query_one("#detail").border_title == "Detail─Team"
            assert app.team.current.detail().plain.startswith("builder · worker · claude/claude-opus-5-5")

    _run(run())


# --- #129 Work outline of goals and tasks ----------------------------------------------------------


def _work_fixture(ctx, clock):
    """The spec's fixture: 63 done goals; an open goal stuck for two days; an open goal with three
    tasks in mixed states (open, done, failed); one orphan task; a goal the lead gave a sub-lead."""
    add_member(ctx, "carol")
    add_member(ctx, "sub", role="sublead")
    add_member(ctx, "dan", reports_to="sub")
    done_goals = []
    for i in range(63):
        g = ctx.ledger.append("liaison", "lead", "goal", f"Done goal {i}")["id"]
        t = ctx.ledger.append("lead", "carol", "task", f"part of done goal {i}", ref=g)["id"]
        ctx.ledger.append("carol", "lead", "done", "finished", ref=t)
        ctx.ledger.append("lead", "liaison", "done", "all done", ref=g)
        done_goals.append(g)
        clock.advance(minutes=10)
    stuck = ctx.ledger.append("liaison", "lead", "goal", "Stuck goal: waits on a vendor")["id"]
    stuck_task = ctx.ledger.append("lead", "carol", "task", "chase the vendor", ref=stuck)["id"]
    clock.advance(days=2)
    busy = ctx.ledger.append("liaison", "lead", "goal", "Busy goal with three tasks")["id"]
    t_open = ctx.ledger.append("lead", "carol", "task", "still going", ref=busy)["id"]
    t_done = ctx.ledger.append("lead", "carol", "task", "finished part", ref=busy)["id"]
    t_failed = ctx.ledger.append("lead", "carol", "task", "the failing part", ref=busy)["id"]
    ctx.ledger.append("carol", "lead", "done", "shipped it", ref=t_done)
    ctx.ledger.append("carol", "lead", "done", "FAIL: the build breaks", ref=t_failed)
    orphan = ctx.ledger.append("lead", "carol", "task", "a task with no goal")["id"]
    sub_goal = ctx.ledger.append("lead", "sub", "goal", "Sub-lead goal: the data pipeline")["id"]
    sub_task = ctx.ledger.append("sub", "dan", "task", "load the data", ref=sub_goal)["id"]
    clock.advance(minutes=5)
    ctx.ledger.append("carol", "lead", "report", "halfway", ref=t_open)
    clock.advance(minutes=3)
    return dict(done_goals=done_goals, stuck=stuck, stuck_task=stuck_task, busy=busy, t_open=t_open,
                t_done=t_done, t_failed=t_failed, orphan=orphan, sub_goal=sub_goal, sub_task=sub_task)


def _work(app):
    return app.panel(WORK)


def _keys(p):
    return [r.key for r in p.rows]


def test_open_goals_first_expanded_done_under_a_collapsed_fold_orphan_under_no_goal(ctx, clock):
    f = _work_fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(WORK))  # the TUI starts in the Inbox since card #130
            await pilot.pause()
            p = _work(app)
            assert app.focused is p
            keys = _keys(p)
            # open goals first, newest activity first, each expanded with its tasks
            assert keys[:10] == [f"goal:{f['busy']}", f"task:{f['t_open']}", f"task:{f['t_done']}",
                                 f"task:{f['t_failed']}", f"goal:{f['sub_goal']}", f"task:{f['sub_task']}",
                                 f"goal:{f['stuck']}", f"task:{f['stuck_task']}", "fold:done", "nogoal"]
            assert keys[10:] == [f"task:{f['orphan']}"]  # the orphan, under `no goal`, the last row
            # the done goals only under `done (63)`, collapsed
            assert not any(f"goal:{g}" in keys for g in f["done_goals"])
            fold = next(r for r in p.rows if r.key == "fold:done")
            assert fold.text.plain == "done (63)" and not p.expanded(fold)
            under = [r for r in p.all_rows if r.data.get("parent") == "fold:done"]
            assert [r.data["id"] for r in under] == f["done_goals"][::-1]  # newest first
            # the stuck goal reads old, the busy one recent
            ages = {r.key: r.age for r in p.rows}
            assert ages[f"goal:{f['stuck']}"] == "2d" and ages[f"goal:{f['busy']}"] == "3m"
            # rows as shown: fold mark, id, first line, owner, done/total; task glyphs
            text = {r.key: str(p.get_option_at_index(i).prompt) for i, r in enumerate(p.rows)}
            busy = text[f"goal:{f['busy']}"]
            assert busy.startswith(f"▾ #{f['busy']} Busy goal with three tasks ") and busy.endswith(" 3m")
            assert " lead " in busy and " 2/3 " in busy
            assert text[f"task:{f['t_open']}"].startswith(f"    ● #{f['t_open']} carol  still going")
            assert text[f"task:{f['t_done']}"].startswith(f"    ✓ #{f['t_done']} carol")
            assert text[f"task:{f['t_failed']}"].startswith(f"    ✗ #{f['t_failed']} carol")
            assert text["fold:done"].startswith("▸ done (63)")
            assert text["nogoal"].startswith("▾ no goal") and " 0/1 " in text["nogoal"]
            assert text[f"goal:{f['sub_goal']}"].startswith(f"▾ #{f['sub_goal']} Sub-lead goal")
            assert " sub " in text[f"goal:{f['sub_goal']}"]

    _run(run())


def test_the_counts_and_the_title_equal_the_ledgers(ctx, clock):
    f = _work_fixture(ctx, clock)
    snap = build(ctx)
    open_goals = [i for i in ctx.ledger.open_items() if i["type"] == "goal"]
    all_goals = [m for m in ctx.ledger.messages() if m["type"] == "goal"]
    assert snap.work_title == f"{len(open_goals)} open · {len(all_goals) - len(open_goals)} done" == "3 open · 63 done"
    open_ids = {i["id"] for i in ctx.ledger.open_items()}
    tasks = [m for m in ctx.ledger.messages() if m["type"] == "task"]
    for row in (r for r in snap.panels["Work"] if r.kind == "goal"):
        mine = [t for t in tasks if t.get("ref") == row.data["id"]]
        shown = row.data["tail"].plain.split()[1]
        assert shown == f"{sum(1 for t in mine if t['id'] not in open_ids)}/{len(mine)}", row.key
        if row.data["parent"] == "fold:done":
            assert row.data["tail"].plain.endswith("1/1 ✓")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)):
            assert _work(app).border_title == f"[{WORK}]─Work─3 open · 63 done"

    _run(run())


def test_space_folds_o_hides_done_work_and_a_refresh_keeps_both(ctx, clock):
    f = _work_fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(WORK))
            await pilot.pause()
            p = _work(app)
            busy = f"goal:{f['busy']}"
            assert p.current.key == busy
            await pilot.press("space")  # fold the busy goal
            await pilot.pause()
            assert f"task:{f['t_open']}" not in _keys(p) and p.current.key == busy
            assert str(p.get_option_at_index(0).prompt).startswith("▸ ")
            await pilot.press("space")  # and unfold it
            await pilot.pause()
            assert f"task:{f['t_open']}" in _keys(p)
            # on a task, space folds its goal and selects it
            await pilot.press("j")
            await pilot.press("space")
            await pilot.pause()
            assert p.current.key == busy and f"task:{f['t_open']}" not in _keys(p)
            await pilot.press("space")
            # unfold `done (63)`, then one done goal in it
            p.highlighted = _keys(p).index("fold:done")
            await pilot.press("space")
            await pilot.pause()
            newest_done = f"goal:{f['done_goals'][-1]}"
            keys = _keys(p)
            assert keys[keys.index("fold:done") + 1] == newest_done and len(keys) == 11 + 63
            assert str(p.get_option_at_index(keys.index(newest_done)).prompt).startswith(
                f"▸ #{f['done_goals'][-1]} Done goal 62")
            p.highlighted = keys.index(newest_done)
            await pilot.press("space")
            await pilot.pause()
            assert _keys(p)[_keys(p).index(newest_done) + 1].startswith("task:")
            # a refresh keeps the folds and the selection
            ctx.ledger.append("carol", "lead", "report", "news", ref=f["t_open"])
            before = _keys(p)
            await pilot.press("r")
            await pilot.pause()
            assert _keys(p) == before and p.current.key == newest_done
            # o: open work only, then everything again
            p.highlighted = 0
            await pilot.press("o")
            await pilot.pause()
            keys = _keys(p)
            assert "fold:done" not in keys and not any(k.startswith("goal:") and int(k[5:]) in f["done_goals"]
                                                       for k in keys)
            assert f"task:{f['t_done']}" not in keys and f"task:{f['t_failed']}" not in keys
            assert f"task:{f['t_open']}" in keys and "open work only" in app.status
            assert p.border_subtitle == "open only · 1 of 8"
            assert keys == [f"goal:{f['busy']}", f"task:{f['t_open']}", f"goal:{f['sub_goal']}",
                            f"task:{f['sub_task']}", f"goal:{f['stuck']}", f"task:{f['stuck_task']}", "nogoal",
                            f"task:{f['orphan']}"]
            await pilot.press("r")  # open-only survives a refresh too
            await pilot.pause()
            assert _keys(p) == keys
            await pilot.press("o")
            await pilot.pause()
            assert _keys(p) == before

    _run(run())


def test_enter_shows_the_selected_row_in_detail(ctx, clock):
    f = _work_fixture(ctx, clock)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(WORK))
            await pilot.pause()
            p = _work(app)
            p.highlighted = _keys(p).index(f"task:{f['t_failed']}")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused.id == "detail"
            body = app.detail_view.plain
            assert f"#{f['t_failed']} task · lead → carol" in body and "FAIL: the build breaks" in body
            assert app.query_one("#detail").border_title == "Detail─Work"
            await pilot.press("escape")  # back to Work, the row still selected
            await pilot.pause()
            assert app.focused is p and p.current.key == f"task:{f['t_failed']}"
            p.highlighted = 0
            await pilot.press("enter")
            await pilot.pause()
            body = app.detail_view.plain
            assert f"#{f['busy']} goal" in body and "tasks 2/3 done" in body

    _run(run())


@pytest.mark.parametrize("size", [(160, 40), (100, 30)])
def test_no_work_row_spills_out_of_the_pane(ctx, clock, size):
    f = _work_fixture(ctx, clock)
    ctx.ledger.append("lead", "carol", "task", "漢字のテスト " * 40, ref=f["busy"])
    add_member(ctx, "a-very-long-agent-name")
    ctx.ledger.append("lead", "a-very-long-agent-name", "task", "long owner " * 20, ref=f["busy"])

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            p = _work(app)
            p.highlighted = _keys(p).index("fold:done")
            await pilot.press("space")  # every done goal shown too
            await pilot.pause()
            width = p.content_size.width
            for i in range(p.option_count):
                prompt = p.get_option_at_index(i).prompt
                assert prompt.cell_len <= width, (i, prompt.plain)
            goal = next(i for i, r in enumerate(p.rows) if r.key == f"goal:{f['busy']}")
            shown = p.get_option_at_index(goal).prompt.plain
            assert shown.endswith(" now") and " 2/5 " in shown  # the count is never cut
            assert (" lead " in shown) == (size == (160, 40))  # the owner gives way in a narrow pane
            assert p.border_title.startswith(f"[{WORK}]─Work")

    _run(run())


def test_a_task_goes_under_the_goal_at_the_root_of_its_ref_chain():
    from xt.tui import work

    def m(i, typ, ref=None, to="carol"):
        return {"id": i, "ts": f"2026-09-26T12:00:{i:02d}+00:00", "type": typ, "from": "lead", "to": to,
                "ref": ref, "body": f"message {i}"}

    msgs = [m(1, "goal", to="lead"), m(2, "task", 1), m(3, "task", 2), m(4, "report", 3), m(5, "task", 4),
            m(6, "task", 99), m(7, "task"), m(8, "report"), m(9, "task", 8), m(10, "task", 11), m(11, "task", 10)]
    out = work.outline(msgs, {}, set())
    assert [t.msg["id"] for t in out.done[0].tasks] == [2, 3, 5]  # through a task and a report
    assert [t.msg["id"] for t in out.orphans] == [6, 7, 9, 10, 11]  # unknown ref, none, no goal, a loop
    assert work.root_goal(5, {x["id"]: x for x in msgs}) == 1


def test_an_open_goal_older_than_the_messages_read_still_shows(ctx, clock):
    old = ctx.ledger.append("liaison", "lead", "goal", "An old open goal")["id"]
    clock.advance(days=40)
    ctx.ledger.append("liaison", "human", "report", "much later")
    rows = build(ctx).panels["Work"]
    goal = next(r for r in rows if r.key == f"goal:{old}")
    assert goal.data["open"] and goal.age == "40d"


def test_an_open_task_whose_owner_is_blocked_shows_the_failed_glyph(ctx, clock):
    add_member(ctx, "carol")
    g = ctx.ledger.append("liaison", "lead", "goal", "Goal")["id"]
    t = ctx.ledger.append("lead", "carol", "task", "stuck on a prompt", ref=g)["id"]
    ctx.herdr.add("carol", "blocked")
    row = next(r for r in build(ctx).panels["Work"] if r.key == f"task:{t}")
    assert row.text.plain.startswith("✗ ") and row.data["open"]
    assert "carol is blocked" in row.detail().plain


def test_space_and_o_outside_work_say_where_they_work(ctx):
    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX), "space")
            assert app.status == f"space works in Work ({WORK})"
            await pilot.press("o")
            assert app.status == f"o works in Work ({WORK})"
            await pilot.press(str(WORK))
            await pilot.pause()
            assert "space fold · o open only" in str(app.query_one("#hints").render())

    _run(run())


# --- #131 Detail shows the thread; Supervisor as a pop-up ------------------------------------------


def _shown(app) -> list[str]:
    """Detail's lines as drawn: the view laid out at Detail's width and height."""
    from rich.console import Console

    pane = app.query_one("#detail")
    view = app.detail_view
    view.height = pane.content_size.height
    console = Console(width=pane.content_size.width, file=io.StringIO(), record=True, color_system=None)
    console.print(view)
    return console.export_text().rstrip("\n").split("\n")


def _flow_select(app, mid):
    """Select message `mid` in Flow (card #130, in place of the Log) as j/k would."""
    p = app.panel(FLOW)
    p.selected = next(i for i, (kind, m) in enumerate(p.rows) if kind == "msg" and m["id"] == mid)
    p.follow = p.selected == p.message_rows()[-1]
    p.place()
    app.show_detail(p)
    return p


def test_selecting_a_task_shows_its_whole_goal_thread_in_time_order_marked(ctx, clock):
    from xt.tui.thread import HERE

    f = _work_fixture(ctx, clock)
    under = [m["id"] for m in ctx.ledger.messages() if m["id"] >= f["busy"]
             and (m["id"] in (f["busy"], f["t_open"], f["t_done"], f["t_failed"])
                  or m.get("ref") in (f["t_open"], f["t_done"], f["t_failed"]))]

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(WORK))
            await pilot.pause()
            p = _work(app)
            p.highlighted = _keys(p).index(f"task:{f['t_failed']}")
            await pilot.press("enter")
            await pilot.pause()
            view = app.detail_view
            assert [m["id"] for m in view.thread] == under  # the goal, its tasks, their replies
            assert [m["id"] for m in view.thread] == sorted(m["id"] for m in view.thread)  # in time order
            lines = _shown(app)
            marked = [ln for ln in lines if HERE.strip() in ln]
            assert len(marked) == 1 and f"#{f['t_failed']} the failing part" in marked[0]
            assert " lead    → carol   task " in marked[0] and re.match(r"\d\d:\d\d  ", marked[0])
            done = next(ln for ln in lines if "FAIL: the build breaks" in ln)
            assert " carol   → lead    done " in done
            # below the thread: the usage line and the keys, no `xt log --id` hint any more
            tail = [ln for ln in lines if ln.strip()][-2:]
            assert tail[0].startswith(f"usage (goal #{f['busy']}): ") and tail[1].startswith("space: fold its goal")
            assert "xt log --id" not in view.plain

    _run(run())


def test_a_lone_message_shows_with_its_replies_and_a_broken_ref_alone(ctx):
    ask = ctx.ledger.append("liaison", "human", "ask", "Tennis or chess?")["id"]
    ctx.ledger.append("lead", "pm", "report", "unrelated")
    answer = ctx.ledger.append("human", "liaison", "report", "tennis", ref=ask)["id"]
    thanks = ctx.ledger.append("liaison", "human", "report", "booked the court", ref=answer)["id"]
    broken = ctx.ledger.append("lead", "pm", "task", "a task whose ref is gone", ref=999)["id"]
    data = build(ctx).flow
    msgs = {m["id"]: m for m in data.msgs}
    view = data.detail(msgs[ask])
    assert [m["id"] for m in view.thread] == [ask, answer, thanks] and view.selected == ask
    assert "usage: counted per goal" in view.plain
    alone = data.detail(msgs[broken])
    assert [m["id"] for m in alone.thread] == [broken]


@pytest.mark.parametrize("size", [(160, 40), (100, 30)])
def test_a_sixty_message_thread_scrolls_keeps_the_selection_and_counts_the_hidden(ctx, clock, size):
    from xt.tui.thread import HERE

    goal = ctx.ledger.append("liaison", "lead", "goal", "A long conversation")["id"]
    ids = [goal]
    for i in range(59):
        clock.advance(minutes=1)
        ids.append(ctx.ledger.append("lead", "liaison", "report", f"step {i}", ref=goal)["id"])
    selected = ids[30]

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.press(str(FLOW))
            _flow_select(app, selected)
            await pilot.press("enter")
            await pilot.pause()
            view = app.detail_view
            assert len(view.thread) == 60
            lines = _shown(app)
            assert len(lines) <= app.query_one("#detail").content_size.height  # fits: nothing below the edge
            start, end = view.window
            assert 0 < start <= 30 < end < 60
            assert f"↑ {start} earlier rows hidden" in "\n".join(lines)
            assert f"↓ {60 - end} later rows hidden" in "\n".join(lines)
            assert sum(HERE.strip() in ln for ln in lines) == 1  # the selection is in view
            shown = [ln for ln in lines if re.match(r"\d\d:\d\d  ", ln)]  # the thread's rows
            assert f"#{ids[start]} " in shown[0] and f"#{ids[end - 1]} " in shown[-1]
            # j/k in Detail move through the hidden rows, and a refresh keeps the place
            for _ in range(5):
                await pilot.press("j")
            await pilot.pause()
            assert app.detail_view.window[0] == start + 5
            await pilot.press("r")
            await pilot.pause()
            _shown(app)
            assert app.detail_view.window[0] == start + 5
            for _ in range(80):
                await pilot.press("k")
            await pilot.pause()
            _shown(app)
            assert app.detail_view.window[0] == 0 and "earlier rows hidden" not in "\n".join(_shown(app))
            # the newest message: nothing hidden below it
            await pilot.press("escape")
            _flow_select(app, ids[-1])
            await pilot.pause()
            lines = _shown(app)
            assert "later rows hidden" not in "\n".join(lines) and "earlier rows hidden" in "\n".join(lines)
            assert HERE.strip() in [ln for ln in lines if re.match(r"\d\d:\d\d  ", ln)][-1]

    _run(run())


def test_v_opens_the_supervisor_pop_up_newest_first_and_esc_closes_it(ctx):
    from xt.tui.app import HINTS, Help, SupervisorPopup
    from xt.watch import Supervisor

    sup = Supervisor(ctx, out=lambda s: None)
    for text in ("delivered #1 to lead", "woke scout (every 60m)", "nudged lead about #3"):
        sup.say(text)
    assert "Supervisor" not in PANELS and "v supervisor" in HINTS and "Supervisor" not in HINTS
    assert dict(Help.KEYS)["v"].startswith("the supervisor's log")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            assert not app.query("#panel-4") and "Supervisor" not in str(app.query_one("#hints").render()).replace(
                "v supervisor", "")
            await pilot.press("v")
            await pilot.pause()
            assert isinstance(app.screen, SupervisorPopup)
            body = str(app.screen.query_one("#supervisor-body").render()).splitlines()
            assert [ln[6:] for ln in body[:3]] == ["nudged lead about #3", "woke scout (every 60m)",
                                                   "delivered #1 to lead"]
            sup.say("a new event while it is open")
            app.refresh_data()  # the 2 s refresh
            await pilot.pause()
            assert "a new event while it is open" in str(app.screen.query_one("#supervisor-body").render())
            for i in range(60):
                sup.say(f"event {i}")
            app.refresh_data()
            await pilot.pause()
            box = app.screen.query_one("#supervisor")
            await pilot.press("j", "j", "j")
            await pilot.pause()
            assert box.scroll_y == 3
            await pilot.press("k")
            await pilot.pause()
            assert box.scroll_y == 2
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, SupervisorPopup) and app.focused is app.panel(INBOX)

    _run(run())


def _needs_you(ctx):
    return _groups(build(ctx).panels["Inbox"]).get("NEEDS YOU", [])


def _alerts_in_inbox(ctx, kind):
    return [r for r in _needs_you(ctx) if r.kind == "alert" and re.match(rf"⚠ (×\d+ )?{kind} failed: ", r.text.plain)]


def test_1a_a_failed_wake_up_raises_one_needs_you_alert_counted_in_title_and_header(ctx, monkeypatch):
    from xt import watch
    from xt.paths import XtError

    add_member(ctx, "scout")
    ctx.herdr.add("scout")
    ctx.team.set_schedule("scout", "60m", "look around")
    ctx.team.save()
    ctx.reload_team()

    def refuse(ctx_, sender, to, mtype, body, *a, **k):
        if mtype == "wake":
            raise XtError("the queue is locked\nsecond line of the error")
        return send(ctx_, sender, to, mtype, body, *a, **k)

    monkeypatch.setattr(watch, "send", refuse)
    sup = watch.Supervisor(ctx, out=lambda s: None)
    sup.wake_scheduled(ctx.herdr.agents(), 1000.0)  # the clock starts
    sup.wake_scheduled(ctx.herdr.agents(), 1000.0 + 3601)  # due: the wake-up fails
    (row,) = _alerts_in_inbox(ctx, "wake-up")
    assert row.text.plain == "⚠ wake-up failed: scout: the queue is locked"  # the error's first line
    assert row.age == "now" and "Alert #" in row.detail().plain
    snap = build(ctx)
    assert snap.inbox_title.startswith("⚑ 1") and "⚑ 1 needs you" in snap.header.plain

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.pause()
            assert app.panel(INBOX).border_title.startswith(f"[{INBOX}]─Inbox─⚑ 1")
            assert "⚑ 1 needs you" in str(app.team.render())

    _run(run())


def test_1b_a_failed_notification_raises_one_alert_and_no_second_notification(ctx, monkeypatch):
    from xt import watch

    calls = []

    def failing(argv):
        calls.append(argv)
        return "notify-send not found"

    monkeypatch.setattr(watch, "run_notify", failing)
    ctx.herdr.add("liaison")
    sup = watch.Supervisor(ctx, out=lambda s: None)
    sup.notify_human(0)  # first run: counting starts
    send(ctx, "liaison", "human", "ask", "Which story?")
    sup.notify_human(0)
    assert len(calls) == 1  # the question's notification, which failed
    (row,) = _alerts_in_inbox(ctx, "notification")
    assert row.text.plain == "⚠ notification failed: notify-send not found"
    alert = next(m for m in ctx.ledger.messages() if m["type"] == "alert")
    assert alert["to"] == "human"
    sup.notify_human(0)  # the alert is new in the ledger: no notification about it
    watch.Supervisor(ctx, out=lambda s: None).notify_human(0)  # nor after a supervisor restart
    assert len(calls) == 1


def test_1c_a_failed_usage_recording_raises_one_alert(ctx, monkeypatch):
    from xt import turns, watch

    def broken(ctx_):
        raise ValueError("unexpected session log line\nat line 3")

    monkeypatch.setattr(turns, "record", broken)
    watch.Supervisor(ctx, out=lambda s: None).record_usage()
    (row,) = _alerts_in_inbox(ctx, "usage recording")
    assert row.text.plain == "⚠ usage recording failed: ValueError: unexpected session log line"


def test_1d_three_failures_make_one_alert_of_3_and_after_c_the_next_raises_a_new_one(ctx, clock, monkeypatch,
                                                                                       capsys):
    from xt import turns, watch
    from xt.brief import waiting_on_human

    monkeypatch.setattr(turns, "record", lambda ctx_: (_ for _ in ()).throw(OSError("disk full")))
    sup = watch.Supervisor(ctx, out=lambda s: None)
    for _ in range(3):
        sup.record_usage()
        clock.advance(minutes=1)
    (row,) = _alerts_in_inbox(ctx, "usage recording")
    first = Alerts(ctx).active()["failed:usage-recording"]
    assert first["count"] == 3 and row.text.plain.startswith("⚠ ×3 usage recording failed: ") and row.age == "1m"
    assert "3 times since it was raised" in row.detail().plain
    assert sum(m["type"] == "alert" for m in ctx.ledger.messages()) == 1  # one alert, not three
    assert "usage recording failed: OSError: disk full  ×3, last 12:02" in _xt_inbox(ctx, monkeypatch, capsys)
    assert any("×3, last 12:02" in ln for ln in waiting_on_human(ctx))

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            p = app.panel(INBOX)
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "alert")
            await pilot.press("c")
            await pilot.pause()
            assert not any(r.kind == "alert" for r in p.rows)

    _run(run())
    sup.record_usage()
    (row,) = _alerts_in_inbox(ctx, "usage recording")
    again = Alerts(ctx).active()["failed:usage-recording"]
    assert again["id"] != first["id"] and again["count"] == 1 and "×" not in row.text.plain


def test_answer_approve_and_send_still_work_from_detail_and_esc_calls_nothing(ctx):
    from xt.tui.app import Compose, Confirm

    add_member(ctx, "carol")
    for a in ("liaison", "lead"):
        ctx.herdr.add(a)
    q, _ = send(ctx, "liaison", "human", "ask", "Tennis or chess?")
    (ctx.paths.roles / "author.md").write_text("# Role: author\n")
    request_spawn(ctx, "lead", "dora", "claude", None, "author", None)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            await pilot.press(str(INBOX))
            p = app.panel(INBOX)
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "question")
            await pilot.press("enter")
            await pilot.pause()
            assert app.focused.id == "detail" and "s: answer (goes to liaison)" in app.detail_view.plain
            before = ctx.ledger.last_id()
            await pilot.press("escape")  # back to the Inbox: no action, no message
            await pilot.pause()
            assert app.focused is p and ctx.ledger.last_id() == before and app.screen is app.screen_stack[0]
            await pilot.press("enter", "s")
            assert isinstance(app.screen, Compose) and app.screen.title_text.startswith(f"Answer question #{q['id']}")
            await pilot.press(*"chess", "ctrl+s")
            await pilot.pause()
            answer = [m for m in ctx.ledger.messages() if m["id"] > before][0]
            assert (answer["from"], answer["to"], answer["type"], answer["ref"], answer["body"]) == \
                ("human", "liaison", "report", q["id"], "chess")
            p.highlighted = next(i for i, r in enumerate(p.rows) if r.kind == "approval")
            await pilot.press("enter", "a")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "dora" in ctx.herdr.live
            await pilot.press("enter", "S")  # S from Detail: a message to the liaison
            assert isinstance(app.screen, Compose) and app.screen.title_text == "Send to the liaison"

    _run(run())
