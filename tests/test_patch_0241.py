"""v0.24.1: #225 (the converted block passes its own extras check, and the check runs at load);
#226 (xt init writes a default capability block)."""

import fnmatch
import shutil

import pytest
import tomlkit

from xt import capstart, init
from xt.adapters import load_adapters
from xt.capabilities import CREDENTIAL_CLIS, effective
from xt.context import Ctx
from xt.ledger import Ledger
from xt.paths import Paths, XtError
from xt.spawn import request_spawn
from xt.team import Team

from .conftest import REPO, FakeHerdr

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


def _repo(root):
    """xt's own files, as a fresh clone has them, and no team.toml yet."""
    root.mkdir(parents=True, exist_ok=True)
    for name in ("protocol.md", "roles", "harnesses"):
        src = REPO / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, root / name)
    return Paths(root)


def test_226_xt_init_on_an_empty_directory_writes_the_default_block(tmp_path, monkeypatch):
    monkeypatch.setattr(init, "prerequisites", lambda paths: ([], []))
    paths = _repo(tmp_path)
    init.init(paths, "t", "t", "claude", "codex", True, yes=True, commit=False)
    text = paths.team_toml.read_text()
    block = ('[defaults.capabilities]\n'
             'write = [".", "/tmp/xt-**"]    # the team repo (relative to it) and xt\'s temporary files\n'
             'credential_clis = []            # gh, aws, gcloud, op, fizzy and so on stay refused by name\n'
             '# network: advisory under Claude Code, as always; commands: not restricted\n')
    assert block in text and text.count("[defaults.capabilities]") == 1
    above = text.split(block)[0].rstrip().splitlines()[-4:]
    assert above[0].startswith("# What every agent may do without asking") and "Change it here" in " ".join(above)
    team = Team.load(paths.team_toml)  # loads, with no warning
    assert team.doc["defaults"]["capabilities"].unwrap() == {"write": [".", "/tmp/xt-**"], "credential_clis": []}
    caps = effective(team, team.agent("liaison"))
    assert caps.configured and caps.write == [".", "/tmp/xt-**"] and caps.commands is None
    assert caps.network == "off" and caps.credential_clis == list(CREDENTIAL_CLIS)  # all still refused


def test_226_xt_init_never_rewrites_an_existing_team_toml(tmp_path, monkeypatch):
    monkeypatch.setattr(init, "prerequisites", lambda paths: ([], []))
    paths = _repo(tmp_path)
    init.init(paths, "t", "t", "claude", "codex", True, yes=True, commit=False)
    once = paths.team_toml.read_bytes()
    out = init.init(paths, "t", "t", "claude", "codex", True, yes=True, commit=False)
    assert paths.team_toml.read_bytes() == once and out[0].startswith("already initialised")
    custom = once.replace(b'write = [".", "/tmp/xt-**"]', b'write = ["/srv/mine"]\ncommands = ["rg"]')
    paths.team_toml.write_bytes(custom)
    init.init(paths, "t", "t", "claude", "codex", True, yes=True, commit=False)
    assert paths.team_toml.read_bytes() == custom  # a block of any content stays byte for byte


def _ctx_at(root, clock, cwds: list) -> Ctx:
    herdr = FakeHerdr()
    create = herdr.create_workspace
    herdr.create_workspace = lambda cwd, label: (cwds.append(cwd), create(cwd, label))[1]
    return Ctx(Paths(root), Team.load(root / "team.toml"), Ledger(Paths(root), clock=clock), herdr)


def test_226_the_team_repo_resolves_relative_to_the_repo_after_a_move(tmp_path, clock):
    """`.` resolves at each start: Claude agents start in the repo (the rule is `Edit(./**)`), Codex
    gets the repo's absolute path; moved or cloned, the block stays valid."""
    first = _repo(tmp_path / "team").root
    (first / "skills").mkdir()
    from xt.team import new_team_doc

    (first / "team.toml").write_text(new_team_doc("t", "t", {"harness": "claude"}, {"harness": "codex"}, True))
    for root in (first, tmp_path / "moved"):
        if root != first:
            shutil.move(first, root)
        cwds: list = []
        ctx = _ctx_at(root, clock, cwds)
        request_spawn(ctx, "human", "liaison", None, None, None, None)
        request_spawn(ctx, "human", "lead", None, None, None, None)
        started = {n: args for n, _, args in ctx.herdr.started}
        assert cwds == [str(root), str(root)]
        settings = _settings(started["liaison"])["permissions"]
        assert "Edit(./**)" in settings["allow"] and "Edit(//tmp/xt-**)" in settings["allow"]
        assert "Edit(team.toml)" in settings["deny"] and "Bash" in settings["allow"]  # commands not restricted
        assert "Bash(gh *)" in settings["deny"] and "WebFetch" in settings["deny"]
        args = started["lead"]
        assert args[args.index("--add-dir") + 1] == str(root) and "/tmp/xt-**" not in args


def test_226_status_shows_the_liaisons_caps_row(ctx, monkeypatch, capsys):
    from .test_caps_start_0230 import _row, _status

    ctx.team.doc["agent"][1]["harness"] = "claude"  # liaison
    ctx.team.save()
    ctx.reload_team()
    request_spawn(ctx, "human", "liaison", None, None, None, None)
    assert _row(_status(ctx, monkeypatch, capsys), "liaison") == "    caps: write enforced; network advisory"


def test_226_the_guide_and_readme_show_the_block_xt_init_writes():
    from xt.team import new_team_doc

    written = new_team_doc("t", "t", {"harness": "claude"}, {"harness": "codex"}, True)
    block = written.split("[defaults.capabilities]\n", 1)[1].split("\n\n", 1)[0]
    guide = (REPO / "docs/user-guide.md").read_text()
    assert f"```toml\n[defaults.capabilities]\n{block}\n```" in guide
    assert "**An agent without a block.** A team made by `xt init` 0.24.1 or later has the block above" in guide
    readme = " ".join((REPO / "README.md").read_text().split())
    assert "`xt init` writes a `[defaults.capabilities]` block into `team.toml`" in readme


def test_225_the_load_check_skips_other_harnesses_and_leaves_a_missing_file_to_the_start(ctx):
    _team(ctx, carol="claude", dana="codex")
    _extras(ctx, "dana", {"allow": ["Bash(curl *)"]})  # codex takes no settings file: its start says so
    _edit(ctx, carol={"capabilities": {"commands": ["rg"], "extras": "settings/nowhere.json"}},
          dana={"capabilities": {"commands": ["rg"], "extras": "settings/dana.json"}})  # loads
    with pytest.raises(XtError, match="no such file in the team repo"):
        _start(ctx, "carol")
