"""v0.15.0: spawn with a permissions file (#122), recent messages by default in xt log (#113)."""

import json
import tomllib

import pytest

from xt import cli, permissions
from xt.paths import XtError
from xt.spawn import Approvals, approval_what, decide, request_spawn, stop
from xt.tui.model import build

from .conftest import add_member

# --- #122 spawn with a permissions file ---------------------------------------------------------


GOOD = {"permissions": {"defaultMode": "dontAsk", "allow": ["Bash(cat *)"], "deny": ["WebFetch"]}}


def _settings(ctx, rel="settings/carol.json", data=GOOD):
    f = ctx.paths.root / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(data if isinstance(data, str) else json.dumps(data))
    return f


def _coder(ctx):
    ctx.herdr.add("lead")
    (ctx.paths.roles / "coder.md").write_text("# Role: coder\n")


def _approval(ctx):
    rid, req = next(iter(Approvals(ctx).pending().items()))
    body = next(m["body"] for m in ctx.ledger.messages() if m["id"] == int(rid))
    return int(rid), req, body


def _entry(ctx, name):
    doc = tomllib.loads(ctx.paths.team_toml.read_text())
    return next(a for a in doc["agent"] if a["name"] == name)


def test_a_lead_spawn_with_permissions_writes_the_line_and_notes_the_hash(ctx):
    _coder(ctx)
    f = _settings(ctx)
    out = request_spawn(ctx, "lead", "carol", "claude", None, "coder", None, "settings/carol.json")
    assert "approval #" in out
    rid, req, body = _approval(ctx)
    assert "Settings: settings/carol.json (permissions.defaultMode dontAsk)." in body
    assert "WARNING" not in body
    assert "settings/carol.json" in approval_what(req)
    decide(ctx, rid, approve=True)
    assert _entry(ctx, "carol")["permissions"] == "settings/carol.json"
    args = next(a for n, _, a in ctx.herdr.started if n == "carol")
    assert args[args.index("--settings") + 1] == str(f.resolve())
    digest = permissions.preflight(ctx.paths.root, "settings/carol.json").digest
    assert any(f"carol: Claude Code settings settings/carol.json (sha256 {digest}" in m["body"]
               for m in ctx.ledger.messages() if m["type"] == "system")


def test_a_claude_spawn_without_any_file_warns_in_the_approval(ctx):
    _coder(ctx)
    request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)
    rid, req, body = _approval(ctx)
    assert "WARNING: carol would start without a permissions file, so the operator's own claude defaults apply" in body
    assert "WARNING" in approval_what(req)
    row = next(r for r in build(ctx).panels["Inbox"] if r.key == f"approval:{rid}")
    assert "without a permissions file" in row.detail().plain


def test_the_team_default_applies_to_a_spawned_claude_agent_and_codex_skips_it(ctx):
    _coder(ctx)
    _settings(ctx, "settings/team.json")
    ctx.team.doc.setdefault("defaults", {})["permissions"] = "settings/team.json"
    ctx.team.save()
    ctx.reload_team()
    request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)
    _, _, body = _approval(ctx)
    assert "Settings: settings/team.json" in body and "WARNING" not in body
    decide(ctx, _approval(ctx)[0], approve=True)
    assert "permissions" not in _entry(ctx, "carol")  # the default stays a default
    assert "--settings" in next(a for n, _, a in ctx.herdr.started if n == "carol")
    request_spawn(ctx, "lead", "dora", "codex", None, "coder", None)
    _, _, body = _approval(ctx)
    assert "settings/team.json not applied (codex takes no settings file)" in body


@pytest.mark.parametrize("rel, content, why", [
    ("settings/none.json", None, "no such file"),
    ("settings/bad.json", '{"permissions": {', "not valid JSON"),
    ("settings/mode.json", {"permissions": {"defaultMode": "nonsense"}}, "unknown permissions.defaultMode"),
    ("../outside.json", None, "`..` isn't allowed"),
])
def test_a_bad_file_refuses_the_request_before_any_approval(ctx, rel, content, why):
    _coder(ctx)
    if content is not None:
        _settings(ctx, rel, content)
    with pytest.raises(XtError, match=why):
        request_spawn(ctx, "lead", "carol", "claude", None, "coder", None, rel)
    assert not Approvals(ctx).pending()
    assert not any(m["type"] == "approval" for m in ctx.ledger.messages())
    assert ctx.team.agent("carol") is None and not ctx.herdr.created


def test_a_codex_spawn_with_permissions_is_refused(ctx):
    _coder(ctx)
    _settings(ctx)
    with pytest.raises(XtError, match="takes no settings file"):
        request_spawn(ctx, "lead", "carol", "codex", None, "coder", None, "settings/carol.json")
    assert not Approvals(ctx).pending()


