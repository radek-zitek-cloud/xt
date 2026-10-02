"""v0.21.0: xt chat (#184)."""

import asyncio
import io
import sys
import time

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Input, Static

from xt import chat, cli
from xt.dispatch import send
from xt.paths import XtError
from xt.spawn import Approvals, request_spawn

from .conftest import REPO, add_member

LONG = ["Approve the plan as written :: the builder starts today and the first candidate reaches QA on Monday, "
        "with both cards in it",
        "Approve with the smaller scope :: only the first card is built now; the second waits for the next release "
        "and its own approval",
        "Defer the whole release :: nothing is built this week and the team picks up the bug backlog instead, which "
        "has eleven cards",
        "Decline it :: the cards close as declined, the spec stays in the Space for reference, and nobody works on it"]


def _team(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)


def _ask(ctx, text, **kw):
    from xt.choices import build

    body, q = build(text, **kw)
    msg, _ = send(ctx, "liaison", "human", "ask", body, data={"question": q})
    return msg


def _text(w) -> str:
    return w.content.plain if hasattr(w.content, "plain") else str(w.content)


def _bodies(app):
    return [_text(w) for w in app.query_one("#history", VerticalScroll).query(".msg")]


def _status(app):
    return _text(app.query_one("#status", Static))


def _run(ctx, steps, size=(80, 24), refresh_s=chat.REFRESH_S):
    app = chat.ChatApp(ctx, refresh_s=refresh_s)

    async def go():
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await steps(app, pilot)

    asyncio.run(go())
    return app


async def _type(pilot, text):
    await pilot.press(*[{" ": "space"}.get(c, c) for c in text])


# --- 1: the last 30 messages of the conversation, oldest first -------------------------------------

def test_1_starts_with_the_last_30_messages_of_the_conversation_oldest_first(ctx):
    _team(ctx)
    add_member(ctx, "carol")
    ids = []
    for i in range(36):
        if i % 2:
            ids.append(send(ctx, "liaison", "human", "report", f"news {i}")[0]["id"])
        else:
            ids.append(send(ctx, "human", "liaison", "ask", f"question {i}")[0]["id"])
        send(ctx, "lead", "carol", "task", f"not part of the chat {i}")
    ctx.ledger.append("liaison", "liaison", "note", "a note isn't part of it either")

    async def steps(app, pilot):
        shown = _bodies(app)
        assert len(shown) == chat.HISTORY == 30
        assert f"#{ids[6]}" in shown[0] and f"#{ids[-1]}" in shown[-1]  # the last 30, oldest first
        assert not any("not part of" in b for b in shown)
        assert "you" in shown[0] and "liaison" in shown[1]

    _run(ctx, steps)


def test_1_fewer_messages_show_all_of_them(ctx):
    _team(ctx)
    send(ctx, "liaison", "human", "report", "Only this one.")
    _run(ctx, lambda app, pilot: _check_one(app))


async def _check_one(app):
    assert len(_bodies(app)) == 1 and "Only this one." in _bodies(app)[0]


# --- 2: a typed message reaches the liaison as the human's -----------------------------------------

def test_2_a_typed_message_goes_to_the_liaison_from_the_human_in_the_ledger(ctx):
    _team(ctx)
    ctx.herdr.add("liaison")
    before = ctx.ledger.last_id()

    async def steps(app, pilot):
        await _type(pilot, "Please start the v0.21 build")
        await pilot.press("enter")
        await pilot.pause()
        m = ctx.ledger.message(before + 1)
        assert (m["type"], m["from"], m["to"], m["body"]) == ("ask", "human", "liaison", "Please start the v0.21 build")
        assert "Please start the v0.21 build" in ctx.herdr.last_prompt("liaison")
        assert app.query_one("#draft", Input).value == ""
        assert any("Please start the v0.21 build" in b for b in _bodies(app))
        from xt.tui.model import build

        assert any(f["id"] == m["id"] for f in build(ctx).flow.msgs)  # Q1: the TUI's Flow shows the same entry

    _run(ctx, steps)


# --- 3: new liaison messages arrive without a restart, within 10 s ---------------------------------

