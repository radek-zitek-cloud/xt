"""v0.22.1: polish and one alert (Space specs/polish-for-0-22-1; cards #207, #204, #203, #201, #202,
#208, #210, #206, #187, #211). Test names start with the card number."""

import pytest

from xt import brief, cli, paneinput
from xt.ledger import pair
from xt.paths import XtError

from . import test_operator_0190
from .test_pane_0220 import _from_human, _liaison, _type

team = test_operator_0190.team  # the #166 fixture: a running liaison and lead, commands run against ctx


def _log(ctx, monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(["log", *argv])
    args.func(args)
    return capsys.readouterr().out


# --- #207: a space before the arrow after the unverified label ---------------------------------------


def test_207_one_space_after_the_label_in_log_and_brief_and_none_added_elsewhere(ctx, fake_home, monkeypatch, capsys):
    from xt import paneinput

    log = _liaison(ctx, fake_home)
    paneinput.scan(ctx)
    _type(log, "codex", "Please ship it")
    paneinput.scan(ctx)
    (m,) = _from_human(ctx)
    plain = cli.send(ctx, "human", "liaison", "ask", "From chat")[0]
    labelled = "human (typed in the pane, unverified) →liaison"
    assert pair(m) == labelled and pair(plain) == "human→liaison"
    for argv in ([], ["--full"], ["--member", "liaison"]):
        out = _log(ctx, monkeypatch, capsys, *argv)
        assert labelled in out and "unverified)→" not in out and "unverified)  →" not in out
        assert f"#{plain['id']} {plain['ts']} ask human→liaison" in out  # no space added, columns unchanged
    text = brief.build(ctx, "liaison")
    assert labelled in text and "unverified)→" not in text and " human→liaison" in text


# --- #204: no "pick" in hidden mode ------------------------------------------------------------------


def test_204_pick_is_offered_only_when_a_one_liner_can_be_picked(ctx):
    from xt.dispatch import send

    from .test_chat_0210 import _run, _status
    from .test_chat_0220 import _team

    _team(ctx)
    send(ctx, "human", "liaison", "ask", "Where are we?")
    send(ctx, "liaison", "lead", "report", "a report, not a goal")  # shows in all mode only

    async def steps(app, pilot):
        await pilot.pause()
        assert app.mode == "goals" and "pick" not in _status(app)  # goals mode, but no goal to pick
        await pilot.press("ctrl+t")  # all: the report can be picked
        assert app.mode == "all" and "↑↓ pick" in _status(app)
        await pilot.press("ctrl+t")  # hidden
        assert app.mode == "hidden" and "pick" not in _status(app) and "ctrl+t" in _status(app)
        await pilot.press("up")  # the pressed-key feedback stays as a fallback
        assert "no team activity lines shown" in _status(app)
        await pilot.press("ctrl+t")
        send(ctx, "liaison", "lead", "goal", "A goal")
        app.refresh_messages()
        await pilot.pause()
        assert app.mode == "goals" and "↑↓ pick" in _status(app)

    _run(ctx, steps, refresh_s=60)


# --- #203: five texts read once ----------------------------------------------------------------------


def test_203_1_the_later_answer_refusal_reads_once_in_xt_answer_and_chat(team, monkeypatch):
    from .test_chat_0210 import _run, _status, _type
    from .test_drive_0220 import _ask, _drive
    from .test_operator_0190 import agent, human

    until = _drive(team, monkeypatch)
    q = _ask(team, monkeypatch, "--closed")
    agent(monkeypatch, "answer", str(q["id"]), "yes", "--as", "op")
    line = f'#{q["id"]} already answered by op (operator, delegated by you until {until}): "yes" — nothing sent.'
    with pytest.raises(XtError) as e:
        human(monkeypatch, "answer", str(q["id"]), "no")
    assert str(e.value) == line

    async def steps(app, pilot):
        app.target = {"id": q["id"], "kind": "question", "from": "liaison", "question": {"kind": "closed"},
                      "text": q["body"]}  # as tab picked it before the operator answered
        await _type(pilot, "no")
        await pilot.press("enter")
        assert _status(app) == line  # no "not sent:" in front

    _run(team, steps, size=(120, 24), refresh_s=60)


def test_203_2_the_questions_header_names_the_type_once(team, monkeypatch, capsys):
    from .test_drive_0220 import _ask, _drive
    from .test_messages_0210 import FOUR
    from .test_operator_0190 import agent

    _drive(team, monkeypatch)
    q = _ask(team, monkeypatch, *FOUR, "--other")
    capsys.readouterr()
    agent(monkeypatch, "inbox", "--questions", "--as", "op")
    out = capsys.readouterr().out
    assert (f"#{q['id']} {q['ts'][5:16]} question from liaison — 4 options · answer 1 to 4, "
            "or in your own words (Other)\n") in out
    assert "Other:" not in out.splitlines()[0]  # the question's own text below still says it


def test_203_3_xt_down_by_an_operator_says_it_is_never_delegated(team, monkeypatch):
    from .test_drive_0220 import _drive
    from .test_operator_0190 import agent, register

    register(team, monkeypatch)
    with pytest.raises(XtError) as e:
        agent(monkeypatch, "down", "--as", "op")
    assert str(e.value) == "xt down is never delegated: the human runs xt down in their own terminal."
    _drive(team, monkeypatch)
    with pytest.raises(XtError) as e:
        agent(monkeypatch, "down", "--as", "op")
    assert str(e.value) == ("xt down is never delegated: op's grant covers drive only. "
                            "The human runs xt down in their own terminal.")


def test_203_4_5_the_status_line_and_the_chat_advice(ctx, fake_home, monkeypatch):
    _liaison(ctx, fake_home, "claude")
    assert paneinput.signal(ctx) == "liaison (claude): pane input recorded (prompt hook and session log)"
    monkeypatch.setattr(paneinput, "session_log", lambda c, a: None)
    for width in (80, 100, 117):
        head = paneinput.header(paneinput.state(ctx), "liaison", width)
        assert "talk in xt chat" not in head and "type here" in head


# --- #201, #202: the pane-input signal per state, in xt status and the chat header -------------------

SHORT = {  # card #202, string-exact at 80 columns
    "recorded": "xt chat with liaison (claude) · pane input recorded",
    "log only": "xt chat with liaison (pi) · pane input: session log only",
    "not running": "xt chat with liaison (claude) · pane input: liaison isn't running",
    "unknown": "xt chat with liaison (claude) · pane input: unknown (herdr unreachable)",
    "not recorded": "xt chat with liaison (claude) · pane input NOT recorded — type here",
}
WIDE = {  # above 96 columns, with the reason
    "recorded": "xt chat with liaison (claude) · pane input recorded (prompt hook and session log)",
    "log only": "xt chat with liaison (pi) · pane input: session log only (no warning in the pane)",
    "not running": SHORT["not running"],
    "unknown": "xt chat with liaison (claude) · pane input: unknown (herdr server not reachable)",
    "not recorded": "xt chat with liaison (claude) · pane input NOT recorded (no session log) — type here in chat",
}
STATUS = {  # xt status keeps the full wording
    "recorded": "liaison (claude): pane input recorded (prompt hook and session log)",
    "log only": "liaison (pi): pane input recorded (session log only; no warning in the pane)",
    "not running": "liaison (claude): pane input: liaison isn't running",
    "unknown": "liaison (claude): pane input: unknown (herdr server not reachable)",
    "not recorded": "liaison (claude): pane input NOT recorded (no session log): talk in xt chat",
}


def _variant(ctx, home, monkeypatch, variant):
    _liaison(ctx, home, "pi" if variant == "log only" else "claude")
    if variant == "not running":
        ctx.herdr.live.pop("liaison")
    if variant == "unknown":
        def down():
            raise XtError("herdr: server_unreachable: no server")
        monkeypatch.setattr(ctx.herdr, "agents", down)
    if variant == "not recorded":
        monkeypatch.setattr(paneinput, "session_log", lambda c, a: None)


def _status_out(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "human_terminal", lambda: True)
    capsys.readouterr()
    args = cli.build_parser().parse_args(["status"])
    args.func(args)
    return capsys.readouterr().out


@pytest.mark.parametrize("variant", list(SHORT))
def test_201_202_status_and_the_header_in_all_five_variants_at_80_100_117(ctx, fake_home, monkeypatch, capsys,
                                                                          variant):
    from .test_chat_0210 import _run, _text

    _variant(ctx, fake_home, monkeypatch, variant)
    assert paneinput.signal(ctx) == STATUS[variant]
    if variant != "unknown":  # with Herdr down, `xt status` stops before its pane line
        assert STATUS[variant] in _status_out(ctx, monkeypatch, capsys).splitlines()
    for width in (80, 100, 117):
        async def steps(app, pilot):
            head = app.query_one("#header")
            text = _text(head)
            assert text == (SHORT if width <= 96 else WIDE)[variant], (width, text)
            assert head.size.height == 1 and len(text) <= width - 4, (width, text)

        _run(ctx, steps, size=(width, 24), refresh_s=60)


def test_201_a_retired_liaison_isnt_running(ctx, fake_home):
    from xt.spawn import retire

    _liaison(ctx, fake_home, "claude")
    retire(ctx, "human", "liaison")
    assert paneinput.signal(ctx) == "liaison (claude): pane input: liaison isn't running"
