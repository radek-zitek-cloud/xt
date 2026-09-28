"""Harness adapters: `harnesses/<kind>.toml` declares how xt starts an agent in that harness."""

import shutil
import tomllib
from dataclasses import dataclass, field

from .paths import Paths, XtError


@dataclass
class Adapter:
    name: str
    herdr_kind: str
    binary: str
    args: list[str] = field(default_factory=list)
    model_flag: str | None = None
    summary: str = ""
    limits: list[str] = field(default_factory=list)
    # Dialogs the harness may show before it takes input: [{"match": [...], "keys": [...]}]
    startup_dialogs: list[dict] = field(default_factory=list)
    # Where the harness keeps its session logs (a glob, ~ allowed) and their format, so xt can
    # read an agent's context usage; windows for models whose logs don't state it.
    sessions: str | None = None
    session_format: str | None = None
    context_windows: dict[str, int] = field(default_factory=dict)
    # Desktop/browser control for agents (card #89): "blocked" (switched off by the args), "none"
    # (the harness has no such tools), "partial" or unset (not fully enforced: xt says so at start).
    desktop_tools: str | None = None
    desktop_tools_note: str = ""

    @property
    def installed(self) -> bool:
        return shutil.which(self.binary) is not None

    def start_args(self, model: str | None) -> list[str]:
        args = list(self.args)
        if model:
            if not self.model_flag:
                raise XtError(f"harness {self.name} has no model flag declared; leave the model empty")
            args += [self.model_flag, model]
        return args


def load_adapters(paths: Paths) -> dict[str, Adapter]:
    out = {}
    for f in sorted(paths.harnesses.glob("*.toml")):
        d = tomllib.loads(f.read_text())
        out[f.stem] = Adapter(
            name=f.stem,
            herdr_kind=d.get("herdr_kind", f.stem),
            binary=d.get("binary", f.stem),
            args=list(d.get("args", [])),
            model_flag=d.get("model_flag"),
            summary=d.get("summary", ""),
            limits=list(d.get("limits", [])),
            startup_dialogs=[
                {
                    "match": [dlg["match"]] if isinstance(dlg["match"], str) else list(dlg["match"]),
                    "keys": list(dlg.get("keys", ["enter"])),
                    "name": dlg.get("name", dlg["match"] if isinstance(dlg["match"], str) else dlg["match"][0]),
                }
                for dlg in d.get("startup_dialogs", [])
            ],
            sessions=d.get("sessions"),
            session_format=d.get("session_format"),
            context_windows={k: int(v) for k, v in d.get("context_windows", {}).items()},
            desktop_tools=d.get("desktop_tools"),
            desktop_tools_note=d.get("desktop_tools_note", ""),
        )
    return out


def get_adapter(paths: Paths, harness: str) -> Adapter:
    adapters = load_adapters(paths)
    if harness not in adapters:
        raise XtError(f"no adapter for harness {harness!r} (have: {', '.join(adapters) or 'none'})")
    a = adapters[harness]
    if not a.installed:
        raise XtError(f"harness {harness!r} isn't installed here (`{a.binary}` not on PATH)")
    return a
