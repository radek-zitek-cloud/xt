"""v0.22.0 #190: a human reply with --ref to a typed question is checked like `xt answer`."""

import pytest

from xt.paths import XtError

from .test_messages_0210 import FOUR, _cli, _human, _last, _team


def _ask(ctx, monkeypatch, *flags, text="Shall we build it?"):
    if ctx.team.agent("liaison") is None:
        _team(ctx)
    _cli(ctx, monkeypatch, "send", "human", "--as", "liaison", "--type", "ask", *flags, text)
    return _last(ctx)


def _reply(ctx, monkeypatch, qid, text):
    _cli(ctx, monkeypatch, "send", "liaison", "--type", "report", "--ref", str(qid), text)


def test_1_free_text_on_a_closed_question_is_refused_and_points_to_xt_answer(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, "--closed")
    _human(monkeypatch)
    n = len(list(ctx.ledger.messages()))
    with pytest.raises(XtError, match=rf"#{q['id']} is a typed question: this is a yes/no question.*"
                                      rf"Nothing was sent. Answer with `xt answer {q['id']}` \(answer yes or no\)"):
        _reply(ctx, monkeypatch, q["id"], "yes, but later")
    assert len(list(ctx.ledger.messages())) == n and ctx.ledger.item(q["id"]) is not None


def test_2_own_words_need_other(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, *FOUR)
    _human(monkeypatch)
    with pytest.raises(XtError, match=r"no Other, so own words.*answer 1 to 4\)$"):
        _reply(ctx, monkeypatch, q["id"], "approve, but tell QA")
    assert ctx.ledger.item(q["id"]) is not None
    q2 = _ask(ctx, monkeypatch, *FOUR, "--other")
    _reply(ctx, monkeypatch, q2["id"], "approve, but tell QA")
    assert _last(ctx)["answer"] == {"kind": "options", "other": True, "value": "approve, but tell QA"}
    assert ctx.ledger.item(q2["id"]) is None


def test_3_a_valid_choice_is_recorded_as_xt_answer_records_it(ctx, monkeypatch, capsys):
    q = _ask(ctx, monkeypatch, *FOUR)
    _human(monkeypatch)
    _reply(ctx, monkeypatch, q["id"], "4")
    a = _last(ctx)
    assert (a["from"], a["to"], a["type"], a["ref"]) == ("human", "liaison", "report", q["id"])
    assert a["body"] == "Option 4: Decline — the card closes and the problem stays as it is"
    assert a["answer"] == {"kind": "options", "option": 4, "value": "Decline — the card closes and the problem stays as it is"}
    assert f"answer to #{q['id']} → liaison" in capsys.readouterr().out
    c = _ask(ctx, monkeypatch, "--closed")
    _reply(ctx, monkeypatch, c["id"], "Y")
    assert _last(ctx)["body"] == "yes" and _last(ctx)["answer"] == {"kind": "closed", "value": "yes"}
    assert ctx.ledger.item(c["id"]) is None


def test_4_open_questions_and_old_asks_behave_as_before(ctx, monkeypatch):
    q = _ask(ctx, monkeypatch, text="What should the digest's title be?")
    _human(monkeypatch)
    _reply(ctx, monkeypatch, q["id"], "Weekly notes")
    a = _last(ctx)
    assert a["body"] == "Weekly notes" and "answer" not in a and ctx.ledger.item(q["id"]) is None
    old = ctx.ledger.append("liaison", "human", "ask", "Ship on Friday?\n1. Ship on Friday — the release waits\n"
                                                       "2. Ship today — no staging check\nRecommended: 1")
    _reply(ctx, monkeypatch, old["id"], "Friday, and tell QA")
    assert _last(ctx)["body"] == "Friday, and tell QA" and ctx.ledger.item(old["id"]) is None


def test_5_the_user_guide_says_so():
    from .conftest import REPO

    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "--ref" in guide and "checked like `xt answer`" in guide
