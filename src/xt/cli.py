import argparse
import datetime as dt
import os
import sys

from . import __version__
from . import brief as brief_mod
from . import goals, operators, permissions
from .adapters import CODEX, allowed_codex_options, load_adapters
from .alerts import Alerts, repeats
from .context import Ctx
from .dispatch import Queue, done_recipient, send
from .ledger import AGENT_TYPES
from .paths import Paths, XtError, find_root
from .spawn import AGENT_ENV, Approvals, approval_what, decide, request_spawn, retire, stop
from .team import ALWAYS, HUMAN, harness_model, parse_window, schedule_text


def _who(args, operator: bool = False) -> str:
    """Who runs this command. A registered operator's name (card #166) is accepted only from the
    operator itself (token and registered process) and only where `operator` says the command
    takes one: sending a report to the liaison and the delegable commands."""
    who = getattr(args, "as_", None)
    if who and who != HUMAN:
        try:
            paths = Paths(find_root())
        except XtError:
            return who
        if operators.is_operator(paths, who):
            operators.verify(paths, who)
            if not operator:
                raise XtError(f"{who} is an operator: it sends reports to the liaison and, under the human's "
                              f"delegation, runs {', '.join(operators.DELEGABLE)}; nothing else")
        return who
    # Acting as the human needs the human's own terminal, so an agent can't simply claim
    # `--as human` to skip approvals. Soft, but it closes the easy paths (card #103).
    if human_terminal():
        return HUMAN
    if who == HUMAN:
        raise XtError(
            "`--as human` only works from the human's own terminal. Agents act as themselves: "
            "pass --as <your name>. If the human wants something done that you're not allowed to "
            "do, ask them (or the agent you report to) to do it."
        )
    raise XtError("pass --as <your name> (agents must always say who they are)")


def _body(args, default: str = "") -> str:
    """The message text: the arguments, or else standard input (a quoted heredoc keeps it exactly as
    written, card #106). A terminal on stdin means nothing was piped in: don't wait for it."""
    if args.body:
        return " ".join(args.body)
    if sys.stdin.isatty():
        return default
    return sys.stdin.read() or default


def controlling_terminal() -> bool:
    """Whether this process has a controlling terminal, even when stdin is a pipe or heredoc."""
    try:
        os.close(os.open("/dev/tty", os.O_RDWR))
        return True
    except OSError:
        return False


HARNESS_BINARIES = ("claude", "codex", "pi")