def test_3_a_new_liaison_message_shows_without_restarting(ctx):
    _team(ctx)
    assert chat.REFRESH_S <= 10

    async def steps(app, pilot):
        msg, _ = send(ctx, "liaison", "human", "report", "The candidate is tagged.")
        start = time.monotonic()
        while not any("The candidate is tagged." in b for b in _bodies(app)):
            assert time.monotonic() - start < 10, "not shown within 10 s"
            await pilot.pause(0.05)

    _run(ctx, steps, refresh_s=0.1)


# --- 4 and 6a: questions answered in place, four options visible at 80 columns ------------------------

@pytest.mark.parametrize("size", [(80, 24), (80, 40)])
def test_4_6a_an_options_question_shows_in_full_at_80_columns_and_a_number_answers_it(ctx, size):
    _team(ctx)
    q = _ask(ctx, "The v0.21.0 plan is ready: how do we go on?", options=LONG, recommend=2, other=True)

    async def steps(app, pilot):
        assert "⚑ 4 options, Other" in _bodies(app)[-1] and "waits for your answer" in _bodies(app)[-1]
        await pilot.press("tab")
        await pilot.pause()
        box = app.query_one("#question", Static)
        assert box.display and _text(app.query_one("#target", Static)) == f"answer #{q['id']} › "
        text = _text(box)
        for opt in LONG:
            o, c = opt.split(" :: ")
            assert f"{o} — {c}" in text
        assert "Recommended: 2" in text and "Other: answer in your own words." in text
        assert box.region.right <= size[0] and box.region.height < size[1]
        from rich.console import Console

        wrapped = box.content.wrap(Console(width=box.content_size.width), box.content_size.width)
        assert len(wrapped) <= box.content_size.height, "every wrapped line of the question is in view"
        assert all(line.cell_len <= box.content_size.width for line in wrapped)  # wrapped, never cut sideways
        draft = app.query_one("#draft", Input)
        assert draft.region.height == 1 and draft.region.bottom <= size[1]
        await _type(pilot, "2")
        await pilot.press("enter")
        await pilot.pause()
        a = ctx.ledger.message(q["id"] + 1)
        assert a["ref"] == q["id"] and a["answer"]["option"] == 2
        assert a["body"].startswith("Option 2: Approve with the smaller scope — only the first card")
        assert ctx.ledger.item(q["id"]) is None and not box.display
        assert "✓ answered" in _bodies(app)[-2] or any("✓ answered" in b for b in _bodies(app))

    _run(ctx, steps, size=size)


def test_4_a_closed_question_refuses_other_words_and_keeps_the_draft(ctx):
    _team(ctx)
    q = _ask(ctx, "Shall the digest go out today?", options=[], closed=True)

    async def steps(app, pilot):
        await pilot.press("tab")
        await _type(pilot, "maybe later")
        await pilot.press("enter")
        await pilot.pause()
        assert "not sent: this is a yes/no question" in _status(app)
        assert app.query_one("#draft", Input).value == "maybe later" and ctx.ledger.item(q["id"]) is not None
        app.query_one("#draft", Input).value = ""
        await _type(pilot, "yes")
        await pilot.press("enter")
        await pilot.pause()
        assert ctx.ledger.message(q["id"] + 1)["answer"] == {"kind": "closed", "value": "yes"}

    _run(ctx, steps)


def test_4_options_without_other_refuse_words_and_esc_goes_back_to_the_liaison(ctx):
    _team(ctx)
    q = _ask(ctx, "Which?", options=LONG[:2], recommend=1)

    async def steps(app, pilot):
        await pilot.press("tab")
        await _type(pilot, "neither")
        await pilot.press("enter")
        await pilot.pause()
        assert "no Other" in _status(app) and ctx.ledger.item(q["id"]) is not None
        await pilot.press("escape")
        assert _text(app.query_one("#target", Static)) == "liaison › "
        await pilot.press("enter")  # now the draft goes to the liaison as a message
        await pilot.pause()
        last = list(ctx.ledger.messages())[-1]
        assert (last["from"], last["to"], last["body"], last["ref"]) == ("human", "liaison", "neither", None)
        assert ctx.ledger.item(q["id"]) is not None  # still waiting

    _run(ctx, steps)


