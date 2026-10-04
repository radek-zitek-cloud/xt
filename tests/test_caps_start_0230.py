"""v0.23.0, card #186: what each harness starts with under the capability model, refusals, the
compact row and the spawn sentence."""

import json
import textwrap

import pytest
import tomlkit

from xt import capstart, cli
from xt.adapters import load_adapters
from xt.approvals import Approvals
from xt.capabilities import NAMES, Caps
from xt.paths import XtError
from xt.spawn import request_spawn

from .conftest import REPO


def _team(ctx, **members):
    """liaison and lead (codex, as new teams have), plus members: name -> harness."""
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    request_spawn(ctx, "human", "lead", None, None, None, None)
    (ctx.paths.roles / "worker.md").write_text("# Role: worker\n")
    for name, harness in members.items():
        ctx.team.upsert_agent(name, "worker", harness, None, "lead")
    ctx.team.save()
    ctx.reload_team()


def _edit(ctx, defaults: dict | None = None, **agents: dict):
    doc = ctx.team.doc
    if defaults is not None:
        doc["defaults"]["capabilities"] = defaults
    for a in doc["agent"]:
        for key, value in agents.get(a["name"], {}).items():
            a[key] = value
    ctx.paths.team_toml.write_text(tomlkit.dumps(doc))
    ctx.reload_team()


def _start(ctx, name):
    request_spawn(ctx, "human", name, None, None, None, None)
    return next(args for n, _, args in reversed(ctx.herdr.started) if n == name)


def _settings(args) -> dict:
    return json.loads(open(args[args.index("--settings") + 1]).read())


def _status(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "human_terminal", lambda: True)
    args = cli.build_parser().parse_args(["status"])
    args.func(args)
    return capsys.readouterr().out


def _row(out: str, name: str) -> str | None:
    """The `    caps:` row under this agent's status row, or None."""
    lines = out.splitlines()
    start = next(i for i, x in enumerate(lines) if x.startswith(f"  {name} "))
    for x in lines[start + 1:]:
        if x.startswith("  ") and not x.startswith("   "):
            return None  # the next agent's row
        if x.startswith("    caps:"):
            return x
    return None


# --- the support table ------------------------------------------------------------------------------


def test_186_each_harness_declares_every_capability_and_the_checked_version(paths):
    adapters = load_adapters(paths)
    versions = {"claude": "Claude Code 2.1.289", "codex": "codex-cli 0.160.0", "pi": "pi 1.0.2"}
    for h, v in versions.items():
        a = adapters[h]
        assert set(a.capabilities) == set(NAMES) and set(a.capabilities.values()) <= {"enforced", "advisory"}
        assert v in a.capabilities_checked
    assert adapters["claude"].capabilities["network"] == "advisory"  # no OS limit: never claimed
    assert adapters["codex"].capabilities["network"] == "enforced" and adapters["codex"].capabilities["write"] == "advisory"
    assert adapters["pi"].capabilities["skills"] == "enforced" and adapters["pi"].capabilities["commands"] == "advisory"


# --- generated configuration ------------------------------------------------------------------------


def test_186_claude_gets_a_generated_settings_file_from_the_block(ctx):
    _team(ctx, carol="claude")
    _edit(ctx, carol={"capabilities": {"write": ["/tmp/carol", "work/"], "deny": ["~/Work"], "commands": ["git"]}})
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert s["defaultMode"] == "dontAsk"
    for rule in ("Edit(members/carol/**)", "Edit(//tmp/carol/**)", "Edit(work/**)", "Bash(git *)", "Bash(git)",
                 f"Bash({ctx.paths.xt_bin} *)", "Read", "Grep"):
        assert rule in s["allow"], rule
    for rule in ("Edit(team.toml)", "Edit(settings/**)", "Read(~/Work/**)", "Edit(~/Work/**)", "Bash(gh *)",
                 "Bash(aws)", "WebFetch", "WebSearch"):
        assert rule in s["deny"], rule
    assert "Bash" not in s["allow"]  # commands set: the shell runs only those


def test_186_credential_clis_are_denied_by_name_even_with_an_open_shell(ctx):
    _team(ctx, carol="claude")
    _edit(ctx, carol={"capabilities": {"network": "on", "credential_clis": {"allow": ["gh"], "deny": ["mytool"]}}})
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert "Bash" in s["allow"] and "WebFetch" in s["allow"]  # commands unset: not restricted
    assert "Bash(mytool *)" in s["deny"] and "Bash(aws *)" in s["deny"] and "Bash(gh *)" not in s["deny"]


