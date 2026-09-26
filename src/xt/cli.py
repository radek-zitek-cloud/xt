import argparse
import sys

from . import brief as brief_mod
from . import goals
from .adapters import load_adapters
from .alerts import Alerts
from .context import Ctx
from .dispatch import Queue, done_recipient, send
from .ledger import AGENT_TYPES
from .paths import Paths, XtError, find_root
from .spawn import Approvals, decide, request_spawn, retire, stop
from .team import HUMAN


def _who(args) -> str:
    who = getattr(args, "as_", None)
    if who and who != HUMAN:
        return who
    # Acting as the human needs a real terminal. Agents' shell tools don't run in one, so an
    # agent can't simply claim `--as human` to skip approvals. Soft, but it closes the easy path.
    if sys.stdin.isatty():
        return HUMAN
    if who == HUMAN:
        raise XtError(
            "`--as human` only works from the human's own terminal. Agents act as themselves: "
            "pass --as <your name>. If the human wants something done that you're not allowed to "
            "do, ask them (or the agent you report to) to do it."
        )
    raise XtError("pass --as <your name> (agents must always say who they are)")


def cmd_default(args) -> None:
    paths = Paths(find_root())
    if not paths.team_toml.exists():
        from .init import init

        for line in init(paths, None, None, None, None, None, yes=False):
            print(line)
        if not paths.team_toml.exists():
            return
    cmd_up(args)
    print("\n(the TUI isn't built yet — use `xt status`, `xt inbox`, and talk to the liaison in its Herdr pane)")


def cmd_init(args) -> None:
    from .init import init

    approval = None if args.approval is None else args.approval == "on"
    for line in init(Paths(find_root()), args.name, args.session, args.liaison, args.lead, approval,
                     yes=args.yes, commit=not args.no_commit):
        print(line)


def cmd_up(args) -> None:
    from .up import up

    for line in up(Ctx.load()):
        print(line)


def cmd_send(args) -> None:
    ctx = Ctx.load()
    body = " ".join(args.body) if args.body else sys.stdin.read()
    msg, status = send(ctx, _who(args), args.to, args.type, body, args.ref)
    print(f"#{msg['id']} {msg['type']} → {msg['to']}: {status}")


def cmd_done(args) -> None:
    ctx = Ctx.load()
    who = _who(args)
    item = ctx.ledger.item(args.id)
    if item is None:
        raise XtError(f"#{args.id} is not an open goal or task")
    to = done_recipient(ctx.team, who, item)
    msg, status = send(ctx, who, to, "done", " ".join(args.body) or "done", args.id)
    print(f"#{msg['id']} done for #{args.id} → {to}: {status}")


def cmd_note(args) -> None:
    ctx = Ctx.load()
    body = " ".join(args.body) if args.body else sys.stdin.read()
    msg, status = send(ctx, _who(args), "", "note", body, args.ref)
    print(f"#{msg['id']} note: {status}")


def cmd_brief(args) -> None:
    ctx = Ctx.load()
    who = _who(args)
    name = args.name or (None if who == HUMAN else who)
    if who != HUMAN and name != who:
        target = ctx.team.agent(name)
        if target is None or target.reports_to != who:
            raise XtError(f"you can read your own brief and your reports' briefs, not {name}'s")
    print(brief_mod.build(ctx, name))


def cmd_log(args) -> None:
    ctx = Ctx.load()
    n = 0
    for m in ctx.ledger.messages(since_days=args.since):
        if args.member and args.member not in (m["from"], m["to"]):
            continue
        if args.id and args.id not in (m["id"], m.get("ref")):
            continue
        if args.type and m["type"] != args.type:
            continue
        ref = f" ref:#{m['ref']}" if m.get("ref") is not None else ""
        print(f"#{m['id']} {m['ts']} {m['type']} {m['from']}→{m['to']}{ref}")
        print("   " + m["body"].replace("\n", "\n   "))
        n += 1
    if not n:
        print("(no messages)")


