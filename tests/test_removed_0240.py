"""v0.24.0, card #218: the `permissions`, `codex_options` and `connectors` lines are removed. A
team.toml that still has one is refused at load, by every command that loads the team, naming each
line and `xt capabilities NAME`; that command alone still reads them, to print the block."""

import json
import re

import pytest
import tomlkit

from xt import capabilities, cli
from xt.paths import XtError
from xt.spawn import request_spawn
from xt.team import Team

from .conftest import REPO, add_member

LINES = {"permissions": "settings/carol.json", "codex_options": ["sandbox_workspace_write.network_access=true"],
         "connectors": ["claude.ai Gmail"]}


def _write(ctx, defaults: dict | None = None, **agents: dict):
    """Put lines into team.toml without loading it (the load is what's under test)."""
    doc = ctx.team.doc
    for key, value in (defaults or {}).items():
        doc["defaults"][key] = value
    for a in doc["agent"]:
        for key, value in agents.get(a["name"], {}).items():
            a[key] = value
    ctx.paths.team_toml.write_text(tomlkit.dumps(doc))


def _refusal(ctx) -> str:
    with pytest.raises(XtError) as e:
        Team.load(ctx.paths.team_toml)
    return str(e.value)


# --- 1: each line, per agent and in [defaults], is refused at load ----------------------------------


@pytest.mark.parametrize("key", list(LINES))
def test_218_each_line_on_an_agent_is_refused_naming_the_line_the_agent_and_the_command(ctx, key):
    add_member(ctx, "carol")
    _write(ctx, carol={key: LINES[key]})
    assert _refusal(ctx) == (
        "team.toml still has permission lines that xt removed in 0.24 (nothing was started or changed):\n"
        f"  agent carol: {key}\n"
        "Replace them with a [capabilities] block. `xt capabilities carol` prints the block to paste in place "
        "of the old lines (it changes nothing).\n"
        "Then remove the old lines; the user guide's Upgrading section has the steps.")


@pytest.mark.parametrize("key", list(LINES))
def test_218_each_line_in_defaults_is_refused_and_says_how_to_convert_without_a_name(ctx, key):
    _write(ctx, defaults={key: LINES[key]})
    text = _refusal(ctx)
    assert f"  [defaults]: {key}\n" in text
    assert ("The [defaults] lines have no agent name of their own: run `xt capabilities NAME` for any agent of "
            "the team (it prints the block including what the agent inherits from [defaults]) and move the "
            "shared part into [defaults.capabilities] by hand.") in text
    assert "`xt capabilities carol`" not in text and "prints the block to paste" not in text