def test_186_codex_gets_its_network_switch_and_the_write_paths_as_add_dir(ctx):
    _team(ctx, dana="codex")
    _edit(ctx, dana={"capabilities": {"network": "on", "write": ["/tmp/dana", "~/notes"]}})
    args = _start(ctx, "dana")
    assert args[args.index("sandbox_workspace_write.network_access=true") - 1] == "-c"
    home = str(__import__("pathlib").Path("~").expanduser())
    assert ["--add-dir", "/tmp/dana"] == args[args.index("--add-dir"):args.index("--add-dir") + 2]
    assert f"{home}/notes" in args and "--settings" not in args


def test_186_pi_starts_without_personal_skills_keeps_the_teams_and_loads_named_ones(ctx, fake_home):
    _team(ctx, erin="pi")
    (ctx.paths.skills / "board").mkdir(parents=True)
    (ctx.paths.skills / "board" / "SKILL.md").write_text("---\nname: board\ndescription: d\n---\n")
    (fake_home / ".agents" / "skills" / "silverbullet").mkdir(parents=True)
    _edit(ctx, erin={"capabilities": {"skills": ["silverbullet"]}})
    args = _start(ctx, "erin")
    assert args[args.index("--no-skills"):] == ["--no-skills", "--skill", str(ctx.paths.skills / "board"),
                                                "--skill", str(fake_home / ".agents" / "skills" / "silverbullet")]


def test_186_a_named_skill_pi_cant_find_or_claude_cant_load_is_refused(ctx):
    _team(ctx, erin="pi", carol="claude")
    _edit(ctx, erin={"capabilities": {"skills": ["nothere"]}}, carol={"capabilities": {"skills": ["x"]}})
    with pytest.raises(XtError, match="skill 'nothere' isn't a personal skill pi can load"):
        _start(ctx, "erin")
    with pytest.raises(XtError, match="claude can't load single personal skills"):
        _start(ctx, "carol")


def test_186_the_liaisons_generated_settings_keep_the_prompt_hook(ctx):
    request_spawn(ctx, "human", "lead", None, None, None, None)
    for a in ctx.team.doc["agent"]:
        if a["name"] == "liaison":
            a["harness"] = "claude"
    _edit(ctx, {"network": "off"})
    s = _settings(_start(ctx, "liaison"))
    assert s["permissions"]["defaultMode"] == "dontAsk" and "Bash(gh *)" in s["permissions"]["deny"]
    assert "pane-input --hook" in json.dumps(s["hooks"])


# --- require refuses, nothing stored -----------------------------------------------------------------


def test_186_require_refuses_at_start_naming_the_harness_and_the_alternative_storing_nothing(ctx):
    _team(ctx, erin="pi")
    _edit(ctx, erin={"capabilities": {"commands": ["git"], "require": ["commands"]}})
    created, versions_before = list(ctx.herdr.created), (ctx.paths.state / "versions.json").read_text()
    with pytest.raises(XtError) as e:
        _start(ctx, "erin")
    assert str(e.value) == ("erin can't start: commands is marked require, and pi can only keep it advisory "
                            "(role text only). Drop require on commands, or hire erin under claude")
    assert ctx.herdr.created == created and "erin" not in ctx.herdr.live
    assert (ctx.paths.state / "versions.json").read_text() == versions_before
    expected = ctx.paths.state / "expected.json"
    assert "erin" not in (json.loads(expected.read_text()) if expected.exists() else [])


def test_186_require_refuses_a_hire_before_any_approval_or_team_change(ctx):
    _team(ctx)
    _edit(ctx, {"network": "off", "require": ["network"]})
    before = ctx.paths.team_toml.read_text()
    with pytest.raises(XtError, match="frank can't start: network is marked require, and pi can only keep it "
                                      "advisory .* hire frank under codex"):
        request_spawn(ctx, "lead", "frank", "pi", None, "worker", None)
    assert Approvals(ctx).pending() == {} and ctx.paths.team_toml.read_text() == before


# --- precedence: legacy lines and extras only restrict -------------------------------------------------


def _extras(ctx, name, perms: dict):
    (ctx.paths.root / "settings").mkdir(exist_ok=True)
    (ctx.paths.root / "settings" / f"{name}.json").write_text(json.dumps({"permissions": perms}))


def test_186_the_legacy_file_adds_restrictions_on_top_of_the_team_default_block(ctx):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"deny": ["Bash(rm *)"], "allow": ["Edit(members/carol/notes.md)", "Read(//tmp/**)"]})
    _edit(ctx, {"commands": ["git"]}, carol={"permissions": "settings/carol.json"})
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert "Bash(rm *)" in s["deny"] and "Bash(git *)" in s["allow"] and s["defaultMode"] == "dontAsk"


