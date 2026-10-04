"""v0.23.0-rc4, card #185: follow-up tasks under a recently closed goal."""

import json

import pytest
from rich.text import Text

from xt import brief, cli
from xt.dispatch import FOLLOW_UP_HOURS, send
from xt.paths import XtError
from xt.spawn import request_spawn
from xt.tui import model, work

from .conftest import REPO, add_member


def _team(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    request_spawn(ctx, "human", "lead", None, None, None, None)
    add_member(ctx, "carol")
    goal, _ = send(ctx, "liaison", "lead", "goal", "Check the site after the release")
    t, _ = send(ctx, "lead", "carol", "task", "Run the site check", ref=goal["id"])
    send(ctx, "carol", "lead", "done", "Site check passed", ref=t["id"])
    send(ctx, "lead", "liaison", "done", "Site checked; report in reports/site.md", ref=goal["id"])
    return goal["id"]


def _raw(ctx, ids) -> list[str]:
    """The log's own lines for these message ids, byte for byte."""
    out = []
    for f in sorted(ctx.paths.log.glob("*.jsonl")):
        out += [line for line in f.read_text().splitlines() if json.loads(line)["id"] in ids]
    return out


def _cli(ctx, monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "human_terminal", lambda: True)
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)
    return capsys.readouterr().out


# --- the window -------------------------------------------------------------------------------------


def test_185_just_inside_the_window_the_lead_sends_a_follow_up(ctx, clock):
    goal = _team(ctx)
    clock.advance(hours=FOLLOW_UP_HOURS, seconds=-1)
    msg, status = send(ctx, "lead", "carol", "task", "Retry the site check: the human renewed the cert", ref=goal)
    assert msg["follow_up"] is True and msg["ref"] == goal
    assert status.startswith(f"follow-up to closed goal #{goal}; ")
    item = ctx.ledger.item(msg["id"])
    assert item["follow_up"] is True and item["goal"] == goal and item["owner"] == "carol"
    assert ctx.ledger.item(goal) is None  # the goal stays closed
    assert "delivered" in status or "queued" in status  # like any task


def test_185_at_and_after_the_window_it_is_refused_naming_the_age_and_the_route(ctx, clock):
    goal = _team(ctx)
    clock.advance(hours=FOLLOW_UP_HOURS)
    with pytest.raises(XtError) as e:
        send(ctx, "lead", "carol", "task", "Retry", ref=goal)
    assert str(e.value) == (f"goal #{goal} closed 24h ago; the follow-up window is 24h. New work needs a new "
                            f"goal: ask the liaison to dispatch one.")
    clock.advance(hours=2, minutes=59)
    with pytest.raises(XtError, match=f"goal #{goal} closed 26h ago; the follow-up window is 24h"):
        send(ctx, "lead", "carol", "task", "Retry", ref=goal)


def test_185_reports_and_dones_about_a_closed_goal_are_not_windowed(ctx, clock):
    goal = _team(ctx)
    clock.advance(hours=30)
    send(ctx, "lead", "liaison", "report", "One more thing about the site check", ref=goal)  # works as before
    with pytest.raises(XtError, match=f"#{goal} is not an open goal, task or question"):
        send(ctx, "lead", "liaison", "done", "again", ref=goal)  # unchanged


def test_185_the_window_belongs_to_the_goal_a_later_follow_up_is_fine(ctx, clock):
    goal = _team(ctx)
    clock.advance(hours=2)
    first, _ = send(ctx, "lead", "carol", "task", "Retry the check", ref=goal)
    send(ctx, "carol", "lead", "done", "Passed", ref=first["id"])
    clock.advance(hours=20)
    second, _ = send(ctx, "lead", "carol", "task", "Check the mirror too, as the human asked", ref=goal)
    assert second["follow_up"] is True


def test_185_only_the_lead_that_owned_the_goal(ctx, clock):
    goal = _team(ctx)
    add_member(ctx, "dana", reports_to="carol")
    with pytest.raises(XtError, match=rf"#{goal} is a closed goal: only the lead that owned it \(lead\) may open a "
                                      rf"follow-up task under it, within 24h of its closing"):
        send(ctx, "carol", "dana", "task", "Retry", ref=goal)
    # a goal the lead didn't own: an operator's goal to the liaison, closed by the liaison
    other = ctx.ledger.append("op", "liaison", "goal", "Dispatch the release goal")
    ctx.ledger.append("liaison", "op", "done", "Dispatched", ref=other["id"])
    with pytest.raises(XtError, match=r"only the lead that owned it \(liaison\)"):
        send(ctx, "lead", "carol", "task", "Retry", ref=other["id"])


