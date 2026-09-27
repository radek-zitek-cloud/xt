import asyncio

from xt.dispatch import send
from xt.spawn import request_spawn
from xt.tui.app import Confirm, Help, LiveActions, Panel, Prompt, XtTui, demo_snapshot
from xt.tui.model import build

from .conftest import add_member


def test_tui_demo_navigation_and_popups():
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.focused.id == "panel-1"
            await pilot.press("2", "j", "j")
            await pilot.pause()
            assert app.focused.id == "panel-2" and app.focused.border_subtitle == "3 of 3"
            await pilot.press("question_mark")
            assert isinstance(app.screen, Help)
            await pilot.press("escape", "tab")
            assert isinstance(app.focused, Panel) and app.focused.id == "panel-3"
            await pilot.press("s")  # actions are disabled in the demo
            assert "demo mode" in app.status

    asyncio.run(run())


def _team_with_work(ctx):
    add_member(ctx, "carol", role="researcher")
    for a in ("liaison", "lead", "carol"):
        ctx.herdr.add(a)
    ctx.paths.goals.mkdir(exist_ok=True)
    g, _ = send(ctx, "liaison", "lead", "goal", "Explain the chip race\nBrief: goals/chips.md")
    (ctx.paths.goals / "chips.md").write_text("# Explain the chip race\n\nOutcome: an article.\n")
    t, _ = send(ctx, "lead", "carol", "task", "research the chip", ref=g["id"])
    (ctx.paths.roles / "author.md").write_text("# Role: author\nPurpose: write the copy.\n")
    request_spawn(ctx, "lead", "dora", "claude", None, "author", None)  # needs approval
    return g, t


def test_model_shows_goals_team_tasks_inbox_and_log(ctx):
    g, t = _team_with_work(ctx)
    snap = build(ctx)
    goal = snap.panels["Goals"][0]
    assert goal.key == f"goal:{g['id']}" and "0/1" in goal.text.plain
    detail = goal.detail().plain
    assert "research the chip" in detail and "Outcome: an article." in detail  # tasks + brief file
    assert [r.data["name"] for r in snap.panels["Team"]] == ["liaison", "lead", "carol"]
    assert snap.panels["Tasks"][0].key == f"task:{t['id']}"
    approval = snap.panels["Inbox"][0]
    assert approval.kind == "approval" and "spawn dora" in approval.text.plain
    assert "Purpose: write the copy." in approval.detail().plain  # the role brief, to decide on
    assert snap.panels["Log"][0].data["id"] > snap.panels["Log"][-1].data["id"]  # newest first
    assert "1 approval" in snap.summary


def test_approving_from_the_inbox_starts_the_agent(ctx):
    _team_with_work(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("4")
            assert app.panel(4).current.kind == "approval"
            await pilot.press("a")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "dora" in ctx.herdr.live
            assert not any(r.kind == "approval" for r in app.panel(4).rows)

    asyncio.run(run())


def test_send_to_liaison_from_the_tui(ctx):
    ctx.herdr.add("liaison")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("s")
            assert isinstance(app.screen, Prompt)
            await pilot.press(*"hello", "enter")
            await pilot.pause()
            assert "delivered" in app.status
            assert "hello" in ctx.herdr.last_prompt("liaison")

    asyncio.run(run())
