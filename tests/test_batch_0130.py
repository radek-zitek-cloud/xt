"""v0.13.0: price and context-window tables for current models (#116), per-agent permission
settings for Claude Code agents (#117)."""

import datetime as dt
import json
import os
import tomllib

import pytest

from xt import cli, permissions, turns, usage
from xt.adapters import get_adapter
from xt.paths import XtError
from xt.spawn import request_spawn
from xt.tui.model import build

from .conftest import REPO, add_member

PRICES = tomllib.loads((REPO / "prices.toml").read_text())["models"]
FIXTURE = REPO / "tests/fixtures/claude-sonnet-5-5-session.jsonl"


# --- #116 prices and windows ----------------------------------------------------------------------------


def test_every_price_row_is_complete_and_dated():
    for model, p in PRICES.items():
        assert p["input"] > 0 and p["output"] > 0, model
        assert p["source"].startswith("https://") and p["tier"].startswith("standard"), model
        assert isinstance(p["checked"], dt.date), model
        if model.startswith("claude-"):
            assert {"cache_write_5m", "cache_write_1h", "cache_read"} <= p.keys(), model
            assert "cached_input" not in p, model
        else:
            assert "cached_input" in p and not {"cache_write_5m", "cache_read"} & p.keys(), model


def test_spot_checks_against_the_cited_pages():
    # Values read off the providers' pages on 2026-09-29 (the rows' `source`), not off this table.
    assert (PRICES["gpt-6-sol"]["input"], PRICES["gpt-6-sol"]["cached_input"], PRICES["gpt-6-sol"]["output"]) == (2, 0.2, 10)
    assert (PRICES["gpt-6-astra"]["input"], PRICES["gpt-6-astra"]["output"]) == (10, 50)
    assert (PRICES["gpt-5.6-terra"]["output"], PRICES["gpt-6-luna"]["cached_input"]) == (12, 0.01)
    s = PRICES["claude-sonnet-5-5"]
    assert (s["input"], s["cache_write_5m"], s["cache_write_1h"], s["cache_read"], s["output"]) == (2, 2.5, 4, 0.2, 10)
    # the model-specific cache-read multipliers: 0.05x on Opus 5.5, 0.025x on Fable 5.1, 0.1x elsewhere
    assert PRICES["claude-opus-5-5"]["cache_read"] == 0.2 and PRICES["claude-fable-5-1"]["cache_read"] == 0.25
    assert PRICES["claude-opus-5"]["cache_read"] == 0.5


def test_every_claude_model_with_a_window_has_a_price_and_haiku_is_the_small_one(paths):
    windows = get_adapter(paths, "claude").context_windows
    assert not set(windows) - set(PRICES)
    assert windows["claude-sonnet-5-5"] == 1_000_000
    assert windows["claude-haiku-4-5"] == windows["claude-haiku-4-5-20251001"] == 200_000


def test_the_auxiliary_review_model_stays_unpriced():
    assert "codex-auto-review" not in PRICES
    assert turns.estimate({"model": "codex-auto-review", "input": 1000, "output": 10}, PRICES) is None


def test_a_real_sonnet_5_5_session_reads_its_context_and_prices_like_claude_code(paths):
    # From a real `claude -p --model claude-sonnet-5-5` call (2026-09-29, Claude Code 2.1.284),
    # trimmed to the usage record. Claude Code itself reported costUSD 0.0489674 for it.
    lines = FIXTURE.read_text().splitlines()
    r = usage._claude(list(reversed(lines)), get_adapter(paths, "claude"))
    assert (r.used, r.window) == (2 + 11818 + 8257 + 4, 1_000_000)
    assert "2%" in usage.describe(r)
    [turn] = turns._claude(lines, {}, False)
    assert turn["model"] == "claude-sonnet-5-5" and turn["cache_write_1h"] == 11818
    # Claude Code's own result for the same call (list prices), kept beside the log
    result = json.loads((REPO / "tests/fixtures/claude-sonnet-5-5-result.json").read_text())
    assert result["usage"]["cache_read_input_tokens"] == turn["cached_input"]
    assert result["modelUsage"]["claude-sonnet-5-5"]["contextWindow"] == r.window
    assert turns.estimate(turn, PRICES) == round(result["total_cost_usd"], 6) == 0.048967


def test_codex_uses_its_logged_window_never_an_api_maximum(paths):
    adapter = get_adapter(paths, "codex")

    def log(info):
        return [json.dumps({"timestamp": "2026-09-29T10:00:00Z", "type": "event_msg",
                            "payload": {"type": "token_count", "info": info}})]

    logged = usage._codex(log({"last_token_usage": {"total_tokens": 50000}, "model_context_window": 258400}), adapter)
    assert (logged.used, logged.window) == (50000, 258400)
    # gpt-6-astra's API window is 1.05M; a session log without a window stays unknown, not 1.05M
    missing = usage._codex(log({"last_token_usage": {"total_tokens": 50000}}), adapter)
    assert missing.used == 50000 and missing.window is None
    assert not adapter.context_windows


# --- #117 per-agent permission settings ----------------------------------------------------------


# Since 0.24 (card #218) a settings file reaches Claude Code only as a [capabilities] block's `extras`,
# on top of the generated settings, where it may only restrict.
GOOD = {"permissions": {"defaultMode": "dontAsk",
                        "allow": ["Bash(/team/bin/xt *)", "Bash(cat *)", "Edit(members/carol/**)", "Read"],
                        "deny": ["Bash(git push *)", "WebFetch", "mcp__claude-in-chrome"]},
        "env": {"SOME_OTHER": "key Claude owns"}}


