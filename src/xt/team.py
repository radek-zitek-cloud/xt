import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import tomlkit

from . import capabilities
from .paths import XtError

HUMAN = "human"
SYSTEM = "xt"

LOG_DEFAULTS = {"raw_days": 30, "delete_after_days": 0, "daily_alert_mb": 5, "message_max_kb": 4}
NOTIFY_DEFAULTS = {"enabled": True, "command": "notify-send --app-name=xt {title} {body}", "quiet": ""}
POLICY_DEFAULTS = {"spawn_approval": True, "max_agents": 8, "heartbeat_minutes": 15,
                   "schedule_approval": True, "min_wake_minutes": 15,
                   # card #114: reset idle agents above an absolute context size (off by default)
                   "auto_reset": False, "auto_reset_tokens": 150_000, "auto_reset_cooldown_hours": 6}
NOTES_BUDGET = 16_000  # bytes of members/<name>/notes.md, when team.toml sets no `notes_budget` (card #198)


def _notes_budget_problem(value, where: str) -> str | None:
    """Why a `notes_budget` value is refused, or None: a positive whole number of bytes."""
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return (f"{where} notes_budget = {value!r} in team.toml isn't a positive whole number of bytes "
                f"(e.g. notes_budget = 16000)")
    return None


@dataclass
class Agent:
    name: str
    role: str | None
    harness: str | None
    model: str | None
    reports_to: str | None
    status: str
    kind: str = "agent"
    wake_every: str | None = None
    wake_message: str | None = None
    wake_between: str | None = None  # "05:00-21:00": local-time window for wake-ups; None = any time
    wake_at: str | None = None  # "09:30": for daily (or longer) schedules, the local time to wake
    connectors: list[str] = field(default_factory=list)  # account connectors opted in (card #101)
    permissions: str | None = None  # settings file for the harness, relative to the team repo (card #117)
    auto_reset_tokens: int | str | None = None  # card #114: this agent's threshold, or "off"; None = the team's
    codex_options: list[str] = field(default_factory=list)  # `-c` overrides for a Codex agent (card #169)
    notes_budget: int | None = None  # card #198: this agent's notes budget in bytes; None = the team's

    @property
    def active(self) -> bool:
        return self.status == "active"


