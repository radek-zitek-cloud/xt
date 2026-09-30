"""v0.15.0: spawn with a permissions file (#122), recent messages by default in xt log (#113),
Claude plan usage in status (#120), liaison goal writes in the protocol (#105), telling the human
when a goal is done (#125)."""

import asyncio
import datetime as dt
import io
import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

import pytest

from xt import cli, goaldone, permissions, planusage, turns
from xt.paths import XtError
from xt.spawn import Approvals, approval_what, decide, request_spawn, stop
from xt.tui.app import LiveActions, XtTui
from xt.tui.model import build
from xt.watch import Supervisor

from .conftest import REPO, add_member

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


# --- #120 Claude plan usage in status -----------------------------------------------------------


SAMPLE = json.loads((REPO / "tests/fixtures/claude-2.1.284-statusline.json").read_text())["payload"]
SEEN = 1790714000  # shortly after the sample was taken; both windows still open
FIRST_CALL = {k: v for k, v in SAMPLE.items() if k != "rate_limits"}  # a session's first call


def _feed(ctx, payload, now, env=None):
    return planusage.main(json.dumps(payload) if not isinstance(payload, str) else payload,
                          env if env is not None else {"XT_ROOT": str(ctx.paths.root)}, Path("/nowhere"), now)


def _snap(ctx):
    return json.loads(planusage.snapshot_path(ctx.paths.root).read_text())


@pytest.fixture
def state(ctx):
    ctx.paths.ensure_runtime()
    return ctx


def test_the_real_payload_is_parsed_and_only_the_windows_are_stored(state):
    ctx = state
    assert planusage.parse(SAMPLE) == {"five_hour": {"used_percentage": 5.0, "resets_at": 1790728200},
                                       "seven_day": {"used_percentage": 7.0, "resets_at": 1791280800}}
    printed = _feed(ctx, SAMPLE, SEEN)
    assert printed == "Sonnet 5.5 · 5h 5% · 7d 7%"
    raw = planusage.snapshot_path(ctx.paths.root).read_text()
    assert _snap(ctx) == {"five_hour": {"used_percentage": 5.0, "resets_at": 1790728200, "observed_at": SEEN},
                          "seven_day": {"used_percentage": 7.0, "resets_at": 1791280800, "observed_at": SEEN}}
    for secret in ("session", "cost", "transcript", "cwd", "0.0547", "Sonnet"):
        assert secret not in raw
    line = planusage.line(ctx.paths.root, SEEN + 120)
    assert line.startswith("claude 5% of 5h, resets ") and "; 7% of 7d, resets " in line
    assert line.endswith("; read 2m ago (account-wide)")


def test_a_first_call_without_rate_limits_keeps_the_last_reading(state):
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    before = planusage.snapshot_path(ctx.paths.root).read_bytes()
    assert _feed(ctx, FIRST_CALL, SEEN + 600) == "Sonnet 5.5"
    assert planusage.snapshot_path(ctx.paths.root).read_bytes() == before
    assert "5% of 5h" in planusage.line(ctx.paths.root, SEEN + 900) and "read 15m ago" in planusage.line(ctx.paths.root, SEEN + 900)


def test_a_payload_with_one_window_keeps_the_other_windows_reading(state):
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    _feed(ctx, {"rate_limits": {"five_hour": {"used_percentage": 9, "resets_at": 1790728200}}}, SEEN + 60)
    snap = _snap(ctx)
    assert snap["five_hour"]["used_percentage"] == 9 and snap["five_hour"]["observed_at"] == SEEN + 60
    assert snap["seven_day"]["observed_at"] == SEEN


def test_a_passed_reset_shows_window_reset_not_the_old_percentage(state):
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    after = 1790728200 + 60  # the five-hour window has reset, the week hasn't
    line = planusage.line(ctx.paths.root, after)
    assert "5h window reset, no reading since" in line and "5% of 5h" not in line
    assert "7% of 7d" not in line  # the reading is older than the stale limit by then
    fresh_week = {"rate_limits": {"seven_day": {"used_percentage": 8, "resets_at": 1791280800}}}
    _feed(ctx, fresh_week, after)
    line = planusage.line(ctx.paths.root, after + 60)
    assert "5h window reset, no reading since" in line and "8% of 7d" in line and "read 1m ago" in line


