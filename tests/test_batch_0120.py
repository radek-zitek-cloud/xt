"""v0.12.0: team version awareness (#58), safe context reset (#56), clearer restore output (#104),
a roomier answer/send dialog (#110)."""

import datetime as dt
import json

from xt import brief, cli, versions
from xt.spawn import do_spawn
from xt.tui.model import build

NOW = dt.datetime(2026, 9, 29, 9, 0, tzinfo=dt.timezone.utc)


def _install(ctx, version):
    (ctx.paths.root / "pyproject.toml").write_text(f'[project]\nname = "xt"\nversion = "{version}"\n')


def _state(ctx, **data):
    (ctx.paths.state / "versions.json").write_text(json.dumps(data))


# --- #58: published, installed and running versions -----------------------------------------------


def test_latest_final_ignores_candidates_and_orders_by_semver():
    lines = "\n".join(f"abc\trefs/tags/{t}" for t in ["v0.9.1", "v0.10.0", "v0.11.0-rc1", "v0.11.0", "v0.12.0-rc1", "v0.2.0"])
    assert versions.latest_final(lines) == "0.11.0"
    assert versions.parse("0.12.0rc1") < versions.parse("0.12.0") < versions.parse("v0.12.1")
    assert versions.display("0.12.0rc1") == "0.12.0-rc1"


def test_three_versions_are_labelled_separately_everywhere(ctx, monkeypatch, capsys):
    _install(ctx, "0.11.0")
    _state(ctx, published={"version": "0.12.0", "checked": NOW.isoformat()},
           supervisor={"version": "0.11.0"}, agents={"liaison": {"version": "0.10.0"}})
    ctx.herdr.add("liaison")
    v = versions.current(ctx, live_names={"liaison"}, supervisor_running=True, now=NOW + dt.timedelta(hours=2))
    assert v.title() == "installed 0.11.0 · running mixed · published 0.12.0"
    line = v.line()
    assert "published 0.12.0 (checked 2 h ago) · installed 0.11.0 · running mixed" in line
    assert "not yet running the installed version: liaison" in line
    assert "a newer release is published (0.12.0); nothing upgrades on its own" in line
    assert "liaison: 0.10.0" in v.detail() and "supervisor: 0.11.0" in v.detail()
    # the same line reaches `xt status` and every brief
    monkeypatch.setattr(versions, "current", lambda ctx, **k: v)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    args = cli.build_parser().parse_args(["status", "--as", "lead"])
    args.func(args)
    assert "xt versions: published 0.12.0" in capsys.readouterr().out
    assert "xt versions: published 0.12.0" in brief.build(ctx, "lead")
    # and the TUI's Team header (card #128): installed, what's published, what's still running
    assert "xt 0.11.0 (0.12.0 published) · running mixed: restart to update" in build(ctx).header.plain


def test_installed_but_not_yet_running(ctx):
    """A pulled upgrade: the repo says 0.12.0, the supervisor and an agent still run 0.11.0."""
    _install(ctx, "0.12.0")
    _state(ctx, supervisor={"version": "0.11.0"}, agents={"lead": {"version": "0.12.0"}, "pm": {"version": "0.11.0"}})
    v = versions.current(ctx, live_names={"lead", "pm"}, supervisor_running=True, now=NOW)
    assert v.running_label == "mixed" and v.restart_needed
    assert "not yet running the installed version: supervisor, pm" in v.line()
    assert "published unknown (not checked yet)" in v.line()


def test_installed_is_what_the_repo_holds_not_a_stale_record(ctx):
    _install(ctx, "0.12.0")
    _state(ctx, installed_seen={"0.11.0": NOW.isoformat()})
    assert versions.current(ctx, live_names=set(), supervisor_running=False).installed == "0.12.0"


def test_an_unreachable_upstream_keeps_the_last_known_release_dated(ctx, monkeypatch):
    import subprocess

    _state(ctx, published={"version": "0.11.0", "checked": NOW.isoformat()})

    def fake_run(argv, **kw):
        if "get-url" in argv:
            return subprocess.CompletedProcess(argv, 0, "https://example.invalid/xt.git\n", "")
        return subprocess.CompletedProcess(argv, 128, "", "fatal: unable to access\n")

    monkeypatch.setattr(versions.subprocess, "run", fake_run)
    assert "unknown (fatal: unable to access)" in versions.refresh_published(ctx, NOW + dt.timedelta(hours=7))
    v = versions.current(ctx, live_names=set(), supervisor_running=False, now=NOW + dt.timedelta(hours=7))
    assert v.published == "0.11.0" and "last known, check failed" in v.line()


