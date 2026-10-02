"""v0.19.0 card #167: pi gets its first prompt whole, and status says why a log is missing.

rc5: a guard line before the prompt takes a lost start, and a prompt still damaged is resent whole
once, when the agent is idle; the alert is the last resort."""

import io
import json
import sys

import pytest

from xt import cli, spawn, usage
from xt.adapters import load_adapters
from xt.alerts import Alerts
from xt.spawn import RESEND_NOTE, Resends, request_spawn, run_resends

from .conftest import FakeHerdr

# characters lost in the damage tests: the whole guard line and the prompt's opening, but not the
# first paragraph's later parts (the team repo's path), which tell xt the prompt arrived damaged
DAMAGE = 150


class SlowPi(FakeHerdr):
    """A pi that draws its start-up screen for a few reads after Herdr reports it started; a prompt
    typed meanwhile loses its first `lost` characters (five on the 2026-10-01 runs). What arrives is
    appended to a pi session log, as pi does."""

    def __init__(self, home, loading=4, lost=5):
        super().__init__()
        self.home, self.loading, self.lost, self.left = home, loading, lost, {}

    def start_agent(self, name, kind, pane, args):
        super().start_agent(name, kind, pane, args)
        self.left[pane] = self.loading

    def read_pane(self, pane, lines=200):
        if self.left.get(pane, 0) > 0:
            self.left[pane] -= 1
            return super().read_pane(pane, lines) + f"\npi starting {self.left[pane]}"
        return super().read_pane(pane, lines) or "pi 0.99.1  ›"

    def prompt(self, name, text, confirm=False):
        pane = self.live[name].pane_id
        if self.left.get(pane, 0) > 0:
            text = text[self.lost:]  # not ready for input yet
        super().prompt(name, text, confirm)
        d = self.home / ".pi/agent/sessions/--team--"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{name}.jsonl"
        if not f.exists():
            f.write_text(json.dumps({"type": "session"}) + "\n")
        rec = {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        with open(f, "a") as fh:
            fh.write(json.dumps(rec) + "\n")


@pytest.fixture
def pi_team(ctx, fake_home):
    ctx.herdr = SlowPi(fake_home)
    (ctx.paths.roles / "worker.md").write_text("# Role: worker\n")
    ctx.team.upsert_agent("dave", "worker", "pi", None, "lead")
    ctx.team.save()
    ctx.reload_team()
    return ctx


def _prefix(ctx):
    return load_adapters(ctx.paths)["pi"].first_prompt_prefix


def _started(ctx, name):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system" and m["body"].startswith(f"started {name} ")][-1]


def _system(ctx):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system"]


def _no_wait(ctx):
    toml = ctx.paths.harnesses / "pi.toml"
    toml.write_text(toml.read_text().replace("ready_settle = 3", "ready_settle = 0"))


def test_the_guard_line_comes_first_and_says_what_it_is(pi_team):
    ctx = pi_team
    prefix = _prefix(ctx)
    assert prefix.startswith("(xt: ") and "ignore it" in prefix and "\n" not in prefix
    request_spawn(ctx, "human", "dave", None, None, None, None)
    first, rest = ctx.herdr.last_prompt("dave").split("\n", 1)
    assert first == prefix and rest.startswith("You are **dave**")


def test_a_slow_starting_pi_gets_its_first_prompt_whole(pi_team):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert not any(k.startswith(("partprompt:", "noprompt:")) for k in Alerts(ctx).active())
    assert "FIRST PROMPT" not in _started(ctx, "dave") and "not checked" not in _started(ctx, "dave")
    path = usage.session_for(ctx, load_adapters(ctx.paths)["pi"], "dave", None)
    assert path and path.endswith("dave.jsonl")  # the log is found on the first start, not only after a reset
    assert not Resends(ctx).load()


def test_a_guard_line_that_lost_characters_is_not_damage(pi_team):
    ctx = pi_team
    _no_wait(ctx)  # typed at once: the five characters are lost, as on rc1 and rc3
    request_spawn(ctx, "human", "dave", None, None, None, None)
    arrived = ctx.herdr.last_prompt("dave")
    assert arrived.startswith(_prefix(ctx)[5:]) and "\nYou are **dave**" in arrived
    assert "FIRST PROMPT" not in _started(ctx, "dave")
    assert not Resends(ctx).load() and "partprompt:dave" not in Alerts(ctx).active()


def test_a_damaged_prompt_is_resent_whole_once_when_the_agent_is_idle(pi_team):
    ctx = pi_team
    _no_wait(ctx)
    ctx.herdr.lost = DAMAGE  # more than the guard line
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "FIRST PROMPT ARRIVED DAMAGED" in _started(ctx, "dave") and "resends it whole" in _started(ctx, "dave")
    assert "dave" in Resends(ctx).load() and "partprompt:dave" not in Alerts(ctx).active()
    prompts = len(ctx.herdr.prompts)
    assert run_resends(ctx, ctx.herdr.agents(), 1000.0) == []  # still working on it: wait
    assert len(ctx.herdr.prompts) == prompts
    ctx.herdr.live["dave"].status = "idle"
    ctx.herdr.left.clear()  # pi takes input by now
    assert run_resends(ctx, ctx.herdr.agents(), 1001.0) == ["resent dave's first prompt"]
    resent = ctx.herdr.last_prompt("dave")
    # whole: the guard line, the note, then the full first prompt (rebuilt, so its brief is current)
    assert resent.startswith(f"{_prefix(ctx)}\n{RESEND_NOTE}\nYou are **dave**, an agent in the xt team")
    assert "===== protocol.md =====" in resent and spawn.START_NOW in resent.splitlines()[-1]
    assert run_resends(ctx, ctx.herdr.agents(), 1002.0) == ["dave's resent first prompt arrived whole"]
    assert not Resends(ctx).load() and "partprompt:dave" not in Alerts(ctx).active()
    ctx.herdr.live["dave"].status = "idle"
    run_resends(ctx, ctx.herdr.agents(), 2000.0)
    assert len(ctx.herdr.prompts) == prompts + 1  # once only
    assert "resent dave's first prompt whole (it arrived with its opening missing)" in _system(ctx)
    assert usage.session_for(ctx, load_adapters(ctx.paths)["pi"], "dave", None)  # status finds the log now


def test_a_second_failure_raises_the_alert(pi_team):
    ctx = pi_team
    ctx.herdr.loading, ctx.herdr.lost = 1000, DAMAGE  # never ready: the resend is damaged too
    request_spawn(ctx, "human", "dave", None, None, None, None)
    ctx.herdr.live["dave"].status = "idle"
    # the resend's guard line and note take a loss too; lose past both, into the opening
    ctx.herdr.lost = len(_prefix(ctx)) + len(RESEND_NOTE) + 2 + 20
    run_resends(ctx, ctx.herdr.agents(), 1000.0)
    assert run_resends(ctx, ctx.herdr.agents(), 1000.0 + 60) == []  # not yet: give the log time
    lines = run_resends(ctx, ctx.herdr.agents(), 1000.0 + spawn.RESEND_CHECK)
    assert lines == ["alert: dave's resent first prompt arrived damaged too"]
    text = Alerts(ctx).active()["partprompt:dave"]["text"]
    assert "so did xt's one resend" in text and "its screen never settled" in text and "xt spawn dave" in text
    ctx.herdr.live["dave"].status = "idle"
    run_resends(ctx, ctx.herdr.agents(), 9999.0)
    assert sum(1 for n, _ in ctx.herdr.prompts if n == "dave") == 2  # the first and one resend


def test_a_resend_that_herdr_refuses_raises_the_alert(pi_team, monkeypatch):
    ctx = pi_team
    _no_wait(ctx)
    ctx.herdr.lost = DAMAGE
    request_spawn(ctx, "human", "dave", None, None, None, None)
    ctx.herdr.live["dave"].status = "idle"
    ctx.herdr.stall["dave"] = 1
    lines = run_resends(ctx, ctx.herdr.agents(), 1000.0)
    assert lines[0].startswith("resend of dave's first prompt failed") and "partprompt:dave" in Alerts(ctx).active()


def test_a_stopped_agent_drops_its_resend_and_a_new_start_clears_the_alert(pi_team):
    from xt.spawn import stop

    ctx = pi_team
    _no_wait(ctx)
    ctx.herdr.lost = DAMAGE
    request_spawn(ctx, "human", "dave", None, None, None, None)
    stop(ctx, "dave")
    assert run_resends(ctx, ctx.herdr.agents(), 1000.0) == [] and not Resends(ctx).load()
    Alerts(ctx).raise_("partprompt:dave", "x")
    ctx.herdr.lost = 5
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "partprompt:dave" not in Alerts(ctx).active()


def test_the_supervisor_runs_the_resend(pi_team):
    from xt.watch import Supervisor

    ctx = pi_team
    _no_wait(ctx)
    ctx.herdr.lost = DAMAGE
    request_spawn(ctx, "human", "dave", None, None, None, None)
    ctx.herdr.live["dave"].status = "idle"
    ctx.herdr.left.clear()
    Supervisor(ctx, out=lambda s: None).tick(1000.0)
    assert ctx.herdr.last_prompt("dave").split("\n", 2)[1] == RESEND_NOTE


def test_no_log_yet_is_said_in_the_start_record(pi_team, monkeypatch):
    ctx = pi_team
    monkeypatch.setattr(SlowPi, "prompt", FakeHerdr.prompt)  # pi writes no log
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "first prompt not checked: no session log showed it yet" in _started(ctx, "dave")
    assert "partprompt:dave" not in Alerts(ctx).active() and not Resends(ctx).load()


def test_codex_and_claude_starts_are_unchanged(ctx):
    from .conftest import add_member

    add_member(ctx, "carol")  # claude
    request_spawn(ctx, "human", "liaison", None, None, None, None)  # codex
    request_spawn(ctx, "human", "carol", None, None, None, None)
    adapters = load_adapters(ctx.paths)
    assert adapters["codex"].first_prompt_prefix is None and adapters["claude"].first_prompt_prefix is None
    for name in ("liaison", "carol"):
        assert ctx.herdr.last_prompt(name).startswith(f"You are **{name}**")  # no guard line
        assert "not checked" not in _started(ctx, name) and "FIRST PROMPT" not in _started(ctx, name)


class _Tty(io.StringIO):
    def isatty(self):
        return True


def test_status_gives_a_reason_when_no_session_log_is_found(pi_team, monkeypatch, capsys):
    ctx = pi_team
    monkeypatch.setattr(SlowPi, "prompt", FakeHerdr.prompt)  # no log
    request_spawn(ctx, "human", "dave", None, None, None, None)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    out = capsys.readouterr().out
    # v0.20.0 #174: which of context and usage can be read, and the precise reason
    assert "dave: nothing can be read: no context and no usage recorded today (no pi session logs at" in out


def test_status_has_no_reason_line_when_the_log_is_found(pi_team, monkeypatch, capsys):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    assert "can't be read" not in capsys.readouterr().out  # a fresh agent's first turn: no line
