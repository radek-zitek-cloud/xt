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
    labelled = "human (typed in the pane, unverified) → liaison"  # spaces on both sides (xt #3389)
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
    "not running": "xt chat with liaison (claude) · pane input: not running",  # xt #3389
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
    "not running": "liaison (claude): pane input not recorded (the liaison isn't running)",  # xt #3389
    "unknown": "liaison (claude): pane input unknown (herdr server not reachable)",
    "not recorded": "liaison (claude): pane input NOT recorded (no session log): talk in xt chat",
}


def _variant(ctx, home, monkeypatch, variant):
    _liaison(ctx, home, "pi" if variant == "log only" else "claude")
    if variant == "not running":
        ctx.herdr.live.pop("liaison")
    if variant == "unknown":
        def down(max_snapshot_age=None):
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
    if variant == "unknown":  # Herdr down: status says so on its pane line, then fails as before
        with pytest.raises(XtError, match="server_unreachable"):
            _status_out(ctx, monkeypatch, capsys)
        assert STATUS[variant] in capsys.readouterr().out.splitlines()
    else:
        assert STATUS[variant] in _status_out(ctx, monkeypatch, capsys).splitlines()
    for width in (80, 100, 117):
        async def steps(app, pilot):
            head = app.query_one("#header")
            text = _text(head)
            assert text == (SHORT if width <= 96 else WIDE)[variant], (width, text)
            assert head.size.height == 1 and len(text) <= width - 4, (width, text)

        _run(ctx, steps, size=(width, 24), refresh_s=60)


def _pane_row(ctx, fake_home, width, body="Please ship the release today, after QA's run"):
    from rich.console import Console

    from xt.tui.thread import ThreadDetail

    log = _liaison(ctx, fake_home)
    paneinput.scan(ctx)
    _type(log, "codex", body)
    paneinput.scan(ctx)
    (m,) = _from_human(ctx)
    td = ThreadDetail.__new__(ThreadDetail)
    import datetime as dt

    later = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.timezone.utc)  # another day: rows show the date
    td.thread, td.selected, td.now, td.type_style = [m], None, later, {}
    out = Console(width=width + 10, record=True)
    out.print(td.row(m, width))
    return out.export_text().rstrip("\n"), body


@pytest.mark.parametrize("width, head, label", [
    (120, "09-26 12:00  human   → liaison ask      #2 ", "(typed in the pane, unverified)"),
    (80, "09-26 12:00  human   → liaison ask      #2 ", "(pane, unverified)"),  # the full one leaves 1
    (60, "12:00 human→liaison #2 ", "(pane, unverified)"),  # no form keeps 12 in the full columns
    (40, "12:00 human→liaison #2 ", "(unverified)"),  # nothing keeps 12: the shortest of both
])
def test_208_a_thread_row_keeps_unverified_and_part_of_the_message(ctx, fake_home, width, head, label):
    row, body = _pane_row(ctx, fake_home, width)
    assert row.startswith(head + label + " ") and len(row) <= width, row
    kept = row[len(head + label) + 1:].rstrip("…")
    assert body.startswith(kept) and kept
    if width >= 60:  # 12 characters of the message before any ellipsis
        assert kept == body or len(kept) >= 12, row


def test_208_chat_log_brief_and_detail_keep_the_full_label(ctx, fake_home, monkeypatch, capsys):
    from xt.tui.model import _msg_block

    row, _ = _pane_row(ctx, fake_home, 80)
    (m,) = _from_human(ctx)
    full = "human (typed in the pane, unverified)"
    assert full in _msg_block(m).plain and full in brief.build(ctx, "liaison")
    assert full in _log(ctx, monkeypatch, capsys)


# --- #210: keys for scrolling the chat history ----------------------------------------------------------


def _long_history(ctx, n=30):
    from xt.dispatch import send

    from .test_chat_0220 import _team

    _team(ctx)
    for i in range(n):
        send(ctx, "liaison", "human", "report", f"news {i}\nsecond line\nthird line")


