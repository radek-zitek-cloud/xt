"""Spawning and retiring agents, with human approval of spawns the lead requests."""

import json
import os
import time

from . import brief, skills
from .adapters import get_adapter
from .alerts import Alerts
from .herdr import HerdrError
from .context import Ctx
from .paths import XtError
from .team import HUMAN, SYSTEM
from .watch import set_expected

PRECEDENCE = """\
PRECEDENCE: for everything about this team — who you are, who you talk to, how you send and
receive messages, how you report, where you keep notes — the xt protocol below wins over any
other instructions you may have (global or project instruction files, memories, skills). For
everything else (how you do your actual work), your usual instructions still apply."""


def first_prompt(ctx: Ctx, name: str) -> str:
    a = ctx.team.agent(name)
    role_file = ctx.paths.role_file(a.role)
    protocol = ctx.paths.protocol.read_text()
    role = role_file.read_text()
    xt = ctx.paths.xt_bin
    return f"""You are **{name}**, an agent in the xt team "{ctx.team.name}". Your role is **{a.role}**; \
you report to **{a.reports_to}**. The team's repo (your home, not your workspace) is {ctx.paths.root}. \
Run xt as `{xt}` (absolute path — don't rely on PATH). Always pass `--as {name}` when you use xt.

{PRECEDENCE}

===== protocol.md =====
{protocol}
===== roles/{a.role}.md =====
{role}
===== team skills (read a skill's file when you need it) =====
{skills.render(ctx.paths)}

===== your brief (`{xt} brief --as {name}`) =====
{brief.build(ctx, name)}

Start now: follow your role's "on start" instructions. If you have nothing to do, say so briefly and stop."""


def do_spawn(ctx: Ctx, name: str) -> str:
    """Start an agent already in team.toml: new workspace, harness start, first prompt."""
    a = ctx.team.agent(name)
    if a is None or not a.active:
        raise XtError(f"{name!r} is not an active agent in team.toml")
    if not ctx.paths.role_file(a.role).exists():
        raise XtError(f"role file {ctx.paths.role_file(a.role)} doesn't exist — write it first")
    if name in ctx.herdr.agents():
        raise XtError(f"{name} is already running")
    adapter = get_adapter(ctx.paths, a.harness)
    pane, workspace = ctx.herdr.create_workspace(str(ctx.paths.root), f"{ctx.team.name}·{name}")
    answered: list[str] = []
    try:
        ctx.herdr.start_agent(name, adapter.herdr_kind, pane, adapter.start_args(a.model))
    except HerdrError as e:
        # Herdr refuses when the harness blocks at startup (e.g. claude's folder-trust question).
        # The agent is registered and blocked; answer the dialog and wait until it's ready.
        if e.code != "agent_not_ready" or not _ready_after_dialogs(ctx, name, adapter, pane, answered):
            ctx.herdr.close_workspace(workspace)
            raise
    except XtError:
        ctx.herdr.close_workspace(workspace)
        raise
    set_expected(ctx, name, True)
    answered += answer_startup_dialogs(ctx, adapter, pane)
    for dialog in answered:
        ctx.ledger.append(SYSTEM, HUMAN, "system", f"answered {a.harness}'s '{dialog}' dialog for {name}")
    landed = send_first_prompt(ctx, name, pane, adapter, first_prompt(ctx, name))
    note = "" if landed else " — FIRST PROMPT NOT CONFIRMED, see alert"
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"started {name} ({a.role}, {a.harness}) in workspace {workspace}{note}")
    return workspace


RETRY_DELAY = 5.0
POLL = 1.0
DIALOG_QUIET_CHECKS = 4  # consecutive checks (POLL apart) without a known dialog = ready
LANDED_WAIT = 20  # seconds to wait for the first prompt's text to show up in the transcript
MARKER = "an agent in the xt team"


def _flat(text: str) -> str:
    """Screen text with line wrapping undone, so a phrase split across lines still matches."""
    return " ".join(text.split())


