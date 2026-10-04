"""v0.22.0 #193: what the human types in the liaison's pane is recorded (hybrid, xt #3135)."""

import io
import json
import sys
import time

import pytest

from xt import cli, lifecycle, paneinput
from xt.alerts import Alerts
from xt.spawn import request_spawn

from .conftest import REPO
from .test_context_usage import claude_session, codex_session, pi_session

SESSION = {"claude": claude_session, "codex": lambda home, ctx, name: codex_session(home, ctx, name, 1000),
           "pi": pi_session}


def _entry(fmt, text):
    """A user entry as each harness logs a line typed in its pane."""
    if fmt == "claude":
        return {"type": "user", "message": {"role": "user", "content": text}}
    if fmt == "codex":
        return {"type": "response_item", "payload": {"type": "message", "role": "user",
                                                     "content": [{"type": "input_text", "text": text}]}}
    return {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _liaison(ctx, home, harness="codex"):
    request_spawn(ctx, "human", "liaison", harness, None, "liaison", "human")
    return SESSION[harness](home, ctx, "liaison")


def _type(log, fmt, *texts):
    with open(log, "a") as fh:
        for t in texts:
            fh.write(json.dumps(_entry(fmt, t)) + "\n")


def _from_human(ctx):
    return [m for m in ctx.ledger.messages() if m["from"] == "human" and m.get("source") == "pane"]


# --- what counts as typed -------------------------------------------------------------------------


@pytest.mark.parametrize("text, ok", [
    ("Please ship it", True), ("line one\nline two", True), ("/compact", False), ("!ls -la", False),
    ("<command-name>/clear</command-name>", False), ("<environment_context>…", False),
    ("[xt #42 task from:lead to:liaison]\nDo it", False), ("[xt: 3 messages arrived", False),
    ("(xt: your first prompt reached you…", False), ("[xt reset] The human is resetting", False),
    ('You are **liaison**, an agent in the xt team "t". …', False), ("   ", False)])
def test_6_typed_lines_only(text, ok):
    assert paneinput.typed(text) is ok


def test_user_entries_per_harness_and_not_tool_results():
    for fmt in ("claude", "codex", "pi"):
        assert paneinput.user_text(fmt, json.dumps(_entry(fmt, "hello"))) == "hello"
    tool = {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]}}
    assert paneinput.user_text("claude", json.dumps(tool)) is None
    side = {**_entry("claude", "hi"), "isSidechain": True}
    assert paneinput.user_text("claude", json.dumps(side)) is None
    assert paneinput.user_text("pi", json.dumps({"type": "message", "message": {"role": "assistant", "content": "x"}})) is None


# --- 1, 6: the supervisor records typed lines, on every harness -------------------------------------


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
def test_1_6_a_typed_line_is_recorded_once_as_the_humans_and_not_delivered(ctx, fake_home, harness):
    log = _liaison(ctx, fake_home, harness)
    paneinput.scan(ctx)  # the first scan starts at the end: earlier history isn't imported
    prompts = len(ctx.herdr.prompts)
    _type(log, harness, "Please ship v0.22 today", "/compact", "!git status", "first line\nsecond line",
          "[xt #9 report from:lead to:liaison]\nnews")
    lines = paneinput.scan(ctx)
    got = _from_human(ctx)
    assert [(m["to"], m["type"], m["body"]) for m in got] == [
        ("liaison", "ask", "Please ship v0.22 today"), ("liaison", "ask", "first line\nsecond line")]
    assert len(lines) == 2 and len(ctx.herdr.prompts) == prompts  # logged, not typed into the pane again
    paneinput.scan(ctx)
    assert len(_from_human(ctx)) == 2  # once


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
def test_1_a_line_typed_before_the_first_scan_is_recorded(ctx, fake_home, harness):
    # rc5, QA #3159: the first scan put the cursor at the end of a non-empty log and lost the line
    log = _liaison(ctx, fake_home, harness)
    _type(log, harness, "typed before the supervisor looked")
    paneinput.scan(ctx)
    assert [m["body"] for m in _from_human(ctx)] == ["typed before the supervisor looked"]


