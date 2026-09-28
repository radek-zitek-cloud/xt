"""Per-turn usage, totals and estimates (card #17 / #54)."""

import datetime as dt
import json

import pytest

from xt import brief, cli, turns
from xt.dispatch import send
from xt.spawn import request_spawn
from xt.tui.model import build
from xt.watch import Supervisor

from .conftest import REPO, add_member
from .test_context_usage import _prompt


@pytest.fixture(autouse=True)
def prices(paths):
    (paths.root / "prices.toml").write_text((REPO / "prices.toml").read_text())


def codex_log(home, ctx, name, events, guardian=False):
    d = home / ".codex/sessions/2026/09/28"
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"rollout-{name}-{'g' if guardian else 'm'}.jsonl"
    source = {"subagent": {"other": "guardian"}} if guardian else "vscode"
    lines = [{"type": "session_meta", "payload": {"source": source}},
             {"type": "response_item", "payload": {"content": [{"text": _prompt(ctx, name)}]}},
             {"type": "turn_context", "payload": {"model": "codex-auto-review" if guardian else "gpt-6-sol"}}]
    total = 0
    for ts, inp, cached, out in events:
        if inp is None:  # a repeated count (no new model call)
            lines.append({"timestamp": ts, "type": "event_msg", "payload": {"type": "token_count", "info": {
                "total_token_usage": {"total_tokens": total}, "last_token_usage": {"total_tokens": 1}}}})
            continue
        total += inp + out
        lines.append({"timestamp": ts, "type": "event_msg", "payload": {
            "type": "token_count",
            "info": {"total_token_usage": {"total_tokens": total},
                     "last_token_usage": {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out,
                                          "total_tokens": inp + out},
                     "model_context_window": 258000},
            "rate_limits": {"primary": {"used_percent": 13.0, "window_minutes": 10080, "resets_at": 1790000000}}}})
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return f


def test_codex_turns_are_recorded_once_priced_and_guardian_counted_as_auxiliary(ctx, fake_home):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    f = codex_log(fake_home, ctx, "liaison", [("2026-09-28T08:00:00Z", 100000, 90000, 1000),
                                              ("2026-09-28T08:00:05Z", None, None, None),
                                              ("2026-09-28T08:05:00Z", 120000, 110000, 2000)])
    codex_log(fake_home, ctx, "liaison", [("2026-09-28T08:01:00Z", 5000, 0, 100)], guardian=True)
    assert turns.record(ctx) == 3
    assert turns.record(ctx) == 0  # nothing new
    recs = turns.records(ctx, ["2026-09-28"])
    main = [r for r in recs if not r["aux"]]
    assert len(main) == 2 and main[0]["input"] == 10000 and main[0]["cached_input"] == 90000
    # gpt-6-sol: 10k × $2 + 90k × $0.20 + 1k × $10 per M
    assert main[0]["est_usd"] == pytest.approx(0.02 + 0.018 + 0.01)
    guardian = [r for r in recs if r["aux"]]
    assert len(guardian) == 1 and guardian[0]["est_usd"] is None  # no public price: unpriced, not zero
    # appending to the log records only the new turn
    with open(f, "a") as fh:
        fh.write(json.dumps({"timestamp": "2026-09-28T09:00:00Z", "type": "event_msg", "payload": {
            "type": "token_count", "info": {"total_token_usage": {"total_tokens": 10 ** 7},
                                            "last_token_usage": {"input_tokens": 1, "output_tokens": 1}}}}) + "\n")
    assert turns.record(ctx) == 1
    allowance = turns.allowance_lines(ctx)
    assert allowance and allowance[0].startswith("codex 13% of 7d") and "account-wide" in allowance[0]


def test_totals_say_what_is_unpriced_and_auxiliary(ctx, fake_home, monkeypatch):
    monkeypatch.setattr(turns, "local_today", lambda: dt.date(2026, 9, 28))
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    codex_log(fake_home, ctx, "liaison", [("2026-09-28T08:00:00Z", 100000, 90000, 1000)])
    codex_log(fake_home, ctx, "liaison", [("2026-09-28T08:01:00Z", 5000, 0, 100)], guardian=True)
    turns.record(ctx)
    t = turns.today(ctx).team_today
    assert (t.tokens, t.aux_tokens, t.unpriced_tokens) == (106100, 5100, 5100)
    assert turns.fmt(t) == "106k tokens (5k auxiliary), est. $0.05 (+5k tokens unpriced)"
    assert turns.fmt_short(t) == "106k/est.$0.05+"


