"""`xt watch`: the supervisor. Delivers queued messages, runs the heartbeat, alerts the human.

It alerts, it never repairs: a crashed agent is a bug to look at, not something to restart.
"""

import datetime as dt
import json
import os
import shlex
import shutil
import subprocess
import time

from .alerts import FAILURES, Alerts
from .context import Ctx
from .dispatch import Queue, drain, send, waiting_on_human
from .herdr import DELIVERABLE
from .jobs import Jobs, run_pending
from .paths import XtError
from .team import HUMAN, SYSTEM, in_window, next_due, schedule_text

TICK = 3
NUDGES_BEFORE_ALERT = 2
WATCH_LOG_MAX = 512 * 1024  # .xt/state/watch.log is rotated to watch.log.1 beyond this
USAGE_EVERY = 60  # seconds between reads of the agents' session logs for per-turn usage
NOTIFY_TYPES = {"ask": "question from {from_}", "approval": "approval needed", "alert": "alert"}


def run_notify(argv: list[str]) -> str | None:
    """Run the notify command; returns an error text, or None when it worked."""
    if shutil.which(argv[0]) is None:
        return f"{argv[0]} not found"
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return None if r.returncode == 0 else (r.stderr.strip() or f"exit {r.returncode}")[:200]


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def watch_log(ctx: Ctx, limit: int = 200) -> list[str]:
    """The supervisor's latest events, oldest first: "YYYY-MM-DD HH:MM:SS text" lines."""
    lines: list[str] = []
    for f in (ctx.paths.state / "watch.log.1", ctx.paths.state / "watch.log"):
        if f.exists():
            lines += f.read_text(errors="replace").splitlines()
    return lines[-limit:]


def next_wake(ctx: Ctx, a) -> float | None:
    """When the supervisor will next wake this agent (None: no schedule, or not seen yet)."""
    if not a.wake_every:
        return None
    try:
        last = json.loads((ctx.paths.state / "wakes.json").read_text()).get(a.name)
    except (OSError, ValueError):
        last = None
    return next_due(a, last) if last is not None else None


def watch_pid(ctx: Ctx) -> int | None:
    f = ctx.paths.state / "watch.pid"
    if not f.exists():
        return None
    pid = int(f.read_text().strip() or 0)
    return pid if pid and pid_alive(pid) else None


TICKED_WITHIN = 30  # seconds: a supervisor that saved live state this recently is running


def recently_ticked(ctx: Ctx) -> bool:
    """The supervisor saved Herdr's agent list (state/live.json) in the last few ticks. Its pid can
    be invisible from a sandboxed shell (a PID namespace) while it runs fine (card #165, rc2)."""
    try:
        ts = json.loads((ctx.paths.state / "live.json").read_text())["ts"]
        age = (ctx.ledger.clock() - dt.datetime.fromisoformat(ts)).total_seconds()
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return -TICKED_WITHIN <= age <= TICKED_WITHIN


def expected(ctx: Ctx) -> set[str]:
    """Agents xt started and hasn't stopped/retired: if one vanishes, something went wrong."""
    f = ctx.paths.state / "expected.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def set_expected(ctx: Ctx, name: str, present: bool) -> None:
    with ctx.ledger.lock():
        names = expected(ctx)
        (names.add if present else names.discard)(name)
        f = ctx.paths.state / "expected.json"
        f.write_text(json.dumps(sorted(names)))


def stopped(ctx: Ctx) -> set[str]:
    """Agents the human stopped on purpose (`xt stop`, `xt down`, `x` in the TUI) and nobody has
    started since: not running is what the human wants, so nothing alerts about it."""
    f = ctx.paths.state / "stopped.json"
    return set(json.loads(f.read_text())) if f.exists() else set()


def set_stopped(ctx: Ctx, name: str, present: bool) -> None:
    with ctx.ledger.lock():
        names = stopped(ctx)
        (names.add if present else names.discard)(name)
        (ctx.paths.state / "stopped.json").write_text(json.dumps(sorted(names)))