class Team:
    def __init__(self, path: Path, doc: tomlkit.TOMLDocument):
        self.path = path
        self.doc = doc

    @classmethod
    def load(cls, path: Path) -> "Team":
        if not path.exists():
            raise XtError(f"no team.toml at {path} — run `xt init` first")
        team = cls(path, tomlkit.parse(path.read_text()))
        team.check()
        return team

    def check(self) -> None:
        """Refuse settings xt can't use, at load (card #198: `notes_budget`)."""
        defaults = self.doc.get("defaults", {})
        problems = []
        if "notes_budget" in defaults:
            problems.append(_notes_budget_problem(defaults["notes_budget"], "[defaults]"))
        for a in self.doc.get("agent", []):
            if "notes_budget" in a:
                problems.append(_notes_budget_problem(a["notes_budget"], f"agent {a.get('name')}'s"))
        problems = [p for p in problems if p] + capabilities.check(self.doc)  # card #186
        if problems:
            raise XtError("; ".join(problems))

    def capabilities_block(self, name: str):
        """The agent's own `[agent.capabilities]` table, or None (card #186)."""
        t = self._table(name)
        return t.get("capabilities") if t is not None else None

    def notes_budget(self, agent: "Agent | None") -> int:
        """The notes budget in bytes for `agent`: its own `notes_budget`, else `[defaults]`, else 16,000."""
        if agent is not None and agent.notes_budget is not None:
            return agent.notes_budget
        return int(self.doc.get("defaults", {}).get("notes_budget", NOTES_BUDGET))

    def save(self) -> None:
        tmp = self.path.with_suffix(".toml.tmp")
        tmp.write_text(tomlkit.dumps(self.doc))
        tmp.replace(self.path)

    @property
    def name(self) -> str:
        return str(self.doc["team"]["name"])

    @property
    def session(self) -> str:
        return str(self.doc["team"]["session"])

    def policy(self, key: str):
        return self.doc.get("policy", {}).get(key, POLICY_DEFAULTS[key])

    def notify_setting(self, key: str):
        return self.doc.get("notify", {}).get(key, NOTIFY_DEFAULTS[key])

    def log_setting(self, key: str):
        return self.doc.get("log", {}).get(key, LOG_DEFAULTS[key])

    @property
    def default_permissions(self) -> str | None:
        """`[defaults] permissions = "…"`: the settings file for every agent whose harness takes one."""
        v = self.doc.get("defaults", {}).get("permissions")
        return str(v) if isinstance(v, str) and v else None

    def default(self, role: str) -> dict:
        return dict(self.doc.get("defaults", {}).get(role, {}))

    def agents(self) -> list[Agent]:
        out = []
        for a in self.doc.get("agent", []):
            out.append(
                Agent(
                    name=str(a["name"]),
                    role=a.get("role"),
                    harness=a.get("harness"),
                    model=a.get("model") or None,
                    reports_to=a.get("reports_to"),
                    status=str(a.get("status", "active")),
                    kind=str(a.get("kind", "agent")),
                    wake_every=a.get("wake_every") or None,
                    wake_message=a.get("wake_message") or None,
                    wake_between=a.get("wake_between") or None,
                    wake_at=a.get("wake_at") or None,
                    connectors=[str(c) for c in a.get("connectors", [])],
                    permissions=str(a["permissions"]) if a.get("permissions") else None,
                    auto_reset_tokens=a.get("auto_reset_tokens"),
                    codex_options=([str(a["codex_options"])] if isinstance(a.get("codex_options"), str)
                                   else [str(o) for o in a.get("codex_options", [])]),
                    notes_budget=int(a["notes_budget"]) if "notes_budget" in a else None,
                )
            )
        return out

    def agent(self, name: str) -> Agent | None:
        return next((a for a in self.agents() if a.name == name), None)

    def reports(self, name: str) -> list[Agent]:
        return [a for a in self.agents() if a.reports_to == name and a.active]

    def lead_of_role(self, role: str) -> Agent | None:
        return next((a for a in self.agents() if a.role == role and a.active), None)

    def _table(self, name: str):
        for a in self.doc.get("agent", []):
            if a["name"] == name:
                return a
        return None

    def upsert_agent(self, name: str, role: str, harness: str, model: str | None, reports_to: str,
                     permissions: str | None = None) -> None:
        """Add or update an agent entry. A `permissions` line is set when given, else kept (card #122)."""
        t = self._table(name)
        if t is None:
            if "agent" not in self.doc:
                self.doc["agent"] = tomlkit.aot()
            t = tomlkit.table()
            t["name"] = name
            self.doc["agent"].append(t)
            t = self._table(name)
            t["added"] = dt.date.today()
        t["role"] = role
        t["harness"] = harness
        if model:
            t["model"] = model
        elif "model" in t:
            del t["model"]
        t["reports_to"] = reports_to
        if permissions:
            t["permissions"] = permissions
        t["status"] = "active"

    def set_schedule(self, name: str, every: str | None, message: str | None = None,
                     between: str | None = None, at: str | None = None) -> None:
        """Set or clear an agent's schedule. `every=None` clears it. A message or window left out
        (None) keeps the one the agent has; `between=ALWAYS` removes the window."""
        t = self._table(name)
        if t is None:
            raise XtError(f"no agent named {name!r} in team.toml")
        if not every:
            for key in ("wake_every", "wake_message", "wake_between", "wake_at"):
                if key in t:
                    del t[key]
            return
        parse_interval(every)
        t["wake_every"] = every
        if message:
            t["wake_message"] = message
        if between == ALWAYS:
            if "wake_between" in t:
                del t["wake_between"]
        elif between:
            parse_window(between)
            t["wake_between"] = normalise_window(between)
        if at == ALWAYS or at == "off":
            if "wake_at" in t:
                del t["wake_at"]
        elif at:
            t["wake_at"] = check_at(at, every, t.get("wake_between"))

    def set_status(self, name: str, status: str) -> None:
        t = self._table(name)
        if t is None:
            raise XtError(f"no agent named {name!r} in team.toml")
        t["status"] = status


def new_team_doc(name: str, session: str, liaison: dict, lead: dict, spawn_approval: bool) -> str:
    """Render a fresh team.toml with comments, as `xt init` writes it."""

    def harness_line(d: dict) -> str:
        s = f'harness = "{d["harness"]}"'
        return s + (f', model = "{d["model"]}"' if d.get("model") else "")

    def agent_block(name: str, role: str, d: dict, reports_to: str) -> str:
        lines = ["[[agent]]", f'name = "{name}"', f'role = "{role}"', f'harness = "{d["harness"]}"']
        if d.get("model"):
            lines.append(f'model = "{d["model"]}"')
        lines += [f'reports_to = "{reports_to}"', 'status = "active"', f"added = {dt.date.today()}"]
        return "\n".join(lines)

    return f"""# xt team: roster and settings. Runtime facts (panes, live status) never go here.

[team]
name = "{name}"
session = "{session}"              # Herdr session this team lives in
created = {dt.date.today()}

[policy]
spawn_approval = {str(spawn_approval).lower()}          # lead's spawns wait for human approval
max_agents = 8                    # soft cap; beyond it the lead must ask the human first
heartbeat_minutes = 15            # supervisor checks for silent agents this often
schedule_approval = true          # an agent's `xt schedule` waits for human approval (each wake-up costs)
min_wake_minutes = 15             # shortest schedule an agent may request; only the human goes lower
auto_reset = false                # reset idle agents without open work whose context is above:
auto_reset_tokens = 150000        #   this many tokens (an agent's own auto_reset_tokens, or "off", wins)
auto_reset_cooldown_hours = 6     #   at most once per agent in this many hours

[log]
raw_days = 30                     # keep daily jsonl files uncompressed this long
delete_after_days = 0             # 0 = never delete archived logs
daily_alert_mb = 5                # supervisor alerts above this (probable message loop)
message_max_kb = 4                # larger payloads go in files, referenced by path

[notify]                          # the supervisor tells the human about questions, approvals, alerts and done goals
enabled = true
command = "notify-send --app-name=xt {{title}} {{body}}"   # e.g. "curl -s -d {{body}} ntfy.sh/<topic>"
quiet = ""                        # local-time window with no notifications, e.g. "21:00-07:00"

[defaults]                        # used when xt starts these without an explicit choice
liaison = {{ {harness_line(liaison)} }}
lead = {{ {harness_line(lead)} }}

# reports_to is the communication chain: an agent may message its reports_to and its reports.

[[agent]]
name = "human"
kind = "human"
status = "active"

{agent_block("liaison", "liaison", liaison, "human")}

{agent_block("lead", "lead", lead, "liaison")}
"""


