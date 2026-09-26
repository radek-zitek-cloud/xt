"""Thin wrapper over the herdr CLI.

Every call is pinned to the team's session with `herdr --session <name>`, so xt never
depends on inherited HERDR_* environment variables (which proved unreliable in v1).
"""

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
    if "error" in data:
        err = data["error"]
        raise HerdrError(err.get("code", "error"), err.get("message", ""))
    if p.returncode != 0:
        raise XtError(f"herdr failed ({p.returncode}): {p.stderr.strip()[:300]}")
    return data


class Herdr:
    def __init__(self, session: str):
        self.session = session

    def _run(self, *args: str, timeout: float = 120) -> dict:
        return _exec(["herdr", "--session", self.session, *args], timeout=timeout)

    def check_session(self) -> None:
        s = sessions().get(self.session)
        if not s or not s.get("running"):
            raise XtError(
                f"Herdr session {self.session!r} is not running — open it with "
                f"`herdr session attach {self.session}` (or `herdr --session {self.session}`) first"
            )

    def agents(self) -> dict[str, LiveAgent]:
        data = self._run("agent", "list")
        out = {}
        for a in data.get("result", {}).get("agents", []):
            name = a.get("name")
            if name:
                out[name] = LiveAgent(name, a.get("agent_status", "unknown"), a["pane_id"], a["workspace_id"])
        return out

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

    def close_workspace(self, workspace_id: str) -> None:
        self._run("workspace", "close", workspace_id)

    def start_agent(self, name: str, kind: str, pane_id: str, args: list[str]) -> None:
        argv = ["agent", "start", name, "--kind", kind, "--pane", pane_id, "--timeout", "120000"]
        if args:
            argv += ["--", *args]
        self._run(*argv, timeout=150)

    def run_in_fresh_pane(self, pane_id: str, command: str) -> None:
        # Only ever used on a pane xt just created (a bare shell): `pane run` types into
        # whatever is in the foreground, so never aim it at a pane running an agent.
        self._run("pane", "run", pane_id, command)

    def focus_workspace(self, workspace_id: str) -> None:
        self._run("workspace", "focus", workspace_id)