def test_4_a_question_answered_elsewhere_drops_out_of_the_chat(ctx):
    _team(ctx)
    q = _ask(ctx, "Shall we?", options=[], closed=True)

    async def steps(app, pilot):
        await pilot.press("tab")
        assert app.target and app.target["id"] == q["id"]
        from xt.tui.app import LiveActions

        LiveActions(ctx).answer(q["id"], "no")  # in the TUI meanwhile
        app.refresh_messages()
        await pilot.pause()
        assert app.target is None and not app.query_one("#question", Static).display
        await _type(pilot, "yes")
        await pilot.press("enter")
        await pilot.pause()
        assert [m["body"] for m in ctx.ledger.messages() if m.get("ref") == q["id"]] == ["no"]  # answered once

    _run(ctx, steps)


# --- 5: approvals are closed questions here too ----------------------------------------------------

def test_5_an_approval_is_answered_yes_or_no_in_place(ctx):
    _team(ctx)
    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")
    request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)
    (rid,) = [int(i) for i in Approvals(ctx).pending()]

    async def steps(app, pilot):
        assert "lead asks to spawn carol" in _bodies(app)[-1] and "⚑ yes/no" in _bodies(app)[-1]
        await pilot.press("tab")
        assert _text(app.query_one("#question", Static)).startswith(f"Approval #{rid} from xt · answer yes or no")
        await _type(pilot, "no")
        await pilot.press("enter")
        await pilot.pause()
        assert not Approvals(ctx).pending() and "carol" not in ctx.herdr.live
        assert "spawn of carol denied" in _status(app)

    _run(ctx, steps)


# --- 6: leaving, and the draft ---------------------------------------------------------------------

def test_6_ctrl_d_leaves_and_a_draft_is_warned_about_and_never_written(ctx):
    _team(ctx)
    before = ctx.ledger.last_id()
    files = sorted(p.name for p in ctx.paths.root.rglob("*") if p.is_file())

    async def steps(app, pilot):
        await _type(pilot, "half a thought")
        await pilot.press("ctrl+d")
        await pilot.pause()
        assert app.is_running and "your draft isn't sent and isn't saved anywhere" in _status(app)
        await pilot.press("ctrl+d")
        await pilot.pause()

    app = _run(ctx, steps)
    assert app.return_code == 0 and ctx.ledger.last_id() == before
    assert sorted(p.name for p in ctx.paths.root.rglob("*") if p.is_file()) == files  # nothing stored


def test_6_ctrl_d_on_an_empty_line_and_exit_leave_at_once(ctx):
    _team(ctx)

    async def steps(app, pilot):
        await pilot.press("ctrl+d")
        await pilot.pause()

    assert _run(ctx, steps).return_code == 0

    async def steps2(app, pilot):
        await _type(pilot, "/exit")
        await pilot.press("enter")
        await pilot.pause()

    before = ctx.ledger.last_id()
    assert _run(ctx, steps2).return_code == 0 and ctx.ledger.last_id() == before


# --- 7: the identity guard -------------------------------------------------------------------------

class _Tty(io.StringIO):
    def isatty(self):
        return True


def _chat(ctx, monkeypatch, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    ran = []
    monkeypatch.setattr(chat, "run", lambda c: ran.append(c))
    args = cli.build_parser().parse_args(["chat", *argv])
    args.func(args)
    return ran


def test_7_an_agent_cannot_chat_as_the_human(ctx, monkeypatch):
    _team(ctx)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli, "human_terminal", lambda: False)
    with pytest.raises(XtError, match="runs only in the human's own terminal"):
        _chat(ctx, monkeypatch, "--as", "liaison")
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        _chat(ctx, monkeypatch, "--as", "human")
    with pytest.raises(XtError, match="pass --as <your name>"):
        _chat(ctx, monkeypatch)
    monkeypatch.setattr(cli, "human_terminal", lambda: True)
    assert _chat(ctx, monkeypatch) == [ctx]  # the human's own terminal
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    with pytest.raises(XtError, match="needs a terminal"):
        _chat(ctx, monkeypatch)


# --- 8: Q1 and the guide ---------------------------------------------------------------------------

def test_8_chat_stores_nothing_of_its_own_and_the_guide_has_a_chat_section():
    source = (REPO / "src/xt/chat.py").read_text()
    assert "open(" not in source and "write_text" not in source and ".state" not in source
    guide = " ".join((REPO / "docs/user-guide.md").read_text().split())
    assert "### `xt chat`" in guide
    for phrase in ("the last 30 messages", "within 10 seconds", "tab", "ctrl+d", "/exit",
                   "nothing of its own", "draft"):
        assert phrase in guide