def test_210_page_keys_home_and_end_scroll_the_history_and_leave_the_draft(ctx):
    from textual.containers import VerticalScroll
    from textual.widgets import Input

    from .test_chat_0210 import _run, _type

    _long_history(ctx)

    async def steps(app, pilot):
        history = app.query_one("#history", VerticalScroll)
        draft = app.query_one("#draft", Input)
        await _type(pilot, "half a thought")
        end = history.max_scroll_y
        assert end > 0 and history.scroll_y == end
        page = history.scrollable_content_region.height - 2  # about 2 rows of overlap
        await pilot.press("pageup")
        await pilot.pause()
        assert history.scroll_y == end - page
        await pilot.press("pageup", "pagedown")
        await pilot.pause()
        assert history.scroll_y == end - page
        await pilot.press("home")
        await pilot.pause()
        assert history.scroll_y == 0
        await pilot.press("end")
        await pilot.pause()
        assert history.scroll_y == end
        assert app.focused is draft and draft.value == "half a thought"  # focus and draft unchanged

    _run(ctx, steps, refresh_s=60)


async def _at_end(pilot, history):
    """Whether the view reaches the end within ten frames (new lines get their height a frame or
    two after they're mounted, later under load)."""
    for _ in range(10):
        if history.scroll_y == history.max_scroll_y:
            return True
        await pilot.pause(0.05)
    return False


def test_210_an_arrival_while_scrolled_up_keeps_the_view_and_shows_the_marker(ctx):
    from textual.containers import VerticalScroll

    from xt.dispatch import send

    from .test_chat_0210 import _run, _text, _type

    _long_history(ctx)

    async def steps(app, pilot):
        history = app.query_one("#history", VerticalScroll)
        mark = app.query_one("#newmark")
        assert not mark.display
        await pilot.press("pageup")
        await pilot.pause()
        y = history.scroll_y
        send(ctx, "liaison", "human", "report", "first arrival")
        send(ctx, "liaison", "human", "report", "second arrival")
        app.refresh_messages()
        await pilot.pause()
        assert history.scroll_y == y and mark.display and _text(mark) == "↓ 2 new (End)"
        await pilot.press("end")
        await pilot.pause()
        assert history.scroll_y == history.max_scroll_y and not mark.display
        send(ctx, "liaison", "human", "report", "arrives at the end")  # at the end: the view follows
        app.refresh_messages()
        await pilot.pause()
        assert await _at_end(pilot, history) and not mark.display
        await pilot.press("home")
        await pilot.pause()
        await _type(pilot, "sent from the top")
        await pilot.press("enter")  # sending returns the view to the end
        await pilot.pause()
        assert await _at_end(pilot, history) and not mark.display

    _run(ctx, steps, refresh_s=60)


def test_210_page_keys_scroll_the_history_while_a_question_is_open(ctx):
    from textual.containers import VerticalScroll

    from xt.dispatch import send

    from .test_chat_0210 import _run

    _long_history(ctx)
    send(ctx, "liaison", "human", "ask", "Ship it?\n\nAnswer yes or no.", data={"question": {"kind": "closed"}})

    async def steps(app, pilot):
        history = app.query_one("#history", VerticalScroll)
        await pilot.press("tab")
        await pilot.pause()
        assert app.target is not None and app.query_one("#question").display
        end = history.scroll_y
        await pilot.press("pageup")
        await pilot.pause()
        assert history.scroll_y < end and app.target is not None

    _run(ctx, steps, refresh_s=60)


# --- #206: the hint fits at every width, with every key named ---------------------------------------

BASE = ["ctrl+t", "pgup/pgdn", "ctrl+d"]
INVENTORY = {  # (state, pickable) -> the keys named, in order
    "plain": ["enter", "↑↓", *BASE],
    "plain, nothing to pick": ["enter", *BASE],
    "waiting": ["enter", "tab", "↑↓", *BASE],
    "answering": ["enter", "esc", *BASE],
    "picked": ["enter", "↑↓", "esc", *BASE],
    "expanded": ["enter", "↑↓", "esc", *BASE],
}


def _keys(line):
    return [part.split(" ", 1)[0] for part in line.split(" · ")]


def _expected(state, mode):
    keys = INVENTORY[state]
    return [k for k in keys if k != "↑↓"] if mode == "hidden" and state in ("plain", "waiting") else keys


