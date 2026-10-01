"""v0.18.0: a reset queued until the agent is idle (#134) and the automatic reset policy (#114)."""

import datetime as dt

import pytest

from xt import cli, reset
from xt.dispatch import send
from xt.paths import XtError
from xt.spawn import request_spawn, retire_now, stop
from xt.team import Team
from xt.usage import Reading
from xt.watch import Supervisor

from .conftest import add_member


def _running(ctx, name="carol"):
    add_member(ctx, name)
    request_spawn(ctx, "human", name, None, None, None, None)
    ctx.herdr.live[name].status = "idle"  # done with its first prompt
    return ctx.herdr.live[name].workspace_id


def _sup(ctx):
    lines = []
    sup = Supervisor(ctx, out=lines.append)
    sup.lines = lines
    return sup


def _system(ctx):
    return [m["body"] for m in ctx.ledger.messages() if m["type"] == "system"]


def _saves(ctx, clock, name="carol", summary="parser half done; see notes"):
    """The agent writes its notes, confirms the checkpoint and goes idle."""
    clock.advance(seconds=30)
    reset.record_checkpoint(ctx, name, summary)
    ctx.herdr.live[name].status = "idle"


# --- #134 -----------------------------------------------------------------------------------------


def test_a_queued_reset_of_a_working_agent_waits_then_runs_through_the_checkpoint(ctx, clock):
    ws = _running(ctx)
    ctx.herdr.live["carol"].status = "working"
    out = reset.queue(ctx, "carol")
    assert out.startswith("reset of carol queued")
    sup = _sup(ctx)
    sup.run_resets()
    assert ctx.herdr.prompts[-1][1].startswith("You are **carol**")  # only its first prompt so far
    assert "carol" in reset.queued(ctx)

    ctx.herdr.live["carol"].status = "idle"
    sup.run_resets()
    assert "[xt reset] The human is resetting your context" in ctx.herdr.last_prompt("carol")
    assert reset.queued(ctx)["carol"]["asked"]
    sup.run_resets()  # still saving: nothing more happens
    assert ctx.herdr.live["carol"].workspace_id == ws

    _saves(ctx, clock)
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id != ws  # a fresh session
    assert reset.queued(ctx) == {}
    done = _system(ctx)[-1]
    assert done.startswith("reset carol (queued by the human at 12:00): checkpoint of 12:00 saved")
    assert any(b.startswith("reset of carol queued by human") for b in _system(ctx))


def test_queueing_twice_reports_the_existing_reset(ctx):
    _running(ctx)
    reset.queue(ctx, "carol")
    again = reset.queue(ctx, "carol")
    assert again.startswith("carol: already reset queued (by human at 12:00)")
    assert len(reset.queued(ctx)) == 1


