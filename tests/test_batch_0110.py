"""v0.11.0: predictable TUI send keys (#102), the human's piped bodies (#103), literal agent
messages (#106), a readable screen preview (#98), agents without account connectors (#101)."""

import asyncio

from xt.dispatch import send
from xt.tui.app import Compose, Help, LiveActions, Prompt, XtTui
from xt.tui.model import build

from .test_questions import _goal_and_question


# --- #102: s says what it will do; S always messages the liaison ---------------------------------


def test_key_line_says_what_s_does_and_S_always_messages_the_liaison(ctx):
    _, _, q, _ = _goal_and_question(ctx)
    ctx.herdr.add("liaison")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(160, 45)) as pilot:
            await pilot.pause()
            hints = lambda: str(app.query_one("#hints").render())  # noqa: E731
            assert hints().startswith("s/S message liaison")  # Work focused: nothing to answer
            for panel in ("2", "3", "4", "tab"):  # every pane but the Inbox (1), and Team
                await pilot.press(panel, "S")
                assert isinstance(app.screen, Compose) and app.screen.title_text == "Send to the liaison"
                await pilot.press("escape")
            await pilot.press("1")
            await pilot.pause()
            assert hints().startswith(f"s answer #{q['id']} · S message liaison")
            await pilot.press("S")  # a question is selected, but S doesn't answer it
            assert isinstance(app.screen, Compose) and app.screen.title_text == "Send to the liaison"
            await pilot.press(*"Stop after this one", "ctrl+s")
            await pilot.pause()
            assert "to liaison" in app.status
            assert ctx.ledger.item(q["id"]) is not None  # still open
            msgs = [m for m in ctx.ledger.messages() if m["from"] == "human" and m["to"] == "liaison"]
            assert [m["body"] for m in msgs] == ["Stop after this one"]  # delivered exactly once
            await pilot.press("s")  # s still answers the selected question
            assert f"#{q['id']}" in app.screen.title_text
            await pilot.press("escape")
            await pilot.press("2")
            await pilot.pause()
            assert hints().startswith("s/S message liaison")

    asyncio.run(run())


def test_S_is_just_a_letter_while_typing(ctx):
    ctx.herdr.add("liaison")

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("S", *"So Send", "ctrl+s")
            await pilot.pause()
            assert [m["body"] for m in ctx.ledger.messages() if m["from"] == "human"] == ["So Send"]
            await pilot.press("slash", *"SS")
            assert isinstance(app.screen, Prompt)
            await pilot.press("escape")
            await pilot.press("h")
            assert "S" in [k for k, _ in Help.KEYS]

    asyncio.run(run())


# --- #103: the human can pipe a body in; agents still can't pass as the human --------------------


import io  # noqa: E402
import sys  # noqa: E402

import pytest  # noqa: E402

from xt import cli  # noqa: E402
from xt.paths import XtError  # noqa: E402


class _Stdin(io.StringIO):
    def __init__(self, text="", tty=False):
        super().__init__(text)
        self._tty = tty

    def isatty(self):
        return self._tty


def _run(monkeypatch, ctx, argv, stdin):
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(argv)
    args.func(args)


def test_human_heredoc_body_is_accepted_from_the_humans_terminal(monkeypatch, ctx):
    monkeypatch.setattr(cli, "controlling_terminal", lambda: True)  # a terminal, stdin a heredoc
    body = "Line one, with `backticks` and $(date)\nline two\n"
    _run(monkeypatch, ctx, ["send", "liaison", "--as", "human", "--type", "report"], _Stdin(body))
    _, _, q, _ = _goal_and_question(ctx)
    _run(monkeypatch, ctx, ["answer", str(q["id"]), "--as", "human"], _Stdin("tennis\nand golf\n"))
    mine = [m["body"] for m in ctx.ledger.messages() if m["from"] == "human" and m["type"] == "report"]
    assert mine == [body.rstrip("\n"), "tennis\nand golf"]  # the text exactly, less the final newline
    assert ctx.ledger.item(q["id"]) is None


@pytest.mark.parametrize("case", ["claude or pi shell tool", "codex pty, marked", "codex pty, unmarked",
                                  "piped"])
def test_agents_still_cannot_act_as_the_human(monkeypatch, ctx, case):
    if case == "claude or pi shell tool":  # no terminal at all
        stdin, tty, marker = _Stdin("x"), False, None
    elif case == "codex pty, marked":  # a terminal on stdin, inside an agent xt started
        stdin, tty, marker = _Stdin("x", tty=True), False, "lead"
    elif case == "codex pty, unmarked":
        # rc1's hole, found in acceptance: an agent started by an older xt (no XT_AGENT), its
        # ancestors hidden by Codex's PID namespace, a terminal on stdin but no controlling one
        stdin, tty, marker = _Stdin("x", tty=True), False, None
    else:  # piped from inside an agent's pane
        stdin, tty, marker = _Stdin("x"), True, "lead"
    monkeypatch.setattr(cli, "controlling_terminal", lambda: tty)
    if marker:
        monkeypatch.setenv("XT_AGENT", marker)
    with pytest.raises(XtError, match="only works from the human's own terminal"):
        _run(monkeypatch, ctx, ["send", "liaison", "--as", "human", "--type", "report"], stdin)
    assert not [m for m in ctx.ledger.messages() if m["from"] == "human"]