def test_stale_absent_and_malformed_snapshots_show_unknown(state):
    ctx = state
    assert planusage.line(ctx.paths.root, SEEN) == "claude 5h unknown; 7d unknown (account-wide)"
    _feed(ctx, SAMPLE, SEEN)
    stale = planusage.line(ctx.paths.root, SEEN + planusage.STALE_SECONDS + 60)
    assert "5h unknown (last reading 3h 01m ago)" in stale and "%" not in stale and "; read" not in stale
    planusage.snapshot_path(ctx.paths.root).write_text("{not json")
    assert planusage.line(ctx.paths.root, SEEN) == "claude 5h unknown; 7d unknown (account-wide)"
    planusage.snapshot_path(ctx.paths.root).write_text(json.dumps({"five_hour": {"used_percentage": "5%"}}))
    assert planusage.line(ctx.paths.root, SEEN) == "claude 5h unknown; 7d unknown (account-wide)"


BAD_VALUES = [10**20, 10**400, -5, 0, float("nan"), float("inf"), float("-inf"), "1790728200", True, None,
              [1790728200], {"v": 1}]


@pytest.mark.parametrize("field", ["resets_at", "observed_at", "used_percentage"])
@pytest.mark.parametrize("bad", BAD_VALUES, ids=repr)
def test_malformed_snapshot_numbers_show_unknown_and_status_still_works(state, monkeypatch, capsys, field, bad):
    """QA's rc2 FAIL on #120: resets_at = 10**20 raised OverflowError and broke status."""
    ctx = state
    add_member(ctx, "carol")
    good = {"used_percentage": 42, "resets_at": 1790728200, "observed_at": SEEN}
    if field == "used_percentage" and bad in (0,):
        bad = 100.5  # 0% is a real reading; over 100% isn't
    raw = {"five_hour": {**good, field: bad}, "seven_day": {**good, "resets_at": 1791280800}}
    planusage.snapshot_path(ctx.paths.root).write_text(json.dumps(raw))  # NaN/Infinity as JSON allows
    line = planusage.line(ctx.paths.root, SEEN + 60)
    assert line.startswith("claude 5h unknown; 42% of 7d, resets ") and line.endswith("; read 1m ago (account-wide)")
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    out = capsys.readouterr().out
    assert "allowance: claude 5h unknown" in out and "carol" in out  # the rest of status is there
    assert "claude account 5h unknown" in build(ctx).usage


@pytest.mark.parametrize("bad", BAD_VALUES + [101], ids=repr)
def test_malformed_payload_numbers_are_never_stored(state, bad):
    ctx = state
    for field in ("used_percentage", "resets_at"):
        if field == "used_percentage" and bad == 0:
            continue  # 0% is a real reading
        payload = {"rate_limits": {"five_hour": {"used_percentage": 5, "resets_at": 1790728200, field: bad}}}
        assert planusage.parse(payload) == {}
        assert _feed(ctx, json.dumps(payload), SEEN) == "xt"
        assert not planusage.snapshot_path(ctx.paths.root).exists()


@pytest.mark.parametrize("ahead", [1, 30, 3600])
def test_a_reading_timestamped_after_now_shows_unknown(state, ahead):
    """QA on rc4: rc4 tolerated 60 s; no reading later than now is valid (same machine)."""
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    line = planusage.line(ctx.paths.root, SEEN - ahead)
    assert line == "claude 5h unknown; 7d unknown (account-wide)"
    assert "5% of 5h" in planusage.line(ctx.paths.root, SEEN)  # at the same second it's valid


def test_a_broken_file_shows_unknown(state):
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    planusage.snapshot_path(ctx.paths.root).write_text("[" * 100000 + "]" * 100000)  # too deep for json
    assert planusage.line(ctx.paths.root, SEEN) == "claude 5h unknown; 7d unknown (account-wide)"