def test_the_supervisor_checks_published_at_most_every_few_hours(ctx, monkeypatch):
    calls = []
    monkeypatch.setattr(versions, "refresh_published", lambda ctx, now: calls.append(now) or "published xt: 0.12.0")
    from xt.watch import Supervisor

    sup = Supervisor(ctx, out=lambda *_: None)
    sup.check_published()
    _state(ctx, published={"version": "0.12.0", "checked": dt.datetime.now(dt.timezone.utc).astimezone().isoformat()})
    sup.check_published()
    assert len(calls) == 1


def test_each_agent_start_records_the_xt_that_started_it(ctx):
    do_spawn(ctx, "liaison")
    rec = versions.load(ctx)["agents"]["liaison"]
    assert rec["version"] == versions.__version__
    started = [m["body"] for m in ctx.ledger.messages() if m["body"].startswith("started liaison")]
    assert started and f"with xt {versions.display(versions.__version__)}" in started[-1]


def test_unknown_running_versions_are_not_reported_as_old(ctx):
    _install(ctx, "0.12.0")
    _state(ctx, supervisor={"version": "0.12.0"})
    v = versions.current(ctx, live_names={"lead"}, supervisor_running=True, now=NOW)
    assert v.running_label == "mixed" and not v.restart_needed
    assert "not yet running" not in v.line()
    assert "version unknown (started before xt recorded versions): lead" in v.line()


# --- #104: restart output says what happened, once --------------------------------------------------


from xt.spawn import request_spawn  # noqa: E402

from .conftest import add_member  # noqa: E402


def _team_then_down(ctx, monkeypatch):
    from xt import up as up_mod
    from xt.spawn import stop
    from xt.up import down

    monkeypatch.setattr(up_mod, "watch_pid", lambda c: None)
    add_member(ctx, "carol")
    add_member(ctx, "dora")
    for n in ("liaison", "lead", "carol", "dora"):
        request_spawn(ctx, "human", n, None, None, None, None)
    stop(ctx, "dora")  # stopped on purpose before the down
    return down(ctx)


def test_restore_output_names_the_restored_and_the_left_stopped_without_contradiction(ctx, monkeypatch):
    from xt.up import restart

    down_out = _team_then_down(ctx, monkeypatch)
    assert any(line.startswith("stopped ") for line in down_out)
    out = restart(ctx, [], everyone=True)
    text = "\n".join(out)
    assert "no agents were running" not in text
    assert "not running;" not in text and "not started" not in text  # up()'s advice would contradict
    assert "restored: liaison, lead, carol (running before xt down)" in out
    assert "left stopped: dora (not running before; `xt spawn <name>` starts one)" in out
    assert out[-1].startswith("supervisor: ")


def test_an_empty_record_is_told_apart_from_a_temporarily_stopped_team(ctx, monkeypatch):
    from xt.up import down, restart

    _team_then_down(ctx, monkeypatch)
    restart(ctx, [], everyone=True)
    down(ctx, keep_supervisor=True)
    (ctx.paths.state / "predown.json").unlink()  # nothing recorded
    out = restart(ctx, [], everyone=True)
    assert "nothing was running, and nothing was recorded at the last xt down" in out
    assert any(line.startswith("restored: nobody") for line in out)
    assert "no agents were running" not in out


# --- #56: a safe manual context reset ------------------------------------------------------------


import pytest  # noqa: E402

from xt import reset as reset_mod  # noqa: E402
from xt.dispatch import send  # noqa: E402
from xt.paths import XtError  # noqa: E402
from xt.usage import Reading  # noqa: E402


def _running_carol(ctx):
    add_member(ctx, "carol")
    request_spawn(ctx, "human", "carol", None, None, None, None)
    ctx.herdr.live["carol"].status = "idle"  # done with its first prompt
    return ctx.herdr.live["carol"].workspace_id


def test_reset_is_refused_while_the_agent_owns_open_work(ctx):
    ws = _running_carol(ctx)
    task, _ = send(ctx, "lead", "carol", "task", "parse the file")
    with pytest.raises(XtError, match=f"owns open work \\(#{task['id']}\\): nothing was reset"):
        reset_mod.reset(ctx, "carol")
    assert ctx.herdr.live["carol"].workspace_id == ws  # the session is untouched


