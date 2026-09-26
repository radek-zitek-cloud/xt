import os
from dataclasses import dataclass
from pathlib import Path


class XtError(Exception):
    """A user-facing error: printed without a traceback."""


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def team_toml(self) -> Path:
        return self.root / "team.toml"

    @property
    def protocol(self) -> Path:
        return self.root / "protocol.md"

    @property
    def roles(self) -> Path:
        return self.root / "roles"

    @property
    def skills(self) -> Path:
        return self.root / "skills"

    @property
    def harnesses(self) -> Path:
        return self.root / "harnesses"

    @property
    def goals(self) -> Path:
        return self.root / "goals"

    @property
    def drafts(self) -> Path:
        return self.goals / "drafts"

    @property
    def members(self) -> Path:
        return self.root / "members"

    @property
    def runtime(self) -> Path:
        return self.root / ".xt"

    @property
    def log(self) -> Path:
        return self.runtime / "log"

    @property
    def archive(self) -> Path:
        return self.log / "archive"

    @property
    def state(self) -> Path:
        return self.runtime / "state"

    @property
    def xt_bin(self) -> Path:
        return self.root / "bin" / "xt"

    def role_file(self, role: str) -> Path:
        return self.roles / f"{role}.md"

    def ensure_runtime(self) -> None:
        for d in (self.log, self.archive, self.state):
            d.mkdir(parents=True, exist_ok=True)


def find_root() -> Path:
    env = os.environ.get("XT_ROOT")
    if env:
        return Path(env).resolve()
    here = Path.cwd().resolve()
    for d in (here, *here.parents):
        if (d / "src" / "xt").is_dir() and (d / "pyproject.toml").is_file():
            return d
    raise XtError("not inside an xt repo (no src/xt found above the current directory)")
