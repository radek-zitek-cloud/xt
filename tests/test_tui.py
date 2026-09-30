import asyncio

from xt.dispatch import send
from xt.spawn import request_spawn
from xt.tui.app import INBOX, Compose, Confirm, Help, LiveActions, Panel, Prompt, XtTui, demo_snapshot
from xt.tui.model import PANELS, build

from .conftest import add_member


def test_tui_demo_navigation_and_popups():
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=(120, 40)) as pilot:
            assert app.focused.id == "panel-1"
            await pilot.press("3", "j", "j")
            await pilot.pause()
            assert app.focused.id == "panel-3" and app.focused.border_subtitle == "3 of 5"
            await pilot.press("question_mark")
            assert isinstance(app.screen, Help)
            await pilot.press("escape", "tab")
            assert isinstance(app.focused, Panel) and app.focused.id == "panel-4"
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
    heading, approval = snap.panels["Inbox"][:2]
    assert heading.kind == "heading" and heading.text.plain == "NEEDS YOU"
    assert approval.kind == "approval" and "spawn dora" in approval.text.plain
    assert "Purpose: write the copy." in approval.detail().plain  # the role brief, to decide on
    assert snap.panels["Log"][0].data["id"] > snap.panels["Log"][-1].data["id"]  # newest first
    assert "⚑ 1 needs you" in snap.header.plain


def test_approving_from_the_inbox_starts_the_agent(ctx):
    _team_with_work(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press(str(INBOX))
            assert app.panel(INBOX).current.kind == "approval"
            await pilot.press("a")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "dora" in ctx.herdr.live
            assert not any(r.kind == "approval" for r in app.panel(INBOX).rows)

    asyncio.run(run())


def test_send_to_liaison_from_the_tui(ctx):
    ctx.herdr.add("liaison")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("s")
            assert isinstance(app.screen, Compose)
            await pilot.press(*"hello", "enter", *"second line", "ctrl+s")  # enter: new line; ctrl+s: send
            await pilot.pause()
            assert "delivered" in app.status
            assert "hello\nsecond line" in ctx.herdr.last_prompt("liaison")

    asyncio.run(run())


def test_h_opens_help_listing_every_key(ctx):
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("h")
            assert isinstance(app.screen, Help)
            keys = " ".join(k for k, _ in Help.KEYS)
            for k in ("a / d", "c", "u", "U", "x", "f", "s", "r", "h / ?", "q", "1-5", "/", "R", "enter", "esc"):
                assert k in keys
            await pilot.press("h")  # h closes it again
            assert not isinstance(app.screen, Help)

    asyncio.run(run())


def test_summary_sits_on_top_and_keys_at_the_bottom(ctx):
    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.pause()
            top = str(app.team.render())
            bottom = str(app.query_one("#hints").render())
            assert ctx.team.name in top and "running" in top
            assert "h help" in bottom and "running" not in bottom

    asyncio.run(run())


def test_u_starts_a_stopped_agent_and_x_stops_it(ctx):
    add_member(ctx, "carol", role="researcher")
    ctx.herdr.add("liaison")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            app.team.focus()
            app.team.select("carol")
            await pilot.pause()
            await pilot.press("u")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "carol" in ctx.herdr.live
            assert "You are **carol**" in ctx.herdr.last_prompt("carol")
            assert app.team.current.data["name"] == "carol"  # the selection stays on the agent
            await pilot.press("x")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "carol" not in ctx.herdr.live
            ctx.reload_team()
            assert ctx.team.agent("carol").active  # stopped, not retired

    asyncio.run(run())


def test_U_starts_every_stopped_agent(ctx):
    add_member(ctx, "carol", role="researcher")
    add_member(ctx, "dave", role="researcher")
    ctx.herdr.add("liaison")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("U")  # from any pane
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            for name in ("lead", "carol", "dave"):
                assert name in ctx.herdr.live, name

    asyncio.run(run())


def test_moving_past_the_ends_of_a_list_does_nothing():
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press(str(INBOX))  # Inbox: 5 rows under 3 headings
            p = app.panel(INBOX)
            await pilot.press("k", "up")
            await pilot.pause()
            assert p.highlighted == 1  # no wrap to the bottom (row 0 is a heading)
            await pilot.press("j", "j", "j", "j", "j", "j", "down")
            await pilot.pause()
            assert p.highlighted == 7 and p.border_subtitle == "5 of 5"  # no wrap to the top
            app.team.focus()  # Team: 3 agents
            await pilot.pause()
            await pilot.press("k", "k", "j", "j", "j", "j")
            assert app.team.current.data["name"] == app.team.rows[-1].data["name"]

    asyncio.run(run())


def test_long_rows_stay_on_one_line():
    from rich.text import Text

    from xt.tui.model import PANELS, Row, Snapshot

    def src():
        rows = [Row(f"r{i}", Text(f"#{i} " + "word " * 100), lambda: Text("detail"), "message") for i in range(3)]
        return Snapshot({p: list(rows) for p in PANELS}, Text("summary"))

    async def run():
        app = XtTui(src)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert len(app.panel(1)._lines) == 3  # one line per item, no wrapping

    asyncio.run(run())


def test_R_retires_the_selected_member_but_not_the_lead(ctx):
    add_member(ctx, "carol", role="researcher")
    ctx.herdr.add("carol")
    ctx.herdr.add("lead")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("R")  # nothing selected in Team
            assert "select an agent in Team first" in app.status
            app.team.focus()
            app.team.select("lead")
            await pilot.pause()
            await pilot.press("R")
            assert "can't be retired" in app.status and not isinstance(app.screen, Confirm)
            app.team.select("carol")
            await pilot.pause()
            await pilot.press("R")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "retired carol" in app.status
            assert "carol" not in ctx.herdr.live
            ctx.reload_team()
            assert ctx.team.agent("carol").status == "retired"

    asyncio.run(run())


def test_panels_keep_their_size_when_focus_moves():
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=(140, 45)) as pilot:
            sizes = lambda: [app.panel(i).size for i in range(0, len(PANELS) + 1)]
            before = sizes()
            for key in ("3", "5", "4", "2", "tab"):
                await pilot.press(key)
                await pilot.pause()
                assert sizes() == before

    asyncio.run(run())


