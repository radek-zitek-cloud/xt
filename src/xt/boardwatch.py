"""The board watch (card #135): tell the lead when a card enters the watched Board column.

xt knows no board tool. The team names a command in team.toml; the supervisor runs it every
`interval`, without a shell, with no input and the supervisor's own environment, and reads what it
prints:

    [board_watch]
    command = ["fizzy", "card", "list", "--board", "BOARD_ID", "--column", "COLUMN_ID", "--all",
               "--jq", "[.data[] | {number, title}]"]
    interval = "5m"     # default 5m
    timeout = "30s"     # default 30s
    column = "Ready to build"   # optional: the column's name, for the message

The contract: exit 0 and, on standard output, one JSON array of the cards now in the column, each an
object with a `number` (integer or string) and an optional `title`. Anything else is a failure.

The first success after the supervisor starts records the set and tells no one, so a restart
replays nothing. After that, each number that wasn't in the set is one system message to the lead.
The first failure raises one Inbox alert; the next success clears it. During an outage the old set
is kept, so cards that entered meanwhile are reported after it. Nothing here is given to agents.
"""

import datetime as dt
import json
import os
import signal
import subprocess

from .alerts import Alerts
from .context import Ctx
from .paths import XtError
from .team import HUMAN, SYSTEM, parse_interval

ALERT = "boardwatch"
MAX_OUTPUT = 64 * 1024
DEFAULTS = {"interval": "5m", "timeout": "30s"}


class Config:
    def __init__(self, raw: dict):
        command = raw.get("command")
        if not (isinstance(command, list) and command and all(isinstance(a, str) and a for a in command)):
            raise XtError("[board_watch] command must be a non-empty argument list of strings, "
                          "e.g. [\"fizzy\", \"card\", \"list\", …]")
        self.command = [str(a) for a in command]
        self.interval = parse_interval(str(raw.get("interval", DEFAULTS["interval"])))
        self.timeout = parse_interval(str(raw.get("timeout", DEFAULTS["timeout"])))
        self.timeout_text = str(raw.get("timeout", DEFAULTS["timeout"])).strip()
        self.column = str(raw["column"]) if raw.get("column") else None


def config(ctx: Ctx) -> dict | None:
    """The `[board_watch]` table, or None when the team has none."""
    raw = ctx.team.doc.get("board_watch")
    return dict(raw) if raw is not None else None


def parse(stdout: bytes) -> dict[str, str]:
    """number -> title from the command's output; raises ValueError for anything off the contract."""
    if len(stdout) > MAX_OUTPUT:
        raise ValueError(f"output over {MAX_OUTPUT // 1024} KB")
    data = json.loads(stdout.decode("utf-8"))
    if not isinstance(data, list):
        raise ValueError("not a JSON array")
    out = {}
    for card in data:
        if not isinstance(card, dict) or "number" not in card:
            raise ValueError("an element is not an object with a number")
        n = card["number"]
        if isinstance(n, bool) or not isinstance(n, (int, str)) or not str(n).strip():
            raise ValueError("a number is not an integer or a string")
        title = card.get("title")
        out[str(n).strip()] = title if isinstance(title, str) else ""
    return out