def test_a_queued_reset_survives_a_supervisor_restart(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    _sup(ctx).run_resets()  # asked for a checkpoint, then the supervisor stops
    _saves(ctx, clock)
    fresh = _sup(ctx)  # a new supervisor reads the queue from .xt/state/resets.json
    fresh.run_resets()
    assert ctx.herdr.live["carol"].workspace_id != ws
    assert reset.queued(ctx) == {}


def test_an_agent_with_open_work_is_never_reset(ctx, clock):
    ws = _running(ctx)
    task, _ = send(ctx, "lead", "carol", "task", "parse the file")
    ctx.herdr.live["carol"].status = "idle"
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    for _ in range(3):
        sup.run_resets()
    assert not any(t.startswith("[xt reset]") for _, t in ctx.herdr.prompts)
    assert ctx.herdr.live["carol"].workspace_id == ws and "carol" in reset.queued(ctx)


def test_work_arriving_while_it_saves_keeps_the_reset_queued(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    sup.run_resets()
    send(ctx, "lead", "carol", "task", "urgent")
    _saves(ctx, clock)
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id == ws  # not reset
    entry = reset.queued(ctx)["carol"]
    assert entry["asked"] is None  # back to waiting
    assert "queued reset of carol postponed: new work arrived while it was saving; it stays queued" in _system(ctx)


def test_after_the_checkpoint_a_working_agent_is_replaced_only_once_idle(ctx, clock):
    """rc1 QA (#2317): the post-checkpoint path must re-verify idle too."""
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    sup.run_resets()
    _saves(ctx, clock)
    ctx.herdr.live["carol"].status = "working"  # still finishing the turn in which it confirmed
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id == ws and reset.queued(ctx)["carol"]["asked"]
    ctx.herdr.live["carol"].status = "idle"
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id != ws


def test_after_the_checkpoint_a_pending_message_postpones_the_reset(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    reset.advance(ctx, ctx.herdr.agents(), set())
    _saves(ctx, clock)
    reset.advance(ctx, ctx.herdr.agents(), pending_to={"carol"})
    assert ctx.herdr.live["carol"].workspace_id == ws
    assert reset.queued(ctx)["carol"]["asked"] is None  # back to waiting; a fresh checkpoint later


def test_after_the_checkpoint_a_delivered_message_postpones_the_reset(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    sup.run_resets()
    _saves(ctx, clock)
    send(ctx, "lead", "carol", "report", "fyi: the parser spec changed")  # not open work, but new input
    ctx.herdr.live["carol"].status = "idle"  # even if it looks idle again by the next tick
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id == ws
    assert reset.queued(ctx)["carol"]["asked"] is None
    from xt.dispatch import drain

    drain(ctx)  # the supervisor delivers it; the agent works on it, then is idle again
    ctx.herdr.live["carol"].status = "idle"
    sup.run_resets()  # asks again, for a checkpoint that includes the new message
    assert reset.queued(ctx)["carol"]["asked"]
    _saves(ctx, clock, summary="saved again")
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id != ws


def test_after_the_checkpoint_a_still_busy_agent_is_dropped_at_the_time_limit(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    sup.run_resets()
    _saves(ctx, clock)
    ctx.herdr.live["carol"].status = "working"
    clock.advance(seconds=reset.CHECKPOINT_TIMEOUT)
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id == ws and reset.queued(ctx) == {}
    assert _system(ctx)[-1].startswith("queued reset of carol dropped: it was still busy 300 s after it was asked")


def test_messages_waiting_for_it_count_as_busy(ctx):
    _running(ctx)
    reset.queue(ctx, "carol")
    out = reset.advance(ctx, ctx.herdr.agents(), pending_to={"carol"})
    assert out == [] and reset.queued(ctx)["carol"]["asked"] is None


def test_no_checkpoint_in_time_drops_the_queued_reset_and_leaves_the_session(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    sup.run_resets()
    clock.advance(seconds=reset.CHECKPOINT_TIMEOUT + 1)
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id == ws and reset.queued(ctx) == {}
    assert _system(ctx)[-1].startswith("queued reset of carol dropped: no checkpoint within 300 s")


def test_cancel_removes_it_and_status_and_tui_show_and_clear_it(ctx, monkeypatch, capsys):
    _running(ctx)
    ctx.herdr.live["carol"].status = "working"
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    monkeypatch.setattr(cli, "controlling_terminal", lambda: True)

    def run(*argv):
        args = cli.build_parser().parse_args(list(argv))
        args.func(args)
        return capsys.readouterr().out

    out = run("reset", "carol", "--when-idle", "--as", "human")
    assert "reset of carol queued" in out
    assert "the supervisor isn't running: the queued reset waits for it" in out
    status = run("status")
    assert "reset queued (by human at 12:00): waits until it's idle with no open work" in status

    from xt.tui import model

    def detail():
        row = next(r for r in model.build(ctx).panels["Team"] if r.key == "agent:carol")
        d = row.detail()
        return getattr(d, "text", d).plain

    assert "reset queued (by human at 12:00)" in detail() and "xt reset carol --cancel" in detail()

    assert run("reset", "carol", "--cancel", "--as", "human").strip() == "queued reset of carol cancelled"
    assert "reset queued" not in run("status")
    assert "reset queued" not in detail()
    assert "queued reset of carol dropped: cancelled by the human" in _system(ctx)
    with pytest.raises(XtError, match="no reset of carol is queued"):
        run("reset", "carol", "--cancel", "--as", "human")


def test_only_the_human_queues_or_cancels_a_reset(ctx, monkeypatch):
    _running(ctx)
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    for flag in ("--when-idle", "--cancel"):
        args = cli.build_parser().parse_args(["reset", "carol", flag, "--as", "lead"])
        with pytest.raises(XtError, match="only the human resets"):
            args.func(args)
    with pytest.raises(SystemExit):  # one or the other
        cli.build_parser().parse_args(["reset", "carol", "--when-idle", "--cancel"])


def test_stopping_or_retiring_drops_the_queued_reset(ctx):
    _running(ctx, "carol")
    _running(ctx, "dave")
    reset.queue(ctx, "carol")
    reset.queue(ctx, "dave")
    stop(ctx, "carol")
    retire_now(ctx, "human", "dave")
    assert reset.queued(ctx) == {}
    assert "queued reset of carol dropped: carol was stopped" in _system(ctx)
    assert "queued reset of dave dropped: dave was retired" in _system(ctx)


def test_a_queued_reset_needs_a_running_active_agent(ctx):
    add_member(ctx, "carol")
    with pytest.raises(XtError, match="carol isn't running"):
        reset.queue(ctx, "carol")
    with pytest.raises(XtError, match="'human' is not an active agent"):
        reset.queue(ctx, "human")


def test_a_plain_reset_is_unchanged_and_replaces_a_queued_one(ctx):
    ws = _running(ctx)
    reset.queue(ctx, "carol")

    def agent_saves(_):
        reset.record_checkpoint(ctx, "carol", "all saved")

    out = reset.reset(ctx, "carol", timeout=10, sleep=agent_saves, clock=lambda: 0)
    assert out[0].startswith("reset carol: checkpoint")
    assert ctx.herdr.live["carol"].workspace_id != ws
    assert reset.queued(ctx) == {}
    assert "queued reset of carol dropped: a plain `xt reset` ran first" in _system(ctx)


def test_the_supervisor_tick_runs_queued_resets(ctx, clock):
    ws = _running(ctx)
    reset.queue(ctx, "carol")
    sup = _sup(ctx)
    sup.tick(now=1000.0)
    assert "[xt reset]" in ctx.herdr.last_prompt("carol")
    _saves(ctx, clock)
    sup.tick(now=1003.0)
    assert ctx.herdr.live["carol"].workspace_id != ws
    assert any(line.endswith("queued reset of carol: asked it for a checkpoint") for line in sup.lines)


# --- #114 -----------------------------------------------------------------------------------------


def _set(ctx, **settings):
    """Set [policy] keys in team.toml (replacing the template's lines)."""
    team = Team.load(ctx.paths.team_toml)
    for k, v in settings.items():
        team.doc["policy"][k] = v
    team.save()
    ctx.reload_team()


def _agent_threshold(ctx, name, value):
    team = Team.load(ctx.paths.team_toml)
    team._table(name)["auto_reset_tokens"] = value
    team.save()
    ctx.reload_team()


def _readings(monkeypatch, clock, **used):
    from xt import usage

    def fake(ctx, names):
        return {n: Reading(used=u, window=w, observed=(clock() - dt.timedelta(minutes=5)).isoformat(),
                           source="test log")
                for n, (u, w) in used.items() if n in names}

    monkeypatch.setattr(usage, "readings", fake)


def test_the_policy_is_off_by_default_and_nothing_changes(ctx, clock, monkeypatch):
    _running(ctx)
    _readings(monkeypatch, clock, carol=(900_000, 1_000_000))
    sup = _sup(ctx)
    sup.auto_reset()
    assert reset.queued(ctx) == {}
    assert ctx.team.policy("auto_reset") is False and ctx.team.policy("auto_reset_tokens") == 150_000
    assert ctx.team.policy("auto_reset_cooldown_hours") == 6


def test_the_threshold_is_a_token_count_whatever_the_window(ctx, clock, monkeypatch):
    for name in ("big", "small", "codex1", "codex2"):
        _running(ctx, name)
    _set(ctx, auto_reset=True)
    _readings(monkeypatch, clock, big=(160_000, 1_000_000), small=(140_000, 1_000_000),
              codex1=(160_000, 258_000), codex2=(140_000, 258_000))
    _sup(ctx).auto_reset()
    assert set(reset.queued(ctx)) == {"big", "codex1"}
    entry = reset.queued(ctx)["big"]
    assert entry["by"] == reset.POLICY
    assert entry["why"] == "context 160000 tokens, above the threshold of 150000 tokens; policy auto_reset"
    assert ("reset of big queued by xt's reset policy (context 160000 tokens, above the threshold of "
            "150000 tokens; policy auto_reset): the supervisor runs it when big is idle with no open work"
            in _system(ctx))


def test_policy_reset_runs_through_the_queued_flow_and_the_ledger_says_why(ctx, clock, monkeypatch):
    ws = _running(ctx)
    _set(ctx, auto_reset=True)
    _readings(monkeypatch, clock, carol=(160_000, 258_000))
    sup = _sup(ctx)
    sup.auto_reset()
    sup.run_resets()
    assert "[xt reset] xt's automatic reset policy is resetting your context" in ctx.herdr.last_prompt("carol")
    _saves(ctx, clock)
    sup.run_resets()
    assert ctx.herdr.live["carol"].workspace_id != ws
    assert _system(ctx)[-1].startswith(
        "reset carol (queued by xt's reset policy at 12:00; context 160000 tokens, above the threshold of "
        "150000 tokens; policy auto_reset): checkpoint")
    assert any("auto reset: queued a reset of carol (context 160k, threshold 150k)" in line
               for line in sup.lines)


def test_open_work_busy_stale_unknown_and_cooldown_are_left_alone(ctx, clock, monkeypatch):
    for name in ("owner", "busy", "stale", "unknown", "cooled", "waiting"):
        _running(ctx, name)
    send(ctx, "lead", "owner", "task", "a task")
    ctx.herdr.live["owner"].status = "idle"
    ctx.herdr.live["busy"].status = "working"
    _set(ctx, auto_reset=True)
    from xt import usage

    fresh_ts = (clock() - dt.timedelta(minutes=5)).isoformat()
    old_ts = (clock() - dt.timedelta(hours=3)).isoformat()
    big = dict(used=200_000, window=258_000, source="test log")
    readings = {"owner": Reading(**big, observed=fresh_ts), "busy": Reading(**big, observed=fresh_ts),
                "stale": Reading(**big, observed=old_ts), "unknown": Reading(reason="no usage recorded yet"),
                "cooled": Reading(**big, observed=fresh_ts), "waiting": Reading(**big, observed=fresh_ts)}
    monkeypatch.setattr(usage, "readings", lambda ctx, names: {n: r for n, r in readings.items() if n in names})
    reset._set_cooldown(ctx, "cooled")  # a reset ran for it a moment ago
    lines, problems = reset.apply_policy(ctx, ctx.herdr.agents(), {"waiting"}, readings)
    assert reset.queued(ctx) == {} and lines == [] and problems == []
    clock.advance(hours=6, minutes=1)  # the cool-down is over; the others' readings are now stale
    readings["cooled"] = Reading(**big, observed=clock().isoformat())
    reset.apply_policy(ctx, ctx.herdr.agents(), set(), readings)
    assert set(reset.queued(ctx)) == {"cooled"}


def test_a_missing_reading_or_agent_off_is_left_alone(ctx, clock, monkeypatch):
    _running(ctx, "carol")
    _running(ctx, "dave")
    _set(ctx, auto_reset=True)
    _agent_threshold(ctx, "carol", "off")
    _readings(monkeypatch, clock, carol=(900_000, 1_000_000))  # dave: no reading at all
    _sup(ctx).auto_reset()
    assert reset.queued(ctx) == {}


def test_a_per_agent_threshold_overrides_the_team_one(ctx, clock, monkeypatch):
    _running(ctx, "carol")
    _running(ctx, "dave")
    _set(ctx, auto_reset=True, auto_reset_tokens=300_000)
    _agent_threshold(ctx, "carol", 100_000)
    _readings(monkeypatch, clock, carol=(120_000, 258_000), dave=(250_000, 1_000_000))
    _sup(ctx).auto_reset()
    assert set(reset.queued(ctx)) == {"carol"}


def test_a_cancelled_policy_reset_waits_for_the_cool_down(ctx, clock, monkeypatch):
    _running(ctx)
    _set(ctx, auto_reset=True, auto_reset_cooldown_hours=2)
    _readings(monkeypatch, clock, carol=(160_000, 258_000))
    sup = _sup(ctx)
    sup.auto_reset()
    reset.cancel(ctx, "carol")
    sup.auto_reset()
    assert reset.queued(ctx) == {}
    clock.advance(hours=2, minutes=1)
    sup.auto_reset()
    assert "carol" in reset.queued(ctx)


def test_bad_settings_are_said_once_and_never_reset_anyone(ctx, clock, monkeypatch):
    _running(ctx)
    _set(ctx, auto_reset=True, auto_reset_tokens="lots")
    _readings(monkeypatch, clock, carol=(900_000, 1_000_000))
    sup = _sup(ctx)
    sup.auto_reset()
    sup.auto_reset()
    assert reset.queued(ctx) == {}
    said = [line for line in sup.lines if "isn't a token count" in line]
    assert len(said) == 1 and "[policy] auto_reset_tokens = 'lots'" in said[0]


def test_the_policy_example_in_the_docs_parses_and_does_what_it_says(tmp_path):
    """rc1 QA (#2317): the copyable configuration in docs/examples.md, section 6."""
    import re

    from xt.team import Team

    from .conftest import REPO

    text = (REPO / "docs/examples.md").read_text().split("## 6. Reset heavy agents automatically")[1]
    blocks = re.findall(r"```toml\n(.*?)```", text, re.S)
    path = tmp_path / "team.toml"
    path.write_text('[team]\nname = "t"\nsession = "t"\n\n' + "\n".join(blocks))
    team = Team.load(path)
    assert team.policy("auto_reset") is True and team.policy("auto_reset_cooldown_hours") == 6
    assert reset.threshold(team, team.agent("builder")) == (250_000, None)
    assert reset.threshold(team, team.agent("analyst")) == (None, None)


def test_a_new_team_toml_documents_the_policy_off(paths):
    text = paths.team_toml.read_text()
    assert "auto_reset = false" in text and "auto_reset_tokens = 150000" in text
    assert "auto_reset_cooldown_hours = 6" in text