def cmd_status(args) -> None:
    ctx = Ctx.load()
    live = ctx.herdr.agents()
    items = ctx.ledger.open_items()
    print(f"team {ctx.team.name} · session {ctx.team.session}")
    for a in ctx.team.agents():
        if a.kind == HUMAN:
            continue
        state = live[a.name].status if a.name in live else ("not running" if a.active else "retired")
        mine = sum(1 for i in items if i["owner"] == a.name)
        print(f"  {a.name:<12} {a.role or '':<12} {a.harness or '':<7} {state:<12} open:{mine}")
    from .jobs import Jobs
    from .watch import watch_pid

    q = Queue(ctx).pending()
    jobs = Jobs(ctx).pending()
    print(f"open goals/tasks: {len(items)} · queued messages: {len(q)} · jobs: {len(jobs)} · "
          f"pending approvals: {len(Approvals(ctx).pending())} · alerts: {len(Alerts(ctx).active())}")
    if (q or jobs) and not watch_pid(ctx):
        print("the supervisor isn't running: queued messages and jobs wait for it (`xt up`)")


def cmd_inbox(args) -> None:
    ctx = Ctx.load()
    alerts = Alerts(ctx).active()
    approvals = Approvals(ctx).pending()
    print("Alerts:")
    for k, a in alerts.items():
        print(f"  #{a['id']} {a['ts'][5:16]} {a['text']}  (clear: xt clear {k})")
    if not alerts:
        print("  (none)")
    print("Pending approvals:")
    for rid, r in approvals.items():
        print(f"  #{rid} {r['requester']} → spawn {r['name']} ({r['role']}, {r['harness']})  xt approve {rid} | xt deny {rid}")
    if not approvals:
        print("  (none)")
    print("Recent messages to you:")
    recent = [m for m in ctx.ledger.messages(since_days=args.days) if m["to"] == HUMAN and m["type"] not in ("system",)]
    for m in recent[-args.limit:]:
        print(f"  #{m['id']} {m['ts'][5:16]} {m['type']} from {m['from']}: {' '.join(m['body'].split())[:160]}")
    if not recent:
        print("  (none)")


def cmd_clear(args) -> None:
    ctx = Ctx.load()
    print("cleared" if Alerts(ctx).resolve(args.key) else f"no alert {args.key!r}")


def cmd_approve(args, approve: bool = True) -> None:
    if _who(args) != HUMAN:
        raise XtError("only the human approves spawns")
    print(decide(Ctx.load(), args.id, approve))


def cmd_spawn(args) -> None:
    ctx = Ctx.load()
    print(request_spawn(ctx, _who(args), args.name, args.harness, args.model, args.role, args.reports_to))


def cmd_retire(args) -> None:
    print(retire(Ctx.load(), _who(args), args.name))


def cmd_stop(args) -> None:
    if _who(args) != HUMAN:
        raise XtError("only the human stops agents (the lead retires its own reports with `xt retire`)")
    print(stop(Ctx.load(), args.name))


def cmd_harnesses(args) -> None:
    paths = Paths(find_root())
    for a in load_adapters(paths).values():
        mark = "installed" if a.installed else "not installed"
        print(f"{a.name} ({mark}) — {a.summary}")
        model = f"model via `{a.model_flag} <model>`" if a.model_flag else "model: harness default only"
        print(f"   {model}; start args: {' '.join(a.args) or '(none)'}")
        for lim in a.limits:
            print(f"   limit: {lim}")


def cmd_goal(args) -> None:
    ctx = Ctx.load()
    if args.goal_cmd == "new":
        print(goals.new(ctx, args.slug, " ".join(args.title) or None))
    elif args.goal_cmd == "dispatch":
        print(goals.dispatch(ctx, _who(args), args.slug))
    else:
        print(goals.listing(ctx))


def cmd_watch(args) -> None:
    from .watch import run

    run(Ctx.load())