@pytest.mark.parametrize("perms, message", [
    ({"allow": ["Bash(curl *)"]}, r"allow rule 'Bash\(curl \*\)' is outside what the \[capabilities\] block allows"),
    ({"allow": ["WebFetch"]}, r"allow rule 'WebFetch' would loosen the \[capabilities\] block, which denies 'WebFetch'"),
    ({"defaultMode": "bypassPermissions"}, r"permissions.defaultMode 'bypassPermissions' would loosen"),
])
def test_186_an_extras_rule_that_loosens_the_block_is_refused_naming_both(ctx, perms, message):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", perms)
    _edit(ctx, {"commands": ["git"]}, carol={"permissions": "settings/carol.json"})
    with pytest.raises(XtError, match=r"settings/carol.json: " + message):
        _start(ctx, "carol")


def test_186_legacy_connectors_and_codex_network_may_only_restrict(ctx):
    _team(ctx, carol="claude", dana="codex")
    _edit(ctx, {"network": "on"}, carol={"connectors": ["mail"]},
          dana={"codex_options": ["sandbox_workspace_write.network_access=false"]})
    with pytest.raises(XtError, match=r"carol: `connectors = \['mail'\]` would loosen the \[capabilities\] block"):
        _start(ctx, "carol")
    args = _start(ctx, "dana")
    assert "sandbox_workspace_write.network_access=false" in args  # the legacy line restricts: kept
    _edit(ctx, {"network": "off"}, dana={"codex_options": ["sandbox_workspace_write.network_access=true"]})
    from xt.spawn import stop

    stop(ctx, "dana")
    with pytest.raises(XtError, match=r"would loosen the \[capabilities\] block \(network = \"off\"\)"):
        _start(ctx, "dana")


# --- legacy-only agents start as before (only skills and the display change) --------------------------


def test_186_legacy_only_agents_start_with_their_own_lines_unchanged(ctx):
    _team(ctx, carol="claude", dana="codex")
    _extras(ctx, "carol", {"allow": ["Bash(curl *)"], "defaultMode": "dontAsk"})
    _edit(ctx, carol={"permissions": "settings/carol.json"},
          dana={"codex_options": ["sandbox_workspace_write.network_access=true"]})
    args = _start(ctx, "carol")
    assert args[args.index("--settings") + 1] == str(ctx.paths.root / "settings" / "carol.json")  # as before
    dargs = _start(ctx, "dana")
    assert "sandbox_workspace_write.network_access=true" in dargs and "--add-dir" not in dargs


# --- display: status row, start note, spawn sentence ---------------------------------------------------


def test_186_advisory_is_visible_in_status_the_start_note_and_the_approval(ctx, monkeypatch, capsys):
    _team(ctx, dana="codex")
    assert _row(_status(ctx, monkeypatch, capsys), "dana") is None  # never started: no row
    _start(ctx, "dana")
    assert _row(_status(ctx, monkeypatch, capsys), "dana") == "    caps: write, deny, skills, credential_clis advisory"
    started = [m for m in ctx.ledger.messages() if m["body"].startswith("started dana")][-1]["body"]
    assert started.splitlines()[1] == "capabilities: write, deny, skills, credential_clis advisory"
    request_spawn(ctx, "lead", "frank", "pi", None, "worker", None)
    body = [m for m in ctx.ledger.messages() if m["type"] == "approval"][-1]["body"]
    assert ("Approve its start: write, deny, network, credential_clis advisory (role text only)."
            in body.splitlines())


