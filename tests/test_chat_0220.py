"""v0.22.0 #199: xt chat shows the operator and the liaison's team activity."""

from textual.containers import VerticalScroll

from xt import chat
from xt.dispatch import send
from xt.spawn import request_spawn
from xt.team import SYSTEM

from .conftest import REPO
from .test_chat_0210 import _bodies, _run, _status, _text, _type

REPORT = "Staging check passed: steps 1-9.\n(sent by op, an operator, on the human's behalf)"
LONG_GOAL = "Patch release v0.21.1: " + "a long goal title that runs past eighty columns " * 3


def _team(ctx):
    for n in ("liaison", "lead"):
        request_spawn(ctx, "human", n, None, None, None, None)


def _activity(app):
    return [(w, _text(w)) for w in app.query_one("#history", VerticalScroll).query(".activity")]


def _shown(app):
    return [t for w, t in _activity(app) if w.display]


def test_1_2_an_operator_report_and_the_liaisons_reply_show_labelled_as_the_operator(ctx):
    _team(ctx)
    own = send(ctx, "human", "liaison", "ask", "Where are we?")[0]

    async def steps(app, pilot):
        op = ctx.ledger.append("op", "liaison", "report", REPORT)
        reply = send(ctx, "liaison", "human", "report", "Thanks op: staging is green.", op["id"])[0]
        app.refresh_messages()
        await pilot.pause()
        shown = _bodies(app)
        assert "» op (operator)" in shown[-2] and f"#{op['id']}" in shown[-2] and "Staging check passed" in shown[-2]
        assert f"#{reply['id']}" in shown[-1] and "liaison" in shown[-1]
        mine = app.shown[own["id"]].content  # the human's own line keeps its look
        theirs = app.shown[op["id"]].content
        assert mine.plain.split()[1] == "you" and any(s.style == "bold cyan" for s in mine.spans)
        assert any(s.style == "bold magenta" for s in theirs.spans) and not any(s.style == "bold cyan" for s in theirs.spans)

    _run(ctx, steps, refresh_s=60)


def test_1_delegated_actions_show_with_their_text(ctx):
    _team(ctx)
    q = send(ctx, "liaison", "human", "ask", "Ship it?\n\nAnswer yes or no.", data={"question": {"kind": "closed"}})[0]
    a = ctx.ledger.append("op", "liaison", "report",
                          "yes\n(op, delegated by human until 14:30: an operator acting on the human's behalf)", q["id"],
                          data={"answer": {"kind": "closed", "value": "yes"},
                                "delegated": {"by": "human", "until": "2026-09-26T14:30:00+00:00"}})
    ctx.ledger.append(SYSTEM, "human", "system", "drive grant for op ended 14:30")

    async def steps(app, pilot):
        shown = _bodies(app)
        assert any("» op (operator)" in b and "op, delegated by human until 14:30" in b and f"#{a['id']}" in b
                   for b in shown)
        assert f"✓ answered by op (operator) #{a['id']}: yes" in next(b for b in shown if f"#{q['id']}" in b)
        assert "drive grant for op ended 14:30" in shown[-1]

    _run(ctx, steps)


def test_3_goals_show_by_default_t_cycles_and_enter_expands(ctx):
    _team(ctx)
    send(ctx, "human", "liaison", "ask", "Please ship v0.21.1")
    goal = send(ctx, "liaison", "lead", "goal", "Patch release v0.21.1\n\nThe whole brief: goals/release.md")[0]
    fwd = send(ctx, "liaison", "lead", "report", "Forwarded from the human: ship before Friday")[0]

    async def steps(app, pilot):
        (line,) = _shown(app)  # goals only, by default
        assert line.endswith(f" to lead: goal #{goal['id']} Patch release v0.21.1") and "ctrl+t team: goals" in _status(app)
        await pilot.press("ctrl+t")
        assert len(_shown(app)) == 2 and f"report #{fwd['id']}" in _shown(app)[1] and "team: all" in _status(app)
        await pilot.press("ctrl+t")
        assert _shown(app) == [] and "team: hidden" in _status(app)
        await pilot.press("ctrl+t")  # back to goals
        await pilot.press("up")
        assert _shown(app)[0].startswith("›") and "enter expand" in _status(app)
        await pilot.press("enter")
        assert "The whole brief: goals/release.md" in _shown(app)[0]
        assert ctx.ledger.last_id() == fwd["id"]  # enter on an empty draft sent nothing
        await pilot.press("enter")
        assert "The whole brief" not in _shown(app)[0]
        await _type(pilot, "x")  # typing leaves the selection
        assert not _shown(app)[0].startswith("›")

    _run(ctx, steps)


def test_3a_at_80_columns_a_one_liner_and_the_hint_fit_one_row_and_the_label_needs_no_colour(ctx):
    _team(ctx)
    send(ctx, "human", "liaison", "ask", "Go")
    send(ctx, "liaison", "lead", "goal", LONG_GOAL)
    ctx.ledger.append("op", "liaison", "report", REPORT)
    send(ctx, "liaison", "human", "ask", "Approve?\n\nAnswer yes or no.", data={"question": {"kind": "closed"}})

    async def steps(app, pilot):
        await pilot.pause()
        (w, text), = _activity(app)
        assert w.size.height == 1 and w.size.width <= 80
        status = app.query_one("#status")
        assert status.size.height == 1 and len(_text(status)) <= 80, _text(status)
        assert "(operator)" in next(b for b in _bodies(app) if "Staging" in b)  # the words alone tell it apart

    _run(ctx, steps, size=(80, 24))


def test_3b_an_arriving_one_liner_keeps_the_reading_position(ctx):
    _team(ctx)
    for i in range(20):
        send(ctx, "liaison", "human", "report", f"news {i}\nsecond line\nthird line")

    async def steps(app, pilot):
        history = app.query_one("#history", VerticalScroll)
        await pilot.pause()
        assert history.max_scroll_y > 0
        history.scroll_home(animate=False)
        await pilot.pause()
        send(ctx, "liaison", "lead", "goal", "A goal arrives while you read")
        app.refresh_messages()
        await pilot.pause()
        assert history.scroll_y == 0 and "A goal arrives" in _shown(app)[-1]
        history.scroll_end(animate=False)
        await pilot.pause()
        send(ctx, "liaison", "lead", "goal", "Another one at the end")
        app.refresh_messages()
        await pilot.pause()
        await pilot.pause()
        assert history.scroll_y >= history.max_scroll_y - 1  # at the end, the view follows

    _run(ctx, steps, refresh_s=60)


def test_4_every_line_is_a_ledger_message(ctx):
    _team(ctx)
    send(ctx, "human", "liaison", "ask", "Go")
    send(ctx, "liaison", "lead", "goal", "A goal")
    send(ctx, "liaison", "lead", "ask", "A question for the lead")
    ctx.ledger.append("op", "liaison", "report", REPORT)
    send(ctx, "lead", "liaison", "report", "lead to liaison: not the liaison's own activity")

    async def steps(app, pilot):
        await pilot.press("ctrl+t")  # all
        widgets = list(app.query_one("#history", VerticalScroll).children)
        assert len(widgets) == 4
        for w in widgets:
            m = ctx.ledger.message(w.msg_id)
            assert m is not None and f"#{m['id']}" in _text(w)

    _run(ctx, steps)


def test_5_the_user_guide_describes_it():
    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "NAME (operator)" in guide and "ctrl+t" in guide and "goals only" in guide