def _ancestor_names():
    """Names of this process's ancestors: each one's command name and its program's file name."""
    pid = os.getppid()
    while pid > 1:
        try:
            comm = open(f"/proc/{pid}/comm").read().strip()
            argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
            ppid = int(open(f"/proc/{pid}/stat").read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            return
        yield {comm, *(os.path.basename(a.decode(errors="replace")) for a in argv[:2] if a)}
        pid = ppid


def under_harness() -> bool:
    """Whether an agent harness (Claude Code, Codex, pi) started this process, however its
    environment was passed on: its shell tools, helpers and daemons all descend from it."""
    return harness_in(_ancestor_names())


def harness_in(chain) -> bool:
    return any(n == b or n.startswith(b + "-") for names in chain for n in names for b in HARNESS_BINARIES)


def human_terminal() -> bool:
    """The human's own terminal: not inside an agent xt started, and attached to a terminal.

    xt exports XT_AGENT in every agent's pane before its harness starts, so every shell the agent
    opens carries it, including a Codex command run in a pseudo-terminal; and in case the
    environment gets lost on the way (a shared daemon, a pooled shell), a harness among the
    process's ancestors counts too (where the harness's process tree is visible: Codex runs
    commands in its own PID namespace). The terminal check is the controlling terminal, which the
    human's terminal has and agents' shells don't (Claude Code and pi: no terminal at all; Codex:
    a pseudo-terminal on stdin but no controlling terminal), and it lets the human pipe a body in
    (`xt send … <<'XT_END'`)."""
    if os.environ.get(AGENT_ENV) or under_harness():
        return False
    # Not stdin: a Codex command in its pseudo-terminal mode has a terminal on stdin but no
    # controlling terminal (rc1 accepted that; card #103, found in acceptance).
    return controlling_terminal()


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


def _delegated(ctx: Ctx, who: str, command: str, what: str, refusal: str) -> None:
    """The human runs it; an operator only under an active delegation (card #166, recorded);
    anyone else gets the command's usual refusal."""
    if who == HUMAN:
        return
    if not operators.is_operator(ctx.paths, who):
        raise XtError(refusal)
    operators.delegated(ctx, who, command, what)


def cmd_up(args) -> None:
    from .up import up

    ctx = Ctx.load()
    if getattr(args, "as_", None) and operators.is_operator(ctx.paths, args.as_):  # card #166
        _delegated(ctx, _who(args, operator=True), "up", "up", "")
    for line in up(ctx):
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
            if args.at and args.at not in (ALWAYS, "off"):
                from .team import check_at

                check_at(args.at, args.every, args.between or target.wake_between)
            rid = Approvals(ctx).add({"kind": "schedule", "requester": who, "name": args.name,
                                      "every": args.every, "message": args.message,
                                      "between": args.between, "at": args.at})
            print(f"approval #{rid} requested from the human; you'll get a message when it's decided")
            return
    ctx.team.set_schedule(args.name, None if off else args.every, args.message, args.between, args.at)
    ctx.team.save()
    ctx.reload_team()
    if off:
        print(f"{args.name}: no scheduled wake-ups")
    else:
        a = ctx.team.agent(args.name)
        print(f"{args.name}: woken {schedule_text(a)} when idle (by the supervisor)"
              + (f": {a.wake_message}" if a.wake_message else ""))
        from .watch import next_wake

        nxt = next_wake(ctx, a)
        if nxt:
            print(f"next wake-up: {dt.datetime.fromtimestamp(nxt):%a %d %b %H:%M}")


def cmd_down(args) -> None:
    if _who(args) != HUMAN:
        raise XtError("only the human takes the team down")
    from .up import down

    for line in down(Ctx.load(), keep_supervisor=args.keep_supervisor):
        print(line)


def cmd_version(args) -> None:
    from . import switch

    ctx = Ctx.load()
    if args.action == "show":
        for line in switch.show(ctx):
            print(line)
        return
    if args.action == "check":  # card #133: ask the upstream now, then show what status shows
        from . import versions

        print(versions.refresh_published(ctx, dt.datetime.now().astimezone()))
        print(versions.current(ctx).line())
        return
    if _who(args) != HUMAN:
        raise XtError("only the human switches the team's xt version")
    if args.action == "use":
        if not args.tag:
            raise XtError("name the tag: xt version use vX.Y.Z (a candidate needs --candidate)")
        lines = switch.use(ctx, args.tag, candidate=args.candidate)
    else:
        lines = switch.rollback(ctx)
    for line in lines:
        print(line)


def cmd_send(args) -> None:
    ctx = Ctx.load()
    body = _body(args)
    if args.option or args.recommend is not None:
        if args.type != "ask":
            raise XtError("--option and --recommend belong to a question: add --type ask. Nothing was sent.")
        from .choices import render

        body = render(body, args.option or [], args.recommend)  # refuses a malformed set before sending
    who = _who(args, operator=True)
    if operators.is_operator(ctx.paths, who):  # card #166: a report to the liaison, marked as such
        msg, status = operators.send(ctx, who, args.to, args.type, body, args.ref)
    else:
        msg, status = send(ctx, who, args.to, args.type, body, args.ref)
    print(f"#{msg['id']} {msg['type']} → {msg['to']}: {status}")


def cmd_done(args) -> None:
    ctx = Ctx.load()
    who = _who(args)
    item = ctx.ledger.item(args.id)
    if item is None:
        raise XtError(f"#{args.id} is not an open goal or task")
    to = done_recipient(ctx.team, who, item)
    msg, status = send(ctx, who, to, "done", _body(args, "done"), args.id)
    print(f"#{msg['id']} done for #{args.id} → {to}: {status}")


def cmd_answer(args) -> None:
    ctx = Ctx.load()
    who = _who(args)
    item = ctx.ledger.item(args.id)
    if item is None or item["type"] != "ask":
        raise XtError(f"#{args.id} is not an open question (see `xt inbox`)")
    if who != item["owner"]:
        raise XtError(f"#{args.id} is a question for {item['owner']}, not {who}")
    from .choices import resolve

    question = ctx.ledger.message(args.id) or {}
    text, chosen = resolve(question.get("body", ""), _body(args))  # "2" → the option's full text
    msg, status = send(ctx, who, item["opener"], "report", text, args.id)
    print(f"#{msg['id']} answer to #{args.id} → {item['opener']}: {status}"
          + (f" (recorded as: {text})" if chosen else ""))


def cmd_friction(args) -> None:
    ctx = Ctx.load()
    msg, status = send(ctx, _who(args), HUMAN, "friction", _body(args), args.ref)
    print(f"#{msg['id']} friction: {status}")


def cmd_note(args) -> None:
    ctx = Ctx.load()
    msg, status = send(ctx, _who(args), "", "note", _body(args), args.ref)
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


LOG_LIMIT = 20  # plain `xt log`: the newest messages only (card #113)
WATCH_LIMIT = 50  # `xt log --watch`: the newest supervisor events


def cmd_log(args) -> None:
    if args.limit is not None and args.limit < 1:
        raise XtError("--limit needs a number of 1 or more (`--full` prints everything)")
    ctx = Ctx.load()
    if args.watch:
        from .watch import watch_log

        lines = watch_log(ctx, args.limit or WATCH_LIMIT)
        print("\n".join(lines) if lines else "(no supervisor events yet)")
        return
    shown = [m for m in ctx.ledger.messages(since_days=args.since)
             if not (args.member and args.member not in (m["from"], m["to"]))
             and not (args.id and args.id not in (m["id"], m.get("ref")))
             and not (args.type and m["type"] != args.type)]
    # Filters first, then the newest N (card #113). `--id` keeps its whole thread unless --limit
    # is given: it was already short, and cutting a thread would hide the message asked for.
    limit = None if args.full else args.limit or (None if args.id else LOG_LIMIT)
    left_out = max(0, len(shown) - limit) if limit else 0
    if left_out:
        shown = shown[left_out:]
        print(f"({left_out} older message{'s' if left_out != 1 else ''} not shown; "
              f"`--limit N` for more, `--full` for all)")
    for m in shown:
        ref = f" ref:#{m['ref']}" if m.get("ref") is not None else ""
        print(f"#{m['id']} {m['ts']} {m['type']} {m['from']}→{m['to']}{ref}")
        print("   " + m["body"].replace("\n", "\n   "))
    if not shown:
        print("(no messages)")


def cmd_status(args) -> None:
    ctx = Ctx.load()
    live = ctx.herdr.agents()
    items = ctx.ledger.open_items()
    print(f"team {ctx.team.name} · session {ctx.team.session}")
    from . import turns, usage, versions

    print(versions.current(ctx, live_names=set(live)).line())

    contexts = usage.readings(ctx, [a.name for a in ctx.team.agents() if a.kind != HUMAN and a.active])
    adapters = load_adapters(ctx.paths)
    spend = turns.today(ctx)
    from .reset import queued, queued_text

    resets = queued(ctx)
    from . import launch

    launched = launch.check(ctx, live)  # card #165
    launch.alert(ctx, launched, live)
    for a in ctx.team.agents():
        if a.kind == HUMAN:
            continue
        state = live[a.name].status if a.name in live else ("not running" if a.active else "retired")
        mine = sum(1 for i in items if i["owner"] == a.name)
        ctx_txt = usage.compact(contexts[a.name]) if a.name in contexts and a.name in live else "—"
        today_txt = turns.fmt_short(spend.agents_today[a.name]) if a.name in spend.agents_today else "—"
        from .watch import next_wake

        nxt = next_wake(ctx, a) if a.active else None
        today_txt += f"  next wake {dt.datetime.fromtimestamp(nxt):%a %H:%M}" if nxt else ""
        print(f"  {a.name:<12} {a.role or '':<12} {harness_model(a.harness, a.model):<18} {state:<12} "
              f"open:{mine:<3} context:{ctx_txt:<12} today:{today_txt}")
        if a.name in live and a.name in contexts and contexts[a.name].reason == usage.NOT_FOUND:
            # blanks with no reason looked like nothing to read (card #167)
            print(f"  {'':<12} no session log found for {a.name}: its context and today's usage can't be read")
        settings_path = permissions.shown(ctx.team, a, adapters.get(a.harness))
        if settings_path:
            print(f"  {'':<12} settings: {settings_path}")
        opts = launch.codex_options_line(ctx, a, a.name in live)
        if opts:
            print(f"  {'':<12} {opts}")
        if a.name in resets:
            print(f"  {'':<12} {queued_text(resets[a.name])}")
        state_launch, why = launched.get(a.name, (None, ""))
        if state_launch == launch.MISSING:
            print(f"  {'':<12} WARNING: {launch.warning(a.name)}")
        elif state_launch == launch.UNCHECKED:
            print(f"  {'':<12} launch settings: not checked ({why})")
    from .jobs import Jobs
    from .reset import suggestion
    from .watch import watch_pid

    now = dt.datetime.now(dt.timezone.utc).astimezone()
    for name, reading in contexts.items():
        tip = suggestion(name, reading, now) if name in live else None
        if tip:
            print(tip)
    q = Queue(ctx).pending()
    jobs = Jobs(ctx).pending()
    questions = sum(1 for i in items if i["type"] == "ask")
    print(f"open goals/tasks: {len(items) - questions} · questions for the human: {questions} · "
          f"queued messages: {len(q)} · jobs: {len(jobs)} · "
          f"pending approvals: {len(Approvals(ctx).pending())} · alerts: {len(Alerts(ctx).active())}")
    print(f"team usage today: {turns.fmt(spend.team_today)}")
    for line in turns.allowance_lines(ctx):
        print(f"allowance: {line}")
    from .boardwatch import status_line

    board = status_line(ctx)  # card #135
    if board:
        print(board)
    for line in operators.active_grants(ctx):  # card #166
        print(f"delegation: {line}")
    from .watch import recently_ticked

    if not watch_pid(ctx) and not recently_ticked(ctx):  # said plainly whenever it's down (card #165)
        if launch.isolated():  # its pid is invisible from a sandbox, so its absence proves nothing
            print("the supervisor: not checked (this shell runs in a sandbox, with its own PID namespace or /proc, and the "
                  "supervisor hasn't saved live state in the last 30 s); `xt status` in your own terminal tells")
        else:
            waiting = " Queued messages and jobs wait for it." if q or jobs else ""
            print(f"the supervisor isn't running: no messages are delivered, no alerts raised and nobody is "
                  f"woken until it runs.{waiting} `xt up` starts it.")


def cmd_restart(args) -> None:
    who = _who(args, operator=True)
    from .up import restart

    if bool(args.names) == args.all:
        raise XtError("name the agents to restart, or pass --all (the whole team and the supervisor)")
    ctx = Ctx.load()
    if args.all and who != HUMAN:  # --all takes the team down first: `down` is never delegated (#166)
        raise XtError("only the human restarts agents with --all (it takes the team down first)")
    _delegated(ctx, who, "restart", f"restart {' '.join(args.names)}", "only the human restarts agents")
    for line in restart(ctx, args.names, args.all):
        print(line)


def cmd_reset(args) -> None:
    who = _who(args, operator=True)
    from .reset import cancel, preflight, queue, reset

    ctx = Ctx.load()
    what = f"reset {args.name}" + (" --when-idle" if args.when_idle else " --cancel" if args.cancel else "")
    _delegated(ctx, who, "reset", what, "only the human resets an agent's context")
    if args.cancel:
        print(cancel(ctx, args.name))
        return
    if args.when_idle:  # card #134
        from .watch import watch_pid

        print(queue(ctx, args.name))
        if not watch_pid(ctx):
            print("the supervisor isn't running: the queued reset waits for it (`xt up`)")
        return
    preflight(ctx, args.name)  # refuse before announcing anything (rc1 QA)
    print(f"asking {args.name} to save a checkpoint (up to {int(args.timeout)} s)…", flush=True)
    for line in reset(ctx, args.name, timeout=args.timeout):
        print(line)


def cmd_checkpoint(args) -> None:
    who = _who(args)
    if who == HUMAN:
        raise XtError("agents confirm their own checkpoint: pass --as <your name>")
    from .reset import record_checkpoint

    print(record_checkpoint(Ctx.load(), who, _body(args)))


DONE_DAYS = 30  # how far back the Inbox looks, as the TUI does (model.HISTORY_DAYS)


def cmd_inbox(args) -> None:
    """The Inbox in the TUI's three groups, empty ones left out (card #127). In the human's own
    terminal the listing counts as a look: New clears and the friction it printed is seen. An
    agent's listing changes nothing."""
    from . import inbox
    from .choices import options_of
    from .goaldone import first_line, mark_seen

    ctx = Ctx.load()
    msgs = list(ctx.ledger.messages(since_days=args.days))
    box = inbox.build(ctx, msgs)
    one = lambda text, n=160: " ".join(text.split())[:n]
    printed = False
    if box.questions or box.approvals or box.alerts:
        print("Needs you:")
        bodies = {m["id"]: m["body"] for m in msgs}
        for q in box.questions:
            n = len(options_of(bodies.get(q["id"], "")))
            opts = f"  {n} options" if n else ""
            print(f"  ⚑ #{q['id']} {q['opened'][5:16]} from {q['opener']}: {q['title']}{opts}  "
                  f"(xt answer {q['id']} \"...\")")
        for rid, r in box.approvals:
            print(f"  ⚑ #{rid} {r['requester']} → {approval_what(r)}  xt approve {rid} | xt deny {rid}")
        for k, a in box.alerts:
            print(f"  ⚠ #{a['id']} {a['ts'][5:16]} {a['text']}{repeats(a)}  (clear: xt clear {k})")
        printed = True

    def more(n: int) -> None:
        if n > 0:
            print(f"  … {n} more (xt inbox --limit {args.limit + n})")

    if box.new:
        print("New since you last looked:")
        for m, goal in box.new[:args.limit]:
            if goal:
                print(f"  ✓ #{goal['id']} {first_line(goal['body'], 80)} — done #{m['id']} {m['ts'][5:16]} by "
                      f"{m['from']}: {first_line(m['body'], 160)}  (xt log --id {goal['id']})")
            else:
                print(f"  ✉ #{m['id']} {m['ts'][5:16]} {m['type']} from {m['from']}: {one(m['body'])}")
        more(len(box.new) - args.limit)
        printed = True
    shown = box.unread[:args.limit]
    if box.unread or box.seen:
        print("Friction reported about xt or a harness:")
        for m in shown:
            print(f"  ✱ #{m['id']} {m['ts'][5:16]} {m['from']}: {one(m['body'])}")
        more(len(box.unread) - args.limit)
        if box.seen and args.seen:
            print(f"  ({len(box.seen)} older, seen)")
            for m in box.seen[:args.limit]:
                print(f"    #{m['id']} {m['ts'][5:16]} {m['from']}: {one(m['body'])}")
            more(len(box.seen) - args.limit)
        elif box.seen:
            print(f"  ({len(box.seen)} older, seen; xt inbox --seen lists them)")
        printed = True
    if not printed:
        print("Nothing for you.")
    if human_terminal():  # only the human's own look counts, never an agent's (cards #125, #127)
        mark_seen(ctx, box.upto)
        inbox.mark_friction_seen(ctx, [m["id"] for m in shown])


def cmd_clear(args) -> None:
    ctx = Ctx.load()
    print("cleared" if Alerts(ctx).resolve(args.key) else f"no alert {args.key!r}")


def cmd_approve(args, approve: bool = True) -> None:
    if _who(args) != HUMAN:
        raise XtError("only the human approves spawns")
    ctx = Ctx.load()
    if not args.ids:  # no ids: show what's waiting, with the commands
        pending = Approvals(ctx).pending()
        if not pending:
            print("nothing is waiting for your approval")
        for rid, r in sorted(pending.items(), key=lambda kv: int(kv[0])):
            print(f"#{rid} {r['requester']} → {approval_what(r)}  (xt approve {rid} | xt deny {rid})")
        if len(pending) > 1:
            print(f"all of them: xt {'approve' if approve else 'deny'} {' '.join(sorted(pending, key=int))}")
        return
    for rid in args.ids:
        try:
            print(f"#{rid}: {decide(ctx, rid, approve)}")
        except XtError as e:
            print(f"#{rid}: {e}")


def cmd_spawn(args) -> None:
    ctx = Ctx.load()
    who = _who(args, operator=True)
    if operators.is_operator(ctx.paths, who):  # card #166: an existing agent, as it is, under a grant
        a = ctx.team.agent(args.name)
        if a is None or a.kind == HUMAN or not a.active:
            raise XtError(f"operator {who} may only start an existing agent; {args.name!r} isn't one")
        if args.harness or args.model or args.role or args.reports_to or args.permissions:
            raise XtError(f"operator {who} starts {args.name} as it is in team.toml: no --harness, --model, "
                          f"--role, --reports-to or --permissions")
        _delegated(ctx, who, "spawn", f"spawn {args.name}", "")
        who = HUMAN
    print(request_spawn(ctx, who, args.name, args.harness, args.model, args.role, args.reports_to,
                        args.permissions))


def cmd_operator(args) -> None:
    """Card #166: register, list and remove operators (human only, except `pid` and `list`)."""
    if args.action == "pid":  # run by the operator itself: what the human registers
        found = operators.harness_ancestor()
        if found is None:
            print(f"no harness process above this one; this shell's own process is {os.getppid()}")
        else:
            print(f"{found[0]} ({found[1]}): give the human this pid for `xt operator add NAME --pid {found[0]}`")
        return
    ctx = Ctx.load()
    if args.action == "list":
        for line in operators.listing(ctx):
            print(line)
        return
    if _who(args) != HUMAN:
        raise XtError("only the human registers or removes operators, from their own terminal")
    if not args.name:
        raise XtError(f"name the operator: xt operator {args.action} NAME")
    if args.action == "add":
        if args.pid is None:
            raise XtError("pass the operator's process: --pid PID (the operator's `xt operator pid` prints it)")
        for line in operators.add(ctx, args.name, args.pid):
            print(line)
    else:
        print(operators.remove(ctx, args.name))


def cmd_delegate(args) -> None:
    """Card #166: a time-bound grant of the delegable commands to an operator (human only)."""
    if _who(args) != HUMAN:
        raise XtError("only the human grants or revokes delegation, from their own terminal")
    ctx = Ctx.load()
    if args.revoke:
        print(operators.revoke(ctx, args.name))
        return
    if not args.name:
        raise XtError("name the operator: xt delegate NAME --for 30m")
    only = [c for part in (args.only or []) for c in part.split(",")]
    print(operators.grant(ctx, args.name, args.for_, only))


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
        print(f"   desktop/browser tools for agents: {a.desktop_tools or 'not restricted'}"
              + (f" ({a.desktop_tools_note})" if a.desktop_tools_note else ""))
        print(f"   account connectors for agents: {a.connectors or 'not restricted'}"
              + (f" ({a.connectors_note})" if a.connectors_note else ""))
        print(f"   per-agent settings file (`permissions` in team.toml): "
              + (f"yes, passed with {a.settings_flag}" if a.settings_flag else "not supported"))
        print("   per-agent options (`codex_options` in team.toml, Codex only): "
              + (f"yes, passed with -c; allowed: {allowed_codex_options()}" if a.name == CODEX else "not supported"))


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
    sp.add_argument("--at", metavar="HH:MM",
                    help="daily or longer schedules: wake at this local time (inside the window, if any; "
                         "'off' removes it). Without it, a daily schedule with a window wakes at the window's start")
    sp.add_argument("--between", metavar="HH:MM-HH:MM",
                    help="only wake within this local-time window, e.g. 05:00-21:00 (may wrap midnight; "
                         "'always' removes it; left out: keep the current one)")

    sp = add("down", cmd_down, "stop every running agent and the supervisor (human only)")
    sp.add_argument("--keep-supervisor", action="store_true", help="stop the agents only")

    sp = add("version", cmd_version, "show, check (ask the upstream for the published version now), select (use) "
                                     "or roll back the team's xt version (use/rollback: human only)")
    sp.add_argument("action", nargs="?", choices=("show", "check", "use", "rollback"), default="show")
    sp.add_argument("tag", nargs="?", help="for use: an upstream release tag, e.g. v0.14.0")
    sp.add_argument("--candidate", action="store_true", help="allow a release candidate tag (vX.Y.Z-rcN)")

    sp = add("send", cmd_send, "send a message through xt (the only sanctioned way agents talk)")
    sp.add_argument("to")
    sp.add_argument("--type", choices=AGENT_TYPES, default="report")
    sp.add_argument("--ref", type=int, help="goal/task/message id this is about")
    sp.add_argument("--option", action="append", metavar="'OPTION :: CONSEQUENCE'",
                    help="with --type ask: one of two or three numbered options (repeat the flag)")
    sp.add_argument("--recommend", type=int, metavar="N", help="with --option: the option you recommend")
    sp.add_argument("body", nargs="*", help="message text (or stdin)")

    sp = add("done", cmd_done, "close an open goal or task you own (reports to whoever opened it)")
    sp.add_argument("id", type=int)
    sp.add_argument("body", nargs="*")

    sp = add("answer", cmd_answer, "answer a question the liaison asked you (see `xt inbox`)")
    sp.add_argument("id", type=int)
    sp.add_argument("body", nargs="*", help="your answer (or stdin)")

    sp = add("friction", cmd_friction,
             "report friction with xt or your harness to the human (not delivered to anyone's pane)")
    sp.add_argument("--ref", type=int, help="the message it happened with, if any")
    sp.add_argument("body", nargs="*", help="what happened, what it cost, a suggested fix (or stdin)")

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
    sp.add_argument("--watch", action="store_true", help="the supervisor's events instead of messages")
    sp.add_argument("--limit", type=int, metavar="N",
                    help=f"the newest N messages (default {LOG_LIMIT}), or with --watch events (default {WATCH_LIMIT})")
    sp.add_argument("--full", action="store_true", help="the whole message history")

    add("status", cmd_status, "one-shot team status")

    sp = add("inbox", cmd_inbox, "what needs the human, what's new, and unread friction")
    sp.add_argument("--days", type=int, default=DONE_DAYS, help=f"how far back to look (default {DONE_DAYS})")
    sp.add_argument("--limit", type=int, default=20, help="rows per group (default 20)")
    sp.add_argument("--seen", action="store_true", help="also list the friction you have already seen")

    sp = add("clear", cmd_clear, "dismiss an alert")
    sp.add_argument("key")

    sp = add("approve", lambda a: cmd_approve(a, True),
             "approve pending hires and schedules (one or more ids; none: list what's waiting)")
    sp.add_argument("ids", type=int, nargs="*", metavar="id")
    sp = add("deny", lambda a: cmd_approve(a, False), "deny pending hires and schedules (one or more ids)")
    sp.add_argument("ids", type=int, nargs="*", metavar="id")

    sp = add("spawn", cmd_spawn, "start an agent (new: needs --harness and --role; existing: restarts it)")
    sp.add_argument("name")
    sp.add_argument("--harness")
    sp.add_argument("--model")
    sp.add_argument("--role")
    sp.add_argument("--reports-to")
    sp.add_argument("--permissions", metavar="FILE",
                    help="Claude Code settings file for the agent, relative to the team repo")

    sp = add("retire", cmd_retire, "close an agent's workspace and mark it retired")
    sp.add_argument("name")
    sp = add("restart", cmd_restart,
             "restart agents with fresh instructions (after an update): names, or --all for the "
             "whole team and the supervisor (human only)")
    sp.add_argument("names", nargs="*", metavar="name")
    sp.add_argument("--all", action="store_true")

    sp = add("reset", cmd_reset,
             "give one agent a fresh context safely: refused while it owns open work; it saves a "
             "checkpoint to its notes first (human only; `restart` is the route without a checkpoint)")
    sp.add_argument("name")
    sp.add_argument("--timeout", type=float, default=300, help="seconds to wait for the checkpoint (default 300)")
    when = sp.add_mutually_exclusive_group()
    when.add_argument("--when-idle", action="store_true",
                      help="queue the reset and return: the supervisor runs it when the agent is idle with no open work")
    when.add_argument("--cancel", action="store_true", help="remove a queued reset")
    sp = add("checkpoint", cmd_checkpoint,
             "confirm that your notes hold what a fresh session needs (asked for by `xt reset`); "
             "text on stdin: what the next session should know first")
    sp.add_argument("body", nargs="*")

    sp = add("stop", cmd_stop, "close an agent's workspace, keep it in the roster (human only)")
    sp.add_argument("name")

    sp = add("operator", cmd_operator,
             "outside operators acting for the human: add NAME --pid PID, remove NAME, list (add/remove: "
             "human only); pid: run by the operator, prints the process to register")
    sp.add_argument("action", choices=("add", "remove", "list", "pid"))
    sp.add_argument("name", nargs="?")
    sp.add_argument("--pid", type=int, help="for add: the operator's process (its harness)")

    sp = add("delegate", cmd_delegate,
             f"let an operator run {', '.join(operators.DELEGABLE)} for a while (human only): "
             f"xt delegate NAME [--for 30m] [--only restart,reset]; xt delegate [NAME] --revoke")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--for", dest="for_", metavar="DURATION",
                    help=f"how long, at most 60m (default {operators.DEFAULT_GRANT})")
    sp.add_argument("--only", action="append", metavar="COMMANDS",
                    help=f"limit the grant to some of: {', '.join(operators.DELEGABLE)} (comma-separated)")
    sp.add_argument("--revoke", action="store_true", help="end the grant now (without NAME: every grant)")

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
