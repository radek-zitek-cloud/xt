"""Jobs: Herdr work that agents ask for (spawn, start, retire), carried out by the supervisor.

Agents never call Herdr themselves: a harness may sandbox the agent's shell (codex does, and its
sandbox blocks Herdr's socket with "Operation not permitted"). So an agent's request is written
to the queue (`lifecycle.Jobs`), and `xt watch`, which runs unsandboxed in its own pane, executes
it on its next tick and reports back to the requester.
"""

from .context import Ctx
from .dispatch import send
from .lifecycle import Jobs
from .paths import XtError
from .spawn import do_spawn, execute_spawn, retire_now
from .team import HUMAN, SYSTEM


def _execute(ctx: Ctx, job: dict) -> str:
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
