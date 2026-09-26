"""`xt init`: turn a fresh clone of xt into the user's own team repo."""

import os
import shutil
import subprocess
import sys

from . import herdr
from .adapters import load_adapters
from .paths import Paths, XtError
from .team import new_team_doc

RECOMMENDED = "codex"


def _git(paths: Paths, *args: str, check: bool = True) -> str:
    p = subprocess.run(["git", "-C", str(paths.root), *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise XtError(f"git {' '.join(args)} failed: {p.stderr.strip()}")
    return p.stdout.strip()


def prerequisites(paths: Paths) -> tuple[list[str], list[str]]:
    report, missing = [], []
    for tool in ("herdr", "git", "uv", "mise"):
        ok = shutil.which(tool) is not None
        report.append(f"{'ok ' if ok else 'MISSING'} {tool}")
        if not ok and tool in ("herdr", "git"):
            missing.append(tool)
    for a in load_adapters(paths).values():
        report.append(f"{'ok ' if a.installed else '-- '} harness {a.name} ({a.binary}){'' if a.installed else ' not installed'}")
    return report, missing


def _ask(question: str, default: str, interactive: bool) -> str:
    if not interactive:
        return default
    ans = input(f"{question} [{default}]: ").strip()
    return ans or default


def _choose_harness(paths: Paths, who: str, preset: str | None, interactive: bool) -> dict:
    adapters = {k: v for k, v in load_adapters(paths).items() if v.installed}
    if not adapters:
        raise XtError("no supported harness is installed (claude, codex or pi)")
    default = RECOMMENDED if RECOMMENDED in adapters else next(iter(adapters))
    if preset:
        harness, _, model = preset.partition(":")
    else:
        if interactive:
            print(f"\nHarness for the {who}:")
            for a in adapters.values():
                tag = " (recommended)" if a.name == RECOMMENDED else ""
                print(f"  {a.name}{tag} — {a.summary}")
        harness = _ask(f"{who} harness", default, interactive)
        model = _ask(f"{who} model (empty = the harness's own default)", "", interactive)
    if harness not in adapters:
        raise XtError(f"harness {harness!r} isn't available (installed: {', '.join(adapters)})")
    return {"harness": harness, "model": model or None}


def init(paths: Paths, name: str | None, session: str | None, liaison: str | None, lead: str | None,
         approval: bool | None, yes: bool, commit: bool = True) -> list[str]:
    if paths.team_toml.exists():
        return [f"already initialised: {paths.team_toml} exists (edit it to change settings)"]
    interactive = not yes and sys.stdin.isatty()
    report, missing = prerequisites(paths)
    out = ["Prerequisites:", *[f"  {r}" for r in report]]
    if missing:
        raise XtError("\n".join(out + [f"missing essentials: {', '.join(missing)} — install them and rerun"]))
    if interactive:
        print("\n".join(out))

    team_name = name or _ask("Team name", paths.root.name, interactive)
    sess = session or _ask("Herdr session for this team", team_name, interactive)
    li = _choose_harness(paths, "liaison", liaison, interactive)
    le = _choose_harness(paths, "lead", lead, interactive)
    if approval is None:
        approval = _ask("Require your approval before the lead spawns agents? (y/n)", "y", interactive).lower().startswith("y")

    if not (paths.root / ".git").exists():
        _git(paths, "init", "-q", "-b", "main")
        out.append("git: initialised a new repo")
    remotes = _git(paths, "remote").split()
    if "origin" in remotes and "upstream" not in remotes:
        _git(paths, "remote", "rename", "origin", "upstream")
        out.append("git: renamed origin → upstream (xt updates: git pull upstream main); add your own origin if you want to push")
    elif "upstream" in remotes:
        out.append("git: upstream remote already set")
    else:
        out.append("git: no remote; add xt as `upstream` later to receive updates")

    paths.team_toml.write_text(new_team_doc(team_name, sess, li, le, approval))
    for d in (paths.drafts, paths.members, paths.skills):
        d.mkdir(parents=True, exist_ok=True)
        keep = d / ".gitkeep"
        if not any(d.iterdir()):
            keep.touch()
    for link_dir in (".agents", ".claude"):
        link = paths.root / link_dir / "skills"
        link.parent.mkdir(exist_ok=True)
        if not link.exists() and not link.is_symlink():
            os.symlink("../skills", link)
    paths.ensure_runtime()
    out.append(f"wrote team.toml (team {team_name}, session {sess}, liaison {li['harness']}, lead {le['harness']})")

    if commit:
        _git(paths, "add", "team.toml", "goals", "members", "skills", ".agents", ".claude")
        _git(paths, "commit", "-q", "-m", f"Initialise team {team_name}")
        out.append(f"git: committed 'Initialise team {team_name}'")
    try:
        if sess not in herdr.sessions():
            out.append(f"next: start the Herdr session with `herdr --session {sess}`, then run `xt` inside it")
        else:
            out.append("next: run `xt` to start the supervisor and the liaison")
    except XtError:
        out.append("next: start Herdr, then run `xt`")
    return out
