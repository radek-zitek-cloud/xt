"""v0.21.0: one structured message format (#182)."""

import asyncio
import io
import json
import sys

import pytest

from xt import choices, cli
from xt.dispatch import send
from xt.paths import XtError
from xt.spawn import request_spawn as _spawn

from .conftest import REPO

FOUR = ["--option", "Approve :: the build starts today",
        "--option", "Approve with a change :: I adjust the spec first, the build starts tomorrow",
        "--option", "Defer :: it moves to the next release and nothing is built now",
        "--option", "Decline :: the card closes and the problem stays as it is",
        "--recommend", "2"]


def _cli(ctx, monkeypatch, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)


def _human(monkeypatch):
    monkeypatch.setattr(cli, "human_terminal", lambda: True)


def _team(ctx):
    _spawn(ctx, "human", "liaison", None, None, None, None)


def _last(ctx):
    return list(ctx.ledger.messages())[-1]


def _ask(ctx, monkeypatch, *flags, text="Shall we build it?"):
    _team(ctx)
    _cli(ctx, monkeypatch, "send", "human", "--as", "liaison", "--type", "ask", *flags, text)
    return _last(ctx)


# --- criterion 1: a narrative without a question ----------------------------------------------------

def test_1_a_narrative_needs_no_answer_and_stays_out_of_needs_you(ctx, monkeypatch):
    _team(ctx)
    _cli(ctx, monkeypatch, "send", "human", "--as", "liaison", "--type", "report", "The build is done.")
    m = _last(ctx)
    assert m["type"] == "report" and "question" not in m
    assert ctx.ledger.item(m["id"]) is None
    from xt import inbox

    assert inbox.build(ctx, list(ctx.ledger.messages())).questions == []


# --- criterion 2: closed ----------------------------------------------------------------------------

def test_2_a_closed_question_takes_only_yes_or_no_and_stores_it(ctx, monkeypatch, capsys):
    q = _ask(ctx, monkeypatch, "--closed")
    assert q["question"] == {"kind": "closed"} and q["body"].endswith("\n\nAnswer yes or no.")
    _human(monkeypatch)
    for bad in ("maybe", "2", "yes, but later"):
        with pytest.raises(XtError, match="yes/no question: answer yes or no"):
            _cli(ctx, monkeypatch, "answer", str(q["id"]), bad)
    assert ctx.ledger.item(q["id"]) is not None  # a refused answer leaves it open
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "Y")
    a = _last(ctx)
    assert (a["type"], a["ref"], a["body"], a["answer"]) == ("report", q["id"], "yes", {"kind": "closed", "value": "yes"})
    assert ctx.ledger.item(q["id"]) is None


# --- criterion 3: options -------------------------------------------------------------------------

def test_3_four_options_with_one_recommendation_take_a_number_stored_as_the_full_text(ctx, monkeypatch, capsys):
    q = _ask(ctx, monkeypatch, *FOUR)
    assert q["question"]["kind"] == "options" and len(q["question"]["options"]) == 4
    assert q["question"]["recommend"] == 2 and q["question"]["other"] is False
    assert q["question"]["options"][3] == {"text": "Decline", "consequence": "the card closes and the problem stays as it is"}
    assert "4. Decline — the card closes" in q["body"] and q["body"].endswith("Recommended: 2\nAnswer with the option's number.")
    _human(monkeypatch)
    with pytest.raises(XtError, match="no Other, so own words"):
        _cli(ctx, monkeypatch, "answer", str(q["id"]), "approve, but tell QA")
    with pytest.raises(XtError, match="no option 5; choose 1, 2, 3, 4$"):
        _cli(ctx, monkeypatch, "answer", str(q["id"]), "5")
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "4")
    a = _last(ctx)
    assert a["body"] == "Option 4: Decline — the card closes and the problem stays as it is"
    assert a["answer"] == {"kind": "options", "option": 4, "value": "Decline — the card closes and the problem stays as it is"}
    assert "recorded as: Option 4: Decline" in capsys.readouterr().out


