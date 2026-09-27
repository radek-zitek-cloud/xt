import argparse
import sys

from . import __version__
from . import brief as brief_mod
from . import goals
from .adapters import load_adapters
from .alerts import Alerts
from .context import Ctx
from .dispatch import Queue, done_recipient, send
from .ledger import AGENT_TYPES
from .paths import Paths, XtError, find_root
from .spawn import Approvals, decide, request_spawn, retire, stop
from .team import ALWAYS, HUMAN, parse_window, schedule_text


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
    if sys.stdin.isatty():
        from .tui.app import run_live

        run_live()


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


def cmd_schedule(args) -> None:
    ctx = Ctx.load()
    who = _who(args)
    target = ctx.team.agent(args.name)
    if target is None or target.kind == HUMAN:
        raise XtError(f"no agent named {args.name!r}")
    if who != HUMAN and target.reports_to != who:
        raise XtError(f"only {target.reports_to} (its lead) or the human can schedule {args.name}")
    off = args.every.lower() in ("off", "none", "0")
    if not off and who != HUMAN:
        # Each wake-up is a billed agent turn: agents get a floor and (by default) the human's approval.
        from .spawn import Approvals
        from .team import parse_interval

        floor = int(ctx.team.policy("min_wake_minutes"))
        if parse_interval(args.every) < floor * 60:
            raise XtError(f"the shortest schedule an agent may request is {floor}m (policy "
                          f"min_wake_minutes); ask the human if it really needs to be more often")
        if ctx.team.policy("schedule_approval"):
            if args.between and args.between != ALWAYS:
                parse_window(args.between)
            rid = Approvals(ctx).add({"kind": "schedule", "requester": who, "name": args.name,
                                      "every": args.every, "message": args.message,
                                      "between": args.between})
            print(f"approval #{rid} requested from the human; you'll get a message when it's decided")
            return
    ctx.team.set_schedule(args.name, None if off else args.every, args.message, args.between)
    ctx.team.save()
    ctx.reload_team()
    if off:
        print(f"{args.name}: no scheduled wake-ups")
    else:
        a = ctx.team.agent(args.name)
        print(f"{args.name}: woken {schedule_text(a)} when idle (by the supervisor)"
              + (f": {a.wake_message}" if a.wake_message else ""))


def cmd_down(args) -> None:
    if _who(args) != HUMAN:
        raise XtError("only the human takes the team down")
    from .up import down

    for line in down(Ctx.load(), keep_supervisor=args.keep_supervisor):
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


def cmd_answer(args) -> None:
    ctx = Ctx.load()
    who = _who(args)
    item = ctx.ledger.item(args.id)
    if item is None or item["type"] != "ask":
        raise XtError(f"#{args.id} is not an open question (see `xt inbox`)")
    if who != item["owner"]:
        raise XtError(f"#{args.id} is a question for {item['owner']}, not {who}")
    body = " ".join(args.body) if args.body else sys.stdin.read()
    msg, status = send(ctx, who, item["opener"], "report", body, args.id)
    print(f"#{msg['id']} answer to #{args.id} → {item['opener']}: {status}")


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
    print(f"team {ctx.team.name} · session {ctx.team.session} · xt {__version__}")
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
    questions = sum(1 for i in items if i["type"] == "ask")
    print(f"open goals/tasks: {len(items) - questions} · questions for the human: {questions} · "
          f"queued messages: {len(q)} · jobs: {len(jobs)} · "
          f"pending approvals: {len(Approvals(ctx).pending())} · alerts: {len(Alerts(ctx).active())}")
    if (q or jobs) and not watch_pid(ctx):
        print("the supervisor isn't running: queued messages and jobs wait for it (`xt up`)")


def cmd_inbox(args) -> None:
    ctx = Ctx.load()
    alerts = Alerts(ctx).active()
    approvals = Approvals(ctx).pending()
    questions = [i for i in ctx.ledger.open_items() if i["type"] == "ask"]
    print("Questions for you:")
    for q in questions:
        print(f"  #{q['id']} {q['opened'][5:16]} from {q['opener']}: {q['title']}  (xt answer {q['id']} \"...\")")
    if not questions:
        print("  (none)")
    print("Alerts:")
    for k, a in alerts.items():
        print(f"  #{a['id']} {a['ts'][5:16]} {a['text']}  (clear: xt clear {k})")
    if not alerts:
        print("  (none)")
    print("Pending approvals:")
    for rid, r in approvals.items():
        what = (f"wake {r['name']} every {r['every']}"
                + (f" between {r['between']}" if r.get("between") and r["between"] != ALWAYS else "")
                if r.get("kind") == "schedule"
                else f"spawn {r['name']} ({r['role']}, {r['harness']})")
        print(f"  #{rid} {r['requester']} → {what}  xt approve {rid} | xt deny {rid}")
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
    ctx = Ctx.load()
    for rid in args.ids:
        try:
            print(f"#{rid}: {decide(ctx, rid, approve)}")
        except XtError as e:
            print(f"#{rid}: {e}")


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
    from .tui.app import run_demo, run_live

    if args.demo:
        run_demo()
        return
    if not sys.stdin.isatty():
        raise XtError("the TUI needs a terminal")
    run_live()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="xt", description="Harness-agnostic hierarchical agent teams on Herdr.")
    p.add_argument("--version", action="version", version=f"xt {__version__}")
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

    sp = add("schedule", cmd_schedule,
             "wake an agent periodically when idle (e.g. a monitor): xt schedule <name> 30m | off")
    sp.add_argument("name")
    sp.add_argument("every", metavar="interval|off", help="like 90s, 30m, 2h, 1d; or off")
    sp.add_argument("--message", help="what the agent should do on each wake-up (left out: keep the current one)")
    sp.add_argument("--between", metavar="HH:MM-HH:MM",
                    help="only wake within this local-time window, e.g. 05:00-21:00 (may wrap midnight; "
                         "'always' removes it; left out: keep the current one)")

    sp = add("down", cmd_down, "stop every running agent and the supervisor (human only)")
    sp.add_argument("--keep-supervisor", action="store_true", help="stop the agents only")

    sp = add("send", cmd_send, "send a message through xt (the only sanctioned way agents talk)")
    sp.add_argument("to")
    sp.add_argument("--type", choices=AGENT_TYPES, default="report")
    sp.add_argument("--ref", type=int, help="goal/task/message id this is about")
    sp.add_argument("body", nargs="*", help="message text (or stdin)")

    sp = add("done", cmd_done, "close an open goal or task you own (reports to whoever opened it)")
    sp.add_argument("id", type=int)
    sp.add_argument("body", nargs="*")

    sp = add("answer", cmd_answer, "answer a question the liaison asked you (see `xt inbox`)")
    sp.add_argument("id", type=int)
    sp.add_argument("body", nargs="*", help="your answer (or stdin)")

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

    sp = add("approve", lambda a: cmd_approve(a, True), "approve pending spawns (one or more ids)")
    sp.add_argument("ids", type=int, nargs="+", metavar="id")
    sp = add("deny", lambda a: cmd_approve(a, False), "deny pending spawns (one or more ids)")
    sp.add_argument("ids", type=int, nargs="+", metavar="id")

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
    sp = add("tui", cmd_tui, "the lazygit-style overview of the team (--demo: static sample data)")
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
