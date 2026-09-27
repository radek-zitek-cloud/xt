"""`xt watch`: the supervisor. Delivers queued messages, runs the heartbeat, alerts the human.

It alerts, it never repairs: a crashed agent is a bug to look at, not something to restart.
"""

import datetime as dt
import json
import os
import time

from .alerts import Alerts
from .context import Ctx
from .dispatch import Queue, drain, send
from .herdr import DELIVERABLE
from .jobs import Jobs, run_pending
from .paths import XtError
from .team import HUMAN, SYSTEM, in_window, parse_interval, schedule_text

TICK = 3
NUDGES_BEFORE_ALERT = 2


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def watch_pid(ctx: Ctx) -> int | None:
    f = ctx.paths.state / "watch.pid"
    if not f.exists():
        return None
    pid = int(f.read_text().strip() or 0)
    return pid if pid and pid_alive(pid) else None


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


class Supervisor:
    def __init__(self, ctx: Ctx, out=print):
        self.ctx = ctx
        self.out = out
        self.alerts = Alerts(ctx)
        self.last_heartbeat = 0.0
        self.last_rotate = 0.0
        self.nudges_path = ctx.paths.state / "nudges.json"

    def say(self, text: str) -> None:
        self.out(f"{dt.datetime.now():%H:%M:%S} {text}")

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
        self.check_volume()
        if now - self.last_heartbeat >= 60 * int(self.ctx.team.policy("heartbeat_minutes")):
            self.last_heartbeat = now
            self.heartbeat(live)
        self.wake_scheduled(live, now)
        if now - self.last_rotate >= 3600:
            self.last_rotate = now
            for line in self.ctx.ledger.rotate(
                int(self.ctx.team.log_setting("raw_days")), int(self.ctx.team.log_setting("delete_after_days"))
            ):
                self.say(line)

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
        if lead and goals_open and lead.name not in live and lead.name not in missing and lead.name not in starting:
            keep.add(f"missing:{lead.name}")
            if self.alerts.raise_(f"missing:{lead.name}", f"{lead.name} is not running but goals are open — `xt up`"):
                self.say(f"alert: {lead.name} not running, goals open")
        # Resolve only after every check has had its say, so an alert raised above isn't
        # cleared in the same pass and raised again on the next one (it spammed every 3 s).
        self.alerts.resolve_prefix("missing:", keep)

    def check_volume(self) -> None:
        limit = int(self.ctx.team.log_setting("daily_alert_mb")) * 1024 * 1024
        if self.ctx.ledger.today_size() > limit:
            day = dt.date.today().isoformat()
            if self.alerts.raise_(f"volume:{day}", f"today's message log is over {limit // 1048576} MB — probably a message loop"):
                self.say("alert: log volume")

    def wake_scheduled(self, live: dict, now: float) -> None:
        """Send a `wake` to agents whose schedule is due, only when they're idle and have nothing
        queued, so a wake-up never interrupts work. The clock starts when a schedule is first seen,
        so restarting the supervisor doesn't wake everyone at once. Outside an agent's
        `wake_between` window nobody is woken; when the window opens, an overdue agent gets one
        wake-up, not one per missed interval."""
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
            if now - last[a.name] < parse_interval(a.wake_every) or agent is None \
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
            last[a.name] = now
            changed = True
        if changed:
            path.write_text(json.dumps(last))

    def _nudges(self) -> dict:
        return json.loads(self.nudges_path.read_text()) if self.nudges_path.exists() else {}

    def heartbeat(self, live: dict) -> None:
        queued = {i["to"] for i in Queue(self.ctx).pending()}
        nudges = self._nudges()
        period = dt.timedelta(minutes=int(self.ctx.team.policy("heartbeat_minutes")))
        now = self.ctx.ledger.clock()
        open_ids = set()
        for item in self.ctx.ledger.open_items():
            key = str(item["id"])
            open_ids.add(key)
            owner = item["owner"]
            if owner == HUMAN or owner in queued:
                continue
            agent = live.get(owner)
            if agent is None or agent.status not in DELIVERABLE:
                continue
            reported = item.get("last_from_owner")
            if reported and now - dt.datetime.fromisoformat(reported) < period:
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
    sup.say(f"xt watch started for team {ctx.team.name} (session {ctx.team.session}); ctrl+c to stop")
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
        if pidfile.exists() and pidfile.read_text().strip() == str(os.getpid()):
            pidfile.unlink()
