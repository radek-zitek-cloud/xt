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