def test_186_a_mixed_set_is_never_enforced_as_a_whole(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _edit(ctx, carol={"capabilities": {"write": ["/tmp/c"], "commands": ["git"], "require": ["write"]}})
    _start(ctx, "carol")
    row = _row(_status(ctx, monkeypatch, capsys), "carol")
    assert row == "    caps: require write; commands enforced; network advisory"


def test_186_a_claude_agent_without_any_file_shows_its_rules_as_advisory_and_a_legacy_file_isnt_judged(ctx):
    _team(ctx, carol="claude", ben="claude")
    _extras(ctx, "ben", {"allow": ["Read"]})
    _edit(ctx, ben={"permissions": "settings/ben.json"})
    ad = load_adapters(ctx.paths)["claude"]
    c = capstart.status_row
    _start(ctx, "carol")
    _start(ctx, "ben")
    assert c(ctx, ctx.team.agent("carol"), ad) == "caps: write, deny, network, credential_clis advisory"
    # the full form (72 columns) doesn't fit, so shorter words; the start note keeps the full one
    assert c(ctx, ctx.team.agent("ben"), ad) == "caps: net advisory; legacy settings/ben.json, deprecated"
    note = [m for m in ctx.ledger.messages() if m["body"].startswith("started ben")][-1]["body"]
    assert note.endswith("capabilities: network advisory; legacy settings/ben.json (deprecated: xt capabilities ben)")


def test_186_rows_fit_80_columns_with_4_spare_and_the_sentence_two_rows(paths):
    ad = load_adapters(paths)
    worst = Caps(write=["/w"], deny=["~/Work"], commands=["git"], network="on", connectors=["mail"],
                 credential_clis=["aws"], require=["write", "commands", "credential_clis"], configured=True)
    cases = [(worst, "claude", []), (Caps(), "codex", ["codex_options"]), (Caps(), "pi", []),
             (Caps(write=["/w"], commands=["git"], configured=True), "pi", [])]
    for caps, h, legacy in cases:
        line = capstart.INDENT + "caps: " + capstart.row(caps, ad[h], legacy, "release-mgr1", capstart.STATUS_WIDTH,
                                                       was_loaded=h == "pi")
        assert len(line) <= 76 and "…" not in line, line
        assert len(textwrap.wrap(capstart.spawn_sentence(caps, ad[h]), 80)) <= 2
    long = capstart.row(worst, ad["claude"], [], "x", 40)
    assert "cmds" in long  # shorter words first


# --- old records and the pi skills mark -------------------------------------------------------------


def test_186_an_old_start_record_reads_and_pi_says_once_that_skills_were_loaded(ctx, monkeypatch, capsys):
    _team(ctx, erin="pi")
    vpath = ctx.paths.state / "versions.json"
    data = json.loads(vpath.read_text()) if vpath.exists() else {}
    data.setdefault("agents", {})["erin"] = {"version": "0.22.1", "since": "2026-09-26T11:00:00+00:00"}
    vpath.write_text(json.dumps(data))  # started by 0.22.1: no capabilities in its record
    assert capstart.status_row(ctx, ctx.team.agent("erin"), load_adapters(ctx.paths)["pi"]).startswith("caps: ")
    _start(ctx, "erin")
    assert _row(_status(ctx, monkeypatch, capsys), "erin").endswith("skills: none, was loaded")
    note = [m for m in ctx.ledger.messages() if m["body"].startswith("started erin")][-1]["body"]
    assert note.endswith("skills: none, was loaded")
    from xt.spawn import stop

    stop(ctx, "erin")
    _start(ctx, "erin")  # its record now has the model: said once
    assert "was loaded" not in _row(_status(ctx, monkeypatch, capsys), "erin")


def _snapshot(root) -> dict:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*"))
            if p.is_file() and "home" not in p.relative_to(root).parts}


def test_186_xt_capabilities_prints_the_equivalent_block_and_changes_nothing(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {
        "defaultMode": "dontAsk",
        "allow": ["Read", f"Bash({ctx.paths.xt_bin} *)", "Bash(git *)", "Bash(sed -n *)", "Bash(gh *)",
                  "Edit(//home/me/work/**)", "Edit(members/carol/**)", "WebFetch", "mcp__claude_ai_Gmail"],
        "deny": ["Edit(team.toml)", "Edit(settings/**)", "Edit(roles/**)", "Read(//home/me/Work/usb/**)",
                 "Bash(rm *)"],
        "ask": ["Bash(git push *)"]})
    _edit(ctx, carol={"permissions": "settings/carol.json", "connectors": ["claude.ai Gmail"]})
    before = _snapshot(ctx.paths.root)
    monkeypatch.setattr(cli, "find_root", lambda: ctx.paths.root)
    args = cli.build_parser().parse_args(["capabilities", "carol"])
    args.func(args)
    out = capsys.readouterr().out
    assert _snapshot(ctx.paths.root) == before  # nothing changed: team files and state
    assert out.splitlines()[:3] == [
        "# xt capabilities carol: the block equivalent to its legacy lines and settings/carol.json (nothing was changed).",
        '# Under its [[agent]] entry (name = "carol"), replacing `permissions` and `connectors`:',
        "[agent.capabilities]"]
    body = tomlkit.parse("\n".join(x for x in out.splitlines() if not x.startswith("#") and x != "[agent.capabilities]"))
    assert body["write"] == ["/home/me/work"] and body["commands"] == ["git", "sed -n"]
    assert body["deny"] == ["roles", "/home/me/Work/usb"] and body["network"] == "on"
    assert body["credential_clis"] == {"allow": ["gh"]} and body["connectors"] == ["claude.ai Gmail"]
    kept = out.split("# kept in extras", 1)[1]
    for k in ("allow mcp__claude_ai_Gmail", "deny Bash(rm *)", "ask Bash(git push *)"):
        assert k in kept


def test_186_xt_harnesses_lists_the_support_table(ctx, monkeypatch, capsys):
    monkeypatch.setattr(cli, "find_root", lambda: ctx.paths.root)
    args = cli.build_parser().parse_args(["harnesses"])
    args.func(args)
    out = capsys.readouterr().out
    assert ("   capabilities: connectors, skills enforced; write, deny, commands, network, credential_clis "
            "advisory (checked: pi 1.0.2 (operator check 2026-10-04: --help))") in out.splitlines()