def test_3_other_lets_own_words_through(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, *FOUR, "--other")
    assert q["question"]["other"] is True and q["body"].endswith("Other: answer in your own words.")
    _human(monkeypatch)
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "Approve, but tell QA first")
    a = _last(ctx)
    assert a["body"] == "Approve, but tell QA first" and a["answer"] == {"kind": "options", "other": True,
                                                                         "value": "Approve, but tell QA first"}


def test_3_two_options_still_work(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, *FOUR[:4], "--recommend", "1")
    assert len(q["question"]["options"]) == 2


# --- criterion 4: open ----------------------------------------------------------------------------

def test_4_an_open_question_takes_free_text(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, text="What should the digest's title be?")
    assert q["question"] == {"kind": "open"} and q["body"] == "What should the digest's title be?"
    _human(monkeypatch)
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "Weekly", "notes")
    assert _last(ctx)["answer"] == {"kind": "open", "value": "Weekly notes"}


# --- criterion 5: malformed questions ---------------------------------------------------------------

@pytest.mark.parametrize("flags,why", [
    (["--option", "a :: x", "--recommend", "1"], "two to four options \\(got 1\\)"),
    (FOUR[:8] + ["--option", "e :: y", "--recommend", "1"], "two to four options \\(got 5\\)"),
    (["--option", "a :: x", "--option", "b :: y"], "recommend exactly one.*got none"),
    (["--option", "a :: x", "--option", "b :: y", "--recommend", "1", "--recommend", "2"], "recommend exactly one.*got 1, 2"),
    (["--option", "a :: x", "--option", "b :: y", "--recommend", "3"], "recommend exactly one"),
    (["--option", " :: x", "--option", "b :: y", "--recommend", "1"], "is empty"),
    (["--option", "a", "--option", "b :: y", "--recommend", "1"], "needs a consequence"),
    (["--closed", "--other"], "closed question is answered yes or no"),
    (["--closed", "--option", "a :: x", "--option", "b :: y", "--recommend", "1"], "closed question is answered yes or no"),
    (["--recommend", "1"], "--recommend needs the options"),
    (["--other"], "--other adds a free-text answer to options"),
])
def test_5_a_malformed_question_is_refused_and_its_text_is_shown_back(ctx, monkeypatch, flags, why):
    _team(ctx)
    before = ctx.ledger.last_id()
    with pytest.raises(XtError, match=why) as e:
        _cli(ctx, monkeypatch, "send", "human", "--as", "liaison", "--type", "ask", *flags, "Shall we build it?")
    assert "Nothing was sent" in str(e.value)
    assert str(e.value).endswith("Your message, as you wrote it:\nShall we build it?")  # the text isn't lost
    assert ctx.ledger.last_id() == before


def test_5_question_flags_need_an_ask(ctx, monkeypatch):
    _team(ctx)
    with pytest.raises(XtError, match="belong to a question: add --type ask"):
        _cli(ctx, monkeypatch, "send", "human", "--as", "liaison", "--closed", "Shall we?")


def test_5_a_heredoc_text_is_shown_back_too(ctx, monkeypatch):
    _team(ctx)
    monkeypatch.setattr(sys, "stdin", io.StringIO("Line one with `backticks`\nline two\n"))
    with pytest.raises(XtError) as e:
        _cli(ctx, monkeypatch, "send", "human", "--as", "liaison", "--type", "ask", "--option", "a :: x")
    assert str(e.value).endswith("Line one with `backticks`\nline two")


# --- criterion 6: data in the ledger and xt log; changed or closed questions ------------------------