def answer_startup_dialogs(ctx: Ctx, adapter, pane: str) -> list[str]:
    """Answer dialogs the adapter declares (e.g. codex's folder trust) before any prompt is sent.

    Typing a prompt into such a dialog loses the prompt: codex's 'Trust this folder?' consumed the
    liaison's first prompt in both of the first two real runs (2026-09-26)."""
    if not adapter.startup_dialogs:
        return []
    answered: list[str] = []
    quiet = checks = 0
    while quiet < DIALOG_QUIET_CHECKS and checks < 40:
        checks += 1
        screen = _flat(ctx.herdr.read_pane(pane, lines=60))
        hit = next((d for d in adapter.startup_dialogs if any(_flat(m) in screen for m in d["match"])), None)
        if hit:
            ctx.herdr.send_keys(pane, *hit["keys"])
            answered.append(hit["name"])
            quiet = 0
            time.sleep(2 * POLL)
            continue
        quiet += 1
        time.sleep(POLL)
    return answered


READY_CHECKS = 30  # POLL-spaced checks for a blocked-at-startup agent to become ready


def _ready_after_dialogs(ctx: Ctx, name: str, adapter, pane: str, answered: list[str]) -> bool:
    answered += answer_startup_dialogs(ctx, adapter, pane)
    for _ in range(READY_CHECKS):
        if ctx.herdr.status(name) in ("idle", "done"):
            return True
        time.sleep(POLL)
    return False


def _landed(ctx: Ctx, pane: str) -> bool:
    deadline = time.monotonic() + LANDED_WAIT
    while True:
        if MARKER in _flat(ctx.herdr.read_pane(pane, lines=400)):
            return True
        if time.monotonic() >= deadline:
            return False
        time.sleep(POLL)


def send_first_prompt(ctx: Ctx, name: str, pane: str, adapter, text: str) -> bool:
    """Deliver the first prompt and confirm it really landed in the conversation.

    Two checks, both needed: herdr must see the agent start working on it (catches a prompt that
    was typed but never submitted), and the prompt's text must appear on the agent's screen
    (catches a prompt swallowed by a startup dialog, where the harness's own startup looked like
    'working'). Retry once; if it still doesn't land, alert the human instead of carrying on."""
    assert MARKER in text
    for attempt in (1, 2):
        try:
            ctx.herdr.prompt(name, text, confirm=True)
        except HerdrError as e:
            if e.code not in ("agent_prompt_stalled", "timeout"):
                raise
            time.sleep(RETRY_DELAY)
        if _landed(ctx, pane):
            return True
        answer_startup_dialogs(ctx, adapter, pane)
    Alerts(ctx).raise_(
        f"noprompt:{name}",
        f"{name} started but its first prompt (identity, role, protocol) never showed up in its "
        f"conversation. It would act without knowing who it is. Look at its pane (a dialog xt doesn't "
        f"know?), then `xt stop {name}` and `xt spawn {name}`.",
    )
    return False


class Approvals:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / "approvals.json"

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        os.replace(tmp, self.path)

    def pending(self) -> dict:
        with self.ctx.ledger.lock():
            return self._load()

    def add(self, req: dict) -> int:
        msg = self.ctx.ledger.append(
            SYSTEM,
            HUMAN,
            "approval",
            f"{req['requester']} asks to spawn {req['name']} as {req['role']} on {req['harness']}"
            + (f" ({req['model']})" if req.get("model") else "")
            + f", reporting to {req['reports_to']}. Approve: xt approve <id>; deny: xt deny <id>",
        )
        with self.ctx.ledger.lock():
            d = self._load()
            d[str(msg["id"])] = req
            self._save(d)
        return msg["id"]

    def pop(self, req_id: int) -> dict:
        with self.ctx.ledger.lock():
            d = self._load()
            req = d.pop(str(req_id), None)
            self._save(d)
        if req is None:
            raise XtError(f"no pending approval #{req_id}")
        return req


