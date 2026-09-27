import datetime as dt
import shutil
from pathlib import Path

import pytest

from xt.adapters import Adapter
from xt.context import Ctx
from xt import spawn
from xt.herdr import HerdrError, LiveAgent
from xt.ledger import Ledger
from xt.paths import Paths
from xt.team import Team, new_team_doc

REPO = Path(__file__).resolve().parents[1]


class FakeHerdr:
    session = "test"

    def __init__(self):
        self.live: dict[str, LiveAgent] = {}
        self.prompts: list[tuple[str, str]] = []
        self.created: list[str] = []
        self.closed: list[str] = []
        self.pane_runs: list[tuple[str, str]] = []
        self.started: list[tuple[str, str, list[str]]] = []
        self.stall: dict[str, int] = {}  # name -> how many confirmed prompts to "lose"
        self.swallow: dict[str, int] = {}  # name -> prompts that vanish silently
        self.dialogs: dict[str, str] = {}  # pane -> startup dialog text currently shown
        self.dialog_on_start: str | None = None  # dialog every newly started agent shows
        self.block_on_start: str | None = None  # dialog that makes herdr refuse the start
        self.screens: dict[str, list[str]] = {}
        self.keys: list[tuple[str, tuple]] = []
        self.snapshots: list = []
        self.labels: dict[str, str] = {}

    def check_session(self):
        pass

    def agents(self):
        return dict(self.live)

    def status(self, name):
        a = self.live.get(name)
        return a.status if a else None

    def prompt(self, name, text, confirm=False):
        if confirm and self.stall.get(name, 0) > 0:
            self.stall[name] -= 1
            raise HerdrError("agent_prompt_stalled", "no working state observed")
        pane = self.live[name].pane_id
        self.live[name].status = "working"  # a harness starting up looks "working" too
        if self.dialogs.get(pane):
            return  # typed into a startup dialog: the prompt is lost
        if self.swallow.get(name, 0) > 0:
            self.swallow[name] -= 1
            return
        self.prompts.append((name, text))
        self.screens.setdefault(pane, []).append(text)

    def save_snapshot(self, agents, ts):
        self.snapshots.append((ts, sorted(agents)))

    def read_pane(self, pane, lines=200):
        parts = list(self.screens.get(pane, []))
        if self.dialogs.get(pane):
            parts.append(self.dialogs[pane])
        return "\n".join(parts)

    def send_keys(self, pane, *keys):
        self.keys.append((pane, keys))
        if "enter" in keys:
            self.dialogs.pop(pane, None)
            for a in self.live.values():
                if a.pane_id == pane and a.status == "blocked":
                    a.status = "idle"

    def create_workspace(self, cwd, label):
        ws = f"w{len(self.created) + 1}"
        self.created.append(ws)
        self.labels[ws] = label
        return f"{ws}:p1", ws

    def workspaces(self):
        return {ws: lab for ws, lab in self.labels.items() if ws not in self.closed}

    def close_workspace(self, ws):
        self.closed.append(ws)
        for n in [n for n, a in self.live.items() if a.workspace_id == ws]:
            del self.live[n]

    def start_agent(self, name, kind, pane, args):
        self.started.append((name, kind, args))
        self.live[name] = LiveAgent(name, "idle", pane, pane.split(":")[0])
        if self.dialog_on_start:
            self.dialogs[pane] = self.dialog_on_start
        if self.block_on_start:
            # like claude's trust question: herdr registers the agent as blocked and refuses
            self.dialogs[pane] = self.block_on_start
            self.live[name].status = "blocked"
            raise HerdrError("agent_not_ready", f"agent {name} is blocked during startup")

    def run_in_fresh_pane(self, pane, cmd):
        self.pane_runs.append((pane, cmd))

    # test helpers
    def add(self, name, status="idle"):
        self.live[name] = LiveAgent(name, status, f"x{name}:p1", f"x{name}")

    def last_prompt(self, name):
        return next(t for n, t in reversed(self.prompts) if n == name)


class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.timezone.utc)

    def __call__(self):
        return self.t

    def advance(self, **kw):
        self.t += dt.timedelta(**kw)


@pytest.fixture(autouse=True)
def all_harnesses_installed(monkeypatch):
    monkeypatch.setattr(Adapter, "installed", property(lambda self: True))
    monkeypatch.setattr(spawn, "RETRY_DELAY", 0)
    monkeypatch.setattr(spawn, "POLL", 0)
    monkeypatch.setattr(spawn, "LANDED_WAIT", 0)


@pytest.fixture
def paths(tmp_path) -> Paths:
    for name in ("protocol.md", "roles", "harnesses"):
        src = REPO / name
        (shutil.copytree if src.is_dir() else shutil.copy)(src, tmp_path / name)
    (tmp_path / "skills").mkdir()
    p = Paths(tmp_path)
    p.team_toml.write_text(
        new_team_doc("t", "test", {"harness": "codex"}, {"harness": "codex"}, spawn_approval=True)
    )
    return p


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def ctx(paths, clock) -> Ctx:
    return Ctx(paths, Team.load(paths.team_toml), Ledger(paths, clock=clock), FakeHerdr())


def add_member(ctx: Ctx, name: str, role: str = "worker", reports_to: str = "lead"):
    (ctx.paths.roles / f"{role}.md").write_text(f"# Role: {role}\n")
    ctx.team.upsert_agent(name, role, "claude", None, reports_to)
    ctx.team.save()
    ctx.reload_team()
