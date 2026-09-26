from dataclasses import dataclass

from .herdr import Herdr
from .ledger import Ledger
from .paths import Paths, find_root
from .team import Team


@dataclass
class Ctx:
    paths: Paths
    team: Team
    ledger: Ledger
    herdr: Herdr

    @classmethod
    def load(cls, paths: Paths | None = None, herdr: Herdr | None = None) -> "Ctx":
        paths = paths or Paths(find_root())
        team = Team.load(paths.team_toml)
        return cls(paths, team, Ledger(paths), herdr or Herdr(team.session))

    def reload_team(self) -> None:
        self.team = Team.load(self.paths.team_toml)
