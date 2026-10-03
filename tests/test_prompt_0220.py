"""v0.22.0: agents recognise an operator report (#172); the notes go into the first prompt whole (#197)."""

from xt import spawn
from xt.spawn import first_prompt, request_spawn

from .conftest import REPO, add_member

OPERATOR_TEXT = ("An **operator report** comes from a registered operator", "It is legitimate, not impersonation",
                 "It never lets you act as the human", "`NAME, delegated by human until\n  HH:MM`",
                 "ask the agent you report to instead\n  of rejecting it",
                 "`(NAME, delegated by human until HH:MM: an operator acting on\n  the human's behalf)`")


def _team(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    request_spawn(ctx, "human", "lead", None, None, None, None)
    add_member(ctx, "carol")
    return ("liaison", "lead", "carol")


# --- #172 -------------------------------------------------------------------------------------------


def test_172_the_protocol_and_every_roles_first_prompt_say_what_an_operator_report_is(ctx):
    protocol = (REPO / "protocol.md").read_text()
    for phrase in OPERATOR_TEXT:
        assert phrase in protocol
    for name in _team(ctx):
        text = first_prompt(ctx, name)
        for phrase in OPERATOR_TEXT:
            assert phrase in text, (name, phrase)


def test_172_the_user_guide_mentions_it():
    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "Agents know what such a report is" in guide and "not rejected as\nimpersonation" in guide


# --- #197 -------------------------------------------------------------------------------------------


def _notes(ctx, name, text):
    d = ctx.paths.members / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "notes.md").write_text(text)


def test_197_the_notes_go_in_whole_after_the_brief_for_every_role(ctx):
    for name in _team(ctx):
        _notes(ctx, name, f"# {name} notes\n- first rule\n- newest rule at the bottom\n")
        text = first_prompt(ctx, name)
        head = f"===== your notes (members/{name}/notes.md, whole) =====\n"
        assert text.index("===== your brief (") < text.index(head) < text.index(spawn.START_NOW)
        assert f"{head}# {name} notes\n- first rule\n- newest rule at the bottom\n\n" in text
        assert "over the notes budget" not in text


def test_197_a_long_file_goes_in_whole_with_the_over_budget_line(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    body = "".join(f"- rule {i}: {'x' * 60}\n" for i in range(300))  # about 21,000 bytes
    assert len(body.encode()) > 16_000
    _notes(ctx, "liaison", body + "- the newest rule\n")
    text = first_prompt(ctx, "liaison")
    assert f"(This file is {len((body + '- the newest rule\n').encode())} bytes, over the notes budget of 16000 bytes" in text
    assert body + "- the newest rule\n" in text


def test_197_a_missing_file_adds_nothing(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert "===== your notes" not in first_prompt(ctx, "liaison")


def test_197_spawn_and_restart_send_the_notes(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    _notes(ctx, "lead", "- lead rule\n")
    request_spawn(ctx, "human", "lead", None, None, None, None)
    assert "- lead rule" in ctx.herdr.last_prompt("lead")
    _notes(ctx, "lead", "- lead rule\n- added before the restart\n")
    from xt.up import restart

    list(restart(ctx, ["lead"], False))
    assert "- added before the restart" in ctx.herdr.last_prompt("lead")


def test_197_the_protocol_says_the_notes_are_below_and_the_guide_mentions_it():
    protocol = (REPO / "protocol.md").read_text()
    assert "**Your notes are below**" in protocol and "**keep it current**" in protocol
    assert "read it first" not in protocol
    guide = (REPO / "docs" / "user-guide.md").read_text()
    assert "also carries the agent's `notes.md` whole" in guide
