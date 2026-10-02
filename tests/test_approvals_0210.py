"""v0.21.0: approvals as closed questions (#183)."""

import asyncio
import re

import pytest

from xt import brief, cli
from xt.paths import XtError
from xt.spawn import Approvals, request_spawn

from .conftest import REPO, add_member


def _cli(ctx, monkeypatch, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(list(argv))
    args.func(args)


def _human(monkeypatch):
    monkeypatch.setattr(cli, "human_terminal", lambda: True)


def _hires(ctx, *names):
    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")
    for n in names:
        request_spawn(ctx, "lead", n, "claude", None, "coder", None)
    return [int(i) for i in sorted(Approvals(ctx).pending(), key=int)]


def _schedule(ctx, monkeypatch, name="scout"):
    add_member(ctx, name)
    ctx.herdr.add("lead")
    monkeypatch.setattr(cli, "human_terminal", lambda: False)
    _cli(ctx, monkeypatch, "schedule", name, "30m", "--message", "check the feeds", "--as", "lead")
    ctx.reload_team()
    return max(int(i) for i in Approvals(ctx).pending())


def _msg(ctx, mid):
    return ctx.ledger.message(mid)


def _after(ctx, mid):
    """What the ledger recorded after message `mid`, without ids and times."""
    return [(m["type"], m["from"], m["to"], re.sub(r"#\d+|\bw\d+\b", "#N", m["body"])) for m in ctx.ledger.messages()
            if m["id"] > mid]


# --- criterion 1: each request is a closed question with the request as its narrative ----------------

def test_1_hire_and_schedule_requests_are_closed_questions(ctx, monkeypatch, capsys):
    (hire,) = _hires(ctx, "carol")
    sched = _schedule(ctx, monkeypatch)
    for rid, first in ((hire, "lead asks to spawn carol as coder on claude"),
                       (sched, "lead asks to wake scout every 30m when idle")):
        m = _msg(ctx, rid)
        assert m["type"] == "approval" and m["question"] == {"kind": "closed"}
        assert m["body"].startswith(first)
        assert f"Answer yes or no: xt answer {rid} yes|no" in m["body"]
    _human(monkeypatch)
    capsys.readouterr()
    _cli(ctx, monkeypatch, "inbox")
    out = capsys.readouterr().out
    assert f"#{hire} lead → spawn carol (coder, claude/default)" in out and f"yes/no  (xt answer {hire} yes|no)" in out
    assert f"yes/no  (xt answer {sched} yes|no)" in out
    b = brief.build(ctx, "liaison")
    assert f"approval #{hire} (yes/no)" in b and "`xt answer <id> yes|no`" in b
    from xt.tui.model import build

    rows = {r.data["id"]: r for r in build(ctx).panels["Inbox"] if r.kind == "approval"}
    assert rows[hire].text.plain.endswith("yes/no") and rows[hire].data["question"] == {"kind": "closed"}
    assert rows[sched].data["text"].startswith("lead asks to wake scout every 30m")


def test_1_goal_dispatch_is_a_closed_read_back_question_and_stays_a_liaison_action():
    liaison = " ".join((REPO / "roles/liaison.md").read_text().split())
    guide = " ".join((REPO / "docs/user-guide.md").read_text().split())
    assert "**as an xt question**, a closed (yes/no) one" in liaison
    assert '--type ask --closed "Ready to dispatch <title>?' in liaison
    assert "Their yes doesn't dispatch anything by itself: dispatching stays your action." in liaison
    assert "dispatching stays the liaison's step (a deliberate limit of 0.21.0)" in guide


# --- criterion 2: yes/no has the same effect and ledger result as approve/deny -----------------------

def test_2_yes_spawns_like_approve_with_the_same_ledger_result(ctx, monkeypatch, capsys):
    carol, dora = _hires(ctx, "carol", "dora")
    _human(monkeypatch)
    mark = ctx.ledger.last_id()
    _cli(ctx, monkeypatch, "answer", str(carol), "yes")
    by_answer = _after(ctx, mark)
    mark = ctx.ledger.last_id()
    _cli(ctx, monkeypatch, "approve", str(dora))
    by_approve = _after(ctx, mark)
    assert {"carol", "dora"} <= set(ctx.herdr.live) and not Approvals(ctx).pending()
    assert [(t, f, to, b.replace("carol", "X")) for t, f, to, b in by_answer] == \
           [(t, f, to, b.replace("dora", "X")) for t, f, to, b in by_approve]
    assert any(t == "system" and "Human approved approval #N" in b for t, _, _, b in by_answer)


def test_2_no_denies_like_deny_for_a_schedule(ctx, monkeypatch):
    first = _schedule(ctx, monkeypatch, "scout")
    second = _schedule(ctx, monkeypatch, "watcher")
    _human(monkeypatch)
    mark = ctx.ledger.last_id()
    _cli(ctx, monkeypatch, "answer", str(first), "no")
    by_answer = _after(ctx, mark)
    mark = ctx.ledger.last_id()
    _cli(ctx, monkeypatch, "deny", str(second))
    by_deny = _after(ctx, mark)
    ctx.reload_team()
    assert ctx.team.agent("scout").wake_every is None and ctx.team.agent("watcher").wake_every is None
    assert [b.replace("scout", "X") for *_, b in by_answer] == [b.replace("watcher", "X") for *_, b in by_deny]
    assert "schedule for X denied" in by_answer[-1][3].replace("scout", "X")


def test_2_only_yes_or_no_answers_an_approval(ctx, monkeypatch):
    (rid,) = _hires(ctx, "carol")
    _human(monkeypatch)
    with pytest.raises(XtError, match="yes/no question: answer yes or no"):
        _cli(ctx, monkeypatch, "answer", str(rid), "sure, go ahead")
    assert Approvals(ctx).pending()


# --- criterion 3: the aliases behave as before, with the note ---------------------------------------

def test_3_approve_and_deny_keep_their_output_and_add_one_note_on_stderr(ctx, monkeypatch, capsys):
    carol, dora, eve = _hires(ctx, "carol", "dora", "eve")
    _human(monkeypatch)
    capsys.readouterr()
    _cli(ctx, monkeypatch, "approve")
    out, err = capsys.readouterr()
    first = out.splitlines()[0]
    assert first.startswith(f"#{carol} lead → spawn carol") and first.endswith(f"(xt approve {carol} | xt deny {carol})")
    assert f"all of them: xt approve {carol} {dora} {eve}" in out
    assert err.count("\n") == 1 and "`xt answer <id> yes|no`" in err and "decided in 0.23.0" in err
    _cli(ctx, monkeypatch, "deny", str(eve))
    out, err = capsys.readouterr()
    assert out == f"#{eve}: spawn of eve denied\n" and "aliases" in err
    _cli(ctx, monkeypatch, "approve", str(carol))
    assert capsys.readouterr()[0].startswith(f"#{carol}: spawned carol")


# --- criterion 4: the TUI keys --------------------------------------------------------------------

def test_4_s_then_y_answers_an_approval_and_a_d_still_work(ctx):
    from xt.tui.app import Confirm, LiveActions, XtTui, YesNo
    from xt.tui.model import build

    carol, dora = _hires(ctx, "carol", "dora")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("1")
            assert app.panel(1).current.data["id"] == carol
            assert "s answer #%d" % carol in str(app.query_one("#hints").render())
            await pilot.press("s")
            await pilot.pause()
            assert isinstance(app.screen, YesNo) and "spawn carol" in app.screen.question
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "carol" in ctx.herdr.live and str(carol) not in Approvals(ctx).pending()
            app.panel(1).focus()
            await pilot.pause()
            assert app.panel(1).current.data["id"] == dora
            await pilot.press("d")
            assert isinstance(app.screen, Confirm)
            await pilot.press("y")
            await app.workers.wait_for_complete()
            await pilot.pause()
            assert "dora" not in ctx.herdr.live and not Approvals(ctx).pending()

    asyncio.run(run())


def test_4_help_and_guide_describe_the_mapping():
    text = (REPO / "src/xt/tui/app.py").read_text()
    assert "approve / deny the selected spawn or schedule (asks y/n); the same as s, then y / n" in text
    assert "answer the question or approval selected in Inbox" in text
    guide = " ".join((REPO / "docs/user-guide.md").read_text().split())
    assert "`xt answer 12 yes` (or `no`), or in the TUI `s` on it and then `y` or `n`. `a` and `d` still" in guide


# --- criterion 5: answered once, whichever route -------------------------------------------------

def test_5_a_second_answer_through_any_route_is_refused_clearly(ctx, monkeypatch, capsys):
    carol, dora = _hires(ctx, "carol", "dora")
    _human(monkeypatch)
    _cli(ctx, monkeypatch, "answer", str(carol), "yes")
    capsys.readouterr()
    _cli(ctx, monkeypatch, "approve", str(carol))
    assert capsys.readouterr()[0] == f"approval #{carol} was already answered; nothing changed (xt log --id {carol})\n"
    with pytest.raises(XtError, match=f"approval #{carol} was already answered"):
        _cli(ctx, monkeypatch, "answer", str(carol), "no")
    _cli(ctx, monkeypatch, "deny", str(dora))
    with pytest.raises(XtError, match=f"approval #{dora} was already answered"):
        _cli(ctx, monkeypatch, "answer", str(dora), "yes")
    from xt.tui.app import LiveActions

    with pytest.raises(XtError, match="already answered"):
        LiveActions(ctx).decide(dora, True)
    assert "dora" not in ctx.herdr.live
    _cli(ctx, monkeypatch, "approve", "12345")  # an id that was never a request: as before
    assert capsys.readouterr()[0].endswith("no pending approval #12345\n")


# --- criterion 6: the identity guard ------------------------------------------------------------

def test_6_only_the_humans_terminal_answers_an_approval(ctx, monkeypatch):
    (rid,) = _hires(ctx, "carol")
    monkeypatch.setattr(cli, "human_terminal", lambda: False)
    with pytest.raises(XtError, match="only the human approves spawns"):
        _cli(ctx, monkeypatch, "answer", str(rid), "yes", "--as", "lead")
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        _cli(ctx, monkeypatch, "answer", str(rid), "yes", "--as", "human")
    with pytest.raises(XtError, match="pass --as <your name>"):
        _cli(ctx, monkeypatch, "answer", str(rid), "yes")
    assert str(rid) in Approvals(ctx).pending() and "carol" not in ctx.herdr.live
