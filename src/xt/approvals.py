"""Approvals waiting for the human: the spawns and schedules agents asked for.

Part of the lifecycle's shared layer (card #215): the brief, the inbox, chat and the supervisor read
the pending approvals, and spawn adds and carries them out, so the store lives apart from spawn.
"""

import json
import os

from .context import Ctx
from .operators import answered_by
from .paths import XtError
from .team import ALWAYS, HUMAN, SYSTEM, harness_model


class Approvals:
    def __init__(self, ctx: Ctx):
        self.ctx = ctx
        self.path = ctx.paths.state / "approvals.json"

    def _load(self) -> dict:
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def _save(self, d: dict) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, indent=1))
        os.replace(tmp, self.path)

    def pending(self) -> dict:
        with self.ctx.ledger.lock():
            return self._load()

    def add(self, req: dict) -> int:
        if req.get("kind") == "schedule":
            what = (f"{req['requester']} asks to wake {req['name']} every {req['every']} when idle"
                    + (f" between {req['between']}" if req.get("between") and req["between"] != ALWAYS else "")
                    + (f" at {req['at']}" if req.get("at") and req["at"] not in (ALWAYS, "off") else "")
                    + (f" ({req['message']})" if req.get("message") else "")
                    + ": each wake-up is a billed agent turn.")
        else:
            what = (f"{req['requester']} asks to spawn {req['name']} as {req['role']} on {req['harness']}"
                    + (f" ({req['model']})" if req.get("model") else "")
                    + f", reporting to {req['reports_to']}."
                    + (f" {req['settings_note']}" if req.get("settings_note") else "")
                    + (f"\n{req['caps_note']}" if req.get("caps_note") else ""))  # card #186, its own rows
        # a closed question with the request as its narrative (card #183): yes approves, no denies
        msg = self.ctx.ledger.append(
            SYSTEM,
            HUMAN,
            "approval",
            what + "\n\nAnswer yes or no: xt answer {id} yes|no (or s, then y / n on it in the TUI's Inbox). "
                   "xt approve {id} and xt deny {id} (a / d) still work.",
            fill_id=True,
            data={"question": {"kind": "closed"}},
        )
        with self.ctx.ledger.lock():
            d = self._load()
            d[str(msg["id"])] = req
            self._save(d)
        return msg["id"]

    def pop(self, req_id: int) -> dict:
        with self.ctx.ledger.lock():
            d = self._load()
            req = d.pop(str(req_id), None)
            self._save(d)
        if req is None:
            asked = self.ctx.ledger.message(req_id)
            if asked and asked["type"] == "approval":  # answered before, through any route (card #183)
                by = answered_by(self.ctx, req_id)  # card #200: by an operator under a drive grant
                if by:
                    raise XtError(f"approval #{req_id}: {by}; nothing changed")
                raise XtError(f"approval #{req_id} was already answered; nothing changed (xt log --id {req_id})")
            raise XtError(f"no pending approval #{req_id}")
        return req

    def is_approval(self, req_id: int) -> bool:
        """Whether this id is an approval request, pending or answered."""
        if str(req_id) in self.pending():
            return True
        asked = self.ctx.ledger.message(req_id)
        return bool(asked and asked["type"] == "approval")


def approval_what(r: dict) -> str:
    """One line for a pending approval: `wake scout every 60m between …` / `spawn carol (role, harness/model)`."""
    if r.get("kind") == "schedule":
        return (f"wake {r['name']} every {r['every']}"
                + (f" between {r['between']}" if r.get("between") and r["between"] != ALWAYS else "")
                + (f" at {r['at']}" if r.get("at") and r["at"] not in (ALWAYS, "off") else ""))
    return (f"spawn {r['name']} ({r['role']}, {harness_model(r['harness'], r.get('model'))})"
            + (f" — {r['settings_note']}" if r.get("settings_note") else ""))