def test_218_one_message_lists_every_offender_and_each_agents_command(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dana")
    _write(ctx, defaults={"permissions": "settings/all.json"},
           carol={"permissions": "settings/carol.json", "connectors": ["claude.ai Gmail"]},
           dana={"codex_options": ["sandbox_workspace_write.network_access=true"]})
    text = _refusal(ctx)
    lines = text.splitlines()
    assert lines[1:4] == ["  [defaults]: permissions", "  agent carol: permissions, connectors",
                          "  agent dana: codex_options"]
    assert ("`xt capabilities carol` and `xt capabilities dana` each print the block to paste in place of the "
            "old lines (it changes nothing).") in text
    assert "The [defaults] lines have no agent name of their own" in text


def test_218_an_agent_with_a_block_and_an_old_line_is_refused_by_the_same_message(ctx):
    add_member(ctx, "carol")
    _write(ctx, carol={"capabilities": {"network": "on"}, "permissions": "settings/carol.json"})
    assert "  agent carol: permissions\n" in _refusal(ctx)


def test_218_an_empty_old_line_is_still_a_line(ctx):
    add_member(ctx, "carol")
    _write(ctx, carol={"connectors": []})
    assert "  agent carol: connectors\n" in _refusal(ctx)


def test_218_the_guides_example_is_what_xt_says():
    guide = (REPO / "docs/user-guide.md").read_text()
    (example,) = [b for b in re.findall(r"```text\n(.*?)```", guide, re.S) if "removed in 0.24" in b]
    doc = tomlkit.parse('[defaults]\n[[agent]]\nname = "carol"\npermissions = "settings/carol.json"\n'
                        'connectors = ["claude.ai Gmail"]\n')
    assert capabilities.removed_refusal(doc) == example.rstrip("\n")


# --- 2: a block alone loads and starts as before -------------------------------------------------------


def test_218_a_block_only_team_loads_and_starts(ctx):
    add_member(ctx, "carol")
    _write(ctx, defaults={"capabilities": {"network": "off"}},
           carol={"capabilities": {"commands": ["git"], "connectors": ["claude.ai Gmail"]}})
    Team.load(ctx.paths.team_toml)
    ctx.reload_team()
    request_spawn(ctx, "human", "carol", None, None, None, None)
    args = next(a for n, _, a in ctx.herdr.started if n == "carol")
    settings = json.loads(open(args[args.index("--settings") + 1]).read())["permissions"]
    assert "Bash(git *)" in settings["allow"] and "mcp__claude_ai_Gmail" in settings["allow"]


# --- 3b: the refusal is in the loader, so every command that loads the team gets it ------------------


@pytest.mark.parametrize("argv", [
    ["status"], ["up"], ["brief", "--as", "lead"], ["send", "lead", "--as", "liaison", "--type", "report", "hi"],
    ["log"], ["inbox"],
])
def test_218_commands_that_load_the_team_refuse_and_start_nothing(ctx, monkeypatch, capsys, argv):
    add_member(ctx, "carol")
    _write(ctx, carol={"permissions": "settings/carol.json"})
    monkeypatch.setenv("XT_ROOT", str(ctx.paths.root))
    before = ctx.paths.team_toml.read_text()
    assert cli.main(argv) != 0
    err = capsys.readouterr().err
    assert "removed in 0.24" in err and "`xt capabilities carol`" in err
    assert ctx.paths.team_toml.read_text() == before


def test_218_the_tui_start_refuses_too(ctx, monkeypatch):
    from xt.tui.app import run_live

    add_member(ctx, "carol")
    _write(ctx, carol={"codex_options": ["sandbox_workspace_write.network_access=true"]})
    monkeypatch.setenv("XT_ROOT", str(ctx.paths.root))
    with pytest.raises(XtError, match="removed in 0.24"):
        run_live()


# --- 3: xt capabilities still reads them, changes nothing ------------------------------------------


def _snapshot(root) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and "home" not in p.relative_to(root).parts}


def test_218_xt_capabilities_converts_an_inherited_defaults_file_and_changes_nothing(ctx, monkeypatch, capsys):
    add_member(ctx, "carol")
    (ctx.paths.root / "settings").mkdir()
    (ctx.paths.root / "settings" / "all.json").write_text(json.dumps(
        {"permissions": {"defaultMode": "dontAsk", "allow": ["Bash(git *)"], "deny": ["Bash(rm *)"]}}))
    _write(ctx, defaults={"permissions": "settings/all.json"})
    before = _snapshot(ctx.paths.root)
    monkeypatch.setenv("XT_ROOT", str(ctx.paths.root))
    assert cli.main(["capabilities", "carol"]) == 0
    out = capsys.readouterr().out
    assert _snapshot(ctx.paths.root) == before
    assert out.splitlines()[:2] == [
        "# xt capabilities carol: the block equivalent to its old permission lines and settings/all.json "
        "(nothing was changed).",
        '# Under its [[agent]] entry (name = "carol"):']  # its own entry has no old line to replace
    assert 'commands = ["git"]' in out and 'extras = "settings/all.json"' in out and "#   deny Bash(rm *)" in out


def test_218_the_spawn_flag_that_wrote_the_line_is_gone():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["spawn", "carol", "--permissions", "settings/carol.json"])


# --- 4: nothing else reads the lines; the deprecation and mixing texts are gone ---------------------


def test_218_only_the_refusal_and_the_conversion_name_the_lines_in_the_source():
    src = REPO / "src" / "xt"
    for path in src.rglob("*.py"):
        text = path.read_text()
        assert "deprecated: xt capabilities" not in text and ", deprecated" not in text, path  # 0.23's row
        assert "has both a [capabilities] block" not in text or path.name == "capabilities.py", path  # 3a only
        assert re.search(r"\blegacy\b", text) is None, path
        assert not re.search(r"\b(agent|existing)\.(permissions|connectors|codex_options)\b", text), path
        assert not re.search(r"\ba\.(permissions|codex_options)\b", text), path  # `a.connectors`: an adapter's
        assert "default_permissions" not in text, path
        if path.name not in ("capabilities.py", "cli.py"):  # removed_refusal, convert, cmd_capabilities
            assert "codex_options" not in text, path
