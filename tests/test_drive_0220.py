"""v0.22.0 card #200: the delegation scope "drive"."""

import pytest

from xt import operators
from xt.paths import XtError
from xt.spawn import Approvals
from xt.tui.model import build

from .conftest import REPO, add_member
from .test_messages_0210 import FOUR
from . import test_operator_0190
from .test_operator_0190 import _system, agent, human, register

team = test_operator_0190.team  # the #166 fixture: a running liaison and lead, commands run against ctx


def _last(ctx):
    return list(ctx.ledger.messages())[-1]


def _ask(ctx, monkeypatch, *flags, text="Shall we build it?"):
    agent(monkeypatch, "send", "human", "--as", "liaison", "--type", "ask", *flags, text)
    return _last(ctx)


def _hire(ctx):
    """A pending hire: the lead asks to spawn carol (spawn_approval is on in the test team)."""
    add_member(ctx, "carol", reports_to="lead")
    ctx.team.set_status("carol", "retired")
    ctx.team.save()
    ctx.reload_team()
    return Approvals(ctx).add({"requester": "lead", "name": "carol", "harness": "claude", "model": None,
                               "role": "worker", "reports_to": "lead"})


def _drive(ctx, monkeypatch, length="30m"):
    register(ctx, monkeypatch)
    human(monkeypatch, "delegate", "op", "--for", length, "--scope", "drive")
    return operators.until_text(operators.active_grant(ctx, "op"))


# --- done-when 1 and 4: no drive grant, no answers, approvals or goals --------------------------------


@pytest.mark.parametrize("grant", [None, "plain"])
def test_1_4_without_a_drive_grant_answers_approvals_and_goals_are_refused(team, monkeypatch, grant):
    register(team, monkeypatch)
    if grant:
        human(monkeypatch, "delegate", "op", "--for", "30m")
    q = _ask(team, monkeypatch, "--closed")
    rid = _hire(team)
    why = "grant active: restart, reset, spawn, up until .*answers, approvals and goals not included" if grant \
        else "operator op has no drive grant: only the human"
    for argv in (["answer", str(q["id"]), "yes"], ["answer", str(rid), "yes"], ["approve", str(rid)],
                 ["deny", str(rid)], ["send", "liaison", "--type", "goal", "Build the digest"]):
        with pytest.raises(XtError, match=why):
            agent(monkeypatch, *argv, "--as", "op")
    assert team.ledger.item(q["id"]) is not None and str(rid) in Approvals(team).pending()
    assert not [m for m in team.ledger.messages() if m["from"] == "op"]


# --- done-when 2 and 3: the three actions, recorded under the operator's name -------------------------


def test_2_3_answers_are_checked_like_xt_answer_and_recorded_under_the_operator(team, monkeypatch, capsys):
    until = _drive(team, monkeypatch)
    mark = f"(op, delegated by human until {until}: an operator acting on the human's behalf)"
    closed = _ask(team, monkeypatch, "--closed")
    with pytest.raises(XtError, match="yes/no question"):
        agent(monkeypatch, "answer", str(closed["id"]), "maybe", "--as", "op")
    agent(monkeypatch, "answer", str(closed["id"]), "y", "--as", "op")
    a = _last(team)
    assert (a["from"], a["to"], a["type"], a["ref"]) == ("op", "liaison", "report", closed["id"])
    assert a["body"] == f"yes\n{mark}" and a["answer"] == {"kind": "closed", "value": "yes"}
    assert a["delegated"]["by"] == "human" and team.ledger.item(closed["id"]) is None
    opts = _ask(team, monkeypatch, *FOUR)
    with pytest.raises(XtError, match="no Other"):
        agent(monkeypatch, "answer", str(opts["id"]), "my own words", "--as", "op")
    agent(monkeypatch, "answer", str(opts["id"]), "2", "--as", "op")
    assert "recorded as: Option 2: Approve with a change" in capsys.readouterr().out
    other = _ask(team, monkeypatch, *FOUR, "--other")
    agent(monkeypatch, "answer", str(other["id"]), "Approve, tell QA", "--as", "op")
    assert _last(team)["answer"] == {"kind": "options", "other": True, "value": "Approve, tell QA"}
    open_q = _ask(team, monkeypatch, text="What title?")
    agent(monkeypatch, "answer", str(open_q["id"]), "Weekly notes", "--as", "op")
    assert _last(team)["answer"] == {"kind": "open", "value": "Weekly notes"}
    assert not [m for m in team.ledger.messages() if m["from"] == "human"]
    assert not [i for i in team.ledger.open_items() if i["type"] == "ask"]