def test_reset_saves_a_checkpoint_then_starts_a_fresh_session(ctx):
    ws = _running_carol(ctx)
    prompts = []
    ctx.herdr.prompt = lambda name, text, confirm=False: prompts.append((name, text))

    def agent_saves(_):  # the agent writes its notes and confirms
        reset_mod.record_checkpoint(ctx, "carol", "working on the parser; see notes")

    out = reset_mod.reset(ctx, "carol", timeout=10, sleep=agent_saves, clock=lambda: 0)
    assert prompts and "checkpoint --as carol <<'XT_END'" in prompts[0][1]
    assert ctx.herdr.live["carol"].workspace_id != ws  # a fresh session
    assert "reset carol: checkpoint" in out[0] and "members/carol/notes.md" in out[0]
    b = brief.build(ctx, "carol")
    assert "Your notes: members/carol/notes.md" in b and "working on the parser; see notes" in b
    notes = [m["body"] for m in ctx.ledger.messages() if m["from"] == "carol" and m["type"] == "note"]
    assert notes == ["checkpoint: working on the parser; see notes"]


def test_a_busy_agent_is_not_reset(ctx):
    _running_carol(ctx)
    ctx.herdr.live["carol"].status = "working"
    with pytest.raises(XtError, match="working right now: nothing was reset"):
        reset_mod.reset(ctx, "carol")


def test_no_checkpoint_or_new_work_means_nothing_is_reset(ctx):
    ws = _running_carol(ctx)
    ctx.herdr.prompt = lambda *a, **k: None
    t = iter(range(0, 1000, 5))
    with pytest.raises(XtError, match="didn't confirm a checkpoint within 10 s: nothing was reset"):
        reset_mod.reset(ctx, "carol", timeout=10, sleep=lambda _: None, clock=lambda: next(t))
    assert ctx.herdr.live["carol"].workspace_id == ws

    def work_arrives(_):
        send(ctx, "lead", "carol", "task", "urgent")

    with pytest.raises(XtError, match="new work arrived"):
        reset_mod.reset(ctx, "carol", timeout=10, sleep=work_arrives, clock=lambda: 0)
    assert ctx.herdr.live["carol"].workspace_id == ws


def test_a_reset_is_suggested_only_on_a_fresh_trustworthy_reading():
    now = dt.datetime(2026, 9, 29, 9, 0, tzinfo=dt.timezone.utc)
    seen = now.isoformat()
    high = Reading(used=185_000, window=258_000, approximate=True, observed=seen, source="codex session log")
    tip = reset_mod.suggestion("lead", high, now)
    assert tip.startswith("reset suggested for lead: context ~185k/258k (72%, from the codex session log)")
    assert reset_mod.suggestion("lead", Reading(used=150_000, window=258_000, observed=seen), now) is None  # 58%
    assert reset_mod.suggestion("lead", Reading(used=200_000, window=None, observed=seen), now) is None  # no window
    assert reset_mod.suggestion("lead", Reading(reason="no usage recorded yet"), now) is None
    stale = Reading(used=200_000, window=258_000, observed=(now - dt.timedelta(hours=3)).isoformat())
    assert reset_mod.suggestion("lead", stale, now) is None


def test_the_cli_keeps_reset_for_the_human_and_checkpoint_for_agents(ctx, monkeypatch):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    with pytest.raises(XtError, match="only the human resets"):
        args = cli.build_parser().parse_args(["reset", "lead", "--as", "lead"])
        args.func(args)
    with pytest.raises(XtError, match="agents confirm their own checkpoint"):
        monkeypatch.setattr(cli, "controlling_terminal", lambda: True)
        args = cli.build_parser().parse_args(["checkpoint", "--as", "human", "x"])
        args.func(args)


# --- #110: a roomy answer/send dialog with a visible cursor and the system clipboard -------------


import asyncio  # noqa: E402

from xt.tui import clipboard  # noqa: E402
from xt.tui.app import Compose, XtTui, demo_snapshot  # noqa: E402


async def _dialog(pilot, app, context="Which story?\n" * 12):
    app.push_screen(Compose("Answer question #812 from liaison", context))
    await pilot.pause()
    s = app.screen
    cx = s.query(".compose-context")
    return s.query_one(".popup.compose"), s.query_one("#compose-text"), cx.first() if cx else None


@pytest.mark.parametrize("path", ["answer", "send"])
def test_the_dialog_uses_most_of_a_large_terminal_and_grows_with_it(path):
    async def run():
        app = XtTui(demo_snapshot, actions=object())
        async with app.run_test(size=(200, 60)) as pilot:
            ctx_text = "Which story?\n" * 12 if path == "answer" else None
            box, ed, cx = await _dialog(pilot, app, ctx_text)
            assert box.region.width == 160 and box.region.height >= 40  # ≤ 160 columns, ~two-thirds high
            assert ed.region.height >= 21
            small = ed.region.height
            await pilot.resize_terminal(200, 80)
            await pilot.pause()
            assert ed.region.height > small  # extra height goes to the editor

    asyncio.run(run())