class Supervisor:
    def __init__(self, ctx: Ctx, out=print):
        self.ctx = ctx
        self.out = out
        self.alerts = Alerts(ctx)
        self.last_heartbeat = 0.0
        self.last_rotate = 0.0
        self.last_usage = 0.0
        self.published_checked = False  # the first tick refreshes the published version (card #133)
        self.usage_error: str | None = None
        self.nudges_path = ctx.paths.state / "nudges.json"
        self.notify_error: str | None = None
        self.quiet_ids: set[int] = set()  # alerts about a failed notification: never notified
        self.policy_problems: set[str] = set()  # bad auto-reset settings already said (card #114)
        from .boardwatch import BoardWatch

        self.board = BoardWatch(ctx)  # card #135

    def failed(self, kind: str, error: str) -> None:
        """A failed wake-up, notification or usage recording raises an Inbox alert (card #131); a
        repeat while it is open counts on the same alert. The supervisor log keeps the detail."""
        first = (str(error).strip().splitlines() or ["(no error text)"])[0]
        msg = self.alerts.raise_or_count(FAILURES[kind], f"{kind} failed: {first}")
        if msg and kind == "notification":
            self.quiet_ids.add(msg["id"])  # a notification about it would fail the same way

    def say(self, text: str) -> None:
        """Print an event in the supervisor's pane and keep it in .xt/state/watch.log (the TUI's
        Supervisor panel and `xt log --watch` read it)."""
        now = dt.datetime.now()
        self.out(f"{now:%H:%M:%S} {text}")
        path = self.ctx.paths.state / "watch.log"
        try:
            if path.exists() and path.stat().st_size > WATCH_LOG_MAX:
                path.replace(path.with_name("watch.log.1"))
            with open(path, "a") as fh:
                fh.write(f"{now:%Y-%m-%d %H:%M:%S} {' '.join(text.split())}\n")
        except OSError:
            pass  # the pane still shows it; a full disk must not stop the supervisor

    def tick(self, now: float | None = None) -> None:
        now = now if now is not None else time.time()
        self.ctx.reload_team()
        for line in run_pending(self.ctx):
            self.say(line)
        live = self.ctx.herdr.agents()
        self.ctx.herdr.save_snapshot(live, self.ctx.ledger.clock().isoformat(timespec="seconds"))
        for line in drain(self.ctx):
            self.say(line)
        self.check_agents(live)
        self.run_resets()
        self.check_volume()
        if now - self.last_heartbeat >= 60 * int(self.ctx.team.policy("heartbeat_minutes")):
            self.last_heartbeat = now
            self.heartbeat(live)
        self.wake_scheduled(live, now)
        self.notify_human(now)
        if now - self.last_usage >= USAGE_EVERY:
            self.last_usage = now
            self.record_usage()
            self.auto_reset()
            self.check_launch(live)
        self.check_published()
        self.watch_board(now)
        if now - self.last_rotate >= 3600:
            self.last_rotate = now
            for line in self.ctx.ledger.rotate(
                int(self.ctx.team.log_setting("raw_days")), int(self.ctx.team.log_setting("delete_after_days"))
            ):
                self.say(line)

    def check_published(self) -> None:
        """The newest published xt release, at most every few hours (card #58): agents' shells often
        have no network, so status and briefs only ever read this cache. Once at start too, whatever
        the cache's age (card #133): a restart after a release must not keep showing the old one. The
        check runs in the loop, so a failing or slow one never holds up the start."""
        from . import versions

        now = dt.datetime.now(dt.timezone.utc).astimezone()
        if not self.published_checked or versions.published_due(self.ctx, now):
            self.published_checked = True
            self.say(versions.refresh_published(self.ctx, now))

    def watch_board(self, now: float) -> None:
        """The team's board command, if it has one (card #135). Its own failures become its alert;
        a bug here must never stop the supervisor."""
        try:
            for line in self.board.tick(now):
                self.say(line)
        except Exception as e:  # noqa: BLE001
            self.say(f"board watch error: {type(e).__name__}: {e}")

    def check_agents(self, live: dict) -> None:
        team = self.ctx.team
        blocked = {n for n, a in live.items() if a.status == "blocked" and team.agent(n)}
        for n in blocked:
            if self.alerts.raise_(f"blocked:{n}", f"{n} is blocked (usually an approval prompt) — look at its pane"):
                self.say(f"alert: {n} blocked")
        self.alerts.resolve_prefix("blocked:", {f"blocked:{n}" for n in blocked})

        missing = {n for n in expected(self.ctx) if n not in live and team.agent(n) and team.agent(n).active}
        keep = {f"missing:{n}" for n in missing}
        for n in missing:
            if self.alerts.raise_(
                f"missing:{n}",
                f"{n} is not running although xt started it (crashed or closed outside xt). "
                f"Look into why, then `xt spawn {n}` to start it again.",
            ):
                self.say(f"alert: {n} not running")

        goals_open = any(i["type"] == "goal" for i in self.ctx.ledger.open_items())
        lead = team.lead_of_role("lead")
        starting = {j["args"].get("name") for j in Jobs(self.ctx).pending() if j["kind"] in ("start", "spawn")}
        if lead and goals_open and lead.name not in live and lead.name not in missing \
                and lead.name not in starting and lead.name not in stopped(self.ctx):
            keep.add(f"missing:{lead.name}")
            if self.alerts.raise_(f"missing:{lead.name}", f"{lead.name} is not running but goals are open — `xt up`"):
                self.say(f"alert: {lead.name} not running, goals open")
        # Resolve only after every check has had its say, so an alert raised above isn't
        # cleared in the same pass and raised again on the next one (it spammed every 3 s).
        self.alerts.resolve_prefix("missing:", keep)

    def run_resets(self) -> None:
        """Queued resets (card #134): one non-blocking step each. Live state is read again, after
        this tick's deliveries, so an agent that just got a message isn't asked for a checkpoint."""
        from . import reset

        if not reset.queued(self.ctx):
            return
        pending_to = {i["to"] for i in Queue(self.ctx).pending()}
        for line in reset.advance(self.ctx, self.ctx.herdr.agents(), pending_to):
            self.say(line)

    def check_launch(self, live: dict) -> None:
        """Agents running without xt's launch settings, e.g. resumed by a restored multiplexer
        session (card #165): one alert each, cleared when xt starts the agent again."""
        from . import launch

        for name in launch.alert(self.ctx, launch.check(self.ctx, live), live):
            self.say(f"alert: {name} runs without xt's launch settings")

    def auto_reset(self) -> None:
        """The automatic reset policy (card #114, off by default): queues resets that run_resets
        then performs. A bad setting is said once in the log, not on every check."""
        from . import reset, usage

        team = self.ctx.team
        if team.policy("auto_reset") is not True:
            return
        live = self.ctx.herdr.agents()
        names = [a.name for a in team.agents() if a.kind != HUMAN and a.active and a.name in live]
        pending_to = {i["to"] for i in Queue(self.ctx).pending()}
        lines, problems = reset.apply_policy(self.ctx, live, pending_to, usage.readings(self.ctx, names))
        for line in lines:
            self.say(line)
        for p in problems:
            if p not in self.policy_problems:
                self.say(f"auto reset: {p}")
        self.policy_problems = set(problems)

    def check_volume(self) -> None:
        limit = int(self.ctx.team.log_setting("daily_alert_mb")) * 1024 * 1024
        if self.ctx.ledger.today_size() > limit:
            day = dt.date.today().isoformat()
            if self.alerts.raise_(f"volume:{day}", f"today's message log is over {limit // 1048576} MB — probably a message loop"):
                self.say("alert: log volume")

    def wake_scheduled(self, live: dict, now: float) -> None:
        """Send a `wake` to agents whose schedule is due, only when they're idle and have nothing
        queued, so a wake-up never interrupts work. The clock starts when a schedule is first seen,
        so restarting the supervisor doesn't wake everyone at once. Daily schedules with a window
        or --at wake at that local time each day (see team.next_due). Outside an agent's
        `wake_between` window nobody is woken; an overdue agent gets one wake-up, not one per
        missed interval."""
        path = self.ctx.paths.state / "wakes.json"
        last = json.loads(path.read_text()) if path.exists() else {}
        queued = {i["to"] for i in Queue(self.ctx).pending()}
        changed = False
        for a in self.ctx.team.agents():
            if not (a.wake_every and a.active):
                if a.name in last:
                    del last[a.name]
                    changed = True
                continue
            if a.name not in last:
                last[a.name] = now
                changed = True
                continue
            agent = live.get(a.name)
            if now < next_due(a, last[a.name]) or agent is None \
                    or agent.status not in DELIVERABLE or a.name in queued \
                    or not in_window(a.wake_between, dt.datetime.fromtimestamp(now)):
                continue
            body = (a.wake_message or "Scheduled wake-up: do your role's periodic duty, report anything "
                    "worth reporting to the agent you report to, then stop.")
            try:
                send(self.ctx, SYSTEM, a.name, "wake", f"{body}\n(schedule: {schedule_text(a)})")
                self.say(f"woke {a.name} ({schedule_text(a)})")
            except XtError as e:
                self.say(f"wake-up for {a.name} failed: {e}")
                self.failed("wake-up", f"{a.name}: {e}")
            last[a.name] = now
            changed = True
        if changed:
            path.write_text(json.dumps(last))

    def notify_human(self, now: float) -> None:
        """Tell the human, outside the notify quiet window, about each new question, approval
        request and alert addressed to them, and once about each goal they dispatched when it's
        done (card #125, see goaldone.py). Counting starts when the supervisor first runs, so an
        old backlog never floods the desktop; what arrives in quiet hours is not sent later (it's
        in the Inbox)."""
        from .goaldone import Notices, seen_upto
        from .inbox import friction_marker

        seen_upto(self.ctx)  # the Inbox's "done since you last looked" counts from the first run
        friction_marker(self.ctx)  # and so does unread friction (card #127)
        path = self.ctx.paths.state / "notified.json"
        seq = self.ctx.ledger.last_id()
        if not path.exists():
            path.write_text(json.dumps({"last": seq}))
            return
        last = json.loads(path.read_text()).get("last", 0)
        notices = Notices(self.ctx)
        if seq <= last and not notices.pending:
            return
        team = self.ctx.team
        quiet = team.notify_setting("quiet")
        send_now = bool(team.notify_setting("enabled")) and not (
            quiet and in_window(quiet, dt.datetime.fromtimestamp(now)))
        new = [m for m in self.ctx.ledger.messages(since_days=1) if m["id"] > last] if seq > last else []
        if any(m["type"] == "alert" for m in new):  # also after a restart of the supervisor
            quiet = self.alerts.active().get(FAILURES["notification"])
            if quiet:
                self.quiet_ids.add(quiet["id"])
        for m in new:
            if m["id"] in self.quiet_ids:
                continue
            if m["to"] == HUMAN and m["type"] in NOTIFY_TYPES:
                note = NOTIFY_TYPES[m["type"]].format(from_=m["from"]), m["body"]
            else:
                note = notices.see(m, now, new)  # goal closures and the liaison's reports
            if note and send_now:
                self._notify(*note, f"#{m['id']}")
        for title, body in notices.due(now):
            if send_now:
                self._notify(title, body, f"{title} (no liaison report)")
        notices.save()
        path.write_text(json.dumps({"last": max(seq, last)}))

    def _notify(self, what: str, body: str, about: str) -> None:
        team = self.ctx.team
        title = f"xt {team.name}: {what}"
        body = " ".join(body.split())
        body = body if len(body) <= 180 else body[:179] + "…"
        argv = [part.replace("{title}", title).replace("{body}", body)
                for part in shlex.split(str(team.notify_setting("command")))]
        err = run_notify(argv) if argv else "empty notify command"
        if err and err != self.notify_error:
            self.say(f"notification failed: {err} ([notify] in team.toml)")
        if err:
            self.failed("notification", err)
        else:
            self.say(f"notified the human about {about}")
        self.notify_error = err

    def record_usage(self) -> None:
        """Per-turn usage from the agents' session logs (see turns.py); a harness changing its log
        format must never stop the supervisor, so failures are reported once and skipped."""
        from . import turns

        try:
            turns.record(self.ctx)
            self.usage_error = None
        except Exception as e:  # noqa: BLE001
            msg = f"usage recording failed: {type(e).__name__}: {e}"
            if msg != self.usage_error:
                self.say(msg)
            self.usage_error = msg
            self.failed("usage recording", f"{type(e).__name__}: {e}")

    def _nudges(self) -> dict:
        return json.loads(self.nudges_path.read_text()) if self.nudges_path.exists() else {}

    def heartbeat(self, live: dict) -> None:
        queued = {i["to"] for i in Queue(self.ctx).pending()}
        nudges = self._nudges()
        period = dt.timedelta(minutes=int(self.ctx.team.policy("heartbeat_minutes")))
        now = self.ctx.ledger.clock()
        open_ids = set()
        waiting = waiting_on_human(self.ctx)
        items = self.ctx.ledger.open_items()
        # an owner whose item has open subtasks is waiting on its reports, not stuck
        delegated = {i["goal"] for i in items if i.get("goal") is not None and i["type"] == "task"}
        for item in items:
            key = str(item["id"])
            open_ids.add(key)
            owner = item["owner"]
            if owner == HUMAN or owner in queued or item["id"] in waiting or item["id"] in delegated:
                continue
            agent = live.get(owner)
            if agent is None or agent.status not in DELIVERABLE:
                continue
            # quiet since the owner last worked on it, or since it opened if it never has
            reported = item.get("last_from_owner")
            if now - dt.datetime.fromisoformat(reported or item["opened"]) < period:
                continue
            state = nudges.get(key, {"count": 0, "last": None})
            if reported and state["last"] and reported > state["last"]:
                state = {"count": 0, "last": None}
            count = state["count"]
            if count >= NUDGES_BEFORE_ALERT:
                self.alerts.raise_(
                    f"silent:{key}",
                    f"{owner} is idle with open {item['type']} #{key} ({item['title']}) and hasn't answered "
                    f"{count} nudges",
                )
                continue
            try:
                msg, _ = send(
                    self.ctx, SYSTEM, owner, "nudge",
                    f"Heartbeat: you're idle with open {item['type']} #{key} ({item['title']}). If you're "
                    f"finished, send `done --ref {key}` to {item['opener']}; if you're stuck or waiting, "
                    f"send a report or ask saying so.",
                )
                nudges[key] = {"count": count + 1, "last": msg["ts"]}
                self.say(f"nudged {owner} about #{key}")
            except XtError as e:
                self.say(f"nudge to {owner} failed: {e}")
        nudges = {k: v for k, v in nudges.items() if k in open_ids}
        self.nudges_path.write_text(json.dumps(nudges))


def run(ctx: Ctx) -> None:
    pid = watch_pid(ctx)
    if pid and pid != os.getpid():
        raise XtError(f"xt watch is already running (pid {pid})")
    pidfile = ctx.paths.state / "watch.pid"
    pidfile.write_text(str(os.getpid()))
    sup = Supervisor(ctx)
    from . import __version__, versions

    versions.record_supervisor(ctx, dt.datetime.now(dt.timezone.utc).astimezone())
    sup.say(f"xt watch {versions.display(__version__)} started for team {ctx.team.name} "
            f"(session {ctx.team.session}); ctrl+c to stop")
    try:
        while True:
            try:
                sup.tick()
            except XtError as e:
                sup.say(f"error: {e}")
            time.sleep(TICK)
    except KeyboardInterrupt:
        sup.say("stopped")
    finally:
        sup.board._stop()  # no board command outlives the supervisor
        if pidfile.exists() and pidfile.read_text().strip() == str(os.getpid()):
            pidfile.unlink()
