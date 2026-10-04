"""Alerts for the human, deduplicated by key, raised by the supervisor."""

import json
import os

from .context import Ctx
from .team import HUMAN, SYSTEM


# Supervisor failures that raise one Inbox alert per kind (card #131): kind -> alert key
FAILURES = {"wake-up": "failed:wake-up", "notification": "failed:notification",
            "usage recording": "failed:usage-recording", "pane-input": "failed:pane-input"}


def repeats(alert: dict) -> str:
    """`  ×3, last 14:05` for an alert that has repeated, else ``."""
    n = int(alert.get("count", 1))
    last = str(alert.get("last") or "")
    return f"  ×{n}, last {last[11:16]}" if n > 1 and last else (f"  ×{n}" if n > 1 else "")


class Alerts:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / "alerts.json"

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        os.replace(tmp, self.path)

    def active(self) -> dict:
        with self.ctx.ledger.lock():
            return self._load()

    def raise_(self, key: str, text: str) -> bool:
        with self.ctx.ledger.lock():
            d = self._load()
            if key in d:
                return False
        msg = self.ctx.ledger.append(SYSTEM, HUMAN, "alert", text)
        with self.ctx.ledger.lock():
            d = self._load()
            d[key] = {"text": text, "ts": msg["ts"], "id": msg["id"]}
            self._save(d)
        return True

    def raise_or_count(self, key: str, text: str) -> dict | None:
        """Raise an alert, or, while one with this key is still open, count the repeat on it (count,
        last time and the newest text) instead of adding another (card #131). Returns the new alert
        message, or None for a repeat. Once the human clears it, the next call raises a new one."""
        with self.ctx.ledger.lock():
            d = self._load()
            if key in d:
                d[key].update(text=text, count=int(d[key].get("count", 1)) + 1,
                              last=self.ctx.ledger.clock().isoformat(timespec="seconds"))
                self._save(d)
                return None
        msg = self.ctx.ledger.append(SYSTEM, HUMAN, "alert", text)
        with self.ctx.ledger.lock():
            d = self._load()
            d[key] = {"text": text, "ts": msg["ts"], "id": msg["id"], "count": 1, "last": msg["ts"]}
            self._save(d)
        return msg

    def update_text(self, key: str, text: str) -> None:
        """New text for an open alert, without a new message or notification (card #187)."""
        with self.ctx.ledger.lock():
            d = self._load()
            if key in d and d[key]["text"] != text:
                d[key]["text"] = text
                self._save(d)

    def fold(self, key: str, line: str | None) -> None:
        """Add `line` under an open alert's own text, replacing an earlier one (None: take it off)
        (card #187: the queue for a member that isn't running joins its `missing:` alert)."""
        with self.ctx.ledger.lock():
            d = self._load()
            if key not in d:
                return
            base = d[key].get("base", d[key]["text"])
            text = f"{base}\n{line}" if line else base
            if d[key]["text"] != text:
                d[key].update(text=text, base=base)
                self._save(d)

    def resolve(self, key: str) -> bool:
        with self.ctx.ledger.lock():
            d = self._load()
            if key not in d:
                return False
            del d[key]
            self._save(d)
        return True

    def resolve_prefix(self, prefix: str, keep: set[str]) -> None:
        with self.ctx.ledger.lock():
            d = self._load()
            for k in [k for k in d if k.startswith(prefix) and k not in keep]:
                del d[k]
            self._save(d)