def test_2_approvals_are_decided_and_recorded_under_the_operator(team, monkeypatch):
    until = _drive(team, monkeypatch)
    rid = _hire(team)
    agent(monkeypatch, "answer", str(rid), "yes", "--as", "op")
    assert "carol" in team.herdr.live and str(rid) not in Approvals(team).pending()
    rec = [m for m in team.ledger.messages() if m["from"] == "op"][-1]
    assert (rec["to"], rec["type"], rec["ref"], rec["answer"]) == ("human", "report", rid, {"kind": "closed", "value": "yes"})
    assert rec["body"].startswith(f"approved approval #{rid} (spawn carol (worker, claude/default)): spawned carol")
    assert rec["body"].endswith(f"(op, delegated by human until {until}: an operator acting on the human's behalf)")
    told = [m for m in team.ledger.messages() if m["to"] == "lead" and m["type"] == "system"][-1]
    assert told["body"].startswith(f"Operator op, delegated by human until {until}, approved approval #{rid}")
    schedule = Approvals(team).add({"kind": "schedule", "requester": "lead", "name": "carol", "every": "1d",
                                    "message": None, "between": None, "at": None})
    agent(monkeypatch, "deny", str(schedule), "--as", "op")
    assert _last(team)["body"].startswith(f"denied approval #{schedule}") and team.ledger.message(schedule)
    assert not [m for m in team.ledger.messages() if m["from"] == "human"]


def test_2_a_goal_reaches_the_liaison_from_the_operator(team, monkeypatch, capsys):
    until = _drive(team, monkeypatch)
    agent(monkeypatch, "send", "liaison", "--as", "op", "--type", "goal", "Build the weekly digest")
    g = _last(team)
    assert (g["from"], g["to"], g["type"]) == ("op", "liaison", "goal")
    assert g["body"] == ("Build the weekly digest\n"
                         f"(op, delegated by human until {until}: an operator acting on the human's behalf)")
    assert operators.is_operator_message(g) and team.ledger.item(g["id"])["owner"] == "liaison"
    with pytest.raises(XtError, match="sends to the liaison only"):
        agent(monkeypatch, "send", "lead", "--as", "op", "--type", "goal", "x")
    with pytest.raises(XtError, match="never opens tasks"):
        agent(monkeypatch, "send", "liaison", "--as", "op", "--type", "task", "x")


# --- done-when 5 and 8: never delegable ------------------------------------------------------------


def test_5_8_non_delegable_commands_stay_refused_under_drive(team, monkeypatch):
    _drive(team, monkeypatch)
    for argv, why in ((["down"], "is an operator"), (["restart", "--all"], "with --all"),
                      (["version", "use", "v0.18.0"], "is an operator"), (["version", "rollback"], "is an operator"),
                      (["operator", "add", "op2", "--pid", "1"], "is an operator"),
                      (["delegate", "op", "--for", "60m"], "is an operator"),
                      (["delegate", "--revoke"], "is an operator"),
                      (["restart", "lead"], r"grant active: drive until \d\d:\d\d; restart not included")):
        with pytest.raises(XtError, match=why):
            agent(monkeypatch, *argv, "--as", "op")
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        agent(monkeypatch, "answer", "1", "yes", "--as", "human")
    assert {"liaison", "lead"} <= set(team.herdr.live)


def test_5_scopes_do_not_combine_and_drive_takes_no_only(team, monkeypatch):
    _drive(team, monkeypatch)
    with pytest.raises(XtError, match="--only picks commands"):
        human(monkeypatch, "delegate", "op", "--scope", "drive", "--only", "restart")
    human(monkeypatch, "delegate", "op", "--for", "20m")  # replaces drive
    assert operators.active_grant(team, "op").get("scope") is None
    q = _ask(team, monkeypatch, "--closed")
    with pytest.raises(XtError, match="answers, approvals and goals not included"):
        agent(monkeypatch, "answer", str(q["id"]), "yes", "--as", "op")