def test_every_agent_pane_is_marked_before_its_harness_starts(ctx):
    from xt.spawn import do_spawn

    do_spawn(ctx, "liaison")
    pane = ctx.herdr.live["liaison"].pane_id
    assert (pane, "export XT_AGENT=liaison") in ctx.herdr.pane_runs


def test_new_agent_names_are_simple(ctx):
    from xt.spawn import request_spawn

    with pytest.raises(XtError, match="lowercase letters"):
        request_spawn(ctx, "human", "Bob; rm -rf ~", "codex", None, "researcher", None)


# --- #106: agent message text reaches xt exactly as written --------------------------------------


import os  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402

from xt.dispatch import envelope  # noqa: E402

from .conftest import add_member  # noqa: E402


def test_the_reply_hint_form_keeps_backticks_and_substitutions_literal(monkeypatch, ctx, tmp_path):
    add_member(ctx, "carol")
    task, _ = send(ctx, "lead", "carol", "task", "parse the file")
    hint = envelope(ctx, task)
    # the hint's own command, with the "..." replaced by awkward text, run by a real shell
    m = re.search(r"\n(\S+ send lead --as carol --type report --ref \d+ <<'XT_END')\n\.\.\.\nXT_END", hint)
    assert m, hint
    marker = tmp_path / "pwned"
    text = f"Used `fizzy card list` and $(touch {marker}); cost: $5 — \"quoted\" and 'single'\nEOF\nlast line"
    # a real shell runs the hint's heredoc; xt's own code then reads what arrives on stdin
    heredoc = m.group(1)[m.group(1).index("<<"):]
    out = tmp_path / "stdin.txt"
    p = subprocess.run(["bash", "-c", f"cat > {out} {heredoc}\n{text}\nXT_END\n"],
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
    assert p.returncode == 0, p.stderr
    monkeypatch.setenv("XT_AGENT", "carol")
    _run(monkeypatch, ctx, ["send", "lead", "--as", "carol", "--type", "report", "--ref", str(task["id"])],
         _Stdin(out.read_text()))
    reports = [m for m in ctx.ledger.messages() if m["from"] == "carol"]
    assert [r["body"] for r in reports] == [text]  # exactly once, byte for byte
    assert not marker.exists()  # the $(…) example was never run


def test_done_and_note_take_their_text_on_stdin(monkeypatch, ctx):
    add_member(ctx, "carol")
    task, _ = send(ctx, "lead", "carol", "task", "parse the file")
    _run(monkeypatch, ctx, ["note", "--as", "carol"], _Stdin("remember `this`\n"))
    _run(monkeypatch, ctx, ["done", str(task["id"]), "--as", "carol"], _Stdin("Parsed; see `out.csv`\n"))
    bodies = [(m["type"], m["body"]) for m in ctx.ledger.messages() if m["from"] == "carol"]
    assert bodies == [("note", "remember `this`"), ("done", "Parsed; see `out.csv`")]


# --- #98: the screen preview reads like the terminal ---------------------------------------------


from rich.console import Console  # noqa: E402

from xt.tui.model import CONTINUED, ScreenPreview, screen_lines  # noqa: E402

LONG = ("• Ran /home/user/Projects/teams/xt-team/bin/xt send lead --as liaison --type report --ref 294 "
        "'Your #294 says Radek decision remains pending'")


def test_screen_lines_drop_blanks_and_collapse_repeats():
    screen = "working\n\n\n─────\n─────\n─────\n" + LONG + "\n   indented line\n"
    assert screen_lines(screen) == [("working", 1), ("─────", 3), (LONG, 1), ("   indented line", 1)]


def test_a_long_line_continues_on_marked_lines_instead_of_rewrapping():
    rows = ScreenPreview([("short one", 1), (LONG, 1), ("   indented line", 1)]).rows(60)
    assert rows[0] == "short one"
    long_rows = rows[1:-1]
    assert len(long_rows) > 1 and all(len(r) <= 60 for r in rows)
    assert all(r.startswith("  " + CONTINUED) for r in long_rows[1:])  # clearly a continuation
    rejoined = " ".join([long_rows[0]] + [r[len("  " + CONTINUED):] for r in long_rows[1:]])
    assert rejoined == LONG  # nothing lost, nothing cut mid-word
    assert rows[-1] == "   indented line"  # a new captured line starts at the margin, indent kept


def test_agent_detail_renders_the_preview_at_the_panes_width(ctx):
    ctx.herdr.add("liaison")
    pane = ctx.herdr.live["liaison"].pane_id
    ctx.herdr.screens[pane] = ["Status line", "", LONG, LONG, "› Ask Codex to do anything"]

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(120, 45)) as pilot:
            app.team.focus()
            await pilot.pause()
            row = app.team.current
            assert row.data["name"] == "liaison"
            detail = row.detail()
            assert "(×2)" in detail.plain and detail.plain.count("Radek decision") == 1
            app.show_detail(app.team)  # the TUI accepts the richer detail
            console = Console(width=60, record=True, color_system=None, file=io.StringIO())
            console.print(detail)
            shown = console.export_text()
            assert "  " + CONTINUED in shown and all(len(ln) <= 60 for ln in shown.splitlines())

    asyncio.run(run())