@pytest.mark.parametrize("stdin", ["", "not json", "[]", '{"rate_limits": "x"}',
                                   '{"rate_limits": {"five_hour": {"used_percentage": true, "resets_at": 1}}}'])
def test_bad_input_prints_a_line_and_leaves_the_snapshot_alone(state, stdin):
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    before = planusage.snapshot_path(ctx.paths.root).read_bytes()
    assert _feed(ctx, stdin, SEEN + 60) == "xt"
    assert planusage.snapshot_path(ctx.paths.root).read_bytes() == before


def test_snapshot_writes_are_atomic(state, monkeypatch):
    ctx = state
    _feed(ctx, SAMPLE, SEEN)
    before = planusage.snapshot_path(ctx.paths.root).read_bytes()

    def crash(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(planusage.os, "replace", crash)
    assert _feed(ctx, SAMPLE, SEEN + 60) == "xt"  # the status line survives the failure
    assert planusage.snapshot_path(ctx.paths.root).read_bytes() == before
    assert [p.name for p in ctx.paths.state.iterdir() if "claude_plan" in p.name] == ["claude_plan.json"]


def test_the_team_root_is_xt_root_else_the_scripts_own_checkout(state, tmp_path):
    ctx = state
    assert planusage.root({"XT_ROOT": str(ctx.paths.root)}, tmp_path) == ctx.paths.root
    assert planusage.root({}, ctx.paths.root) == ctx.paths.root
    _feed(ctx, SAMPLE, SEEN, env={})  # no XT_ROOT: the script's checkout, here one without state
    assert not planusage.snapshot_path(ctx.paths.root).exists()
    assert not (Path("/nowhere") / ".xt").exists()
    _feed(ctx, SAMPLE, SEEN, env={"XT_ROOT": str(tmp_path / "no-team")})  # never makes a state dir
    assert not (tmp_path / "no-team").exists()


def test_the_shipped_script_runs_with_plain_python_from_xt_owned_bin(state):
    ctx = state
    script = REPO / "bin/xt-statusline"
    env = {**os.environ, "XT_ROOT": str(ctx.paths.root)}
    ok = subprocess.run([sys.executable, str(script)], input=json.dumps(SAMPLE), env=env,
                        capture_output=True, text=True, timeout=30)
    assert ok.returncode == 0 and ok.stdout.strip() == "Sonnet 5.5 · 5h 5% · 7d 7%" and not ok.stderr
    assert _snap(ctx)["five_hour"]["used_percentage"] == 5.0
    bad = subprocess.run([sys.executable, str(script)], input="garbage", env=env,
                         capture_output=True, text=True, timeout=30)
    assert bad.returncode == 0 and bad.stdout.strip() == "xt"


def test_status_and_tui_show_the_claude_windows(state, monkeypatch, capsys):
    ctx = state
    assert not any(line.startswith("claude") for line in turns.allowance_lines(ctx))  # codex-only team, no reading
    add_member(ctx, "carol")  # a claude agent
    assert "claude 5h unknown; 7d unknown (account-wide)" in turns.allowance_lines(ctx)
    now = time.time()
    _feed(ctx, {"rate_limits": {"five_hour": {"used_percentage": 42, "resets_at": int(now) + 3600},
                                "seven_day": {"used_percentage": 11, "resets_at": int(now) + 86400}}}, now)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    out = capsys.readouterr().out
    assert "allowance: claude 42% of 5h, resets " in out and "11% of 7d" in out and "read just now" in out
    assert "team " in out  # the rest of status is there
    usage = build(ctx).usage
    assert "claude account 42% of 5h" in usage and "11% of the week" in usage
    planusage.snapshot_path(ctx.paths.root).write_text("garbage")
    assert "claude account 5h unknown; 7d unknown" in build(ctx).usage


def test_the_guide_documents_the_status_line_setting():
    guide = (REPO / "docs/user-guide.md").read_text()
    assert "xt-statusline" in guide and '"statusLine"' in guide and "account-wide" in guide


# --- #105 liaison goal writes in the protocol ----------------------------------------------------


def test_protocol_section_6_permits_the_liaisons_goal_writes_and_nothing_else():
    protocol = (REPO / "protocol.md").read_text()
    s6 = protocol[protocol.index("## 6."):protocol.index("## 7.")]
    flat = " ".join(s6.split())
    assert "(liaison only) goals" in flat and "xt goal new" in flat and "xt goal dispatch" in flat
    assert "The liaison writes nothing else in the repo besides its notes." in flat
    liaison = " ".join((REPO / "roles/liaison.md").read_text().split())
    assert "xt goal dispatch` writes the final `goals/<slug>.md`) and your own notes" in liaison


# --- #125 tell the human when a goal is done -----------------------------------------------------


def _local(h, m=0):
    return time.mktime(dt.datetime(2026, 9, 27, h, m).timetuple())


def _sup(ctx):
    sup = Supervisor(ctx, out=lambda s: None)
    sup.notify_human(_local(12))  # first run: counting starts here
    return sup


def _goal(ctx, sender="liaison", to="lead", title="Write the weekly digest"):
    return ctx.ledger.append(sender, to, "goal", f"{title}\n\nMore detail.")["id"]


def _done(ctx, goal, owner="lead", to="liaison", body="Digest published at /digest\nwith notes"):
    return ctx.ledger.append(owner, to, "done", body, ref=goal)["id"]


def _titles(notifications):
    return [argv[2] for argv in notifications]


def test_the_liaisons_report_is_the_goals_one_notification(ctx, notifications):
    sup = _sup(ctx)
    goal = _goal(ctx)
    _done(ctx, goal)
    sup.notify_human(_local(12, 1))
    assert notifications == []  # waiting for the liaison's report
    ctx.ledger.append("liaison", "human", "report", "The digest is out: /digest", ref=goal)
    sup.notify_human(_local(12, 2))
    assert _titles(notifications) == [f"xt t: goal #{goal} done"]
    assert notifications[0][3] == "The digest is out: /digest"
    sup.notify_human(_local(12, 30))  # no fallback after the report
    ctx.ledger.append("liaison", "human", "report", "Also: a typo fixed", ref=goal)  # same ref again
    sup.notify_human(_local(12, 31))
    assert len(notifications) == 1


def test_a_report_referring_to_the_leads_done_counts_too(ctx, notifications):
    sup = _sup(ctx)
    goal = _goal(ctx)
    done = _done(ctx, goal)
    ctx.ledger.append("liaison", "human", "report", "Done: the digest", ref=done)
    sup.notify_human(_local(12, 1))
    sup.notify_human(_local(12, 20))
    assert _titles(notifications) == [f"xt t: goal #{goal} done"]


def test_without_a_report_the_supervisor_notifies_after_the_wait_once(ctx, notifications):
    sup = _sup(ctx)
    goal = _goal(ctx)
    _done(ctx, goal)
    sup.notify_human(_local(12, 1))
    sup.notify_human(_local(12, 1) + goaldone.FALLBACK_SECONDS - 10)
    assert notifications == []
    sup.notify_human(_local(12, 1) + goaldone.FALLBACK_SECONDS)
    assert _titles(notifications) == [f"xt t: goal #{goal} done"]
    assert notifications[0][3] == "Digest published at /digest"  # the closing summary's first line
    ctx.ledger.append("liaison", "human", "report", "late report", ref=goal)
    sup.notify_human(_local(12, 20))
    assert len(notifications) == 1


def test_tasks_and_goals_the_liaison_didnt_open_never_notify(ctx, notifications):
    sup = _sup(ctx)
    task = ctx.ledger.append("lead", "carol", "task", "a task")["id"]
    ctx.ledger.append("carol", "lead", "done", "task done", ref=task)
    sub = _goal(ctx, sender="lead", to="sublead", title="a sub-goal")
    _done(ctx, sub, owner="sublead", to="lead")
    human_goal = _goal(ctx, sender="human", title="dispatched by the human directly")
    _done(ctx, human_goal, to="human")
    ctx.ledger.append("carol", "human", "friction", "a sandbox refused something")
    sup.notify_human(_local(12, 1))
    sup.notify_human(_local(13))
    assert notifications == []


def test_progress_on_an_open_goal_never_notifies_the_goal_notifies_once_when_done(ctx, notifications):
    """QA's rc3 FAIL on #125: one notification per goal, when it's done."""
    sup = _sup(ctx)
    goal = _goal(ctx)
    ctx.ledger.append("liaison", "human", "report", "Progress: half done", ref=goal)
    ctx.ledger.append("liaison", "human", "report", "Progress again", ref=goal)
    sup.notify_human(_local(12, 1))
    assert notifications == []  # the goal is still open
    done = _done(ctx, goal)
    ctx.ledger.append("liaison", "human", "report", "Finished: the digest", ref=goal)
    ctx.ledger.append("liaison", "human", "report", "And one more thing about it", ref=done)
    sup.notify_human(_local(12, 2))
    sup.notify_human(_local(12, 30))  # no fallback either
    assert _titles(notifications) == [f"xt t: goal #{goal} done"]
    assert notifications[0][3] == "Finished: the digest"


def test_other_liaison_reports_notify_once_per_ref(ctx, notifications):
    sup = _sup(ctx)
    question = ctx.ledger.append("liaison", "human", "ask", "Which story?")["id"]
    ctx.ledger.append("liaison", "human", "report", "About that question: context", ref=question)
    ctx.ledger.append("liaison", "human", "report", "And more context", ref=question)
    ctx.ledger.append("liaison", "human", "report", "A note without a ref")
    ctx.ledger.append("lead", "liaison", "report", "not for the human")
    sup.notify_human(_local(12, 1))
    assert _titles(notifications) == ["xt t: question from liaison"] + ["xt t: report from liaison"] * 2


def test_quiet_hours_drop_the_goal_notification(ctx, notifications):
    sup = Supervisor(ctx, out=lambda s: None)
    sup.notify_human(_local(20))
    ctx.team.doc["notify"]["quiet"] = "21:00-07:00"
    goal = _goal(ctx)
    _done(ctx, goal)
    sup.notify_human(_local(22))
    sup.notify_human(_local(22, 30))  # the fallback falls due in quiet hours
    sup.notify_human(_local(8))
    assert notifications == []
    assert f"goal:{goal}" in goaldone.Notices(ctx).notified and not goaldone.Notices(ctx).pending


def _human_inbox(ctx, monkeypatch, capsys, human=True):
    class Tty(io.StringIO):
        def isatty(self):
            return human

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_inbox(cli.build_parser().parse_args(["inbox"]))
    out = capsys.readouterr().out
    # v0.16.0 (card #127): the section is "New since you last looked", left out when empty
    return out.split("New since you last looked:")[1].split("Friction")[0] if "New since" in out else "(none)"


def test_the_inbox_lists_goals_done_since_the_last_look_until_seen(ctx, monkeypatch, capsys):
    old = _goal(ctx, title="an old goal")
    _done(ctx, old)
    assert "(none)" in _human_inbox(ctx, monkeypatch, capsys)  # the first look starts from now
    goal = _goal(ctx)
    done = _done(ctx, goal)
    task = ctx.ledger.append("lead", "carol", "task", "a task")["id"]
    ctx.ledger.append("carol", "lead", "done", "task done", ref=task)
    section = _human_inbox(ctx, monkeypatch, capsys, human=False)  # an agent's look doesn't clear it
    assert f"#{goal} Write the weekly digest — done #{done}" in section and "Digest published" in section
    assert "task done" not in section and "an old goal" not in section
    section = _human_inbox(ctx, monkeypatch, capsys)
    assert f"#{goal} Write the weekly digest" in section
    assert "(none)" in _human_inbox(ctx, monkeypatch, capsys)  # seen now


def test_goals_done_before_the_first_inbox_look_are_listed_once_the_supervisor_ran(ctx, monkeypatch, capsys):
    _sup(ctx)
    goal = _goal(ctx)
    _done(ctx, goal)
    assert f"#{goal} Write the weekly digest" in _human_inbox(ctx, monkeypatch, capsys)


def test_the_tui_inbox_shows_done_goals_and_clears_them_after_a_look(ctx):
    ctx.paths.ensure_runtime()
    goaldone.seen_upto(ctx)
    goal = _goal(ctx)
    done = _done(ctx, goal)

    async def run():
        app = XtTui(lambda: build(ctx), LiveActions(ctx))
        async with app.run_test(size=(140, 45)) as pilot:
            await pilot.press("4")
            row = next(r for r in app.panel(4).rows if r.kind == "done")
            assert row.data == {"id": goal, "done": done}
            detail = row.detail().plain
            assert "Write the weekly digest" in detail and f"closing summary: #{done}" in detail
            assert "Digest published at /digest" in detail
            await pilot.press("1")  # leaving the Inbox: seen
            await pilot.pause()
            app.refresh_data()
            assert not any(r.kind == "done" for r in app.panel(4).rows)

    asyncio.run(run())
    assert goaldone.seen_upto(ctx) >= done


def _blocks(text: str, lang: str) -> list[str]:
    parts = text.split(f"```{lang}\n")[1:]
    return [p.split("```", 1)[0] for p in parts]


def test_the_examples_settings_file_passes_the_preflight_and_its_question_renders_as_shown(ctx):
    """#124: docs/examples.md's copyable settings file and decision question match what xt does."""
    from xt import choices

    examples = (REPO / "docs/examples.md").read_text()
    (settings,) = [b for b in _blocks(examples, "json") if '"defaultMode"' in b]
    f = ctx.paths.root / "settings/researcher.json"
    f.parent.mkdir()
    f.write_text(settings)
    assert permissions.preflight(ctx.paths.root, "settings/researcher.json").mode == "dontAsk"
    (toml_block,) = [b for b in _blocks(examples, "toml") if 'name = "researcher"' in b]
    assert tomllib.loads(toml_block)["agent"][0]["permissions"] == "settings/researcher.json"
    (shown,) = [b for b in _blocks(examples, "text") if "Options:" in b]
    rendered = choices.render("Should the weekly digest go out today or tomorrow?",
                              ["Publish the digest today :: readers get it on time; the last section is unreviewed",
                               "Publish tomorrow :: fully reviewed, one day late"], 2)
    assert rendered == shown.rstrip("\n")
    assert choices.resolve(rendered, "2")[0] == "Option 2: Publish tomorrow — fully reviewed, one day late"


def test_architecture_names_every_module_and_repo_doc_links_resolve():
    """#124: every source file is named in docs/architecture.md; relative links in the docs resolve."""
    import re

    arch = (REPO / "docs/architecture.md").read_text()
    for p in sorted((REPO / "src/xt").rglob("*")):
        if p.is_file() and p.suffix in (".py", ".tcss"):
            assert f"`{p.relative_to(REPO)}`" in arch, p
    for doc in ["README.md", "docs/architecture.md", "docs/examples.md", "docs/user-guide.md", "docs/story.md",
                "CHANGELOG.md"]:
        text = (REPO / doc).read_text()
        for target in re.findall(r"\]\(([^)\s]+)\)", text):
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path, _, anchor = target.partition("#")
            dest = (REPO / doc).parent / path if path else REPO / doc
            assert dest.exists(), f"{doc}: {target}"
            if anchor and dest.suffix == ".md":
                slugs = {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-")
                         for h in re.findall(r"^#+ (.+)$", dest.read_text(), re.M)}
                assert anchor in slugs, f"{doc}: {target}"


def test_the_liaison_role_sends_the_goal_done_summary_as_an_xt_report():
    liaison = " ".join((REPO / "roles/liaison.md").read_text().split())
    assert "as an xt report**, not only in your pane: `xt send human --as liaison --type report --ref <goal id>`" in liaison
