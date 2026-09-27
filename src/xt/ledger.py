"""The message log, which is also the ledger of open goals and tasks.

Log: `.xt/log/YYYY-MM-DD.jsonl`, append-only, one message per line.
Snapshot: `.xt/state/ledger.json` holds the id sequence and the open items; it can always be
rebuilt from the logs, so archiving old log files never loses an open item.
"""

import contextlib
import datetime as dt
import fcntl
import gzip
import json
import os
from pathlib import Path
from typing import Iterator

from .paths import Paths, XtError

AGENT_TYPES = ("goal", "task", "ask", "report", "done", "note")
SYSTEM_TYPES = ("alert", "approval", "nudge", "system", "wake")
OPENING = ("goal", "task")
HUMAN = "human"  # same as team.HUMAN (not imported, to keep the ledger free of team logic)


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def title_of(body: str, width: int = 80) -> str:
    first = body.strip().splitlines()[0] if body.strip() else ""
    return first if len(first) <= width else first[: width - 1] + "…"


class Ledger:
    def __init__(self, paths: Paths, clock=now):
        self.paths = paths
        self.clock = clock
        paths.ensure_runtime()

    @property
    def snapshot_path(self) -> Path:
        return self.paths.state / "ledger.json"

    @contextlib.contextmanager
    def lock(self):
        with open(self.paths.state / "lock", "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def _read_snapshot(self) -> dict:
        if self.snapshot_path.exists():
            return json.loads(self.snapshot_path.read_text())
        return self._rebuild()

    def _write_snapshot(self, snap: dict) -> None:
        tmp = self.snapshot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(snap, indent=1))
        os.replace(tmp, self.snapshot_path)

    @staticmethod
    def _apply(snap: dict, msg: dict) -> None:
        snap["seq"] = max(snap.get("seq", 0), msg["id"])
        items = snap.setdefault("open", {})
        ref = str(msg["ref"]) if msg.get("ref") is not None else None
        if msg["type"] in OPENING:
            items[str(msg["id"])] = {
                "id": msg["id"],
                "type": msg["type"],
                "title": title_of(msg["body"]),
                "owner": msg["to"],
                "opener": msg["from"],
                "goal": msg.get("ref"),
                "opened": msg["ts"],
                "last_activity": msg["ts"],
                "last_from_owner": None,
            }
        elif msg["type"] == "ask" and msg["to"] == HUMAN:
            # A question for the human stays open (in their Inbox) until they answer it (any
            # message from them with --ref to it) or the asker closes it with `done`.
            items[str(msg["id"])] = {
                "id": msg["id"],
                "type": "ask",
                "title": title_of(msg["body"]),
                "owner": HUMAN,
                "opener": msg["from"],
                "goal": None,
                "about": msg.get("ref"),
                "opened": msg["ts"],
                "last_activity": msg["ts"],
                "last_from_owner": None,
            }
        elif msg["type"] == "done" and ref in items:
            del items[ref]
        elif ref in items and items[ref]["type"] == "ask" and msg["from"] == items[ref]["owner"]:
            del items[ref]  # the human answered
        elif ref in items:
            items[ref]["last_activity"] = msg["ts"]
            if msg["from"] == items[ref]["owner"]:
                items[ref]["last_from_owner"] = msg["ts"]

    def _rebuild(self) -> dict:
        snap: dict = {"seq": 0, "open": {}}
        for msg in self.messages():
            self._apply(snap, msg)
        return snap

    def rebuild(self) -> None:
        with self.lock():
            self._write_snapshot(self._rebuild())

    def append(self, sender: str, to: str, mtype: str, body: str, ref: int | None = None,
               fill_id: bool = False) -> dict:
        """Log a message. With fill_id, "{id}" in the body becomes the message's own id."""
        if mtype not in AGENT_TYPES + SYSTEM_TYPES:
            raise XtError(f"unknown message type {mtype!r}")
        with self.lock():
            snap = self._read_snapshot()
            ts = self.clock()
            new_id = snap.get("seq", 0) + 1
            if fill_id:
                body = body.replace("{id}", str(new_id))
            msg = {
                "id": new_id,
                "ts": ts.isoformat(timespec="seconds"),
                "type": mtype,
                "from": sender,
                "to": to,
                "ref": ref,
                "body": body,
            }
            day = self.paths.log / f"{ts.date().isoformat()}.jsonl"
            with open(day, "a") as fh:
                fh.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self._apply(snap, msg)
            self._write_snapshot(snap)
        return msg

    def last_id(self) -> int:
        with self.lock():
            return self._read_snapshot().get("seq", 0)

    def open_items(self) -> list[dict]:
        with self.lock():
            snap = self._read_snapshot()
        return sorted(snap.get("open", {}).values(), key=lambda i: i["id"])

    def item(self, item_id: int) -> dict | None:
        return next((i for i in self.open_items() if i["id"] == item_id), None)

    def _files(self) -> list[Path]:
        files = list(self.paths.archive.glob("*.jsonl.gz")) + list(self.paths.log.glob("*.jsonl"))
        return sorted(files, key=lambda p: p.name.split(".")[0])

    def messages(self, since_days: int | None = None) -> Iterator[dict]:
        cutoff = None
        if since_days is not None:
            cutoff = (self.clock() - dt.timedelta(days=since_days)).date().isoformat()
        for f in self._files():
            if cutoff and f.name.split(".")[0] < cutoff:
                continue
            opener = gzip.open if f.suffix == ".gz" else open
            with opener(f, "rt") as fh:
                for line in fh:
                    if line.strip():
                        yield json.loads(line)

    def message(self, msg_id: int) -> dict | None:
        return next((m for m in self.messages() if m["id"] == msg_id), None)

    def today_size(self) -> int:
        f = self.paths.log / f"{self.clock().date().isoformat()}.jsonl"
        return f.stat().st_size if f.exists() else 0

    def rotate(self, raw_days: int, delete_after_days: int) -> list[str]:
        """Gzip logs older than raw_days; delete archives older than delete_after_days (0 = never)."""
        done = []
        today = self.clock().date()
        with self.lock():
            for f in sorted(self.paths.log.glob("*.jsonl")):
                day = dt.date.fromisoformat(f.name.split(".")[0])
                if (today - day).days > raw_days:
                    target = self.paths.archive / (f.name + ".gz")
                    with open(f, "rb") as src, gzip.open(target, "wb") as dst:
                        dst.write(src.read())
                    f.unlink()
                    done.append(f"archived {f.name}")
            if delete_after_days:
                for f in sorted(self.paths.archive.glob("*.jsonl.gz")):
                    day = dt.date.fromisoformat(f.name.split(".")[0])
                    if (today - day).days > delete_after_days:
                        f.unlink()
                        done.append(f"deleted {f.name}")
        return done