def test_claude_turns_dedupe_message_ids_and_price_cache_writes(ctx, fake_home):
    add_member(ctx, "carol")
    request_spawn(ctx, "human", "carol", None, None, None, None)
    d = fake_home / ".claude/projects/-team"
    d.mkdir(parents=True)
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 3000, "cache_read_input_tokens": 50000,
             "output_tokens": 500, "cache_creation": {"ephemeral_1h_input_tokens": 1000}}
    lines = [{"type": "user", "message": {"content": _prompt(ctx, "carol")}}]
    for block in range(3):  # one API message, logged once per content block
        lines.append({"timestamp": "2026-09-28T08:00:00Z", "message": {"id": "msg1", "model": "claude-opus-5-5", "usage": usage}})
    lines.append({"timestamp": "2026-09-28T08:02:00Z", "isSidechain": True,
                  "message": {"id": "msg2", "model": "claude-opus-5-5", "usage": {"input_tokens": 100, "output_tokens": 10}}})
    (d / "carol.jsonl").write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    assert turns.record(ctx) == 2
    recs = turns.records(ctx, ["2026-09-28"])
    first = next(r for r in recs if not r["aux"])
    # $4 input, 2000 × $5 (5m write) + 1000 × $8 (1h write), 50k × $0.20 read, 500 × $20 output, per M
    assert first["est_usd"] == pytest.approx((10 * 4 + 2000 * 5 + 1000 * 8 + 50000 * 0.2 + 500 * 20) / 1e6)
    assert next(r for r in recs if r["aux"])["agent"] == "carol"  # a subagent turn: auxiliary


def test_turns_belong_to_the_goal_being_worked_on_and_to_their_completion_day(ctx, fake_home, monkeypatch):
    import time

    monkeypatch.setenv("TZ", "Europe/Prague")  # the team's local day
    time.tzset()
    for n in ("liaison", "lead"):
        request_spawn(ctx, "human", n, None, None, None, None)
    ctx.ledger.clock.t = dt.datetime(2026, 9, 27, 21, 0, tzinfo=dt.timezone.utc)
    goal, _ = send(ctx, "liaison", "lead", "goal", "Write the report")
    codex_log(fake_home, ctx, "lead", [("2026-09-27T21:59:59Z", 1000, 0, 10),  # 23:59:59 in Prague
                                       ("2026-09-27T22:00:01Z", 1000, 0, 10)])  # 00:00:01 next day
    turns.record(ctx)
    before = [r for r in turns.records(ctx, ["2026-09-27"]) if r["agent"] == "lead"]
    after = [r for r in turns.records(ctx, ["2026-09-28"]) if r["agent"] == "lead"]
    assert len(before) == 1 and len(after) == 1  # a turn counts on the local day it completed
    assert all(r["goal"] == goal["id"] for r in before + after)
    monkeypatch.setattr(turns, "local_today", lambda: dt.date(2026, 9, 28))
    assert turns.goal_totals(ctx, goal["id"], goal["ts"]).turns == 2
    monkeypatch.delenv("TZ")
    time.tzset()


def test_supervisor_records_usage_and_survives_a_broken_log(ctx, fake_home, monkeypatch):
    lines = []
    sup = Supervisor(ctx, out=lines.append)
    monkeypatch.setattr(turns, "record", lambda c: (_ for _ in ()).throw(ValueError("odd format")))
    sup.tick(now=1000)
    sup.tick(now=1100)
    assert sum("usage recording failed" in ln for ln in lines) == 1  # said once, not every minute


def test_usage_shows_in_status_brief_tui_and_not_in_member_briefs(ctx, fake_home, monkeypatch, capsys):
    import io
    import sys

    monkeypatch.setattr(turns, "local_today", lambda: dt.date(2026, 9, 28))
    add_member(ctx, "carol")
    for n in ("liaison", "lead", "carol"):
        request_spawn(ctx, "human", n, None, None, None, None)
    codex_log(fake_home, ctx, "lead", [("2026-09-28T08:00:00Z", 100000, 90000, 1000)])
    turns.record(ctx)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    out = capsys.readouterr().out
    assert "today:101k/est.$0.05" in out and "team usage today: 101k tokens, est. $0.05" in out
    assert "allowance: codex 13% of 7d" in out
    assert "Team usage today: 101k tokens" in brief.build(ctx, "lead")
    assert "Team usage today" not in brief.build(ctx, "carol")
    snap = build(ctx)
    assert "today 101k tokens · est. $0.05" in snap.usage and "codex account 13% of the week" in snap.usage
    lead = next(r for r in snap.panels["Team"] if r.data["name"] == "lead")
    assert "usage today: 101k tokens, est. $0.05" in lead.detail().plain


def test_usage_from_before_a_restart_is_still_recorded(ctx, fake_home):
    """An upgrade restarts every agent: the sessions they used before must still be counted."""
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    codex_log(fake_home, ctx, "liaison", [("2026-09-28T07:00:00Z", 1000, 0, 10)])  # before the restart
    old = fake_home / ".codex/sessions/2026/09/28/rollout-liaison-m.jsonl"
    old = old.rename(old.with_name("rollout-liaison-old.jsonl"))
    ctx.ledger.clock.advance(hours=30)  # the restart is much later than that session
    import os
    import time

    last_written = ctx.ledger.clock().timestamp() - 3600  # written an hour before the restart,
    assert time.time() - last_written < 2 * 86400  # but within the last two days
    os.utime(old, (last_written, last_written))
    from xt.up import restart

    restart(ctx, ["liaison"])
    codex_log(fake_home, ctx, "liaison", [("2026-09-28T09:00:00Z", 2000, 0, 20)])  # the new session
    assert turns.record(ctx) == 2
    assert turns.record(ctx) == 0