def test_6_type_options_recommendation_and_answer_are_data_in_the_log_file_and_xt_log(ctx, monkeypatch, capsys):
    q = _ask(ctx, monkeypatch, *FOUR, "--other")
    _human(monkeypatch)
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "1")
    lines = [json.loads(ln) for f in sorted(ctx.paths.log.glob("*.jsonl")) for ln in f.read_text().splitlines()]
    stored = {m["id"]: m for m in lines}
    assert stored[q["id"]]["question"]["recommend"] == 2 and stored[q["id"]]["question"]["other"] is True
    assert stored[q["id"] + 1]["answer"]["option"] == 1
    capsys.readouterr()
    _cli(ctx, monkeypatch, "log", "--id", str(q["id"]))
    out = capsys.readouterr().out
    assert "[question: options 1-4, recommended 2, Other allowed]" in out and "[answer: option 1]" in out


def test_6_an_answer_to_a_closed_question_is_refused(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, "--closed")
    send(ctx, "liaison", "human", "done", "Superseded: the lead decided", q["id"])  # withdrawn by the asker
    _human(monkeypatch)
    with pytest.raises(XtError, match="not an open question"):
        _cli(ctx, monkeypatch, "answer", str(q["id"]), "yes")
    from xt.tui.app import LiveActions

    with pytest.raises(RuntimeError, match="no longer an open question"):
        LiveActions(ctx).answer(q["id"], "yes")


# --- criterion 7: 80 columns in the TUI -------------------------------------------------------------

LONG = ["--option", "Approve the plan as written :: the builder starts today and the first candidate reaches QA "
                    "on Monday, with both cards in it",
        "--option", "Approve with the smaller scope :: only the first card is built now; the second waits for "
                    "the next release and its own approval",
        "--option", "Defer the whole release :: nothing is built this week and the team picks up the bug backlog "
                    "instead, which has eleven cards",
        "--option", "Decline it :: the cards close as declined, the spec stays in the Space for reference, and "
                    "nobody works on it",
        "--recommend", "2", "--other"]


@pytest.mark.parametrize("size", [(80, 24), (80, 40)])
def test_7_all_four_long_options_and_other_show_wrapped_at_80_columns_and_a_number_answers(ctx, monkeypatch, size):
    from textual.containers import VerticalScroll
    from textual.widgets import Static, TextArea

    from xt.tui.app import Compose, LiveActions, XtTui
    from xt.tui.model import build

    q = _ask(ctx, monkeypatch, *LONG, text="The v0.21.0 plan is ready: how do we go on?")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=size) as pilot:
            await pilot.press("1")
            assert app.panel(1).current.data["id"] == q["id"]
            assert "4 options, Other" in app.panel(1).current.text.plain
            await pilot.press("s")
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, Compose) and screen.options[4].startswith("Decline it — the cards close")
            box = screen.query_one(".compose-context", VerticalScroll)
            text = screen.query_one(".compose-context Static", Static)
            assert box.region.right <= size[0] and box.max_scroll_x == 0  # no horizontal scrolling
            assert box.max_scroll_y == 0, "the whole question and its options fit without scrolling"
            shown = text.render().plain if hasattr(text.render(), "plain") else str(text.render())
            for flag in LONG[1:8:2]:  # every option's full text, consequence included
                opt, cons = flag.split(" :: ")
                assert f"{opt} — {cons}" in shown
            assert "Recommended: 2" in shown and "Other: answer in your own words." in shown
            assert screen.query_one(TextArea).region.height >= 1  # room left to type
            await pilot.press("4")
            assert screen.query_one(TextArea).text.startswith("Option 4: Decline it — the cards close")
            await pilot.press("ctrl+s")
            await pilot.pause()
            assert ctx.ledger.item(q["id"]) is None
            assert _last(ctx)["answer"]["option"] == 4

    asyncio.run(run())


def test_7_a_closed_question_answers_with_y_in_the_tui(ctx, monkeypatch):
    from xt.tui.app import LiveActions, XtTui, YesNo
    from xt.tui.model import build

    q = _ask(ctx, monkeypatch, "--closed", text="Shall the digest go out today?")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.press("1", "s")
            await pilot.pause()
            assert isinstance(app.screen, YesNo) and "Shall the digest go out today?" in app.screen.question
            await pilot.press("escape")  # leaves it unanswered
            await pilot.pause()
            assert ctx.ledger.item(q["id"]) is not None
            await pilot.press("s", "y")
            await pilot.pause()
            assert ctx.ledger.item(q["id"]) is None and _last(ctx)["answer"] == {"kind": "closed", "value": "yes"}

    asyncio.run(run())