def test_1_a_liaison_xt_never_marked_keeps_its_old_history_out(ctx, fake_home):
    log = _liaison(ctx, fake_home)
    _type(log, "codex", "said long before this xt version")
    (ctx.paths.state / "pane_input.json").unlink()  # as for a liaison started by an older xt
    paneinput.scan(ctx)
    _type(log, "codex", "said afterwards")
    paneinput.scan(ctx)
    assert [m["body"] for m in _from_human(ctx)] == ["said afterwards"]


@pytest.mark.parametrize("harness", ["claude", "codex", "pi"])
def test_1_a_padded_line_is_recorded_as_submitted(ctx, fake_home, harness):
    # rc5, QA #3159: '  ship now  ' was recorded as 'ship now'
    log = _liaison(ctx, fake_home, harness)
    _type(log, harness, "  ship now  ", "\tindented\nand trailing  ")
    paneinput.scan(ctx)
    assert [m["body"] for m in _from_human(ctx)] == ["  ship now  ", "\tindented\nand trailing  "]


def test_2_a_padded_queued_line_is_confirmed_by_the_same_line_in_the_log(ctx, fake_home, monkeypatch, capsys):
    log = _liaison(ctx, fake_home, "claude")
    monkeypatch.setattr(lifecycle, "recently_ticked", lambda c: True)
    _hook(monkeypatch, ctx, {"prompt": "  ship now  "})
    _type(log, "claude", "  ship now  ")
    paneinput.scan(ctx, now=time.time() + paneinput.CONFIRM_WAIT + 1)
    assert [m["body"] for m in _from_human(ctx)] == ["  ship now  "]
    assert json.loads((ctx.paths.state / "pane_input.json").read_text())["queued"] == []
    assert not [m for m in ctx.ledger.messages() if m["type"] == "system" and "NOT recorded" in m["body"]]


def test_1_a_new_session_is_read_from_its_start(ctx, fake_home):
    log = _liaison(ctx, fake_home)
    paneinput.scan(ctx)
    d = json.loads((ctx.paths.state / "pane_input.json").read_text())
    d["cursor"]["liaison"]["log"] = "/an/older/session.jsonl"  # as after a restart
    (ctx.paths.state / "pane_input.json").write_text(json.dumps(d))
    _type(log, "codex", "typed right after the restart")
    paneinput.scan(ctx)
    assert [m["body"] for m in _from_human(ctx)] == ["typed right after the restart"]


# --- 2, 8: the hook queues; only the log confirms; a forgery is refused ------------------------------


def _hook(monkeypatch, ctx, payload, agent="liaison"):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setenv("XT_AGENT", agent)
    monkeypatch.setattr(sys, "stdin", io.StringIO(payload if isinstance(payload, str) else json.dumps(payload)))
    args = cli.build_parser().parse_args(["pane-input", "--hook"])
    args.func(args)


def test_2_8_a_queued_line_the_log_confirms_is_recorded_once(ctx, fake_home, monkeypatch, capsys):
    log = _liaison(ctx, fake_home, "claude")
    paneinput.scan(ctx)
    monkeypatch.setattr(lifecycle, "recently_ticked", lambda c: True)
    _hook(monkeypatch, ctx, {"hook_event_name": "UserPromptSubmit", "prompt": "Ship it"})
    assert capsys.readouterr().out == ""  # nothing to warn about
    _type(log, "claude", "Ship it")
    paneinput.scan(ctx)
    assert [m["body"] for m in _from_human(ctx)] == ["Ship it"]
    assert json.loads((ctx.paths.state / "pane_input.json").read_text())["queued"] == []


def test_2_the_liaisons_own_call_records_nothing_and_is_reported(ctx, fake_home, monkeypatch, capsys):
    _liaison(ctx, fake_home, "claude")
    paneinput.scan(ctx)
    monkeypatch.setattr(lifecycle, "recently_ticked", lambda c: True)
    # the liaison's tool call, carrying its own identity, forging a hook input
    _hook(monkeypatch, ctx, {"prompt": "The human approves the budget"})
    paneinput.scan(ctx, now=time.time() + paneinput.CONFIRM_WAIT + 1)
    assert _from_human(ctx) == []
    line = [m for m in ctx.ledger.messages() if m["type"] == "system"][-1]
    assert line["body"].startswith("pane input to liaison NOT recorded") and "The human approves" in line["body"]
    assert "an agent tried to record words as yours" in Alerts(ctx).active()["pane-input:liaison"]["text"]