def _settings(ctx, rel="settings/carol.json", data=GOOD):
    f = ctx.paths.root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(data if isinstance(data, str) else json.dumps(data))
    return f


def _set(ctx, agent):
    next(a for a in ctx.team.doc["agent"] if a["name"] == agent[0])["capabilities"] = {"extras": agent[1]}
    ctx.team.save()
    ctx.reload_team()


def _args(ctx, name):
    return next(args for n, _, args in ctx.herdr.started if n == name)


def _system(ctx):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system"]


def test_an_agent_settings_file_is_passed_checked_and_shown(ctx, capsys, monkeypatch):
    add_member(ctx, "carol")
    f = _settings(ctx)
    _set(ctx, agent=("carol", "settings/carol.json"))
    request_spawn(ctx, "human", "carol", None, None, None, None)
    args = _args(ctx, "carol")
    passed = args[args.index("--settings") + 1]
    assert passed == str(ctx.paths.state / "settings" / "carol.json")  # generated, with the file on top
    assert "Bash(git push *)" in json.loads(open(passed).read())["permissions"]["deny"]
    assert f.read_text() == json.dumps(GOOD)  # the file itself is unchanged
    note = next(b for b in _system(ctx) if "Claude Code settings" in b)
    digest = permissions.preflight(ctx.paths.root, "settings/carol.json").digest
    assert f"settings/carol.json (sha256 {digest}, permissions.defaultMode dontAsk)" in note
    assert "Bash(" not in note  # the path and hash, never the contents
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    out = capsys.readouterr().out
    assert "caps: " in out and "legacy" not in out and "deprecated" not in out
    row = next(r for r in build(ctx).panels["Team"] if r.data and r.data.get("name") == "carol")
    assert "caps: " in row.detail().plain and "legacy" not in row.detail().plain


def test_a_changed_file_gets_a_new_hash_at_the_next_start(ctx):
    add_member(ctx, "carol")
    _settings(ctx)
    first = permissions.preflight(ctx.paths.root, "settings/carol.json").digest
    _settings(ctx, data={**GOOD, "env": {}})
    assert permissions.preflight(ctx.paths.root, "settings/carol.json").digest != first


def test_an_agent_without_a_block_starts_without_a_settings_file(ctx):
    add_member(ctx, "dave")
    request_spawn(ctx, "human", "dave", None, None, None, None)
    assert "--settings" not in _args(ctx, "dave")  # nothing configured


def test_a_codex_agent_with_an_extras_file_is_refused(ctx):
    _settings(ctx, "settings/liaison.json")
    _set(ctx, agent=("liaison", "settings/liaison.json"))
    with pytest.raises(XtError, match="codex takes none"):
        request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert not ctx.herdr.started


@pytest.mark.parametrize("rel, content, why", [
    ("settings/none.json", None, "no such file"),
    ("settings", None, "not a regular file"),
    ("settings/bad.json", '{"permissions": {', "not valid JSON"),
    ("settings/list.json", "[]", "must be a JSON object"),
    ("settings/mode.json", {"permissions": {"defaultMode": "nonsense"}}, "unknown permissions.defaultMode"),
    ("settings/rule.json", {"permissions": {"allow": ["Bash(ls *"]}}, "malformed permissions.allow"),
    ("settings/rule2.json", {"permissions": {"deny": ["Bash) ls ("]}}, "malformed permissions.deny"),
    ("settings/rule3.json", {"permissions": {"allow": "Bash(ls *)"}}, "must be a list"),
    ("/etc/claude.json", None, "relative to it"),
    ("settings/../../x.json", None, "`..` isn't allowed"),
])
def test_preflight_refuses_bad_files_before_anything_starts(ctx, rel, content, why):
    add_member(ctx, "carol")
    (ctx.paths.root / "settings").mkdir(exist_ok=True)
    if content is not None:
        _settings(ctx, rel, content)
    _set(ctx, agent=("carol", rel))
    with pytest.raises(XtError, match=why):
        request_spawn(ctx, "human", "carol", None, None, None, None)
    assert not ctx.herdr.started and not ctx.herdr.created  # no retry without the file, no workspace


def test_a_symlink_out_of_the_team_repo_is_refused(ctx, tmp_path_factory):
    outside = tmp_path_factory.mktemp("outside") / "s.json"
    outside.write_text(json.dumps(GOOD))
    (ctx.paths.root / "settings").mkdir()
    os.symlink(outside, ctx.paths.root / "settings/link.json")
    with pytest.raises(XtError, match="outside the team repo"):
        permissions.preflight(ctx.paths.root, "settings/link.json")


def test_other_claude_keys_are_accepted(ctx):
    add_member(ctx, "carol")
    _settings(ctx, data={"permissions": {}, "hooks": {}, "model": "x"})
    _set(ctx, agent=("carol", "settings/carol.json"))
    request_spawn(ctx, "human", "carol", None, None, None, None)
    args = _args(ctx, "carol")
    assert json.loads(open(args[args.index("--settings") + 1]).read())["model"] == "x"


def test_xt_harnesses_describes_capability_not_a_path(ctx, capsys, monkeypatch):
    monkeypatch.setenv("XT_ROOT", str(ctx.paths.root))
    cli.cmd_harnesses(None)
    out = capsys.readouterr().out
    assert "settings file (generated from [capabilities], `extras` on top): yes, passed with --settings" in out
    assert "not supported" in out  # codex
