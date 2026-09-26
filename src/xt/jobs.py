"""Jobs: Herdr work that agents ask for (spawn, start, retire), carried out by the supervisor.

Agents never call Herdr themselves: a harness may sandbox the agent's shell (codex does, and its
sandbox blocks Herdr's socket with "Operation not permitted"). So an agent's request is written
here, and `xt watch`, which runs unsandboxed in its own pane, executes it on its next tick and
reports back to the requester.
"""

import json
import os

from .context import Ctx
from .paths import XtError
from .team import HUMAN, SYSTEM


class Jobs:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / "jobs.json"

    def _load(self) -> list[dict]:
        return json.loads(self.path.read_text()) if self.path.exists() else []

    def _save(self, items: list[dict]) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(items, indent=1))
        os.replace(tmp, self.path)

    def pending(self) -> list[dict]:
        with self.ctx.ledger.lock():
            return self._load()

    def add(self, kind: str, args: dict, requester: str) -> int:
        with self.ctx.ledger.lock():
            items = self._load()
            job_id = max((j["id"] for j in items), default=0) + 1
            items.append({"id": job_id, "kind": kind, "args": args, "requester": requester})
            self._save(items)
        return job_id

    def remove(self, job_id: int) -> None:
        with self.ctx.ledger.lock():
            self._save([j for j in self._load() if j["id"] != job_id])


def _execute(ctx: Ctx, job: dict) -> str:
    from .spawn import do_spawn, execute_spawn, retire_now

    kind, args = job["kind"], job["args"]
    if kind == "spawn":
        return execute_spawn(ctx, args)
    if kind == "start":
        name = args["name"]
        if name in ctx.herdr.agents():
            return f"{name} is already running"
        ws = do_spawn(ctx, name)
        return f"started {name} in workspace {ws}"
    if kind == "retire":
        return retire_now(ctx, job["requester"], args["name"])
    raise XtError(f"unknown job kind {kind!r}")


def run_pending(ctx: Ctx) -> list[str]:
    from .dispatch import send

    out = []
    for job in Jobs(ctx).pending():
        Jobs(ctx).remove(job["id"])  # at most once, even if it fails half-way
        try:
            result = _execute(ctx, job)
            text = f"Done: {job['kind']} {job['args'].get('name', '')} — {result}"
        except XtError as e:
            text = f"Failed: {job['kind']} {job['args'].get('name', '')} — {e}"
        out.append(text)
        ctx.reload_team()
        requester = job["requester"]
        if requester == HUMAN or ctx.team.agent(requester) is None:
            ctx.ledger.append(SYSTEM, HUMAN, "system", text)
        else:
            send(ctx, SYSTEM, requester, "system", text)
    return out