def test_186_status_brief_and_the_tui_show_the_same_row(ctx, monkeypatch, capsys):
    from xt import brief
    from xt.tui.model import build

    _team(ctx, carol="claude")
    _edit(ctx, carol={"capabilities": {"write": ["/tmp/c"], "commands": ["git"], "require": ["write"]}})
    _start(ctx, "carol")
    row = "caps: require write; commands enforced; network advisory"
    assert _row(_status(ctx, monkeypatch, capsys), "carol") == "    " + row
    lines = brief.build(ctx, "lead").splitlines()
    assert lines[lines.index(next(x for x in lines if x.startswith("- carol "))) + 1] == "  " + row
    team = {r.data["name"]: r for r in build(ctx).panels["Team"] if r.data and r.data.get("name")}
    assert row in team["carol"].detail().plain.splitlines()
    note = [m for m in ctx.ledger.messages() if m["body"].startswith("started carol")][-1]["body"]
    assert note.splitlines()[1].startswith("capabilities: require write; commands enforced; network advisory")


def test_186_the_guide_section_has_the_vocabulary_a_require_example_and_the_conversion():
    guide = " ".join((REPO / "docs" / "user-guide.md").read_text().split())
    for phrase in ("**Capabilities: one model for every harness** (from 0.23.0)", "[defaults.capabilities]",
                   "`erin can't start: commands is marked require, and pi can only keep it advisory (role text "
                   "only). Drop require on commands, or hire erin under claude`",
                   "`xt capabilities <name>` prints the block equivalent",
                   "That was always true; it is now visible.",
                   "An agent with only these lines, or none, gets two changes from 0.23.0 and nothing else",
                   "`caps: require write, cmds; deny, creds enforced; net advisory`"):
        assert phrase in guide, phrase
    for name in NAMES:
        assert f"{name} = " in guide or f"`{name}`" in guide, name


def test_186_the_examples_conversion_is_what_xt_prints(ctx, monkeypatch, capsys):
    from .test_batch_0150 import _blocks

    examples = (REPO / "docs/examples.md").read_text()
    (settings,) = [b for b in _blocks(examples, "json") if '"defaultMode"' in b]
    _extras(ctx, "researcher", {})
    (ctx.paths.root / "settings" / "researcher.json").write_text(settings)
    _team(ctx, researcher="claude")
    _edit(ctx, researcher={"permissions": "settings/researcher.json"})
    monkeypatch.setattr(cli, "find_root", lambda: ctx.paths.root)
    args = cli.build_parser().parse_args(["capabilities", "researcher"])
    args.func(args)
    (doc,) = [b for b in _blocks(examples, "text") if "xt capabilities researcher" in b]
    assert capsys.readouterr().out.strip() == doc.strip()


# --- the conversion round-trips (QA on rc6, #3610) ----------------------------------------------------


def _convert(ctx, monkeypatch, capsys, name) -> str:
    monkeypatch.setattr(cli, "find_root", lambda: ctx.paths.root)  # xt capabilities loads team.toml itself
    args = cli.build_parser().parse_args(["capabilities", name])
    args.func(args)
    return capsys.readouterr().out


def _apply(ctx, name, out: str):
    """Do what the output says: its block under the agent, the legacy lines removed."""
    parsed = tomlkit.parse("\n".join(x for x in out.splitlines() if not x.startswith("#")
                                     and x != "[agent.capabilities]") + "\n")
    block = tomlkit.table()
    for k, v in parsed.items():
        block[k] = v
    for a in ctx.team.doc["agent"]:
        if a["name"] == name:
            for k in ("permissions", "codex_options", "connectors"):
                if k in a:
                    del a[k]
            a["capabilities"] = block
    ctx.paths.team_toml.write_text(tomlkit.dumps(ctx.team.doc))
    ctx.reload_team()  # loads: not mixing