def cmd_tui(args) -> None:
    if not args.demo:
        raise XtError("the TUI is a look-and-feel spike so far — try `xt tui --demo`; use `xt status` and `xt inbox`")
    from .tui.app import run_demo

    run_demo()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xt", description="Harness-agnostic hierarchical agent teams on Herdr.")
    p.set_defaults(func=cmd_default)
    sub = p.add_subparsers(dest="cmd")

    def add(name, func, help_):
        sp = sub.add_parser(name, help=help_, description=help_)
        sp.set_defaults(func=func)
        sp.add_argument("--as", dest="as_", metavar="NAME", help="who you are (agents: always pass this)")
        return sp

    sp = add("init", cmd_init, "turn this clone into your team's repo (asks for the essentials)")
    sp.add_argument("--name")
    sp.add_argument("--session")
    sp.add_argument("--liaison", metavar="HARNESS[:MODEL]")
    sp.add_argument("--lead", metavar="HARNESS[:MODEL]")
    sp.add_argument("--approval", choices=["on", "off"])
    sp.add_argument("--yes", action="store_true", help="accept recommended defaults, no questions")
    sp.add_argument("--no-commit", action="store_true")

    add("up", cmd_up, "start the supervisor and liaison (and the lead if goals are open)")

    sp = add("send", cmd_send, "send a message through xt (the only sanctioned way agents talk)")
    sp.add_argument("to")
    sp.add_argument("--type", choices=AGENT_TYPES, default="report")
    sp.add_argument("--ref", type=int, help="goal/task/message id this is about")
    sp.add_argument("body", nargs="*", help="message text (or stdin)")

    sp = add("done", cmd_done, "close an open goal or task you own (reports to whoever opened it)")
    sp.add_argument("id", type=int)
    sp.add_argument("body", nargs="*")

    sp = add("note", cmd_note, "log a note in the ledger for yourself (not delivered to anyone)")
    sp.add_argument("--ref", type=int, help="goal/task/message id this is about")
    sp.add_argument("body", nargs="*")

    sp = add("brief", cmd_brief, "recovery summary: team, open work, recent messages")
    sp.add_argument("name", nargs="?")

    sp = add("log", cmd_log, "message history")
    sp.add_argument("--member")
    sp.add_argument("--id", type=int)
    sp.add_argument("--type")
    sp.add_argument("--since", type=int, metavar="DAYS")

    add("status", cmd_status, "one-shot team status")

    sp = add("inbox", cmd_inbox, "alerts, pending approvals and messages for the human")
    sp.add_argument("--days", type=int, default=7)
    sp.add_argument("--limit", type=int, default=20)

    sp = add("clear", cmd_clear, "dismiss an alert")
    sp.add_argument("key")

    sp = add("approve", lambda a: cmd_approve(a, True), "approve a pending spawn")
    sp.add_argument("id", type=int)
    sp = add("deny", lambda a: cmd_approve(a, False), "deny a pending spawn")
    sp.add_argument("id", type=int)

    sp = add("spawn", cmd_spawn, "start an agent (new: needs --harness and --role; existing: restarts it)")
    sp.add_argument("name")
    sp.add_argument("--harness")
    sp.add_argument("--model")
    sp.add_argument("--role")
    sp.add_argument("--reports-to")

    sp = add("retire", cmd_retire, "close an agent's workspace and mark it retired")
    sp.add_argument("name")
    sp = add("stop", cmd_stop, "close an agent's workspace, keep it in the roster (human only)")
    sp.add_argument("name")

    add("harnesses", cmd_harnesses, "which harnesses xt can use here")

    sp = add("goal", cmd_goal, "goals: new draft, dispatch to the lead, list")
    gsub = sp.add_subparsers(dest="goal_cmd")
    g = gsub.add_parser("new", help="create a draft in goals/drafts/")
    g.add_argument("slug")
    g.add_argument("title", nargs="*")
    g2 = gsub.add_parser("dispatch", help="send a finished draft to the lead")
    g2.add_argument("slug")
    g3 = gsub.add_parser("list", help="drafts and open goals")
    for gp in (g, g2, g3):
        gp.add_argument("--as", dest="as_", metavar="NAME", default=argparse.SUPPRESS)

    add("watch", cmd_watch, "run the supervisor (xt up starts it in its own pane)")
    sp = add("tui", cmd_tui, "the lazygit-style overview (spike: --demo)")
    sp.add_argument("--demo", action="store_true", help="show the look-and-feel spike with demo data")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
        return 0
    except XtError as e:
        print(f"xt: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
