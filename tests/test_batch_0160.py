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
            agent_lines = [ln for ln in lines if "▕" in ln]
            width = app.team.content_size.width
            assert all(len(ln) <= width for ln in lines)
            assert sum(ln.count("▕") for ln in agent_lines) == 12  # every agent shown
            assert app.team.outer_size.height == len(lines) + 2  # no empty space: content plus the frame
            return len(agent_lines), app.team.outer_size.height, app.panel(INBOX).content_size.height

    assert asyncio.run(run((160, 40)))[0] == 4
    lines, height, inbox_rows = asyncio.run(run((100, 30)))
    assert lines == 6 and height <= 12 and inbox_rows >= 1  # two columns, Claude's block over Codex's


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
    assert "1-5 panels" in HINTS and "1-6" not in HINTS and "tab Team" in HINTS
    keys = dict(Help.KEYS)
    assert keys["1-5"] == "jump to a panel: Goals, Tasks, Inbox, Log, Supervisor"

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 40)) as pilot:
            for n, title in enumerate(PANELS, start=1):
                await pilot.press(str(n))
                await pilot.pause()
                assert app.focused.title == title
            await pilot.press("6")  # no sixth pane: nothing happens
            assert app.focused.title == "Supervisor"
            await pilot.press("tab")  # past the last panel: Team, at the top
            await pilot.pause()
            assert app.focused is app.team and app.team.current.data["name"] == "pm"
            await pilot.press("j")
            await pilot.pause()
            assert app.team.current.data["name"] == "builder"
            assert app.query_one("#detail").border_title == "Detail─Team"
            assert app.team.current.detail().plain.startswith("builder · worker · claude/claude-opus-5-5")

    _run(run())
