"""v0.23.0, card #186: the capability model (parsing, defaults, precedence, mixing)."""

import pytest
import tomlkit

from xt import capabilities as caps_mod
from xt.capabilities import CREDENTIAL_CLIS, Caps, effective
from xt.paths import XtError
from xt.spawn import request_spawn
from xt.team import Team

from .conftest import add_member


def _team(ctx):
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    request_spawn(ctx, "human", "lead", None, None, None, None)
    add_member(ctx, "carol")


def _set(ctx, defaults: dict | None = None, **agents: dict):
    doc = ctx.team.doc
    if defaults is not None:
        doc["defaults"]["capabilities"] = defaults
    for a in doc["agent"]:
        for key, value in agents.get(a["name"], {}).items():
            a[key] = value
    ctx.paths.team_toml.write_text(tomlkit.dumps(doc))
    ctx.reload_team()


def test_186_no_block_means_the_defaults_and_not_configured(ctx):
    _team(ctx)
    c = effective(ctx.team, ctx.team.agent("carol"))
    assert c == Caps() and not c.configured and c.changed() == []
    assert c.network == "off" and c.commands is None and c.skills == [] and "gh" in c.credential_clis


def test_186_team_default_then_agent_block_then_require_from_both(ctx):
    _team(ctx)
    _set(ctx, {"network": "on", "commands": ["git"], "require": ["network"]},
         carol={"capabilities": {"commands": ["git", "uv"], "write": ["/tmp/carol"], "require": ["write"],
                                 "credential_clis": {"allow": ["gh"], "deny": ["mytool"]}}})
    c = effective(ctx.team, ctx.team.agent("carol"))
    assert c.configured and c.network == "on" and c.commands == ["git", "uv"] and c.write == ["/tmp/carol"]
    assert c.require == ["write", "network"]
    assert "gh" not in c.credential_clis and "mytool" in c.credential_clis and "aws" in c.credential_clis
    lead = effective(ctx.team, ctx.team.agent("lead"))  # the team default alone
    assert lead.configured and lead.commands == ["git"] and lead.require == ["network"]
    assert c.changed() == ["write", "commands", "network", "credential_clis"]


@pytest.mark.parametrize("block, message", [
    ({"netwerk": "on"}, r"capabilities.netwerk in team.toml isn't a capability"),
    ({"network": "maybe"}, r"capabilities.network = 'maybe' in team.toml must be \"off\" or \"on\""),
    ({"write": "/tmp"}, r"capabilities.write = '/tmp' in team.toml isn't a list of names"),
    ({"commands": ["git", ""]}, r"capabilities.commands = .* isn't a list of names"),
    ({"require": ["write", "teleport"]}, r"capabilities.require names teleport, which isn't a capability"),
    ({"credential_clis": {"permit": ["gh"]}}, r"capabilities.credential_clis takes `allow` and `deny` lists, not permit"),
    ({"skills": "all"}, r"capabilities.skills = 'all' in team.toml isn't a list of names"),
])
def test_186_unknown_names_and_bad_values_are_refused_at_load(ctx, block, message):
    _team(ctx)
    ctx.team.doc["defaults"]["capabilities"] = block
    ctx.paths.team_toml.write_text(tomlkit.dumps(ctx.team.doc))
    with pytest.raises(XtError, match=r"\[defaults\] " + message):
        Team.load(ctx.paths.team_toml)


def test_186_skills_none_or_names(ctx):
    _team(ctx)
    _set(ctx, carol={"capabilities": {"skills": ["silverbullet"]}})
    assert effective(ctx.team, ctx.team.agent("carol")).skills == ["silverbullet"]
    _set(ctx, carol={"capabilities": {"skills": "none"}})
    assert effective(ctx.team, ctx.team.agent("carol")).skills == []


def test_186_the_credential_list_is_its_own_list_not_commands():
    assert set(CREDENTIAL_CLIS) >= {"gh", "aws", "gcloud", "fizzy"}
    assert Caps().commands is None and caps_mod.NAMES.index("credential_clis") > caps_mod.NAMES.index("commands")