def test_terminal_padding_does_not_squeeze_the_preview_into_a_column():
    tip = " " * 64 + "Tip: Use /permissions to control when Codex asks for confirmation."
    bar = "  ? for shortcuts" + " " * 80 + "⚠ 1 warning · f2 to view"
    rows = ScreenPreview([(tip, 1), (bar, 1)]).rows(72)
    assert len(rows) <= 3 and all(len(r) <= 72 for r in rows)
    assert rows[0].startswith("        Tip: Use /permissions")


def test_a_harness_among_the_ancestors_marks_an_agent_even_without_the_variable():
    assert cli.harness_in([{"bash"}, {"codex-code-mode"}, {"codex"}, {"herdr"}])  # a Codex helper's shell
    assert cli.harness_in([{"bash"}, {"claude"}, {"herdr"}])  # Claude Code's shell tool
    assert cli.harness_in([{"bash"}, {"pi"}])
    assert not cli.harness_in([{"bash"}, {"herdr"}, {"kitty"}, {"Hyprland"}])  # the human's terminal
    assert not cli.harness_in([{"bash"}, {"pipewire"}, {"picom"}])  # names merely starting with "pi"


# --- #101: agents start without the operator's account connectors -------------------------------


from xt import adapters  # noqa: E402
from xt.adapters import load_adapters  # noqa: E402


def test_connectors_are_blocked_by_default_in_every_harness(ctx):
    ad = load_adapters(ctx.paths)
    assert "--strict-mcp-config" in ad["claude"].start_args(None)
    assert "features.apps=false" in ad["codex"].start_args(None)
    assert ad["pi"].connectors == "none"
    for name in ("claude", "codex", "pi"):
        assert ad[name].connectors in ("blocked", "none") and "CLIs" in ad[name].connectors_note


def test_a_named_opt_in_exposes_only_those_connectors(ctx, monkeypatch):
    servers = ["claude.ai Gmail", "claude.ai Context7", "plugin:operations:slack"]
    monkeypatch.setattr(adapters, "claude_mcp_servers", lambda binary="claude", cwd=None: servers)
    ad = load_adapters(ctx.paths)
    args = ad["claude"].start_args(None, ["claude.ai Context7"])
    assert "--strict-mcp-config" not in args
    denied = args[args.index("--disallowedTools", args.index("--disallowedTools") + 1) + 1:]
    assert denied == ["mcp__claude_ai_Gmail", "mcp__plugin_operations_slack"]
    # Codex can only switch every app on at once, so it takes no named opt-in (rc1 did, and failed)
    with pytest.raises(XtError, match="can't expose single account connectors"):
        ad["codex"].start_args(None, ["Google Drive"])


def test_start_note_and_detail_show_an_opt_in(ctx, monkeypatch):
    from xt.spawn import do_spawn

    monkeypatch.setattr(adapters, "claude_mcp_servers", lambda binary="claude", cwd=None: ["claude.ai Context7"])
    add_member(ctx, "carol")  # a claude agent
    table = ctx.team._table("carol")
    table["connectors"] = ["claude.ai Context7"]
    ctx.team.save()
    ctx.reload_team()
    do_spawn(ctx, "carol")
    started = [a for n, _, a in ctx.herdr.started if n == "carol"][-1]
    assert "--strict-mcp-config" not in started
    notes = [m["body"] for m in ctx.ledger.messages() if m["type"] == "system"]
    assert any("carol: account connectors opted in: claude.ai Context7" in b for b in notes)
    row = next(r for r in build(ctx).panels["Team"] if r.data and r.data.get("name") == "carol")
    assert "account connectors (opted in): claude.ai Context7" in row.detail().plain
    # removing the opt-in restores the default at the next start
    del ctx.team._table("carol")["connectors"]
    ctx.team.save()
    ctx.reload_team()
    assert "--strict-mcp-config" in load_adapters(ctx.paths)["claude"].start_args(None, ctx.team.agent("carol").connectors)


def test_xt_harnesses_reports_connector_coverage(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(["harnesses"])
    args.func(args)
    out = capsys.readouterr().out
    assert out.count("account connectors for agents:") == 3 and "blocked" in out


def test_a_codex_agent_with_an_opt_in_is_refused_before_any_workspace_opens(ctx):
    from xt.spawn import do_spawn

    ctx.team._table("liaison")["connectors"] = ["Google Drive"]  # the liaison runs on codex here?
    ctx.team.save()
    ctx.reload_team()
    if ctx.team.agent("liaison").harness != "codex":
        pytest.skip("fixture liaison isn't codex")
    before = dict(ctx.herdr.labels)
    with pytest.raises(XtError, match="can't expose single account connectors"):
        do_spawn(ctx, "liaison")
    assert ctx.herdr.labels == before and "liaison" not in ctx.herdr.live