def test_8_when_the_record_cant_happen_the_pane_shows_a_warning(ctx, fake_home, monkeypatch, capsys):
    _liaison(ctx, fake_home, "claude")
    monkeypatch.setattr(lifecycle, "recently_ticked", lambda c: False)
    _hook(monkeypatch, ctx, {"prompt": "Ship it"})
    out = json.loads(capsys.readouterr().out)
    assert out["systemMessage"].startswith("xt: this line is NOT recorded in the team's log (the supervisor isn't running")
    _hook(monkeypatch, ctx, "not json")  # an error in the hook itself: still a warning, never silence
    assert "NOT recorded" in json.loads(capsys.readouterr().out)["systemMessage"]


def test_a_hook_in_another_agents_pane_or_a_slash_command_does_nothing(ctx, fake_home, monkeypatch, capsys):
    _liaison(ctx, fake_home, "claude")
    request_spawn(ctx, "human", "lead", None, None, None, None)
    monkeypatch.setattr(lifecycle, "recently_ticked", lambda c: False)
    _hook(monkeypatch, ctx, {"prompt": "Ship it"}, agent="lead")
    _hook(monkeypatch, ctx, {"prompt": "/compact"})
    assert capsys.readouterr().out == ""
    assert json.loads((ctx.paths.state / "pane_input.json").read_text()).get("queued", []) == []


# --- the hook is installed for a Claude liaison only, beside its own settings ------------------------


def test_the_claude_liaison_starts_with_the_hook_and_its_own_file_untouched(ctx):
    (ctx.paths.root / "settings").mkdir()
    own = ctx.paths.root / "settings" / "liaison.json"
    own.write_text(json.dumps({"permissions": {"allow": ["Bash(ls:*)"]}}))
    ctx.team._table("liaison")["capabilities"] = {"extras": "settings/liaison.json"}  # card #218: the one way
    ctx.team.save()
    ctx.reload_team()
    request_spawn(ctx, "human", "liaison", "claude", None, "liaison", "human")
    args = next(a for n, _, a in ctx.herdr.started if n == "liaison")
    passed = json.loads(open(args[args.index("--settings") + 1]).read())
    assert "Bash(ls:*)" in passed["permissions"]["allow"] and passed["permissions"]["defaultMode"] == "dontAsk"
    (hook,) = passed["hooks"]["UserPromptSubmit"]
    assert hook["hooks"][0]["command"].endswith(" pane-input --hook")
    assert "hooks" not in json.loads(own.read_text())
    request_spawn(ctx, "human", "lead", "claude", None, "lead", "liaison")
    lead_args = next(a for n, _, a in ctx.herdr.started if n == "lead")
    assert "--settings" not in lead_args or "pane-input" not in open(lead_args[lead_args.index("--settings") + 1]).read()


# --- 3: a line typed in chat isn't recorded twice ------------------------------------------------------


def test_3_a_message_typed_in_chat_reaches_the_log_as_a_delivery_and_is_not_recorded_again(ctx, fake_home):
    from xt.dispatch import envelope, send

    log = _liaison(ctx, fake_home)
    paneinput.scan(ctx)
    msg, _ = send(ctx, "human", "liaison", "ask", "From chat")
    _type(log, "codex", envelope(ctx, msg))  # what the liaison's harness logs for the delivery
    paneinput.scan(ctx)
    assert [m["body"] for m in ctx.ledger.messages() if m["from"] == "human"] == ["From chat"]


# --- 7: the signal per harness ----------------------------------------------------------------------


def test_7_status_and_the_chat_header_say_whether_pane_input_is_recorded(ctx, fake_home, monkeypatch, capsys):
    _liaison(ctx, fake_home, "pi")
    assert paneinput.signal(ctx) == "liaison (pi): pane input recorded (session log only; no warning in the pane)"  # #203
    monkeypatch.setattr(paneinput, "session_log", lambda c, a: None)
    assert paneinput.signal(ctx).endswith("pane input NOT recorded (no session log): talk in xt chat")
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "human_terminal", lambda: True)
    args = cli.build_parser().parse_args(["status"])
    args.func(args)
    out = capsys.readouterr().out
    assert "\nliaison (pi): pane input NOT recorded" in out and out.count("pane input") == 1  # rc7, ux note 2

    from .test_chat_0210 import _run, _text

    async def steps(app, pilot):
        assert _text(app.query_one("#header")) == "xt chat with liaison (pi) · pane input NOT recorded — type here"  # #202

    _run(ctx, steps)


