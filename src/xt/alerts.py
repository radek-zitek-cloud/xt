"""Alerts for the human, deduplicated by key, raised by the supervisor."""

import json
import os

from .context import Ctx
from .team import HUMAN, SYSTEM


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