# --- done-when 6, 7, 11: expiry, revoke, status, header ---------------------------------------------


@pytest.mark.parametrize("end", ["expired", "revoked"])
def test_6_11_after_the_grant_ends_actions_are_refused_and_one_line_says_so(team, monkeypatch, clock, capsys, end):
    _drive(team, monkeypatch, "5m")
    q = _ask(team, monkeypatch, "--closed")
    if end == "expired":
        clock.advance(minutes=5)
    else:
        human(monkeypatch, "delegate", "--revoke")
    with pytest.raises(XtError, match=rf"operator op's drive grant ended \d\d:\d\d \({end}\): only the human"):
        agent(monkeypatch, "answer", str(q["id"]), "yes", "--as", "op")
    with pytest.raises(XtError, match="drive grant ended"):
        agent(monkeypatch, "send", "liaison", "--as", "op", "--type", "goal", "x")
    human(monkeypatch, "status")
    lines = [b for b in _system(team) if "drive grant for op ended" in b]
    assert len(lines) == 1  # once, however often it's checked
    assert "drive grant for op ended" in capsys.readouterr().out
    assert "drive grant for op ended" in build(team).header.plain


def test_6_the_supervisor_writes_the_expiry_line_without_a_command(team, monkeypatch, clock):
    _drive(team, monkeypatch, "5m")
    clock.advance(minutes=6)
    assert operators.announce_ended(team) == [f"drive grant for op ended {operators._local(operators.load(team.paths)['ended']['op']['at']):%H:%M}"]
    assert operators.announce_ended(team) == []


def test_7_status_and_the_tui_header_show_drive_and_the_end_time(team, monkeypatch, capsys):
    until = _drive(team, monkeypatch, "45m")
    assert f"human delegated drive (answers, approvals and goals) to operator op until {until}" in _system(team)
    capsys.readouterr()
    human(monkeypatch, "status")
    assert f"delegation: delegated to op until {until}: drive" in capsys.readouterr().out
    assert f"delegated to op until {until}: drive" in build(team).header.plain


# --- done-when 10: the read path, and the human's later answer -----------------------------------------


def test_10_the_operator_reads_the_pending_questions_whole(team, monkeypatch, capsys):
    _drive(team, monkeypatch)
    q = _ask(team, monkeypatch, *FOUR, text="Which way for the digest?")
    rid = _hire(team)
    capsys.readouterr()
    agent(monkeypatch, "inbox", "--questions")
    out = capsys.readouterr().out
    assert f"#{q['id']} " in out and "question from liaison — 4 options: answer 1 to 4" in out
    assert "  2. Approve with a change — I adjust the spec first" in out and "  Recommended: 2" in out
    assert f"answer: xt answer {q['id']}" in out
    assert f"#{rid} approval requested by lead — yes/no" in out and "spawn carol (worker, claude/default)" in out


def test_10_the_humans_later_answer_names_the_operator_and_quotes_the_answer(team, monkeypatch):
    until = _drive(team, monkeypatch)
    q = _ask(team, monkeypatch, *FOUR)
    agent(monkeypatch, "answer", str(q["id"]), "3", "--as", "op")
    expected = (f"#{q['id']}: answered by op (operator, delegated by you until {until}): "
                "Option 3: Defer — it moves to the next release and nothing is built now")
    with pytest.raises(XtError, match="^" + expected.replace("(", r"\(").replace(")", r"\)")):
        human(monkeypatch, "answer", str(q["id"]), "1")
    from xt import cli

    with pytest.raises(XtError, match="answered by op"):
        cli.answer(team, "human", q["id"], "1")  # the path `xt chat` takes
    rid = _hire(team)
    agent(monkeypatch, "answer", str(rid), "no", "--as", "op")
    with pytest.raises(XtError, match=rf"approval #{rid}: answered by op \(operator, delegated by you until {until}\)"):
        cli.answer(team, "human", rid, "yes")


def test_9_the_user_guide_and_examples_explain_drive():
    guide = (REPO / "docs" / "user-guide.md").read_text()
    for cmd in ("xt delegate helper --for 30m --scope drive", "xt inbox --questions",
                "xt answer 1290 yes --as helper", "xt send liaison --as helper --type goal"):
        assert cmd in guide, cmd
    assert "--scope drive" in (REPO / "docs" / "examples.md").read_text()
