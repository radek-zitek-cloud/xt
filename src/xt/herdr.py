"""Thin wrapper over the herdr CLI.

Every call is pinned to the team's session with `herdr --session <name>`, so xt never
depends on inherited HERDR_* environment variables (which proved unreliable in v1).
"""

import datetime as dt
import json
import subprocess
from dataclasses import dataclass

from .paths import XtError

DELIVERABLE = ("idle", "done")


class HerdrError(XtError):
    def __init__(self, code: str, message: str):
        super().__init__(f"herdr: {code}: {message}")
        self.code = code


@dataclass
class LiveAgent:
    name: str
    status: str
    pane_id: str
    workspace_id: str


def sessions() -> dict[str, dict]:
    out = _exec(["herdr", "session", "list", "--json"])
    return {s["name"]: s for s in out.get("sessions", [])}


def _exec(argv: list[str], timeout: float = 120) -> dict:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        raise XtError("herdr is not installed (it's xt's one real prerequisite)")
    except subprocess.TimeoutExpired:
        raise XtError(f"herdr timed out: {' '.join(argv[1:])}")
    text = (p.stdout or "").strip()
    try:
        data = json.loads(text) if text else {}
    except json.JSONDecodeError:
        raise XtError(f"herdr returned non-JSON output for {' '.join(argv[1:])}: {text[:200] or p.stderr[:200]}")
    if "error" not in data and p.returncode != 0:
        # Some failures (e.g. agent_not_ready from `agent start`) put the error JSON on stderr.
        try:
            data = json.loads((p.stderr or "").strip() or "{}")
        except json.JSONDecodeError:
            raise XtError(f"herdr failed ({p.returncode}): {p.stderr.strip()[:300]}")
    if "error" in data:
        err = data["error"]
        raise HerdrError(err.get("code", "error"), err.get("message", ""))
    if p.returncode != 0:
        raise XtError(f"herdr failed ({p.returncode}): {p.stderr.strip()[:300]}")
    return data


def _recent(ts: str | None, seconds: float) -> bool:
    try:
        saved = dt.datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return False
    return (dt.datetime.now(dt.timezone.utc) - saved).total_seconds() <= seconds


class Herdr:
    def __init__(self, session: str, snapshot=None):
        self.session = session
        # Where the supervisor saves `agent list` each tick. Agents whose harness sandboxes their
        # shell (codex: "Operation not permitted" on Herdr's socket) read live state from it.
        self.snapshot = snapshot

    def _run(self, *args: str, timeout: float = 120) -> dict:
        return _exec(["herdr", "--session", self.session, *args], timeout=timeout)

    def check_session(self) -> None:
        s = sessions().get(self.session)
        if not s or not s.get("running"):
            raise XtError(
                f"Herdr session {self.session!r} is not running — open it with "
                f"`herdr session attach {self.session}` (or `herdr --session {self.session}`) first"
            )

    def agents(self, max_snapshot_age: float | None = None) -> dict[str, LiveAgent]:
        """The live agents. When Herdr can't be reached, the supervisor's saved snapshot, if any;
        with `max_snapshot_age` (seconds) only a snapshot that recent (card #201: a server that is
        down reads as unknown once the supervisor can no longer save one)."""
        try:
            data = self._run("agent", "list")
        except XtError:
            if self.snapshot is not None and self.snapshot.exists():
                snap = json.loads(self.snapshot.read_text())
                if max_snapshot_age is not None and not _recent(snap.get("ts"), max_snapshot_age):
                    raise
                return {n: LiveAgent(n, *v) for n, v in snap.get("agents", {}).items()}
            raise
        out = {}
        for a in data.get("result", {}).get("agents", []):
            name = a.get("name")
            if name:
                out[name] = LiveAgent(name, a.get("agent_status", "unknown"), a["pane_id"], a["workspace_id"])
        return out

    def save_snapshot(self, agents: dict[str, LiveAgent], ts: str) -> None:
        if self.snapshot is None:
            return
        tmp = self.snapshot.with_suffix(".tmp")
        tmp.write_text(json.dumps({"ts": ts, "agents": {
            n: [a.status, a.pane_id, a.workspace_id] for n, a in agents.items()
        }}))
        tmp.replace(self.snapshot)

    def status(self, name: str) -> str | None:
        a = self.agents().get(name)
        return a.status if a else None

    def prompt(self, name: str, text: str, confirm: bool = False) -> None:
        """Submit a prompt. With confirm, fail with `agent_prompt_stalled` unless the agent is
        seen to start working (or block) on it, which catches prompts lost during startup."""
        args = ["agent", "prompt", name, text]
        if confirm:
            args += ["--wait", "--until", "working", "--until", "blocked", "--timeout", "30000"]
        self._run(*args, timeout=60)

    def create_workspace(self, cwd: str, label: str) -> tuple[str, str]:
        data = self._run("workspace", "create", "--cwd", cwd, "--label", label, "--no-focus")
        pane = data["result"]["root_pane"]
        return pane["pane_id"], pane["workspace_id"]

    def workspaces(self) -> dict[str, str]:
        """workspace_id -> label"""
        data = self._run("workspace", "list")
        return {w["workspace_id"]: w.get("label", "") for w in data.get("result", {}).get("workspaces", [])}

    def close_workspace(self, workspace_id: str) -> None:
        self._run("workspace", "close", workspace_id)

    def start_agent(self, name: str, kind: str, pane_id: str, args: list[str]) -> None:
        argv = ["agent", "start", name, "--kind", kind, "--pane", pane_id, "--timeout", "120000"]
        if args:
            argv += ["--", *args]
        self._run(*argv, timeout=150)

    def read_pane(self, pane_id: str, lines: int = 200) -> str:
        """Recent screen text of a pane (plain text, as the terminal shows it)."""
        p = subprocess.run(
            ["herdr", "--session", self.session, "pane", "read", pane_id, "--source", "recent", "--lines", str(lines)],
            capture_output=True, text=True, timeout=20,
        )
        return p.stdout

    def send_keys(self, pane_id: str, *keys: str) -> None:
        self._run("pane", "send-keys", pane_id, *keys)

    def run_in_fresh_pane(self, pane_id: str, command: str) -> None:
        # Only ever used on a pane xt just created (a bare shell): `pane run` types into
        # whatever is in the foreground, so never aim it at a pane running an agent.
        self._run("pane", "run", pane_id, command)

    def focus_workspace(self, workspace_id: str) -> None:
        self._run("workspace", "focus", workspace_id)