def test_186_qas_case_the_unrepresentable_deny_survives_the_conversion(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Bash(git *)"], "deny": ["Bash(rm *)"]})
    _edit(ctx, carol={"permissions": "settings/carol.json"})
    out = _convert(ctx, monkeypatch, capsys, "carol")
    assert 'extras = "settings/carol.json"' in out and 'commands = ["git"]' in out
    _apply(ctx, "carol", out)
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert "Bash(rm *)" in s["deny"] and "Bash(git *)" in s["allow"] and "Bash" not in s["allow"]


def test_186_the_printed_text_pasted_as_is_under_the_agent_loads_and_starts(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")  # carol is the last [[agent]] entry
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Bash(git *)"], "deny": ["Bash(rm *)"]})
    _edit(ctx, carol={"permissions": "settings/carol.json"})
    out = _convert(ctx, monkeypatch, capsys, "carol")
    text = ctx.paths.team_toml.read_text().replace('permissions = "settings/carol.json"\n', "")
    ctx.paths.team_toml.write_text(text.rstrip("\n") + "\n" + out)  # comments, header and all
    ctx.reload_team()
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert "Bash(rm *)" in s["deny"] and "Bash(git *)" in s["allow"]


def test_186_where_nothing_is_lost_there_are_no_extras(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Bash(git *)", "Edit(//tmp/carol/**)", "Read"],
                           "deny": ["Edit(team.toml)", "WebFetch", "Bash(gh *)"]})
    _edit(ctx, carol={"permissions": "settings/carol.json"})
    out = _convert(ctx, monkeypatch, capsys, "carol")
    assert "extras" not in out and "kept in extras" not in out
    _apply(ctx, "carol", out)
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert "Edit(//tmp/carol/**)" in s["allow"] and "Bash(gh *)" in s["deny"]


def test_186_a_realistic_settings_file_round_trips_and_starts(ctx, monkeypatch, capsys):
    """Shaped like this team's builder file: xt in three spellings, :* and space forms, absolute and
    relative paths, a denied skill folder, web tools denied, other tools allowed."""
    _team(ctx, builder="claude")
    xt = str(ctx.paths.xt_bin)
    _extras(ctx, "builder", {
        "defaultMode": "dontAsk",
        "allow": [f"Bash({xt} *)", "Bash(./bin/xt *)", "Bash(bin/xt *)", "Bash(rg *)", "Bash(sed -n *)",
                  "Bash(git:*)", "Bash(uv run *)", "Edit(//home/me/work/**)", "Edit(members/builder/**)",
                  "Edit(//tmp/xt-**)", "Read(//home/me/**)", "Read", "Glob", "Grep", "TodoWrite", "Task"],
        "deny": ["Bash(rm *)", "Bash(git push *)", "Edit(settings/**)", "Edit(team.toml)", "Edit(roles/**)",
                 "Edit(//home/me/Work/**)", "Read(//home/me/.agents/skills/fizzy/**)", "WebFetch", "WebSearch"]})
    _edit(ctx, builder={"permissions": "settings/builder.json"})
    out = _convert(ctx, monkeypatch, capsys, "builder")
    assert "would loosen" not in out
    _apply(ctx, "builder", out)
    s = _settings(_start(ctx, "builder"))["permissions"]
    for rule in ("Bash(rg *)", "Bash(sed -n *)", "Bash(git *)", "Bash(uv run *)", "Edit(//home/me/work/**)",
                 "Task", f"Bash({xt} *)"):
        assert rule in s["allow"], rule
    for rule in ("Bash(rm *)", "Bash(git push *)", "Edit(roles/**)", "Edit(//home/me/Work/**)",
                 "Read(//home/me/.agents/skills/fizzy/**)", "WebFetch"):
        assert rule in s["deny"], rule


def test_186_what_would_loosen_is_named_and_the_start_says_so(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "acceptEdits", "allow": ["Bash(git *)"]})
    _edit(ctx, carol={"permissions": "settings/carol.json"})
    out = _convert(ctx, monkeypatch, capsys, "carol")
    assert "# would loosen the block, so the start refuses them until they are removed from settings/carol.json:" in out
    assert "#   defaultMode acceptEdits (the block's settings use dontAsk)" in out
    _apply(ctx, "carol", out)
    with pytest.raises(XtError, match="permissions.defaultMode 'acceptEdits' would loosen"):
        _start(ctx, "carol")


def test_186_codex_network_and_claude_connectors_round_trip(ctx, monkeypatch, capsys):
    from xt import adapters

    monkeypatch.setattr(adapters, "claude_mcp_servers", lambda *a, **k: ["claude.ai Gmail", "claude.ai Drive"])
    _team(ctx, carol="claude", dana="codex")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["mcp__claude_ai_Gmail__search"]})
    _edit(ctx, carol={"permissions": "settings/carol.json", "connectors": ["claude.ai Gmail"]},
          dana={"codex_options": ["sandbox_workspace_write.network_access=true"]})
    for name in ("carol", "dana"):
        _apply(ctx, name, _convert(ctx, monkeypatch, capsys, name))
    s = _settings(_start(ctx, "carol"))["permissions"]
    assert "mcp__claude_ai_Gmail" in s["allow"] and "mcp__claude_ai_Gmail__search" in s["allow"]
    assert "sandbox_workspace_write.network_access=true" in _start(ctx, "dana")


