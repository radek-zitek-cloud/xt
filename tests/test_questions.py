"""Questions for the human (backlog item 26): open items in the human's Inbox, answered or withdrawn."""

import asyncio
import datetime as dt
import io
import sys
import time

import pytest

from xt import brief, cli
from xt.dispatch import send, waiting_on_human
from xt.paths import XtError
from xt.tui.app import Compose, LiveActions, XtTui
from xt.tui.model import build
from xt.watch import Supervisor

from .conftest import add_member


def _as_human(monkeypatch, ctx):
    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))


def _goal_and_question(ctx):
    """A goal with the lead, the lead's report about it, and the liaison's question about that."""
    ctx.herdr.add("liaison")
    ctx.herdr.add("lead")
    goal, _ = send(ctx, "human", "lead", "goal", "Find stories")
    batch, _ = send(ctx, "lead", "liaison", "report", "Batch: 1) avalanche 2) tennis", goal["id"])
    q, status = send(ctx, "liaison", "human", "ask", "Which story? 1 avalanche, 2 tennis", batch["id"])
    return goal, batch, q, status


def test_a_question_to_the_human_stays_open_until_answered(ctx, monkeypatch, capsys):
    goal, batch, q, status = _goal_and_question(ctx)
    assert "xt inbox" in status
    item = ctx.ledger.item(q["id"])
    assert (item["type"], item["owner"], item["opener"], item["about"]) == ("ask", "human", "liaison", batch["id"])
    for who in ("liaison", "lead"):
        b = brief.build(ctx, who)
        assert f"question #{q['id']} from liaison" in b and "xt answer <id>" in b
        assert "Which story?" not in b.split("## Open goals and tasks")[1].split("## ")[0]
    _as_human(monkeypatch, ctx)
    p = cli.build_parser()
    cli.cmd_inbox(p.parse_args(["inbox"]))
    assert f"#{q['id']}" in capsys.readouterr().out.split("Alerts:")[0]

    cli.cmd_answer(p.parse_args(["answer", str(q["id"]), "the", "tennis", "one"]))
    assert ctx.ledger.item(q["id"]) is None
    answer = ctx.herdr.last_prompt("liaison")
    assert f"report from:human to:liaison ref:#{q['id']}" in answer and "the tennis one" in answer
    with pytest.raises(XtError, match="not an open question"):
        cli.cmd_answer(p.parse_args(["answer", str(q["id"]), "again"]))


def test_the_asker_withdraws_a_question_answered_elsewhere(ctx):
    add_member(ctx, "carol")
    _, _, q, _ = _goal_and_question(ctx)
    with pytest.raises(XtError, match="owned by human"):
        send(ctx, "lead", "liaison", "done", "not mine", q["id"])
    with pytest.raises(XtError, match="may only message"):
        send(ctx, "lead", "human", "ask", "the lead can't ask the human directly")
    msg, _ = cli.send(ctx, "liaison", "human", "done", "Superseded: the lead auto-picked the avalanche", q["id"])
    assert msg["to"] == "human" and ctx.ledger.item(q["id"]) is None


def test_no_nudges_for_work_waiting_on_the_human(ctx):
    goal, batch, q, _ = _goal_and_question(ctx)
    assert waiting_on_human(ctx) == {goal["id"]: q["id"]}
    sup = Supervisor(ctx, out=lambda s: None)
    ctx.ledger.clock.advance(minutes=40)
    sup.heartbeat(ctx.herdr.agents())
    assert not any(m["type"] == "nudge" for m in ctx.ledger.messages())
    send(ctx, "human", "liaison", "report", "tennis", q["id"])  # answered: the goal is live again
    assert waiting_on_human(ctx) == {}
    ctx.herdr.live["lead"].status = "idle"
    sup.heartbeat(ctx.herdr.agents())
    assert any(m["type"] == "nudge" and m["to"] == "lead" for m in ctx.ledger.messages())


def test_the_human_is_notified_outside_quiet_hours(ctx, notifications):
    ctx.herdr.add("liaison")
    local = lambda h: time.mktime(dt.datetime(2026, 9, 27, h, 0).timetuple())
    sup = Supervisor(ctx, out=lambda s: None)
    send(ctx, "liaison", "human", "ask", "old question before the supervisor ran")
    sup.notify_human(local(12))  # first run: counting starts now, no flood
    assert notifications == []
    send(ctx, "liaison", "human", "ask", "Which story?")
    send(ctx, "liaison", "lead", "report", "not for the human")
    sup.notify_human(local(12))
    (argv,) = notifications
    assert argv[:2] == ["notify-send", "--app-name=xt"]
    assert argv[2] == "xt t: question from liaison" and argv[3] == "Which story?"

    ctx.team.doc["notify"]["quiet"] = "21:00-07:00"
    send(ctx, "liaison", "human", "ask", "a night question")
    sup.notify_human(local(23))
    assert len(notifications) == 1  # quiet hours: only the Inbox
    ctx.team.doc["notify"]["command"] = "curl -s -d {body} ntfy.sh/xt-test"
    send(ctx, "liaison", "human", "ask", "morning question")
    sup.notify_human(local(8))
    assert notifications[-1] == ["curl", "-s", "-d", "morning question", "ntfy.sh/xt-test"]


def test_answering_a_question_from_the_tui_inbox(ctx):
    _, _, q, _ = _goal_and_question(ctx)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("3")  # the Inbox
            row = app.panel(3).current
            assert row.kind == "question" and row.data["id"] == q["id"]
            assert "⚑ 1 needs you" in str(app.team.render())
            await pilot.press("s")
            assert isinstance(app.screen, Compose) and f"#{q['id']}" in app.screen.title_text
            assert "Which story?" in app.screen.context  # the question stays in view
            await pilot.press(*"tennis", "ctrl+s")
            await pilot.pause()
            assert f"answer to #{q['id']}" in app.status
            assert ctx.ledger.item(q["id"]) is None
            assert not any(r.kind == "question" for r in app.panel(3).rows)

    asyncio.run(run())