def test_185_open_goals_tasks_without_a_goal_and_other_refs_behave_as_before(ctx, clock):
    goal = _team(ctx)
    open_goal, _ = send(ctx, "liaison", "lead", "goal", "A new goal")
    t, _ = send(ctx, "lead", "carol", "task", "Under the open goal", ref=open_goal["id"])
    assert "follow_up" not in t and "follow_up" not in ctx.ledger.item(t["id"])
    loose, _ = send(ctx, "lead", "carol", "task", "No goal at all")
    assert "follow_up" not in loose
    report, _ = send(ctx, "lead", "liaison", "report", "a report", ref=goal)
    with pytest.raises(XtError, match=f"--ref for a task must be an open goal id; #{report['id']} isn't one"):
        send(ctx, "lead", "carol", "task", "Retry", ref=report["id"])
    with pytest.raises(XtError, match="--ref for a task must be an open goal id; #9999 isn't one"):
        send(ctx, "lead", "carol", "task", "Retry", ref=9999)


def test_185_the_goals_closing_record_is_byte_identical_after_a_follow_up_runs(ctx, clock):
    goal = _team(ctx)
    closing = [m["id"] for m in ctx.ledger.messages() if m["type"] == "done" and m["ref"] == goal]
    before = _raw(ctx, {goal, *closing})
    clock.advance(hours=3)
    f, _ = send(ctx, "lead", "carol", "task", "Retry the site check", ref=goal)
    send(ctx, "carol", "lead", "done", "Passed again", ref=f["id"])
    assert _raw(ctx, {goal, *closing}) == before
    assert ctx.ledger.item(goal) is None and ctx.ledger.item(f["id"]) is None


# --- displays ---------------------------------------------------------------------------------------


def _follow_up(ctx, clock):
    goal = _team(ctx)
    clock.advance(hours=3)
    f, _ = send(ctx, "lead", "carol", "task", "Retry the site check", ref=goal)
    clock.advance(hours=2)
    return goal, f["id"]


def test_185_brief_status_and_log_show_it_with_its_age_and_the_counts(ctx, clock, monkeypatch, capsys):
    goal, f = _follow_up(ctx, clock)
    # 77 columns with the full label, so the shorter words (the line stays within 76)
    line = f"- #{f} task → carol [follow-up, goal #{goal}], open 2h: Retry the site check"
    assert line in brief.build(ctx).splitlines()
    assert line in brief.build(ctx, "carol").splitlines()
    out = _cli(ctx, monkeypatch, capsys, "status")
    assert line in out.splitlines()
    assert "open goals/tasks: 1 · " in out  # the follow-up is an open task; the closed goal isn't open
    assert next(x for x in out.splitlines() if x.startswith("  carol ")).count("open:1")
    assert "open:0" in next(x for x in out.splitlines() if x.startswith("  lead "))
    log = _cli(ctx, monkeypatch, capsys, "log")
    assert f"task lead→carol ref:#{goal} (follow-up to a closed goal)" in log


def test_185_the_brief_line_takes_shorter_words_before_it_cuts_and_keeps_4_columns(ctx):
    import datetime as dt

    now = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)
    item = {"id": 12345, "owner": "release-mgr1", "goal": 12340, "opened": "2026-10-03T13:00:00+00:00",
            "title": "Retry"}
    assert brief.follow_up_line(item, now) == "- #12345 task → release-mgr1 [follow-up, goal #12340], open 23h: Retry"
    item["title"] = "Re"
    assert brief.follow_up_line(item, now) == ("- #12345 task → release-mgr1 [follow-up to closed goal #12340], "
                                               "open 23h: Re")
    item["title"] = "Retry the site check with the renewed certificate"
    line = brief.follow_up_line(item, now)
    assert line.startswith("- #12345 task → release-mgr1 [f/u #12340], open 23h: Retry the site check")
    assert line.endswith("…") and len(line) == 76  # 80 columns with 4 to spare
    for title in ("x", "Retry the site check", "y" * 200):
        item["title"] = title
        assert len(brief.follow_up_line(item, now)) <= 76


def _rows(ctx):
    msgs = list(ctx.ledger.messages())
    open_items = {i["id"]: i for i in ctx.ledger.open_items()}
    rows, _ = model._work(ctx, msgs, open_items, {}, ctx.ledger.clock(), lambda *a, **k: Text())
    return {r.key: r for r in rows}, [r.key for r in rows]