def _args(state):
    return {"plain": (0, False, None, True), "plain, nothing to pick": (0, False, None, False),
            "waiting": (12, False, None, True), "answering": (12, True, None, True),
            "picked": (0, False, "picked", True), "expanded": (0, False, "expanded", True)}[state]


@pytest.mark.parametrize("state", list(INVENTORY))
def test_206_every_width_80_to_120_every_state_and_mode(state):
    from rich.text import Text

    from xt import chat

    for mode in chat.MODES:
        if state in ("picked", "expanded") and mode == "hidden":
            continue  # hidden mode shows no line to pick
        for width in range(80, 121):
            waiting, answering, picked, pickable = _args(state)
            line = chat.hint_line(width, waiting, answering, picked, mode, pickable, 1234 if answering else None)
            assert Text(line).cell_len <= width - 4 and "…" not in line, (width, line)
            assert _keys(line) == _expected(state, mode), (width, mode, line)
            assert f"ctrl+t {mode}" in line or f"ctrl+t team activity ({mode})" in line
            # ux on rc2 (xt #3389): enter always says what it does, ctrl+d always says leave
            assert not line.startswith("enter ·") and line.endswith("ctrl+d leave"), (width, line)


def test_206_the_strings_quoted_in_the_guide():
    from xt import chat

    from .conftest import REPO

    guide = (REPO / "docs" / "user-guide.md").read_text()
    lines = {
        (80, 2, False, None, "goals", True, None): "enter send · tab (2) · ↑↓ pick · ctrl+t goals · pgup/pgdn · ctrl+d leave",
        (80, 2, False, None, "hidden", True, None): "enter send · tab answer (2) · ctrl+t hidden · pgup/pgdn · ctrl+d leave",
        (80, 0, False, "picked", "goals", True, None): "enter expand · ↑↓ pick · esc back · ctrl+t goals · pgup/pgdn · ctrl+d leave",
        (80, 2, True, None, "goals", True, 812): "enter send #812 · esc back · ctrl+t goals · pgup/pgdn scroll · ctrl+d leave",
        (80, 0, False, None, "goals", False, None): "enter send · ctrl+t goals · pgup/pgdn scroll · ctrl+d leave",
        (120, 2, False, None, "goals", True, None): "enter send · tab answer (2 waiting) · ↑↓ pick · "
                                                     "ctrl+t team activity (goals) · pgup/pgdn scroll · ctrl+d leave",
        (120, 2, True, None, "goals", True, 812): "enter send #812 · esc message the liaison · "
                                                   "ctrl+t team activity (goals) · pgup/pgdn scroll · ctrl+d leave",
    }
    for args, line in lines.items():
        assert chat.hint_line(*args) == line, (args, chat.hint_line(*args))
        assert f"`{line}`" in guide, line


@pytest.mark.parametrize("state", ["plain", "waiting", "answering", "picked"])
def test_206_the_rendered_hint_at_every_width_in_pilot(ctx, state):
    from rich.text import Text

    from xt.dispatch import send

    from .test_chat_0210 import _run, _status
    from .test_chat_0220 import _team

    _team(ctx)
    if state in ("waiting", "answering"):
        for q in ("Ship it?", "And this?"):
            send(ctx, "liaison", "human", "ask", f"{q}\n\nAnswer yes or no.", data={"question": {"kind": "closed"}})
    send(ctx, "liaison", "lead", "goal", "A goal to pick")  # after the conversation's first line, so it shows

    async def steps(app, pilot):
        if state == "answering":
            await pilot.press("tab")
        if state == "picked":
            await pilot.press("up")
        for _ in range(1 if state == "picked" else 3):  # goals, all, hidden (picking needs a shown line)
            for width in range(80, 121):
                await pilot.resize_terminal(width, 24)
                await pilot.pause()
                status = app.query_one("#status")
                line = _status(app)
                assert status.size.height == 1 and Text(line).cell_len <= width - 4 and "…" not in line, (width, line)
                assert _keys(line) == _expected(state, app.mode), (width, app.mode, line)
            await pilot.press("ctrl+t")

    _run(ctx, steps, refresh_s=60)


