"""v0.19.0 card #167: pi gets its first prompt whole, and status says why a log is missing."""

import io
import json
import sys

import pytest

from xt import cli, usage
from xt.adapters import load_adapters
from xt.alerts import Alerts
from xt.spawn import request_spawn

from .conftest import FakeHerdr


class SlowPi(FakeHerdr):
    """A pi that draws its start-up screen for a few reads after Herdr reports it started; a prompt
    typed meanwhile loses its first five characters, as on the 2026-10-01 smoke test. What arrives
    is written to a pi session log, as pi does."""

    def __init__(self, home, loading=4):
        super().__init__()
        self.home, self.loading, self.left = home, loading, {}

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
            text = text[5:]  # not ready for input yet
        super().prompt(name, text, confirm)
        d = self.home / ".pi/agent/sessions/--team--"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
        (d / f"{name}.jsonl").write_text(json.dumps({"type": "session"}) + "\n" + json.dumps(rec) + "\n")


@pytest.fixture
def pi_team(ctx, fake_home):
    ctx.herdr = SlowPi(fake_home)
    (ctx.paths.roles / "worker.md").write_text("# Role: worker\n")
    ctx.team.upsert_agent("dave", "worker", "pi", None, "lead")
    ctx.team.save()
    ctx.reload_team()
    return ctx


def _started(ctx, name):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system" and m["body"].startswith(f"started {name} ")][-1]


def test_a_slow_starting_pi_gets_its_first_prompt_whole(pi_team):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert ctx.herdr.last_prompt("dave").startswith("You are **dave**")
    assert not any(k.startswith(("partprompt:", "noprompt:")) for k in Alerts(ctx).active())
    assert "FIRST PROMPT" not in _started(ctx, "dave") and "not checked" not in _started(ctx, "dave")
    path = usage.session_for(ctx, load_adapters(ctx.paths)["pi"], "dave", None)
    assert path and path.endswith("dave.jsonl")  # the log is found on the first start, not only after a reset


def test_a_prompt_that_still_arrives_incomplete_is_reported_not_passed(pi_team):
    ctx = pi_team
    toml = ctx.paths.harnesses / "pi.toml"
    toml.write_text(toml.read_text().replace("ready_settle = 3", "ready_settle = 0"))  # no wait: as before
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert ctx.herdr.last_prompt("dave").startswith("re **dave**")
    alert = Alerts(ctx).active()["partprompt:dave"]
    assert "without its opening" in alert["text"] and "xt spawn dave" in alert["text"]
    assert "FIRST PROMPT ARRIVED INCOMPLETE" in _started(ctx, "dave")


def test_a_pi_screen_that_never_settles_is_said_in_the_alert(pi_team):
    ctx = pi_team
    ctx.herdr.loading = 1000  # keeps drawing
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "its screen never settled" in Alerts(ctx).active()["partprompt:dave"]["text"]


def test_a_new_start_clears_the_incomplete_prompt_alert(pi_team):
    from xt.spawn import stop

    ctx = pi_team
    ctx.herdr.loading = 1000
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "partprompt:dave" in Alerts(ctx).active()
    stop(ctx, "dave")
    ctx.herdr.loading = 4
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "partprompt:dave" not in Alerts(ctx).active()


def test_no_log_yet_is_said_in_the_start_record(pi_team, monkeypatch):
    ctx = pi_team
    monkeypatch.setattr(SlowPi, "prompt", FakeHerdr.prompt)  # pi writes no log
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "first prompt not checked: no session log showed it yet" in _started(ctx, "dave")
    assert "partprompt:dave" not in Alerts(ctx).active()


def test_codex_and_claude_starts_are_unchanged(ctx):
    from .conftest import add_member

    add_member(ctx, "carol")  # claude
    request_spawn(ctx, "human", "liaison", None, None, None, None)  # codex
    request_spawn(ctx, "human", "carol", None, None, None, None)
    for name in ("liaison", "carol"):
        assert ctx.herdr.last_prompt(name).startswith(f"You are **{name}**")
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
    assert "no session log found for dave: its context and today's usage can't be read" in out


def test_status_has_no_reason_line_when_the_log_is_found(pi_team, monkeypatch, capsys):
    ctx = pi_team
    request_spawn(ctx, "human", "dave", None, None, None, None)
    monkeypatch.setattr(sys, "stdin", _Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    assert "no session log found" not in capsys.readouterr().out
