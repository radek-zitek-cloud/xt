import datetime as dt
import shutil
from pathlib import Path

import pytest

from xt.adapters import Adapter
from xt.context import Ctx
from xt.herdr import LiveAgent
from xt.ledger import Ledger
from xt.paths import Paths
from xt.team import Team, new_team_doc

REPO = Path(__file__).resolve().parents[1]


class FakeHerdr:
    session = "test"

    def __init__(self):
        self.live: dict[str, LiveAgent] = {}
        self.prompts: list[tuple[str, str]] = []
        self.workspaces: list[str] = []
        self.closed: list[str] = []
        self.pane_runs: list[tuple[str, str]] = []
        self.started: list[tuple[str, str, list[str]]] = []

    def check_session(self):
        pass

    def agents(self):
        return dict(self.live)

    def status(self, name):
        a = self.live.get(name)
        return a.status if a else None

    def prompt(self, name, text):
        self.prompts.append((name, text))
        self.live[name].status = "working"

    def create_workspace(self, cwd, label):
        ws = f"w{len(self.workspaces) + 1}"
        self.workspaces.append(ws)
        return f"{ws}:p1", ws

    def close_workspace(self, ws):
        self.closed.append(ws)
        for n in [n for n, a in self.live.items() if a.workspace_id == ws]:
            del self.live[n]

    def start_agent(self, name, kind, pane, args):
        self.started.append((name, kind, args))
        self.live[name] = LiveAgent(name, "idle", pane, pane.split(":")[0])

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