def test_186_extras_is_claude_only_and_not_mixing(ctx):
    _team(ctx, carol="claude", dana="codex")
    _extras(ctx, "carol", {"deny": ["Bash(rm *)"]})
    _edit(ctx, carol={"capabilities": {"extras": "settings/carol.json"}},
          dana={"capabilities": {"extras": "settings/carol.json"}})  # loads: extras isn't a legacy line
    assert "Bash(rm *)" in _settings(_start(ctx, "carol"))["permissions"]["deny"]
    with pytest.raises(XtError, match="dana: extras = 'settings/carol.json' is a Claude Code settings file, and codex takes none"):
        _start(ctx, "dana")


# --- live round on rc8 (members/operator/live-v0230-rc8.md) ------------------------------------------


def test_186_c_a_codex_agent_with_a_block_runs_in_the_workspace_write_sandbox(ctx):
    _team(ctx, dana="codex")
    _edit(ctx, dana={"capabilities": {"write": ["/tmp/dana"]}})
    args = _start(ctx, "dana")
    i = args.index("-s")
    assert args[i + 1] == "workspace-write" and i < args.index("--add-dir")  # else codex exits 1 on --add-dir
    assert "sandbox_workspace_write.network_access=false" in args


def _allowed(command: str, allow: list[str], deny: list[str]) -> bool:
    """An approximation of Claude Code's Bash prefix rules: the first line (a heredoc's text is
    stdin), split on && ; | into commands, each matched by `Bash(X *)` / `Bash(X)`, deny first."""
    first = command.splitlines()[0].split("<<")[0]
    parts = [p.strip() for p in first.replace("&&", ";").replace("|", ";").split(";") if p.strip()]

    def match(p, rules):
        for r in rules:
            if not r.startswith("Bash("):
                continue
            spec = r[5:-1]
            if spec.endswith(" *") and (p == spec[:-2] or p.startswith(spec[:-1])):
                return True
            if p == spec:
                return True
        return "Bash" in rules

    return all(not match(p, deny) and match(p, allow) for p in parts)


def test_186_b_the_protocols_xt_forms_pass_the_generated_rules(ctx):
    _team(ctx, carol="claude")
    _edit(ctx, carol={"capabilities": {"commands": ["echo"]}})
    s = _settings(_start(ctx, "carol"))["permissions"]
    xt, root = str(ctx.paths.xt_bin), str(ctx.paths.root)
    forms = [
        f"{xt} send lead --as carol --type report --ref 3 <<'XT_END'\nThe report, as the reply hint writes it.\nXT_END",
        f"{xt} done 3 --as carol <<'XT_END'\nDone: results in members/carol/out.md\nXT_END",
        f"{xt} answer 7 --as carol <<'XT_END'\nyes\nXT_END",
        f"{xt} note --as carol <<'XT_END'\na decision\nXT_END",
        f"cd {root} && {xt} send lead --as carol --type report <<'XT_END'\ntext\nXT_END",
        f"cd {root} && bin/xt brief --as carol",
        "./bin/xt log --member carol --limit 5",
        "xt brief --as carol",
    ]
    for form in forms:
        assert _allowed(form, s["allow"], s["deny"]), form
    assert not _allowed("date && rm -rf /tmp/x", s["allow"], s["deny"])  # the rest of the shell stays closed
    assert not _allowed("cd /tmp && gh auth status", s["allow"], s["deny"])