def test_7_words_on_options_without_other_are_refused_in_the_tui_and_the_question_stays(ctx, monkeypatch):
    from xt.tui.app import LiveActions

    q = _ask(ctx, monkeypatch, *FOUR)
    with pytest.raises(XtError, match="no Other"):
        LiveActions(ctx).answer(q["id"], "something else")
    assert ctx.ledger.item(q["id"]) is not None


# --- criterion 8: older asks ------------------------------------------------------------------------

OLD_111 = ("When do we ship 0.14.0?\n\nOptions:\n1. Ship on Friday — the release waits two days\n"
           "2. Ship today — no staging check\n3. Split the release — two smaller releases\nRecommended: 1\n"
           "Or answer in your own words.")


def _old_ledger_entry(ctx, body):
    """An ask written by an older xt: no `question` field."""
    _team(ctx)
    m = ctx.ledger.append("liaison", "human", "ask", body)
    assert "question" not in m
    return m


def test_8_a_111_ask_from_an_older_ledger_takes_a_number_or_own_words(ctx, monkeypatch, capsys):
    q = _old_ledger_entry(ctx, OLD_111)
    assert choices.question_of(q) == {"kind": "options", "other": True, "recommend": 1, "options": [
        {"text": "Ship on Friday", "consequence": "the release waits two days"},
        {"text": "Ship today", "consequence": "no staging check"},
        {"text": "Split the release", "consequence": "two smaller releases"}]}
    _human(monkeypatch)
    _cli(ctx, monkeypatch, "inbox")
    assert "3 options, Other" in capsys.readouterr().out
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "3")
    assert _last(ctx)["body"] == "Option 3: Split the release — two smaller releases"
    q2 = ctx.ledger.append("liaison", "human", "ask", OLD_111)
    _cli(ctx, monkeypatch, "answer", str(q2["id"]), "Friday, and tell QA")
    assert _last(ctx)["body"] == "Friday, and tell QA"


def test_8_a_plain_old_ask_is_an_open_question(ctx, monkeypatch):
    q = _old_ledger_entry(ctx, "Which story? 1 avalanche, 2 tennis")
    assert choices.question_of(q) == {"kind": "open"}
    _human(monkeypatch)
    _cli(ctx, monkeypatch, "answer", str(q["id"]), "2")  # a bare number stays a bare answer
    assert _last(ctx)["body"] == "2" and _last(ctx)["answer"] == {"kind": "open", "value": "2"}


def test_8_older_readers_ignore_the_new_fields_and_the_snapshot_rebuilds(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, "--closed")
    ctx.ledger.rebuild()
    assert ctx.ledger.item(q["id"])["type"] == "ask"
    assert set(q) == {"id", "ts", "type", "from", "to", "ref", "body", "question"}


# --- criterion 9: guidance and the user guide ------------------------------------------------------

def test_9_the_shipped_guidance_and_the_user_guide_describe_the_format():
    flat = lambda f: " ".join((REPO / f).read_text().split())  # noqa: E731 (lines wrap anywhere)
    protocol, liaison, lead, guide = map(flat, ("protocol.md", "roles/liaison.md", "roles/lead.md",
                                                "docs/user-guide.md"))
    for flag in ("--closed", "--option", "--recommend", "--other"):
        assert flag in protocol and flag in liaison and flag in guide
    assert "two to four options" in protocol and "two to four" in lead
    assert "Information alone is a `report`: it needs no answer" in liaison
    assert "**open** (free text)" in liaison and "**closed** (yes or no)" in liaison
    assert "| **closed** |" in guide and "| **options** |" in guide and "| **open** |" in guide
    assert "Questions asked before 0.21.0 still read and answer as they did" in guide