def test_206_esc_puts_a_picked_line_back(ctx):
    from xt.dispatch import send

    from .test_chat_0210 import _run, _status
    from .test_chat_0220 import _team

    _team(ctx)
    send(ctx, "liaison", "lead", "goal", "A goal to pick")

    async def steps(app, pilot):
        await pilot.press("up")
        assert app.selected is not None and "esc back" in _status(app)
        await pilot.press("escape")
        assert app.selected is None and _status(app).startswith("enter send")

    _run(ctx, steps, refresh_s=60)


# --- #187: one alert when a message waits for a member that isn't running -----------------------------


def _crew(ctx):
    """A running liaison and lead, and builder (reports to lead) in the roster: xt started it once
    (a member never started isn't alerted about, rc4), and it isn't running now."""
    from xt import versions
    from xt.spawn import request_spawn

    from .conftest import add_member

    for n in ("liaison", "lead"):
        request_spawn(ctx, "human", n, None, None, None, None)
    add_member(ctx, "builder", reports_to="lead")
    versions.record_agent_start(ctx, "builder", ctx.ledger.clock())


def _tick(ctx):
    from xt.watch import Supervisor

    sup = Supervisor(ctx, out=lambda line: None)
    live = ctx.herdr.agents()
    sup.check_agents(live)
    sup.check_queued(live)


def _task(ctx, text="Build v0.22.1", to="builder", sender="lead"):
    from xt.dispatch import send

    return send(ctx, sender, to, "task", text)[0]


def _alerts(ctx):
    from xt.alerts import Alerts

    return Alerts(ctx).active()


def _since(m):
    import datetime as dt

    return dt.datetime.fromisoformat(m["ts"]).astimezone().strftime("%H:%M")


def test_187_nothing_at_119_seconds_one_alert_at_120_in_status_and_inbox(ctx, clock, monkeypatch, capsys):
    from xt import inbox

    _crew(ctx)
    m = _task(ctx)
    clock.advance(seconds=119)
    _tick(ctx)
    assert "queued:builder" not in _alerts(ctx)
    clock.advance(seconds=1)
    _tick(ctx)
    text = (f"builder isn't running: 1 message waiting 2m (task #{m['id']} from lead, since {_since(m)}). "
            "Start it: u (or xt spawn builder).")
    assert _alerts(ctx)["queued:builder"]["text"] == text
    box = inbox.build(ctx, list(ctx.ledger.messages()))
    assert ("queued:builder", text) in [(k, a["text"]) for k, a in box.alerts]
    assert f"⚠ {text}  (xt clear queued:builder)" in _status_out(ctx, monkeypatch, capsys).splitlines()
    clock.advance(minutes=15)
    _tick(ctx)  # the age moves on, on the same alert: one alert message, notified once
    assert "waiting 17m" in _alerts(ctx)["queued:builder"]["text"]
    assert len([x for x in ctx.ledger.messages() if x["type"] == "alert"]) == 1


def test_187_two_messages_give_one_alert_with_the_count_and_the_oldest(ctx, clock):
    _crew(ctx)
    first = _task(ctx)
    clock.advance(minutes=1)
    _task(ctx, "And the docs")
    clock.advance(minutes=2)
    _tick(ctx)
    assert [k for k in _alerts(ctx) if k.startswith("queued:")] == ["queued:builder"]
    assert _alerts(ctx)["queued:builder"]["text"] == (
        f"builder isn't running: 2 messages waiting, oldest 3m (task #{first['id']} from lead). "
        "Start it: u (or xt spawn builder).")


def test_187_a_running_member_with_a_queue_raises_nothing_and_running_clears_it(ctx, clock):
    _crew(ctx)
    _task(ctx)
    clock.advance(minutes=3)
    _tick(ctx)
    assert "queued:builder" in _alerts(ctx)
    ctx.herdr.add("builder", status="working")  # it runs (busy: the queue waits, as normal)
    _tick(ctx)
    assert "queued:builder" not in _alerts(ctx)
    clock.advance(hours=1)
    _tick(ctx)
    assert "queued:builder" not in _alerts(ctx)


