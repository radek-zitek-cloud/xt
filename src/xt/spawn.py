"""Spawning and retiring agents, with human approval of spawns the lead requests."""

import json
import os

from . import brief, skills
from .adapters import get_adapter
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
    try:
        ctx.herdr.start_agent(name, adapter.herdr_kind, pane, adapter.start_args(a.model))
    except XtError:
        ctx.herdr.close_workspace(workspace)
        raise
    set_expected(ctx, name, True)
    ctx.herdr.prompt(name, first_prompt(ctx, name))
    ctx.ledger.append(SYSTEM, HUMAN, "system", f"started {name} ({a.role}, {a.harness}) in workspace {workspace}")
    return workspace


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
    if requester != HUMAN and a.reports_to != requester:
        raise XtError(f"only {a.reports_to} or the human can retire {name}")
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
