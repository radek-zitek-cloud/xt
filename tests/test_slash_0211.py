"""v0.21.1: Claude Code agents start without the operator's slash skills (#188)."""

from xt import adapters
from xt.adapters import load_adapters
from xt.spawn import do_spawn

from .conftest import add_member


def test_every_started_claude_agent_has_disable_slash_commands(ctx, monkeypatch):
    monkeypatch.setattr(adapters, "claude_mcp_servers", lambda binary="claude", cwd=None: ["claude.ai Context7"])
    add_member(ctx, "carol")  # default start
    add_member(ctx, "dave")
    ctx.team.upsert_agent("dave", "worker", "claude", "claude-sonnet-5-5", "lead")  # with a model
    add_member(ctx, "erin")
    ctx.team._table("erin")["connectors"] = ["claude.ai Context7"]  # with a connector opt-in
    ctx.team.save()
    ctx.reload_team()
    for name in ("carol", "dave", "erin"):
        do_spawn(ctx, name)
        started = [a for n, _, a in ctx.herdr.started if n == name][-1]
        assert "--disable-slash-commands" in started, name
    assert "--model" in [a for n, _, a in ctx.herdr.started if n == "dave"][-1]


def test_the_argument_is_a_default_of_the_claude_harness_only(ctx):
    ad = load_adapters(ctx.paths)
    assert "--disable-slash-commands" in ad["claude"].args
    assert "--disable-slash-commands" in ad["claude"].start_args(None)
    for name in ("codex", "pi"):
        assert "--disable-slash-commands" not in ad[name].start_args(None)