def test_187_an_open_missing_alert_gets_the_queue_line_and_no_second_alert(ctx, clock):
    from xt.lifecycle import set_expected

    _crew(ctx)
    set_expected(ctx, "builder", True)  # xt started it and it vanished: missing:builder
    _task(ctx)
    clock.advance(minutes=17)
    _tick(ctx)
    alerts = _alerts(ctx)
    assert "queued:builder" not in alerts
    assert alerts["missing:builder"]["text"].endswith("to start it again.\n1 message waiting 17m")
    _tick(ctx)  # a second pass adds nothing
    assert _alerts(ctx)["missing:builder"]["text"].count("waiting") == 1


def test_187_after_a_clear_it_returns_only_on_a_new_message_or_a_new_stop(ctx, clock, monkeypatch, capsys):
    _crew(ctx)
    _task(ctx)
    clock.advance(minutes=3)
    _tick(ctx)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(["clear", "queued:builder"])
    args.func(args)
    assert capsys.readouterr().out.strip() == "cleared"
    clock.advance(hours=5)
    _tick(ctx)
    assert "queued:builder" not in _alerts(ctx)  # time alone doesn't bring it back
    _task(ctx, "One more")
    clock.advance(minutes=3)
    _tick(ctx)
    assert "queued:builder" in _alerts(ctx)  # a new message queued
    args.func(args)
    ctx.herdr.add("builder", status="working")  # it ran ...
    _tick(ctx)
    ctx.herdr.live.pop("builder")  # ... and stopped again with the queue still waiting
    _tick(ctx)
    assert "queued:builder" in _alerts(ctx)


def test_187_messages_to_the_human_or_a_retired_member_raise_nothing(ctx, clock):
    from xt.dispatch import Queue

    from xt.dispatch import send

    _crew(ctx)
    send(ctx, "liaison", "human", "report", "to the human")
    m = _task(ctx)
    ctx.team.set_status("builder", "retired")
    ctx.team.save()
    ctx.reload_team()
    Queue(ctx).add(m["id"], "builder", "not running")  # left in the queue from before
    clock.advance(minutes=30)
    _tick(ctx)
    assert not [k for k in _alerts(ctx) if k.startswith("queued:")]


def test_187_the_start_command_matches_the_state(ctx, clock):
    from xt.dispatch import send
    from xt.spawn import Approvals
    from xt.lifecycle import set_expected, set_stopped

    _crew(ctx)
    ctx.herdr.live.pop("liaison")
    set_expected(ctx, "liaison", False)  # not started this run (a vanished one is `missing:`)
    send(ctx, "human", "liaison", "ask", "Are you there?")
    _task(ctx)
    clock.advance(minutes=3)
    _tick(ctx)
    assert _alerts(ctx)["queued:liaison"]["text"].endswith("Start it: xt up.")
    assert _alerts(ctx)["queued:builder"]["text"].endswith("Start it: u (or xt spawn builder).")
    rid = Approvals(ctx).add({"requester": "lead", "name": "builder", "harness": "claude", "model": None,
                              "role": "worker", "reports_to": "lead"})
    set_stopped(ctx, "builder", True)
    _tick(ctx)
    assert _alerts(ctx)["queued:builder"]["text"].startswith("builder isn't running (you stopped it): 1 message")
    assert _alerts(ctx)["queued:builder"]["text"].endswith(f"Approve its start: xt approve {rid}.")  # xt #3389


def test_187_ages_over_a_day():
    from xt.watch import age_text

    assert [age_text(s) for s in (119, 120, 17 * 60, 3 * 3600 + 12 * 60, 27 * 3600, 48 * 3600)] == \
        ["1m", "2m", "17m", "3h12m", "1d3h", "2d"]