def test_slash_filters_the_focused_panel():
    async def run():
        app = XtTui(demo_snapshot)
        async with app.run_test(size=(140, 45)) as pilot:
            p = app.panel(INBOX)
            await pilot.press(str(INBOX), "slash")
            assert isinstance(app.screen, Prompt)
            await pilot.press(*"dave", "enter")
            await pilot.pause()
            assert [r.kind for r in p.rows] == ["alert"] and "/dave" in p.border_subtitle
            await pilot.press("slash", "enter")  # empty clears
            await pilot.pause()
            assert len(p.rows) == 8 and "/" not in p.border_subtitle
            app.team.focus()
            await pilot.pause()
            await pilot.press("slash")  # Team always shows every agent
            assert not isinstance(app.screen, Prompt) and "Team has no filter" in app.status

    asyncio.run(run())


def test_supervisor_panel_and_goal_drafts(ctx):
    from xt.watch import Supervisor

    sup = Supervisor(ctx, out=lambda s: None)
    sup.say("woke scout (every 60m)")
    sup.say("notification failed: notify-send not found ([notify] in team.toml)")
    ctx.paths.drafts.mkdir(parents=True, exist_ok=True)
    (ctx.paths.drafts / "weekly-digest.md").write_text("# Weekly digest\nA draft goal.\n")
    snap = build(ctx)
    events = [r.text.plain for r in snap.panels["Supervisor"]]
    assert "notification failed" in events[0] and "woke scout" in events[1]  # newest first
    drafts = [r for r in snap.panels["Goals"] if r.kind == "draft"]
    assert drafts and drafts[0].text.plain.startswith("✎ weekly-digest")
    assert "A draft goal." in drafts[0].detail().plain


def test_xt_log_watch_prints_supervisor_events(ctx, monkeypatch, capsys):
    from xt import cli
    from xt.watch import Supervisor

    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    Supervisor(ctx, out=lambda s: None).say("delivered #5 to lead")
    cli.cmd_log(cli.build_parser().parse_args(["log", "--watch"]))
    assert "delivered #5 to lead" in capsys.readouterr().out