def request_spawn(
    ctx: Ctx, requester: str, name: str, harness: str | None, model: str | None,
    role: str | None, reports_to: str | None,
) -> str:
    existing = ctx.team.agent(name)
    if existing and existing.kind == HUMAN:
        raise XtError("can't spawn the human")
    if existing and not (harness or role):
        harness, role, model = existing.harness, existing.role, model or existing.model
        reports_to = reports_to or existing.reports_to
    if not (harness and role):
        raise XtError("new agents need --harness and --role")
    reports_to = reports_to or requester
    if requester != HUMAN:
        r = ctx.team.agent(requester)
        if r is None or not r.active:
            raise XtError(f"{requester!r} is not an active member")
        if r.role == "liaison":
            raise XtError(
                "the liaison doesn't spawn agents: write what the human wants into a goal "
                "(`xt goal new` / `xt goal dispatch`) and the lead will design and staff the team"
            )
        if reports_to != requester and ctx.team.agent(reports_to) and ctx.team.agent(reports_to).reports_to != requester:
            raise XtError("you can spawn agents only into your own part of the hierarchy")
    if ctx.team.agent(reports_to) is None:
        raise XtError(f"reports_to {reports_to!r} is not in the team")
    get_adapter(ctx.paths, harness)
    if not ctx.paths.role_file(role).exists():
        raise XtError(f"roles/{role}.md doesn't exist — write the role brief first")
    active = [a for a in ctx.team.agents() if a.active and a.kind != HUMAN]
    if not existing and len(active) >= int(ctx.team.policy("max_agents")) and requester != HUMAN:
        raise XtError(f"team is at max_agents ({len(active)}); ask the human to raise it first")

    req = {"requester": requester, "name": name, "harness": harness, "model": model,
           "role": role, "reports_to": reports_to}
    if requester != HUMAN and ctx.team.policy("spawn_approval"):
        rid = Approvals(ctx).add(req)
        return f"approval #{rid} requested from the human; you'll get a message when it's decided"
    if requester != HUMAN:
        from .jobs import Jobs

        jid = Jobs(ctx).add("spawn", req, requester)
        return f"spawn job #{jid} queued; the supervisor starts {name} within seconds and messages you"
    return execute_spawn(ctx, req)


def execute_spawn(ctx: Ctx, req: dict) -> str:
    ctx.team.upsert_agent(req["name"], req["role"], req["harness"], req.get("model"), req["reports_to"])
    ctx.team.save()
    ctx.reload_team()
    ws = do_spawn(ctx, req["name"])
    return f"spawned {req['name']} in workspace {ws}"


def decide(ctx: Ctx, req_id: int, approve: bool) -> str:
    req = Approvals(ctx).pop(req_id)
    if approve:
        result = execute_spawn(ctx, req)
    else:
        result = f"spawn of {req['name']} denied"
    if req["requester"] != HUMAN:
        from .dispatch import send

        send(ctx, SYSTEM, req["requester"], "system",
             f"Human {'approved' if approve else 'denied'} approval #{req_id}: {result}")
    return result


def retire(ctx: Ctx, requester: str, name: str) -> str:
    a = ctx.team.agent(name)
    if a is None or a.kind == HUMAN:
        raise XtError(f"no agent named {name!r}")
    r = ctx.team.agent(requester)
    if requester != HUMAN and r is not None and r.role == "liaison":
        raise XtError("the liaison doesn't retire agents; ask the human")
    if requester != HUMAN and a.reports_to != requester:
        raise XtError(f"only {a.reports_to} or the human can retire {name}")
    if requester != HUMAN:
        from .jobs import Jobs

        jid = Jobs(ctx).add("retire", {"name": name}, requester)
        return f"retire job #{jid} queued; the supervisor closes {name} within seconds and messages you"
    return retire_now(ctx, requester, name)


def retire_now(ctx: Ctx, requester: str, name: str) -> str:
    """Close the agent's workspace and mark it retired (the human, or the supervisor for a job)."""
    live = ctx.herdr.agents().get(name)
    set_expected(ctx, name, False)
    if live:
        ctx.herdr.close_workspace(live.workspace_id)
    ctx.team.set_status(name, "retired")
    ctx.team.save()
    ctx.reload_team()
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"{requester} retired {name}")
    return f"retired {name}" + (" (workspace closed)" if live else "")


def stop(ctx: Ctx, name: str) -> str:
    """Close an agent's workspace without changing the roster (it can be started again)."""
    live = ctx.herdr.agents().get(name)
    set_expected(ctx, name, False)
    if not live:
        return f"{name} isn't running"
    ctx.herdr.close_workspace(live.workspace_id)
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"stopped {name}")
    return f"stopped {name}"
