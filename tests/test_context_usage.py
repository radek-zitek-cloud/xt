"""Live context per agent, read from the harness's session log (card #25/#53)."""

import datetime as dt
import json
import os
import time

from xt import brief, cli, usage
from xt.adapters import load_adapters
from xt.spawn import request_spawn
from xt.tui.model import build

from .conftest import add_member


def _prompt(ctx, name):
    return f'You are **{name}**, an agent in the xt team "{ctx.team.name}". Your role is ...'


def codex_session(home, ctx, name, used, window=258000, guardian=False, when=None):
    d = home / ".codex/sessions/2026/09/28"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"rollout-{name}-{'g' if guardian else 'm'}-{time.time_ns()}.jsonl"
    source = {"subagent": {"other": "guardian"}} if guardian else "vscode"
    lines = [
        {"type": "session_meta", "payload": {"cwd": str(ctx.paths.root), "source": source}},
        {"type": "response_item", "payload": {"role": "user", "content": [{"text": _prompt(ctx, name)}]}},
        {"timestamp": "2026-09-28T08:00:00Z", "type": "event_msg",
         "payload": {"type": "token_count", "info": {"total_token_usage": {"total_tokens": used * 10},
                                                     "last_token_usage": {"total_tokens": used},
                                                     "model_context_window": window}}},
    ]
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    if when:
        os.utime(f, (when, when))
    return f


def claude_session(home, ctx, name, model="claude-opus-5-5"):
    d = home / ".claude/projects/-team"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.jsonl"
    lines = [
        {"type": "user", "message": {"role": "user", "content": _prompt(ctx, name)}},
        {"type": "assistant", "timestamp": "2026-09-28T08:00:00Z",
         "message": {"model": model, "usage": {"input_tokens": 5, "cache_creation_input_tokens": 1000,
                                               "cache_read_input_tokens": 40000, "output_tokens": 200}}},
        {"type": "assistant", "isSidechain": True, "timestamp": "2026-09-28T08:01:00Z",
         "message": {"model": model, "usage": {"input_tokens": 999999}}},
    ]
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return f


def pi_session(home, ctx, name):
    d = home / ".pi/agent/sessions/--team--"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{name}.jsonl"
    lines = [
        {"type": "session", "cwd": str(ctx.paths.root)},
        {"type": "message", "message": {"role": "user", "content": [{"type": "text", "text": _prompt(ctx, name)}]}},
        {"type": "message", "message": {"role": "assistant", "provider": "openrouter", "model": "moonshotai/kimi-k2.6",
                                        "timestamp": 1790000000000,
                                        "usage": {"input": 100, "output": 50, "cacheRead": 7000, "cacheWrite": 0,
                                                  "totalTokens": 7150}}},
    ]
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return f


def test_reads_codex_context_from_the_main_session_not_the_guardian(ctx, fake_home):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    codex_session(fake_home, ctx, "liaison", 54000)
    codex_session(fake_home, ctx, "liaison", 999, guardian=True)  # newer, but the reviewer's
    r = usage.reading(ctx, "liaison")
    assert (r.used, r.window, r.approximate) == (54000, 258000, True)
    assert usage.compact(r) == "~54k/258k"
    assert "21%" in usage.describe(r) and "codex session log" in usage.describe(r)
    assert json.loads((ctx.paths.state / "sessions.json").read_text())["liaison"]["harness"] == "codex"


def test_a_restarted_agent_is_linked_to_its_new_session(ctx, fake_home):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    started = ctx.ledger.clock().timestamp()  # the test ledger's clock
    codex_session(fake_home, ctx, "liaison", 200000, when=started - 3600)  # before this start
    assert not usage.reading(ctx, "liaison").known  # an old session is never used for the current agent
    codex_session(fake_home, ctx, "liaison", 12000)
    assert usage.reading(ctx, "liaison").used == 12000


def test_other_teams_and_other_agents_dont_match(ctx, fake_home):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    f = codex_session(fake_home, ctx, "liaison", 54000)
    f.write_text(f.read_text().replace(f'team \\"{ctx.team.name}\\"', 'team \\"another\\"'))
    r = usage.reading(ctx, "liaison")
    assert not r.known and r.missing and "none with its first prompt" in r.reason  # v0.20.0 #174 wording


def test_claude_context_ignores_subagent_turns_and_takes_the_window_from_the_adapter(ctx, fake_home):
    add_member(ctx, "carol")  # claude
    request_spawn(ctx, "human", "carol", None, None, None, None)
    claude_session(fake_home, ctx, "carol")
    r = usage.reading(ctx, "carol")
    assert (r.used, r.window, r.approximate) == (41205, 1000000, False)
    assert usage.compact(r) == "41k/1M"
    claude_session(fake_home, ctx, "carol", model="claude-unknown")
    assert usage.compact(usage.reading(ctx, "carol")) == "41k/?"  # window unknown, not guessed


def test_pi_context_and_window_from_its_model_list(ctx, fake_home, monkeypatch):
    ctx.team.upsert_agent("dave", "worker", "pi", None, "lead")
    ctx.team.save()
    ctx.reload_team()
    (ctx.paths.roles / "worker.md").write_text("# Role: worker\n")
    request_spawn(ctx, "human", "dave", None, None, None, None)
    pi_session(fake_home, ctx, "dave")
    monkeypatch.setattr(usage, "_pi_windows", lambda c: {"openrouter/moonshotai/kimi-k2.6": 262144})
    r = usage.reading(ctx, "dave")
    assert (r.used, r.window) == (7150, 262144) and usage.compact(r) == "7k/262k"
    assert r.observed.startswith("2026-09-") and "ago" in usage.describe(r, ctx.ledger.clock())


def test_unknown_when_nothing_is_recorded(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    r = usage.reading(ctx, "liaison")
    assert not r.known and usage.compact(r) == "—" and "context unknown" in usage.describe(r)


def test_context_shows_in_team_row_detail_status_and_lead_brief(ctx, fake_home, monkeypatch, capsys):
    import io
    import sys

    add_member(ctx, "carol")
    for n in ("liaison", "lead", "carol"):
        request_spawn(ctx, "human", n, None, None, None, None)
    codex_session(fake_home, ctx, "lead", 211000)
    claude_session(fake_home, ctx, "carol")
    team = {r.data["name"]: r for r in build(ctx).panels["Team"]}
    lead, carol = team["lead"].text.plain, team["carol"].text.plain  # tokens, a bar and the share (card #128)
    assert "~211k ▕" in lead and lead.endswith(" 82%") and "41k ▕" in carol and carol.endswith(" 4%")
    assert "82%" in team["lead"].detail().plain

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    assert "context:~211k/258k" in capsys.readouterr().out
    assert "context ~211k/258k" in brief.build(ctx, "lead")
    assert "context ~211k" not in brief.build(ctx, "carol")  # members don't get it