class BoardWatch:
    """Run by the supervisor on every tick; never blocks it: the command runs in the background and
    its result is read on a later tick."""

    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.state_path = ctx.paths.state / "board_watch.json"
        self.out_path = ctx.paths.state / "board_watch.out"
        self.err_path = ctx.paths.state / "board_watch.err"
        self.baseline: dict[str, str] | None = None  # set by the first success after this start
        self.proc: subprocess.Popen | None = None
        self.began = 0.0
        self.last_run = None  # monotonic-like `now` of the last start; None = never

    # --- state shown by status -------------------------------------------------------------------

    def _load(self) -> dict:
        try:
            return json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, **changes) -> None:
        d = self._load()
        d.update(changes)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        os.replace(tmp, self.state_path)

    # --- the tick --------------------------------------------------------------------------------

    def tick(self, now: float) -> list[str]:
        """Start the command when due, or read its result when it's done. Returns log lines."""
        raw = config(self.ctx)
        if raw is None:
            self._stop()
            return []
        try:
            cfg = Config(raw)
        except XtError as e:
            self._stop()
            return self._failed(f"bad [board_watch] in team.toml: {e}", "")
        if self.proc is not None:
            return self._collect(cfg, now)
        if self.last_run is None or now - self.last_run >= cfg.interval:
            return self._start(cfg, now)
        return []

    def _stop(self) -> None:
        """Kill a running command and whatever it started (it runs in its own process group)."""
        if self.proc is not None and self.proc.poll() is None:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except OSError:
                self.proc.kill()
            self.proc.wait()
        self.proc = None

    def _start(self, cfg: Config, now: float) -> list[str]:
        self.last_run = now
        try:
            with open(self.out_path, "wb") as out, open(self.err_path, "wb") as err:
                # an argument list, no shell: metacharacters stay plain text
                self.proc = subprocess.Popen(cfg.command, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                             cwd=str(self.ctx.paths.root), start_new_session=True)
        except OSError as e:
            self.proc = None
            return self._failed(f"the command can't be started ({e.strerror or e})", "")
        self.began = now
        return []

    def _collect(self, cfg: Config, now: float) -> list[str]:
        code = self.proc.poll()
        if code is None:
            too_big = self.out_path.exists() and self.out_path.stat().st_size > MAX_OUTPUT
            if now - self.began < cfg.timeout and not too_big:
                return []
            self._stop()
            cause = f"output over {MAX_OUTPUT // 1024} KB" if too_big else f"timed out after {cfg.timeout_text}"
            return self._failed(cause, self._first_err())
        self.proc = None
        if code != 0:
            return self._failed(f"exit code {code}", self._first_err())
        try:
            with open(self.out_path, "rb") as fh:
                cards = parse(fh.read(MAX_OUTPUT + 1))
        except (OSError, ValueError) as e:
            return self._failed(f"unreadable output ({e})", self._first_err())
        return self._succeeded(cfg, cards)

    def _first_err(self) -> str:
        try:
            with open(self.err_path, "rb") as fh:
                text = fh.read(4096).decode("utf-8", "replace")
        except OSError:
            return ""
        return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")[:200]

    def _clock(self) -> str:
        return self.ctx.ledger.clock().isoformat(timespec="seconds")

    def _failed(self, cause: str, err: str) -> list[str]:
        state = self._load()
        text = f"board watch failed: {cause}" + (f": {err}" if err else "")
        if not state.get("failure"):  # once per outage, not per run
            Alerts(self.ctx).raise_(
                ALERT, f"{text}. The team isn't told about cards entering the column until it works again "
                       f"([board_watch] in team.toml; the next success clears this).")
            self._save(failure=text, failing_since=self._clock())
            return [text]
        self._save(failure=text)
        return []

    def _succeeded(self, cfg: Config, cards: dict[str, str]) -> list[str]:
        lines = []
        if self._load().get("failure"):
            Alerts(self.ctx).resolve(ALERT)
            lines.append("board watch works again")
        if self.baseline is None:
            lines.append(f"board watch: baseline of {len(cards)} card(s) recorded")
        else:
            for n in [n for n in cards if n not in self.baseline]:
                lines.append(self._tell_lead(cfg, n, cards[n]))
        self.baseline = cards
        self._save(failure=None, failing_since=None, last_ok=self._clock(), cards=len(cards))
        return lines

    def _tell_lead(self, cfg: Config, number: str, title: str) -> str:
        from .dispatch import send

        where = cfg.column or "the watched column"
        text = f"Card {number}{f' ({title})' if title else ''} is now in {where} (seen by the board watch)"
        lead = self.ctx.team.lead_of_role("lead")
        if lead is None:
            self.ctx.ledger.append(SYSTEM, HUMAN, "system", text + "; the team has no lead")
        else:
            send(self.ctx, SYSTEM, lead.name, "system", text)
        return f"board watch: card {number} entered; told {lead.name if lead else 'nobody (no lead)'}"


def status_line(ctx: Ctx) -> str | None:
    """`board watch: …` for `xt status`; None when the team has no `[board_watch]`."""
    if config(ctx) is None:
        return None
    try:
        d = json.loads((ctx.paths.state / "board_watch.json").read_text())
    except (OSError, ValueError):
        d = {}

    def hhmm(ts):
        try:
            return dt.datetime.fromisoformat(ts).astimezone().strftime("%a %H:%M")
        except (TypeError, ValueError):
            return "?"

    if d.get("failure"):
        return f"board watch: FAILING since {hhmm(d.get('failing_since'))}: {d['failure']}"
    if d.get("last_ok"):
        return f"board watch: last success {hhmm(d['last_ok'])} ({d.get('cards', 0)} card(s) in the column)"
    return "board watch: no successful run yet (the supervisor runs it)"
