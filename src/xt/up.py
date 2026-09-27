"""`xt up`: bring the team to its resting state — supervisor and liaison running, lead if goals are open."""

from .context import Ctx
from .spawn import do_spawn
from .watch import expected, watch_pid


def up(ctx: Ctx) -> list[str]:
    ctx.herdr.check_session()
    out = []
    if watch_pid(ctx):
        out.append("supervisor: running")
    else:
        pane, ws = ctx.herdr.create_workspace(str(ctx.paths.root), f"{ctx.team.name}·watch")
        ctx.herdr.run_in_fresh_pane(pane, f"{ctx.paths.xt_bin} watch")
        out.append(f"supervisor: started in workspace {ws}")

    live = ctx.herdr.agents()
    liaison = ctx.team.lead_of_role("liaison")
    if liaison is None:
        out.append("liaison: none in team.toml (add one, see roles/liaison.md)")
    elif liaison.name in live:
        out.append(f"liaison: {liaison.name} running ({live[liaison.name].status})")
    else:
        ws = do_spawn(ctx, liaison.name)
        out.append(f"liaison: started {liaison.name} in workspace {ws}")

    lead = ctx.team.lead_of_role("lead")
    goals_open = any(i["type"] == "goal" for i in ctx.ledger.open_items())
    if lead and lead.name in live:
        out.append(f"lead: {lead.name} running ({live[lead.name].status})")
    elif lead and goals_open:
        ws = do_spawn(ctx, lead.name)
        out.append(f"lead: started {lead.name} in workspace {ws} (open goals)")
    elif lead:
        out.append(f"lead: {lead.name} not started (starts when the first goal is dispatched)")

    skip = {a.name for a in (liaison, lead) if a}
    exp = expected(ctx)
    for a in ctx.team.agents():
        if a.kind == "human" or not a.active or a.name in skip:
            continue
        if a.name in live:
            out.append(f"member: {a.name} running ({live[a.name].status})")
        else:
            note = " — was running before; find out why it stopped" if a.name in exp else ""
            out.append(f"member: {a.name} not running{note}; `xt spawn {a.name}` starts it again")
    return out


def down(ctx: Ctx, keep_supervisor: bool = False) -> list[str]:
    """Stop the whole team cleanly: the supervisor and its workspace first (so no tick sees a
    half-stopped team and raises false alerts), then every running agent the way `xt stop` does
    (so the next `xt up` raises no false "crashed" alerts)."""
    from .spawn import stop

    out = []
    if not keep_supervisor:
        out += _stop_supervisor(ctx)
    live = ctx.herdr.agents()
    agents = [stop(ctx, a.name) for a in ctx.team.agents() if a.kind != "human" and a.name in live]
    out += agents or ["no agents were running"]
    return out


def restart(ctx: Ctx, names: list[str], everyone: bool = False) -> list[str]:
    """Stop and start agents so they pick up new instructions (a changed role, a new xt version).
    With everyone: the whole team the way `xt down` + `xt up` would, then every agent that was
    running before starts again, so the team comes back as it was."""
    from .spawn import stop
    from .team import HUMAN

    if everyone:
        live = ctx.herdr.agents()
        was_running = [a.name for a in ctx.team.agents() if a.kind != HUMAN and a.name in live]
        out = down(ctx) + up(ctx)
        live = ctx.herdr.agents()
        for name in was_running:
            if name not in live:
                out.append(f"member: started {name} again in workspace {do_spawn(ctx, name)}")
        return out
    out = []
    for name in names:
        a = ctx.team.agent(name)
        if a is None or a.kind == HUMAN:
            out.append(f"{name}: no such agent")
            continue
        if not a.active:
            out.append(f"{name} is retired")
            continue
        stop(ctx, name)
        out.append(f"restarted {name} in workspace {do_spawn(ctx, name)}")
    return out


def _stop_supervisor(ctx: Ctx) -> list[str]:
    import os
    import signal
    import time

    out = []
    pid = watch_pid(ctx)
    if pid:
        os.kill(pid, signal.SIGINT)
        for _ in range(20):
            if not watch_pid(ctx):
                break
            time.sleep(0.25)
        out.append(f"supervisor stopped (pid {pid})")
    label = f"{ctx.team.name}·watch"
    for ws, lab in ctx.herdr.workspaces().items():
        if lab == label:
            ctx.herdr.close_workspace(ws)
            out.append(f"closed the supervisor's workspace {ws}")
    return out