def test_spawning_over_an_existing_entry_keeps_its_line(ctx):
    _coder(ctx)
    add_member(ctx, "carol", role="coder")
    _settings(ctx, "settings/own.json")
    doc_agent = next(a for a in ctx.team.doc["agent"] if a["name"] == "carol")
    doc_agent["permissions"] = "settings/own.json"
    ctx.team.save()
    ctx.reload_team()
    request_spawn(ctx, "lead", "carol", "claude", None, "coder", None)  # new harness/role, no flag
    rid, _, body = _approval(ctx)
    assert "Settings: settings/own.json" in body
    decide(ctx, rid, approve=True)
    assert _entry(ctx, "carol")["permissions"] == "settings/own.json"
    stop(ctx, "carol")
    request_spawn(ctx, "human", "carol", None, None, None, None)  # plain restart after a stop
    assert _entry(ctx, "carol")["permissions"] == "settings/own.json"


def test_the_cli_passes_the_flag(ctx, monkeypatch):
    _coder(ctx)
    _settings(ctx)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_spawn(cli.build_parser().parse_args(
        ["spawn", "carol", "--harness", "claude", "--role", "coder", "--permissions", "settings/carol.json",
         "--as", "lead"]))
    decide(ctx, _approval(ctx)[0], approve=True)
    assert _entry(ctx, "carol")["permissions"] == "settings/carol.json"


def test_the_shipped_lead_role_mentions_the_flag():
    from .conftest import REPO

    assert "--permissions" in (REPO / "roles/lead.md").read_text()


# --- #113 recent messages by default in xt log ---------------------------------------------------


def _log(ctx, monkeypatch, capsys, *argv):
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_log(cli.build_parser().parse_args(["log", *argv]))
    return capsys.readouterr().out


def _ids(out):
    return [int(line.split()[0][1:]) for line in out.splitlines() if line.startswith("#")]


def _fill(ctx, n):
    return [ctx.ledger.append("lead", "carol" if i % 2 else "dora", "report" if i % 3 else "task", f"m{i}")["id"]
            for i in range(n)]


def test_plain_log_prints_the_newest_20_oldest_first_with_the_omitted_count(ctx, monkeypatch, capsys):
    ids = _fill(ctx, 30)
    out = _log(ctx, monkeypatch, capsys)
    assert _ids(out) == ids[-20:]
    assert out.splitlines()[0] == "(10 older messages not shown; `--limit N` for more, `--full` for all)"


def test_a_short_history_prints_everything_without_the_line(ctx, monkeypatch, capsys):
    ids = _fill(ctx, 5)
    out = _log(ctx, monkeypatch, capsys)
    assert _ids(out) == ids and "not shown" not in out


def test_limit_and_full(ctx, monkeypatch, capsys):
    ids = _fill(ctx, 30)
    out = _log(ctx, monkeypatch, capsys, "--limit", "3")
    assert _ids(out) == ids[-3:] and "(27 older messages not shown" in out
    out = _log(ctx, monkeypatch, capsys, "--full")
    assert _ids(out) == ids and "not shown" not in out
    with pytest.raises(XtError, match="1 or more"):
        _log(ctx, monkeypatch, capsys, "--limit", "0")


def test_filters_apply_before_the_limit(ctx, monkeypatch, capsys):
    msgs = [ctx.ledger.append("lead", "carol" if i % 2 else "dora", "report" if i % 3 else "task", f"m{i}")
            for i in range(60)]
    carol = [m["id"] for m in msgs if m["to"] == "carol"]
    out = _log(ctx, monkeypatch, capsys, "--member", "carol")
    assert _ids(out) == carol[-20:] and f"({len(carol) - 20} older messages" in out
    tasks = [m["id"] for m in msgs if m["type"] == "task"]
    out = _log(ctx, monkeypatch, capsys, "--type", "task", "--limit", "5")
    assert _ids(out) == tasks[-5:]
    carol_reports = [m["id"] for m in msgs if m["to"] == "carol" and m["type"] == "report"]
    out = _log(ctx, monkeypatch, capsys, "--member", "carol", "--type", "report", "--limit", "4")
    assert _ids(out) == carol_reports[-4:]


def test_id_still_prints_the_whole_thread(ctx, monkeypatch, capsys):
    goal = ctx.ledger.append("liaison", "lead", "goal", "the goal")["id"]
    replies = [ctx.ledger.append("lead", "carol", "task", f"t{i}", ref=goal)["id"] for i in range(25)]
    _fill(ctx, 30)
    out = _log(ctx, monkeypatch, capsys, "--id", str(goal))
    assert _ids(out) == [goal, *replies] and "not shown" not in out
    out = _log(ctx, monkeypatch, capsys, "--id", str(goal), "--limit", "2")
    assert _ids(out) == replies[-2:]


def test_watch_keeps_its_own_default(ctx, monkeypatch, capsys):
    from xt.watch import Supervisor

    sup = Supervisor(ctx, out=lambda s: None)
    for i in range(60):
        sup.say(f"event {i}")
    out = _log(ctx, monkeypatch, capsys, "--watch")
    assert "event 10" in out and "event 9\n" not in out and len(out.splitlines()) == 50
    out = _log(ctx, monkeypatch, capsys, "--watch", "--limit", "5")
    assert len(out.splitlines()) == 5
