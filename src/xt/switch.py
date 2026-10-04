"""Select a team's xt version and roll back (card #100): `xt version use <tag>`, `xt version rollback`.

A team repo is a clone of xt with the team's own commits and files on top, so a version switch is a
git merge of an upstream tag into it, never a fresh checkout. Rules, in order:

- Human only, and only with the team fully down: no supervisor, no live agent, and xt holds the
  ledger lock for the whole switch, so no other xt command can write meanwhile.
- The tag must exist upstream; a release candidate (`-rcN`) is used only with `--candidate`.
- The team's tracked files must be committed first, so a merge or an abort can't lose a change.
- The persistent state (`.xt/state/`) has a format number. The target version must declare that it
  reads the team's format (looked up in the target tag's own source); otherwise xt refuses. xt never
  migrates state.
- Before merging, xt copies the mutable state into a verified snapshot and records a fingerprint of
  the ledger. The ledger (`.xt/log/`) is append-only and is never copied back or rewritten.
- The merge always makes a merge commit (`--no-ff`), so a rollback can revert exactly that commit and
  keep every team commit. A conflict aborts the merge, names the files and leaves the previous
  version installed. The switch is recorded only after every check passed.
"""

import datetime as dt
import fcntl
import hashlib
import json
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

from . import versions
from .context import Ctx
from .paths import XtError
from .team import HUMAN, SYSTEM

# The state formats this code reads. Format 1 is the `.xt/state/` layout since xt 0.12.0.
STATE_FORMATS = (1,)
CURRENT_FORMAT = 1
# What xt versions released before this declaration read: every version from 0.12.0 reads format 1.
# A version outside this table that doesn't declare STATE_FORMATS in its source is "unknown".
KNOWN_FORMATS = {(0, 12): (1,), (0, 13): (1,)}
SOURCE = "src/xt/switch.py"