def test_a_small_terminal_keeps_question_editor_and_controls_usable():
    async def run():
        app = XtTui(demo_snapshot, actions=object())
        async with app.run_test(size=(80, 24)) as pilot:
            box, ed, cx = await _dialog(pilot, app)
            assert box.region.bottom <= 24 and box.region.width <= 72  # nothing clipped, ≤ 90%
            assert ed.region.height >= 3 and cx.region.height >= 1
            await pilot.press(*"still typing", "enter", *"line two")
            assert ed.text == "still typing\nline two"

    asyncio.run(run())


def test_cursor_and_selection_are_visible_in_the_tui_colour_mode():
    async def run():
        app = XtTui(demo_snapshot, actions=object())
        async with app.run_test(size=(160, 50)) as pilot:
            _, ed, _ = await _dialog(pilot, app)
            cursor = ed.get_component_rich_style("text-area--cursor")
            selection = ed.get_component_rich_style("text-area--selection")
            assert cursor.reverse and cursor.color.is_default and cursor.bgcolor.is_default  # the text's own colour
            assert selection.bgcolor is not None and not selection.bgcolor.is_default

    asyncio.run(run())


def test_copy_and_paste_go_through_the_system_clipboard(monkeypatch):
    board = {"text": "pasted\nfrom elsewhere"}
    monkeypatch.setattr(clipboard, "copy", lambda t: board.update(text=t) or True)
    monkeypatch.setattr(clipboard, "paste", lambda: board["text"])

    async def run():
        app = XtTui(demo_snapshot, actions=object())
        async with app.run_test(size=(160, 50)) as pilot:
            _, ed, _ = await _dialog(pilot, app)
            await pilot.press(*"keep this", "shift+home", "ctrl+c")
            assert board["text"] == "keep this"
            await pilot.press("end", "enter")
            board["text"] = "multi\nline"
            await pilot.press("ctrl+v")
            assert ed.text == "keep this\nmulti\nline"

    asyncio.run(run())


def test_an_unavailable_clipboard_says_so_instead_of_pasting_something_else(monkeypatch):
    monkeypatch.setattr(clipboard, "paste", lambda: None)
    notes = []

    async def run():
        app = XtTui(demo_snapshot, actions=object())
        async with app.run_test(size=(160, 50)) as pilot:
            _, ed, _ = await _dialog(pilot, app)
            monkeypatch.setattr(type(ed), "notify", lambda self, msg, **k: notes.append(msg))
            app.copy_to_clipboard("xt's own clipboard")
            await pilot.press("ctrl+v")
            assert ed.text == "" and notes and "couldn't read the system clipboard" in notes[0]

    asyncio.run(run())


# --- rc2: the three #56 findings from rc1's acceptance --------------------------------------------


def test_a_reading_without_a_timestamp_never_suggests_a_reset():
    now = dt.datetime(2026, 9, 29, 9, 0, tzinfo=dt.timezone.utc)
    no_time = Reading(used=220_000, window=258_000, observed=None, source="codex session log")
    assert reset_mod.suggestion("lead", no_time, now) is None
    assert reset_mod.suggestion("lead", Reading(used=220_000, window=258_000, observed="not a time"), now) is None


def test_reset_refuses_an_unknown_name_before_announcing_anything(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "controlling_terminal", lambda: True)
    args = cli.build_parser().parse_args(["reset", "liason", "--as", "human"])
    with pytest.raises(XtError, match="'liason' is not an active agent"):
        args.func(args)
    assert "asking" not in capsys.readouterr().out


def test_the_reset_line_cuts_the_checkpoint_summary_at_a_word():
    long = "No open work; read members/liaison/notes.md and the latest xt brief, then await the human's request."
    cut = reset_mod.clip(long)
    assert cut.endswith("…") and len(cut) <= 81 and long.startswith(cut[:-1])
    assert cut[:-1] == long[:len(cut) - 1] and long[len(cut) - 1] == " "  # ends before a space, not mid-word
    assert reset_mod.clip("short") == "short"


def test_a_reading_from_the_future_never_suggests_a_reset():
    """rc2 QA: a timestamp a year ahead passed the "not older than 2 h" check."""
    now = dt.datetime(2026, 9, 29, 9, 0, tzinfo=dt.timezone.utc)
    def at(delta):
        return Reading(used=200_000, window=258_000, observed=(now + delta).isoformat(), source="session log")
    assert reset_mod.suggestion("agent", at(dt.timedelta(days=365)), now) is None
    assert reset_mod.suggestion("agent", at(dt.timedelta(minutes=10)), now) is None
    assert reset_mod.suggestion("agent", at(dt.timedelta(minutes=2)), now) is not None  # small clock skew is fine
    assert reset_mod.suggestion("agent", at(-dt.timedelta(minutes=30)), now) is not None
    assert reset_mod.suggestion("agent", at(-dt.timedelta(hours=3)), now) is None