def test_185_the_work_outline_puts_it_below_the_goals_own_tasks_and_leaves_the_goal_row(ctx, clock):
    goal = _team(ctx)
    clock.advance(hours=3)
    before, _ = _rows(ctx)  # at the same time as the follow-up, so ages compare
    goal_row = before[f"goal:{goal}"]
    f, _ = send(ctx, "lead", "carol", "task", "Retry the site check", ref=goal)
    send(ctx, "carol", "lead", "report", "Started", ref=f["id"])  # activity under the follow-up
    rows, order = _rows(ctx)
    g = rows[f"goal:{goal}"]
    assert g.text.plain == goal_row.text.plain and g.age == goal_row.age  # not re-sorted by its follow-up
    assert g.data["tail"].plain == goal_row.data["tail"].plain  # same `1/1 ✓`, closed marker
    row = rows[f"task:{f['id']}"]
    assert row.data["parent"] == f"goal:{goal}" and row.data["level"] == 2 and row.data["open"]
    tasks = [k for k in order if rows[k].data.get("parent") == f"goal:{goal}"]
    assert tasks[-1] == f"task:{f['id']}"  # below the goal's own tasks
    assert "● ↳ follow-up #" in row.text.plain and "carol" in row.text.plain
    assert rows[work.DONE_FOLD].text.plain == "done (1) · 1 follow-up open"
    assert rows[work.DONE_FOLD].data["expanded"] and g.data["expanded"]  # the open follow-up is in view
    send(ctx, "carol", "lead", "done", "Passed", ref=f["id"])
    rows, _ = _rows(ctx)
    assert rows[f"task:{f['id']}"].text.plain.startswith("✓ ↳ follow-up")  # closed in the outline
    assert rows[work.DONE_FOLD].text.plain == "done (1)" and not rows[work.DONE_FOLD].data["expanded"]


def test_185_the_work_row_fits_80_columns_and_shortens_its_label_before_cutting(ctx, clock):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    request_spawn(ctx, "human", "lead", None, None, None, None)
    add_member(ctx, "release-mgr1")
    goal, _ = send(ctx, "liaison", "lead", "goal", "Ship the release")
    send(ctx, "lead", "liaison", "done", "Shipped", ref=goal["id"])
    clock.advance(hours=1)
    f, _ = send(ctx, "lead", "release-mgr1", "task", "Retry the site check after it", ref=goal["id"])
    clock.advance(hours=22)
    row = _rows(ctx)[0][f"task:{f['id']}"]
    line = work.line(row.text, row.data, row.age, 80, False)
    content = line.plain.rstrip(row.age).rstrip()
    assert "↳ follow-up" in content and "…" not in content and row.age == "22h"
    assert len(content) + 1 + len(row.age) <= 76  # the longest realistic row keeps 4 columns spare
    narrow = work.line(row.text, row.data, row.age, 64, False).plain  # 68 with the full label, 62 short
    assert "↳ f/u #" in narrow and "Retry the site check after it" in narrow  # shorter words, no cut yet
    assert "…" in work.line(row.text, row.data, row.age, 50, False).plain


def test_185_in_the_tui_at_80_columns_the_row_keeps_4_columns_spare(ctx, clock):
    import asyncio

    from xt.tui.app import WORK, LiveActions, XtTui

    request_spawn(ctx, "human", "liaison", None, None, None, None)
    request_spawn(ctx, "human", "lead", None, None, None, None)
    add_member(ctx, "release-mgr1")  # 12 characters, the owner column's limit
    goal, _ = send(ctx, "liaison", "lead", "goal", "Ship the release")
    t, _ = send(ctx, "lead", "release-mgr1", "task", "Publish it", ref=goal["id"])
    send(ctx, "release-mgr1", "lead", "done", "Published", ref=t["id"])
    send(ctx, "lead", "liaison", "done", "Shipped", ref=goal["id"])
    clock.advance(hours=1)
    f, _ = send(ctx, "lead", "release-mgr1", "task", "Retry the site check", ref=goal["id"])
    clock.advance(hours=22)
    seen = {}

    async def run():
        app = XtTui(lambda: model.build(ctx), LiveActions(ctx))
        async with app.run_test(size=(80, 30)) as pilot:
            await pilot.press(str(WORK))
            await pilot.pause()
            panel = app.panel(WORK)
            keys = [r.key for r in panel.visible(panel.all_rows)]
            row = next(r for r in panel.all_rows if r.key == f"task:{f['id']}")
            seen["width"] = panel.content_size.width
            seen["line"] = panel.line(row, seen["width"]).plain
            seen["visible"] = row.key in keys

    asyncio.run(run())
    line = seen["line"]
    assert seen["visible"]  # in view without unfolding anything
    assert seen["width"] <= 80 and len(line) <= seen["width"]
    assert "↳ follow-up" in line and "Retry the site check" in line and "…" not in line
    assert line.endswith(" 22h")
    used = len(line[: -len(" 22h")].rstrip()) + len(" 22h")
    assert used <= 76, line  # text and age within 80 columns less 4


def test_185_the_guide_and_the_lead_role_mention_follow_ups():
    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "**Follow-ups under a closed goal** (from 0.23.0)" in guide and "↳ follow-up" in guide
    role = " ".join((REPO / "roles" / "lead.md").read_text().split())
    assert "**Follow-ups under a closed goal.** For 24 hours after you close a goal" in role
    assert "new scope still needs a new goal from the liaison" in role