def test_187_the_sender_line_at_xt_send(team, monkeypatch, capsys):
    from .conftest import add_member
    from .test_operator_0190 import agent

    from xt import versions

    add_member(team, "builder", reports_to="lead")
    versions.record_agent_start(team, "builder", team.ledger.clock())  # started once, not running now
    capsys.readouterr()
    agent(monkeypatch, "send", "builder", "--as", "lead", "--type", "task", "Build it")
    out = capsys.readouterr()
    assert out.err == "queued: builder isn't running; the human is alerted if it still isn't in 2 minutes.\n"
    assert out.out.startswith("#") and out.out.count("\n") == 1  # stdout as before
    from .test_operator_0190 import human

    human(monkeypatch, "send", "builder", "--type", "ask", "Are you there?")  # the human gets the alert
    out = capsys.readouterr()
    assert out.err == "queued: builder isn't running; you get an alert (queued:builder) if it still isn't in 2 minutes.\n"
    assert out.out.startswith("#") and out.out.count("\n") == 1
    agent(monkeypatch, "send", "lead", "--as", "liaison", "--type", "report", "Hi")  # running: no line
    assert capsys.readouterr().err == ""

    def unreadable(max_snapshot_age=None):
        raise XtError("herdr: server_unreachable")

    monkeypatch.setattr(team.herdr, "agents", unreadable)
    before = len(list(team.ledger.messages()))
    agent(monkeypatch, "send", "builder", "--as", "lead", "--type", "task", "Still queued")  # no exception
    out = capsys.readouterr()
    assert out.err == "" and "queued" in out.out and len(list(team.ledger.messages())) == before + 1


def _new_team(ctx):
    """A new team (the operator's finding, xt #3404): the liaison runs, the lead is in the roster
    and xt hasn't started it, by design, before the first goal is dispatched."""
    from xt.spawn import request_spawn

    from .conftest import add_member

    request_spawn(ctx, "human", "liaison", None, None, None, None)
    add_member(ctx, "lead", role="lead", reports_to="liaison")


def test_187_rc4_no_alert_for_a_member_xt_hasnt_started_yet(ctx, clock, monkeypatch, capsys):
    from xt.dispatch import send
    from xt.team import SYSTEM

    _new_team(ctx)
    send(ctx, SYSTEM, "lead", "system", "Human approved approval #12: spawned scout")  # as after a hire
    clock.advance(minutes=10)
    _tick(ctx)
    assert not [k for k in _alerts(ctx) if k.startswith(("queued:", "missing:"))]
    assert not [m for m in ctx.ledger.messages() if m["type"] == "alert"]
    out = _status_out(ctx, monkeypatch, capsys)
    assert "lead not started yet (starts when the first goal is dispatched): 1 message waits for it" in out
    assert "⚠" not in out


def test_187_rc4_a_stopped_member_still_alerts_after_its_first_start(ctx, clock):
    from xt.dispatch import send
    from xt.team import SYSTEM
    from xt.lifecycle import set_stopped

    _new_team(ctx)
    set_stopped(ctx, "lead", True)  # the human stopped it: no longer "not started yet"
    send(ctx, SYSTEM, "lead", "system", "a notice")
    clock.advance(minutes=3)
    _tick(ctx)
    assert _alerts(ctx)["queued:lead"]["text"].startswith("lead isn't running (you stopped it): 1 message")


def test_187_rc4_the_sender_line_for_a_member_not_started_yet(team, monkeypatch, capsys):
    from .conftest import add_member
    from .test_operator_0190 import agent

    add_member(team, "builder", reports_to="lead")  # never started
    capsys.readouterr()
    agent(monkeypatch, "send", "builder", "--as", "lead", "--type", "task", "Build it")
    assert capsys.readouterr().err == "queued: builder hasn't been started yet; it gets this when it starts.\n"


def test_187_rc4_xt_inbox_indents_the_folded_queue_line(ctx, clock, monkeypatch, capsys):
    from xt.lifecycle import set_expected

    _crew(ctx)
    set_expected(ctx, "builder", True)
    _task(ctx)
    clock.advance(minutes=17)
    _tick(ctx)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "human_terminal", lambda: True)
    capsys.readouterr()
    args = cli.build_parser().parse_args(["inbox"])
    args.func(args)
    assert "to start it again.\n    1 message waiting 17m  (clear: xt clear missing:builder)" in capsys.readouterr().out


def test_187_the_guide_has_the_row_and_the_amended_sentences():
    from .conftest import REPO

    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "| `queued:<name>` |" in guide
    assert "`queued: builder isn't running; the human is alerted if it still isn't in 2 minutes.`" in guide
    assert "`queued: builder isn't running; you get an alert (queued:builder) if it still isn't in 2 minutes.`" in guide
    assert "nothing alerts about an agent you stopped" not in guide
    assert guide.count("a message queued for it still alerts") == 2