ALWAYS = "always"


def parse_window(text: str) -> tuple[int, int]:
    """'05:00-21:00' -> (300, 1260), minutes after local midnight. The window may wrap past
    midnight ('22:00-06:00'); start and end must differ."""
    import re

    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", text or "")
    if not m:
        raise XtError(f"window {text!r} isn't like 05:00-21:00 (local time)")
    h1, m1, h2, m2 = (int(g) for g in m.groups())
    if h1 > 23 or h2 > 24 or m1 > 59 or m2 > 59 or (h2 == 24 and m2):
        raise XtError(f"window {text!r} has an impossible time")
    start, end = h1 * 60 + m1, h2 * 60 + m2
    if start == end % 1440:
        raise XtError(f"window {text!r} is empty; leave it out to allow any time")
    return start, end


def normalise_window(text: str) -> str:
    start, end = parse_window(text)
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def in_window(window: str | None, when: dt.datetime) -> bool:
    """Is local time `when` inside the window? No window means always."""
    if not window:
        return True
    start, end = parse_window(window)
    t = when.hour * 60 + when.minute
    return start <= t < end if start < end else (t >= start or t < end)


def harness_model(harness: str | None, model: str | None) -> str:
    """'codex/default' or 'claude/opus': which harness and model an agent runs on."""
    return f"{harness or '?'}/{model or 'default'}"


def check_at(at: str, every: str, window: str | None) -> str:
    """Validate `--at HH:MM` (daily or longer schedules, inside the window if there is one)."""
    import re

    m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", at or "")
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise XtError(f"--at {at!r} isn't a time like 09:30")
    if parse_interval(every) < 86400:
        raise XtError("--at is for daily or longer schedules (e.g. 1d); shorter ones run on their interval")
    hhmm = f"{int(m.group(1)):02d}:{m.group(2)}"
    if window and not in_window(window, dt.datetime(2000, 1, 1, int(m.group(1)), int(m.group(2)))):
        raise XtError(f"--at {hhmm} is outside the schedule's window {window}")
    return hhmm


def next_due(a: "Agent", last: float) -> float:
    """When the agent's next wake-up is due (epoch seconds, local time rules).

    Daily or longer schedules with a window or an --at time are anchored to a local time: the
    window's start, or --at. The next wake is the first such time after the last one (for N days,
    after N-1 days have passed), so it doesn't depend on when the schedule was approved and stays
    on the wall clock across daylight-saving changes. Shorter schedules run every interval (inside
    their window, if any)."""
    every = parse_interval(a.wake_every)
    anchor = a.wake_at or (a.wake_between.split("-")[0] if a.wake_between else None)
    if every >= 86400 and anchor:
        h, m = (int(x) for x in anchor.split(":"))
        base = dt.datetime.fromtimestamp(last) + dt.timedelta(days=round(every / 86400) - 1)
        slot = dt.datetime.combine(base.date(), dt.time(h, m))
        if slot.timestamp() <= base.timestamp():
            slot = dt.datetime.combine(base.date() + dt.timedelta(days=1), dt.time(h, m))
        return slot.timestamp()
    due = last + every
    if a.wake_between and not in_window(a.wake_between, dt.datetime.fromtimestamp(due)):
        start_h, start_m = (int(x) for x in a.wake_between.split("-")[0].split(":"))
        d = dt.datetime.fromtimestamp(due)
        slot = dt.datetime.combine(d.date(), dt.time(start_h, start_m))
        if slot <= d:
            slot = dt.datetime.combine(d.date() + dt.timedelta(days=1), dt.time(start_h, start_m))
        return slot.timestamp()
    return due


def schedule_text(a: "Agent") -> str:
    """'every 60m, 05:00-21:00' for displays; '' when the agent has no schedule."""
    if not a.wake_every:
        return ""
    return (f"every {a.wake_every}" + (f", {a.wake_between}" if a.wake_between else "")
            + (f", at {a.wake_at}" if a.wake_at else ""))


def parse_interval(text: str) -> int:
    """'90s', '30m', '2h', '1d' -> seconds."""
    import re

    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", text or "")
    if not m or int(m.group(1)) == 0:
        raise XtError(f"interval {text!r} isn't like 90s, 30m, 2h or 1d")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]