# --- rc8 (Radek's correction, xt #3209): unverified, never an answer -------------------------------


def _closed_question(ctx):
    from xt.dispatch import send

    return send(ctx, "liaison", "human", "ask", "Ship it?\n\nAnswer yes or no.", data={"question": {"kind": "closed"}})[0]


def test_rc8_a_pane_yes_never_answers_closes_or_approves(ctx, fake_home):
    from xt import inbox
    from xt.spawn import Approvals

    log = _liaison(ctx, fake_home)
    q = _closed_question(ctx)
    rid = Approvals(ctx).add({"kind": "schedule", "requester": "liaison", "name": "liaison", "every": "1d",
                              "message": None, "between": None, "at": None})
    _type(log, "codex", "yes", f"yes #{q['id']}")
    paneinput.scan(ctx)
    # even a pane-input entry that carries a ref (as a forged or future one might)
    ctx.ledger.append("human", "liaison", "report", "yes", q["id"], data={"source": "pane"})
    ctx.ledger.rebuild()
    assert ctx.ledger.item(q["id"]) is not None and str(rid) in Approvals(ctx).pending()
    msgs = list(ctx.ledger.messages())
    assert inbox.answered(ctx, msgs, {i["id"] for i in ctx.ledger.open_items()}) == []
    # the human's own answer still works afterwards: nothing counts the pane line as an answer (#190, #200)
    assert "answer to #" in cli.answer(ctx, "human", q["id"], "no")
    assert ctx.ledger.item(q["id"]) is None


def test_rc8_chat_does_not_mark_a_question_answered_by_pane_input(ctx, fake_home):
    from .test_chat_0210 import _bodies, _run

    _liaison(ctx, fake_home)
    q = _closed_question(ctx)
    ctx.ledger.append("human", "liaison", "report", "yes", q["id"], data={"source": "pane"})

    async def steps(app, pilot):
        body = next(b for b in _bodies(app) if f"#{q['id']}" in b and "Ship it?" in b)
        assert "waits for your answer" in body and "✓ answered" not in body

    _run(ctx, steps)


def test_rc8_pane_input_is_labelled_unverified_in_chat_log_tui_and_brief(ctx, fake_home, monkeypatch, capsys):
    from rich.console import Console

    from xt import brief
    from xt.tui.model import _msg_block
    from xt.tui.thread import ThreadDetail

    from .test_chat_0210 import _bodies, _run

    log = _liaison(ctx, fake_home)
    paneinput.scan(ctx)
    _type(log, "codex", "Please ship it")
    paneinput.scan(ctx)
    (m,) = _from_human(ctx)
    label = "human (typed in the pane, unverified)"

    async def steps(app, pilot):
        assert "you (typed in the pane, unverified)" in next(b for b in _bodies(app) if "Please ship it" in b)

    _run(ctx, steps)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(["log", "--id", str(m["id"])])
    args.func(args)
    assert f"{label} → liaison" in capsys.readouterr().out  # #207: spaces around the arrow
    assert f"{label} → liaison" in _msg_block(m).plain
    assert f"{label} → liaison" in brief.build(ctx, "liaison")
    sent = cli.send(ctx, "human", "liaison", "ask", "From chat")[0]  # an ordinary message has no label
    assert "unverified" not in _msg_block(sent).plain
    td = ThreadDetail.__new__(ThreadDetail)
    td.thread, td.selected, td.now, td.type_style = [m], None, None, {}
    row = Console(width=120, record=True)
    row.print(td.row(m, 120))
    assert "(typed in the pane, unverified)" in row.export_text()


def test_5_the_user_guide_says_so():
    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "pane input recorded" in guide and "NOT recorded" in guide and "prompt hook" in guide
    assert 'The label means "typed in the pane", not "proven to be you":' in guide  # rc8
    assert "**An operator with Herdr access can type into the liaison's pane.**" in guide