def test_186_a_status_and_the_start_note_say_claudes_built_in_commands_run_anyway(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude", dana="codex")
    _edit(ctx, carol={"capabilities": {"commands": ["git"]}}, dana={"capabilities": {"commands": ["git"]}})
    _start(ctx, "dana")
    assert capstart.BUILTIN_NOTE not in _status(ctx, monkeypatch, capsys)  # codex: commands is advisory anyway
    _start(ctx, "carol")
    out = _status(ctx, monkeypatch, capsys)
    assert out.count(capstart.BUILTIN_NOTE) == 1 and len(capstart.BUILTIN_NOTE) <= 76
    note = [m for m in ctx.ledger.messages() if m["body"].startswith("started carol")][-1]["body"]
    assert note.endswith(capstart.BUILTIN_NOTE)
    guide = " ".join((REPO / "docs" / "user-guide.md").read_text().split())
    assert "beyond Claude Code's own built-in read-only commands" in guide


# --- ux's walk of rc6 (members/ux/walk-v0230-rc6.md) -------------------------------------------------


def test_186_the_tuis_approval_detail_and_s_dialog_show_the_capability_sentence(ctx):
    import asyncio

    from xt.tui.app import DetailBody, LiveActions, XtTui, YesNo
    from xt.tui.model import build

    _team(ctx)
    request_spawn(ctx, "lead", "zoe", "codex", None, "worker", None)
    sentence = "Approve its start: write, deny, skills, credential_clis advisory (role text only)."
    seen = {}

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("1")
            await pilot.pause()
            assert app.panel(1).current.data["id"] == next(int(k) for k in Approvals(ctx).pending())
            await pilot.press("enter")
            await pilot.pause()
            seen["detail"] = app.query_one(DetailBody).content.plain
            app.panel(1).focus()
            await pilot.press("s")
            await pilot.pause()
            seen["dialog"] = app.screen.question if isinstance(app.screen, YesNo) else None

    asyncio.run(run())
    assert sentence in seen["detail"].splitlines()  # beside the settings note, before a / d
    assert seen["dialog"] is not None and sentence in seen["dialog"].splitlines()


def test_186_xt_capabilities_runs_while_mixing_is_refused(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Bash(git *)"]})
    for a in ctx.team.doc["agent"]:
        if a["name"] == "carol":
            a["permissions"] = "settings/carol.json"
            a["capabilities"] = {"network": "on"}
    ctx.paths.team_toml.write_text(tomlkit.dumps(ctx.team.doc))
    with pytest.raises(XtError, match="`xt capabilities carol` prints the block"):
        ctx.reload_team()  # every other command refuses
    out = _convert(ctx, monkeypatch, capsys, "carol")  # the way out it names works
    assert 'commands = ["git"]' in out and "replacing `permissions`:" in out


def test_186_an_agent_without_old_lines_gets_no_dangling_replacing(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    out = _convert(ctx, monkeypatch, capsys, "carol")
    assert out.splitlines()[1] == '# Under its [[agent]] entry (name = "carol"):'
    assert "# (the defaults: nothing to set)" in out


def test_186_the_tui_detail_folds_the_old_lines_into_the_full_row(ctx):
    from xt.tui.model import build

    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Read"]})
    _edit(ctx, carol={"permissions": "settings/carol.json"})
    team = lambda: {r.data["name"]: r for r in build(ctx).panels["Team"] if r.data and r.data.get("name")}
    assert "settings file: settings/carol.json" in team()["carol"].detail().plain  # never started: as before
    _start(ctx, "carol")
    detail = team()["carol"].detail().plain
    assert "caps: network advisory; legacy settings/carol.json (deprecated: xt capabilities carol)" in detail
    assert "settings file:" not in detail  # said once, in the row


def test_186_connectors_per_harness_are_pinned_statically(ctx, monkeypatch):
    """Radek's decision (#3674): connectors are checked statically, not by a live probe. Claude: the
    named connectors allowed, every other server refused; Codex: apps off as a whole, a named list
    refused; pi: nothing to switch off, a named list refused."""
    from xt import adapters
    from xt.spawn import stop

    monkeypatch.setattr(adapters, "claude_mcp_servers", lambda *a, **k: ["claude.ai Gmail", "claude.ai Drive"])
    _team(ctx, carol="claude", dana="codex", erin="pi")
    _edit(ctx, {"network": "off"})
    args = _start(ctx, "carol")
    assert "--strict-mcp-config" in args and not any(a.startswith("mcp__") for a in _settings(args)["permissions"]["allow"])
    stop(ctx, "carol")
    _edit(ctx, carol={"capabilities": {"connectors": ["claude.ai Gmail"]}})
    args = _start(ctx, "carol")
    assert "--strict-mcp-config" not in args
    assert args[args.index("--disallowedTools") + 1:].count("mcp__claude_ai_Drive") == 1  # the unlisted one refused
    allow = _settings(args)["permissions"]["allow"]
    assert "mcp__claude_ai_Gmail" in allow and "mcp__claude_ai_Drive" not in allow
    dargs = _start(ctx, "dana")
    assert dargs[dargs.index("features.apps=false") - 1] == "-c"  # all or nothing: off
    stop(ctx, "dana")
    _edit(ctx, dana={"capabilities": {"connectors": ["claude.ai Gmail"]}})
    with pytest.raises(XtError, match="harness codex can't expose single account connectors"):
        _start(ctx, "dana")
    eargs = _start(ctx, "erin")
    assert not any("mcp" in a or "apps" in a for a in eargs)  # pi has none to switch off
    stop(ctx, "erin")
    _edit(ctx, erin={"capabilities": {"connectors": ["claude.ai Gmail"]}})
    with pytest.raises(XtError, match="harness pi can't expose single account connectors"):
        _start(ctx, "erin")


def test_186_the_harness_files_parse_and_keep_their_other_keys(paths):
    ad = load_adapters(paths)
    assert ad["claude"].settings_flag == "--settings" and ad["claude"].context_windows
    assert ad["codex"].startup_dialogs and ad["pi"].first_prompt_note
    assert (REPO / "harnesses" / "pi.toml").read_text().rstrip().endswith('credential_clis = "advisory"')