def _git(ctx: Ctx, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    p = subprocess.run(["git", "-C", str(ctx.paths.root), *args], capture_output=True, text=True)
    if check and p.returncode != 0:
        raise XtError(f"git {' '.join(args)} failed: {(p.stderr or p.stdout).strip()}")
    return p


# --- state format -------------------------------------------------------------------------------


def _format_file(ctx: Ctx) -> Path:
    return ctx.paths.state / "format.json"


def team_format(ctx: Ctx) -> int | None:
    try:
        return int(json.loads(_format_file(ctx).read_text())["format"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def stamp_format(ctx: Ctx) -> None:
    """Record the format of a team's state if it has none yet: a label for the layout that's
    already there (format 1 since 0.12.0), not a migration. Called by `xt up`."""
    if team_format(ctx) is None and ctx.paths.state.exists():
        try:
            _format_file(ctx).write_text(json.dumps({"format": CURRENT_FORMAT}) + "\n")
        except OSError:
            pass


def formats_of(ctx: Ctx, commit: str) -> tuple[int, ...] | None:
    """The state formats the xt at `commit` reads: its own declaration, or the table of earlier
    releases; None when neither says (unknown)."""
    src = _git(ctx, "show", f"{commit}:{SOURCE}", check=False)
    if src.returncode == 0:
        m = re.search(r"(?m)^STATE_FORMATS\s*=\s*\(([\d,\s]*)\)", src.stdout)
        if m:
            return tuple(int(x) for x in m.group(1).replace(",", " ").split())
    py = _git(ctx, "show", f"{commit}:pyproject.toml", check=False)
    m = re.search(r'(?m)^version\s*=\s*"([^"]+)"', py.stdout) if py.returncode == 0 else None
    v = versions.parse(m.group(1)) if m else None
    return KNOWN_FORMATS.get(v[:2]) if v else None


def _check_format(ctx: Ctx, commit: str, label: str) -> int:
    fmt = team_format(ctx)
    if fmt is None:
        raise XtError("the team's state has no format record (.xt/state/format.json); run `xt up` once with "
                      "the current version to record it, then `xt down` and try again")
    reads = formats_of(ctx, commit)
    if reads is None:
        raise XtError(f"{label} doesn't say which state formats it reads, so switching to it could leave "
                      f"state it can't use; xt refuses (no automatic migration)")
    if fmt not in reads:
        raise XtError(f"{label} reads state format(s) {', '.join(map(str, reads))}, the team's state is format "
                      f"{fmt}; xt refuses (no automatic migration)")
    return fmt


# --- down, lock, clean ------------------------------------------------------------------------------


def _require_down(ctx: Ctx) -> None:
    from .lifecycle import watch_pid

    if watch_pid(ctx):
        raise XtError("the supervisor is running: `xt down` first (a version switch needs the team fully down)")
    live = sorted(ctx.herdr.agents())
    if live:
        raise XtError(f"agents are running ({', '.join(live)}): `xt down` first")


@contextmanager
def _exclusive(ctx: Ctx):
    """The ledger lock, without waiting: another xt command writing now means someone is still at work."""
    ctx.paths.state.mkdir(parents=True, exist_ok=True)
    with open(ctx.paths.state / "lock", "a") as fh:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise XtError("another xt command is writing the team's state right now; wait and try again") from None
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _require_clean(ctx: Ctx) -> None:
    dirty = [line for line in _git(ctx, "status", "--porcelain", "--untracked-files=no").stdout.splitlines() if line.strip()]
    if dirty:
        files = ", ".join(line[3:] for line in dirty[:6])  # "XY path": two status letters, a space
        raise XtError(f"the team repo has uncommitted changes ({files}); commit them first so a merge can't "
                      f"lose them")
    for marker in ("MERGE_HEAD", "REVERT_HEAD", "CHERRY_PICK_HEAD"):
        if _git(ctx, "rev-parse", "-q", "--verify", marker, check=False).returncode == 0:
            raise XtError(f"a git operation is in progress in the team repo ({marker}); finish or abort it first")


# --- tags ---------------------------------------------------------------------------------------------


def resolve_tag(ctx: Ctx, tag: str, candidate: bool) -> tuple[str, str]:
    """(tag, commit) after fetching the upstream tags; refuses unknown tags and unannounced candidates."""
    tag = tag if tag.startswith("v") else f"v{tag}"
    v = versions.parse(tag)
    if v is None:
        raise XtError(f"{tag!r} isn't an xt release tag (vX.Y.Z or vX.Y.Z-rcN)")
    if v[3] == 0 and not candidate:
        raise XtError(f"{tag} is a release candidate: pass --candidate to use it on purpose")
    remote = versions._upstream(ctx)
    if remote:
        _git(ctx, "fetch", "--quiet", "--tags", remote, check=False)
    p = _git(ctx, "rev-parse", "-q", "--verify", f"refs/tags/{tag}^{{commit}}", check=False)
    if p.returncode != 0:
        raise XtError(f"no tag {tag} in the team repo or its upstream" + ("" if remote else " (no upstream remote)"))
    return tag, p.stdout.strip()


# --- snapshot and ledger fingerprint ----------------------------------------------------------------


def ledger_fingerprint(ctx: Ctx) -> dict:
    h = hashlib.sha256()
    count = last = 0
    for m in ctx.ledger.messages():
        h.update(json.dumps(m, sort_keys=True).encode())
        count += 1
        last = max(last, int(m.get("id") or 0))
    return {"count": count, "last_id": last, "sha256": h.hexdigest()}


def ledger_continues(ctx: Ctx, fp: dict) -> bool:
    """The first `count` messages are exactly the recorded ones: nothing lost, changed or reordered."""
    h = hashlib.sha256()
    n = 0
    for m in ctx.ledger.messages():
        if n == fp["count"]:
            break
        h.update(json.dumps(m, sort_keys=True).encode())
        n += 1
    return n == fp["count"] and h.hexdigest() == fp["sha256"]


def _digest_dir(d: Path) -> dict[str, str]:
    return {str(f.relative_to(d)): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in sorted(d.rglob("*")) if f.is_file()}


def take_snapshot(ctx: Ctx, label: str) -> Path:
    """A verified copy of `.xt/state/` (the mutable state; not the ledger, which is only ever appended)."""
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    dest = ctx.paths.root / ".xt" / "snapshots" / f"{stamp}-{label}"
    try:
        dest.mkdir(parents=True, exist_ok=False)  # never reuse (or later clean up) another snapshot's folder
    except OSError as e:
        raise XtError(f"couldn't create a snapshot folder ({e}); nothing was switched") from None
    try:
        shutil.copytree(ctx.paths.state, dest / "state", ignore=shutil.ignore_patterns("lock", "watch.pid"))
        want = _digest_dir(ctx.paths.state)
        want = {k: v for k, v in want.items() if k not in ("lock", "watch.pid")}
        got = _digest_dir(dest / "state")
        if got != want:
            raise OSError("copy differs from the original")
        (dest / "manifest.json").write_text(json.dumps({"files": got}, indent=1))
    except OSError as e:
        shutil.rmtree(dest, ignore_errors=True)
        raise XtError(f"couldn't take a verified state snapshot ({e}); nothing was switched") from None
    return dest


# --- records ------------------------------------------------------------------------------------


def _records_path(ctx: Ctx) -> Path:
    return ctx.paths.state / "switches.json"


def records(ctx: Ctx) -> list[dict]:
    try:
        return json.loads(_records_path(ctx).read_text())
    except (OSError, ValueError):
        return []


def _save_records(ctx: Ctx, recs: list[dict]) -> None:
    _records_path(ctx).write_text(json.dumps(recs, indent=1))


def _installed_matches(ctx: Ctx, tag: str) -> bool:
    inst = versions.installed(ctx)
    return versions.parse(inst) == versions.parse(tag)


# --- use ------------------------------------------------------------------------------------------


def use(ctx: Ctx, tag: str, candidate: bool = False) -> list[str]:
    lines: list[str] = []
    with _exclusive(ctx):
        _require_down(ctx)
        _require_clean(ctx)
        tag, target = resolve_tag(ctx, tag, candidate)
        prev_version = versions.installed(ctx)
        prev_head = _git(ctx, "rev-parse", "HEAD").stdout.strip()
        fmt = _check_format(ctx, target, tag)
        recs = records(ctx)
        already = _git(ctx, "merge-base", "--is-ancestor", target, "HEAD", check=False).returncode == 0
        undone = next((r for r in reversed(recs) if r.get("commit") == target and r.get("rolled_back")), None)
        if already and not undone:
            if not _installed_matches(ctx, tag):
                raise XtError(f"{tag} is already part of the team repo but the installed version is "
                              f"{versions.display(prev_version)}; nothing to merge")
            return [f"{tag} is already installed ({versions.display(prev_version)}); nothing to do"]
        # A newer tag whose history contains a switch that was rolled back: git counts that switch's
        # commits as already merged, so a plain merge would bring only what came after it and leave the
        # rolled-back changes out (an install that says the new version but isn't). Re-apply those
        # rollbacks first (revert the revert), then merge.
        reapply = [r for r in recs if r.get("rolled_back") and not r.get("reapplied") and r is not undone
                   and _git(ctx, "merge-base", "--is-ancestor", r["commit"], target, check=False).returncode == 0]
        fp = ledger_fingerprint(ctx)
        snap = take_snapshot(ctx, f"before-{tag}")
        steps = [("revert", r["revert_commit"]) for r in reapply]
        steps.append(("revert", undone["revert_commit"]) if undone else ("merge", target))
        p = None
        made = []  # every commit this switch makes, in order, so a rollback can undo all of them
        for kind, ref in steps:
            if kind == "revert":
                p = _git(ctx, "revert", "--no-edit", ref, check=False)
                op_abort = ("revert", "--abort")
            else:
                p = _git(ctx, "merge", "--no-ff", "--no-edit", "-m", f"xt version use {tag}", ref, check=False)
                op_abort = ("merge", "--abort")
            if p.returncode != 0:
                break
            made.append({"commit": _git(ctx, "rev-parse", "HEAD").stdout.strip(), "merge": kind == "merge"})
        if p.returncode != 0:
            conflicts = _git(ctx, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            _git(ctx, *op_abort, check=False)
            if _git(ctx, "rev-parse", "HEAD").stdout.strip() != prev_head:  # an earlier re-apply went in: undo it
                _git(ctx, "reset", "--hard", prev_head, check=False)  # safe: the tree was clean at the start
            if _git(ctx, "rev-parse", "HEAD").stdout.strip() != prev_head:
                raise XtError("the merge failed and the repo isn't back at its previous commit; restore it by hand "
                              f"(`git reset --hard {prev_head}`), snapshot {snap}")
            raise XtError(
                f"merging {tag} conflicts in: {', '.join(conflicts) or '(see git)'}. Nothing changed: the team repo is "
                f"back at {versions.display(prev_version)} and still down. To resolve by hand: `git merge --no-ff {tag}`, "
                f"fix the files, `git commit`, then run `xt version use {tag}{' --candidate' if candidate else ''}` again "
                f"to finish the checks.")
        merge_commit = _git(ctx, "rev-parse", "HEAD").stdout.strip()
        problems = []
        if not _installed_matches(ctx, tag):
            problems.append(f"installed version is {versions.display(versions.installed(ctx))}, not {tag}")
        if not ledger_continues(ctx, fp):
            problems.append("the ledger no longer starts with the recorded messages")
        if problems:
            raise XtError(f"after merging {tag}: {'; '.join(problems)}. The team stays down; the merge is commit "
                          f"{merge_commit[:12]}, the previous code {prev_head[:12]}, the snapshot {snap}.")
        for r in reapply + ([undone] if undone else []):
            r["reapplied"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        recs.append({"at": dt.datetime.now().astimezone().isoformat(timespec="seconds"), "tag": tag,
                     "commit": target, "merge_commit": merge_commit, "made": made, "previous_version": prev_version,
                     "previous_head": prev_head, "state_format": fmt, "snapshot": str(snap.relative_to(ctx.paths.root)),
                     "ledger": fp})
        _save_records(ctx, recs)
        lines.append(f"switched to {tag} (commit {target[:12]}; merge {merge_commit[:12]}): previous "
                     f"{versions.display(prev_version)}, installed now {versions.display(versions.installed(ctx))}, "
                     f"state format {fmt}, snapshot {snap.relative_to(ctx.paths.root)}")
        lines.append("not running yet: `xt up` (or `xt restart --all`) starts the team on it")
    ctx.ledger.append(SYSTEM, HUMAN, "system", lines[0])
    return lines + [_refresh(ctx)]


def _refresh(ctx: Ctx) -> str:
    """After a switch or a rollback, the published version is read again (card #133): the upstream
    was just asked, and the cached one may predate the release switched to."""
    return versions.refresh_published(ctx, dt.datetime.now().astimezone())


# --- rollback -------------------------------------------------------------------------------------


def rollback(ctx: Ctx) -> list[str]:
    with _exclusive(ctx):
        _require_down(ctx)
        _require_clean(ctx)
        recs = records(ctx)
        rec = next((r for r in reversed(recs) if not r.get("rolled_back")), None)
        if rec is None:
            raise XtError("no recorded version switch to roll back")
        prev = rec.get("previous_version")
        snap = ctx.paths.root / rec["snapshot"]
        if not (snap / "manifest.json").exists():
            raise XtError(f"the snapshot of that switch is missing ({rec['snapshot']}); rollback refused, nothing changed")
        head = _git(ctx, "rev-parse", "HEAD").stdout.strip()
        prev_commit = rec.get("previous_head")
        reads = formats_of(ctx, prev_commit) if prev_commit else None
        fmt = team_format(ctx)
        if reads is None or fmt not in reads:
            raise XtError(f"{versions.display(prev)} doesn't read the team's state format {fmt}; rollback refused "
                          f"(state isn't restored across formats). Nothing changed; snapshot {rec['snapshot']}.")
        if not ledger_continues(ctx, rec["ledger"]):
            raise XtError("the ledger doesn't continue the one recorded at the switch; rollback refused, nothing changed")
        made = rec.get("made") or [{"commit": rec["merge_commit"], "merge": True}]
        p = None
        for step in reversed(made):  # undo everything the switch made, newest first
            args = ["revert", "--no-edit"] + (["-m", "1"] if step["merge"] else []) + [step["commit"]]
            p = _git(ctx, *args, check=False)
            if p.returncode != 0:
                break
        if p.returncode != 0:
            conflicts = _git(ctx, "diff", "--name-only", "--diff-filter=U", check=False).stdout.split()
            _git(ctx, "revert", "--abort", check=False)
            if _git(ctx, "rev-parse", "HEAD").stdout.strip() != head:  # an earlier revert went in: undo it
                _git(ctx, "reset", "--hard", head, check=False)  # safe: the tree was clean at the start
            raise XtError(f"undoing {rec['tag']} conflicts in: {', '.join(conflicts) or '(see git)'} (files changed since "
                          f"the switch). Nothing changed: still {rec['tag']}, team down. To do it by hand: "
                          f"`git revert -m 1 {rec['merge_commit'][:12]}`, resolve, `git commit`.")
        revert_commit = _git(ctx, "rev-parse", "HEAD").stdout.strip()
        problems = []
        if versions.parse(versions.installed(ctx)) != versions.parse(prev):
            problems.append(f"installed version is {versions.display(versions.installed(ctx))}, not {versions.display(prev)}")
        if not ledger_continues(ctx, rec["ledger"]):
            problems.append("the ledger no longer starts with the recorded messages")
        if problems:
            raise XtError(f"rollback incomplete: {'; '.join(problems)}. The team stays down; revert commit "
                          f"{revert_commit[:12]}, before it {head[:12]}, snapshot {rec['snapshot']}.")
        rec["rolled_back"] = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        rec["revert_commit"] = revert_commit
        _save_records(ctx, recs)
        line = (f"rolled back {rec['tag']} to {versions.display(prev)} (revert {revert_commit[:12]}); team commits kept; "
                f"state format {fmt} unchanged, so the current state stays (it matches the ledger); "
                f"ledger intact ({rec['ledger']['count']} recorded messages); snapshot kept at {rec['snapshot']}")
    ctx.ledger.append(SYSTEM, HUMAN, "system", line)
    return [line, "not running yet: `xt up` (or `xt restart --all`) starts the team on it", _refresh(ctx)]


def show(ctx: Ctx) -> list[str]:
    out = [versions.current(ctx).line(), f"state format: {team_format(ctx) or 'not recorded (run `xt up`)'}; "
           f"this xt reads {', '.join(map(str, STATE_FORMATS))}"]
    for r in records(ctx)[-5:]:
        state = f"rolled back {r['rolled_back']}" if r.get("rolled_back") else "current"
        out.append(f"  {r['at']}  {versions.display(r.get('previous_version'))} → {r['tag']}  ({state}; snapshot {r['snapshot']})")
    return out
