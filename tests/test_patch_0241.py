"""v0.24.1: #225 (the converted block passes its own extras check, and the check runs at load)."""

import fnmatch

import pytest
import tomlkit

from xt import capstart
from xt.adapters import load_adapters
from xt.paths import XtError

from .test_caps_start_0230 import _apply, _convert, _edit, _extras, _old, _settings, _start, _team

# --- #225: narrow credential-CLI rules keep their scope -------------------------------------------------

NARROW = ["Bash(rg *)", "Bash(fizzy card show *)", "Bash(fizzy comment create:*)", "Bash(gh release view *)",
          "Bash(gh api repos/OWNER/REPO/*)"]


def _body(out: str) -> dict:
    return tomlkit.parse("\n".join(x for x in out.splitlines() if not x.startswith("#")
                                   and x != "[agent.capabilities]")).unwrap()


def _allowed(perms: dict, command: str) -> bool:
    """Claude Code's reading of a Bash rule, for these tests: `*` matches anything; deny wins; under
    dontAsk a command no allow rule matches is refused."""
    def hits(rules):
        return any(r == "Bash" or (r.startswith("Bash(") and fnmatch.fnmatchcase(command, r[5:-1])) for r in rules)

    return perms["defaultMode"] == "dontAsk" and hits(perms["allow"]) and not hits(perms["deny"])


def test_225_narrow_fizzy_and_gh_rules_go_into_commands_and_pass_capstart_plan(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": NARROW, "deny": ["Bash(rm *)"]})
    _old(ctx, carol={"permissions": "settings/carol.json"})
    out = _convert(ctx, monkeypatch, capsys, "carol")
    body = _body(out)
    assert body["commands"] == ["rg", "fizzy card show", "fizzy comment create", "gh release view",
                                "gh api repos/OWNER/REPO/*"]
    assert not {"fizzy", "gh", "gh api"} & set(body["commands"])
    assert body["credential_clis"] == {"allow": ["fizzy", "gh"]}  # names only, never subcommands
    assert body["extras"] == "settings/carol.json" and "would loosen" not in out
    _apply(ctx, "carol", out)  # loads: the load-time check passes
    adapters = load_adapters(ctx.paths)
    plan = capstart.plan(ctx, ctx.team.agent("carol"), adapters["claude"], adapters)  # generated + merge_extras
    assert plan.generated and plan.settings.rel == "settings/carol.json"


def test_225_a_path_scoped_gh_api_rule_stays_path_scoped(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": NARROW, "deny": ["Bash(rm *)"]})
    _old(ctx, carol={"permissions": "settings/carol.json"})
    _apply(ctx, "carol", _convert(ctx, monkeypatch, capsys, "carol"))
    perms = _settings(_start(ctx, "carol"))["permissions"]
    for ok in ("gh api repos/OWNER/REPO/releases", "gh release view v1", "fizzy card show 225",
               "fizzy comment create --card 225 --body x", "rg foo"):
        assert _allowed(perms, ok), ok
    for refused in ("gh api repos/OTHER/REPO/issues", "gh api user", "gh api", "gh auth token", "gh",
                    "fizzy card close 225", "fizzy", "curl https://example.org"):
        assert not _allowed(perms, refused), refused


def test_225_a_rule_commands_cant_hold_at_its_scope_is_named_not_widened(ctx, monkeypatch, capsys):
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Bash(rg *)", "Bash(gh auth status)"]})
    _old(ctx, carol={"permissions": "settings/carol.json"})
    out = _convert(ctx, monkeypatch, capsys, "carol")
    body = _body(out)
    assert body["commands"] == ["rg"] and "credential_clis" not in body
    assert "# would loosen the block" in out
    assert "#   allow Bash(gh auth status) (commands would allow `gh auth status` with any arguments" in out


def test_225_a_converted_team_with_a_rule_outside_the_block_fails_to_load(ctx):
    """The 0.24.0 conversion of the xt-team's lead: the CLI allowed by name, the subcommand left out."""
    _team(ctx, carol="claude")
    _extras(ctx, "carol", {"defaultMode": "dontAsk", "allow": ["Bash(rg *)", "Bash(fizzy card show *)"]})
    with pytest.raises(XtError) as e:
        _edit(ctx, carol={"capabilities": {"commands": ["rg"], "credential_clis": {"allow": ["fizzy"]},
                                           "extras": "settings/carol.json"}})
    assert str(e.value) == ("agent carol: settings/carol.json: allow rule 'Bash(fizzy card show *)' is outside "
                            "what the [capabilities] block allows; add it to the block (write, commands, "
                            "network, connectors) or remove it from settings/carol.json")
    assert "carol" not in [n for n, _, _ in ctx.herdr.started]


PM_LIKE = {"defaultMode": "dontAsk",  # shaped like the xt-team's settings/pm.json before 0.24 (#3932)
           "allow": ["Edit(goals/drafts/**)", "Bash(rg *)", "Bash(git log *)", "Bash(fizzy card show *)",
                     "Bash(fizzy comment create *)"],
           "deny": ["Edit(roles/**)", "Edit(skills/**)", "Edit(members/builder/**)", "Edit(//home/me/Work/**)",
                    "Read(//home/me/Work/usb/**)", "Edit(//home/me/Work/usb/**)", "Edit(team.toml)", "Bash(rm *)"]}


def test_225_edit_only_denials_stay_in_extras_so_the_agent_still_reads_them(ctx, monkeypatch, capsys):
    _team(ctx, pm="claude")
    _extras(ctx, "pm", PM_LIKE)
    _old(ctx, pm={"permissions": "settings/pm.json"})
    out = _convert(ctx, monkeypatch, capsys, "pm")
    body = _body(out)
    assert body["deny"] == ["/home/me/Work/usb"]  # only the Read denial; its Edit twin is covered by it
    kept = out.split("# kept in extras", 1)[1]
    for k in ("deny Edit(roles/**)", "deny Edit(skills/**)", "deny Edit(members/builder/**)",
              "deny Edit(//home/me/Work/**)"):
        assert k in kept, k
    assert "Edit(//home/me/Work/usb/**)" not in out and "Edit(team.toml)" not in out
    _apply(ctx, "pm", out)
    perms = _settings(_start(ctx, "pm"))["permissions"]
    assert "Read" in perms["allow"]
    for path in ("roles/**", "skills/**", "members/builder/**", "//home/me/Work/**"):
        assert f"Edit({path})" in perms["deny"], path  # editing stays refused
        assert f"Read({path})" not in perms["deny"], path  # reading is not
    assert "Read(//home/me/Work/usb/**)" in perms["deny"]


def test_225_the_load_check_skips_other_harnesses_and_leaves_a_missing_file_to_the_start(ctx):
    _team(ctx, carol="claude", dana="codex")
    _extras(ctx, "dana", {"allow": ["Bash(curl *)"]})  # codex takes no settings file: its start says so
    _edit(ctx, carol={"capabilities": {"commands": ["rg"], "extras": "settings/nowhere.json"}},
          dana={"capabilities": {"commands": ["rg"], "extras": "settings/dana.json"}})  # loads
    with pytest.raises(XtError, match="no such file in the team repo"):
        _start(ctx, "carol")