# --- #211: the chat example and README versions -------------------------------------------------------


def test_211_example_11_matches_what_chat_shows(ctx, fake_home):
    from xt.dispatch import send
    from xt.spawn import request_spawn

    from .conftest import REPO
    from .test_chat_0210 import _bodies, _run, _status, _text
    from .test_chat_0210 import _type as _keys_typed

    example = (REPO / "docs" / "examples.md").read_text().split("## 11.", 1)[1]
    log = _liaison(ctx, fake_home, "claude")
    request_spawn(ctx, "human", "lead", None, None, None, None)
    paneinput.scan(ctx)
    send(ctx, "human", "liaison", "ask", "Where is the digest?")
    ctx.ledger.append("op", "liaison", "report",
                      "Staging check passed: steps 1-9.\n(sent by op, an operator, on the human's behalf)")
    _type(log, "claude", "Ship the digest after QA's run")
    paneinput.scan(ctx)
    send(ctx, "liaison", "human", "ask", "QA passed the digest. Publish it now?\n\nAnswer yes or no.",
         data={"question": {"kind": "closed"}})

    async def steps(app, pilot):
        assert _text(app.query_one("#header")) in example
        for body in _bodies(app):
            assert body.replace("\n\n", "\n") in example.replace("\n\n", "\n"), body
        assert _status(app) in example
        await pilot.press("tab")
        assert f"`{_text(app.query_one('#target'))}`" in example and _status(app) in example.replace(" ·\n  ", " · ")
        await _keys_typed(pilot, "yes")
        await pilot.press("enter")
        await pilot.pause()
        assert _status(app).startswith("#8 answer to #7 → liaison: ") and "✓ answered #8: yes" in _bodies(app)[-2]

    _run(ctx, steps, size=(80, 30), refresh_s=60)


def test_211_readme_examples_carry_no_release_placeholders_and_the_caption_names_the_image():
    from .conftest import REPO

    readme = (REPO / "README.md").read_text()
    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "version use v0." not in readme + guide and "git merge v0." not in readme
    assert "*The 0.18.0 TUI screenshot (`docs/screen-v0180.png`), taken on xt 0.18.0" in readme
    assert "](docs/screen-v0180.png)" in readme


def test_201_with_herdr_unreachable_a_fresh_snapshot_counts_a_stale_one_or_none_is_unknown(ctx, fake_home, monkeypatch):
    # QA #3373, lead #3384: any shell that can't reach Herdr (Ctx.load gives every caller the
    # snapshot) reads the supervisor's saved live state for the pane line only while it is at most
    # 30 s old; older, or none, the line says unknown with its reason.
    import datetime as dt

    from xt import herdr
    from xt.herdr import Herdr, LiveAgent

    _liaison(ctx, fake_home, "claude")

    def unreachable(argv, timeout=120):
        raise XtError("herdr: server_unreachable: no server")

    monkeypatch.setattr(herdr, "_exec", unreachable)
    monkeypatch.setattr(ctx, "herdr", Herdr("test", snapshot=ctx.paths.state / "live.json"))
    assert paneinput.signal(ctx) == STATUS["unknown"]  # no snapshot

    def saved(agents, seconds_ago):
        ts = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=seconds_ago)
        ctx.herdr.save_snapshot(agents, ts.isoformat(timespec="seconds"))

    liaison = {"liaison": LiveAgent("liaison", "idle", "w1:p1", "w1")}
    saved(liaison, 5)
    assert paneinput.signal(ctx) == STATUS["recorded"]  # fresh: it runs
    saved({}, 5)
    assert paneinput.signal(ctx) == STATUS["not running"]  # fresh: it doesn't
    saved(liaison, 60)
    assert paneinput.signal(ctx) == STATUS["unknown"]  # stale: the server is down, not the liaison
    assert ctx.herdr.agents() == liaison  # every other caller still reads the snapshot, as before


def test_201_a_retired_liaison_isnt_running(ctx, fake_home):
    from xt.spawn import retire

    _liaison(ctx, fake_home, "claude")
    retire(ctx, "human", "liaison")
    assert paneinput.signal(ctx) == STATUS["not running"]
