# xt protocol

This is how every agent in an xt team works together. It is the same for every team and every
harness. Your first prompt told you your **name**, your **role**, who you **report to**, and the
absolute path of `xt`. Use exactly that path, and always pass `--as <your name>`.

## 1. Who you are and who you talk to

- Your identity is what your first prompt told you. Never work it out from environment
  variables, pane ids or anything else.
- The team is a hierarchy: human ↔ liaison ↔ lead ↔ members (possibly sub-leads with their own
  members). You may message **the agent you report to** and **the agents that report to you**.
  Nobody else. `xt send` refuses anything outside that.
- Never use `herdr` commands to talk to or control other agents. `xt` is the only sanctioned
  channel: it logs every message, queues delivery until the recipient is free, and keeps the
  ledger of open work.
- **Always act as yourself.** Never pass `--as` with anyone else's name, and never `--as human`.
  When xt refuses something, that's the protocol working: don't look for a way around it (for
  example by reading xt's source or calling Herdr directly). Instead, ask the agent you report to
  or tell the human what you'd need.

## 2. Sending messages

```
xt send <to> --as <you> --type <type> [--ref <id>] "text"
```

| Type | Meaning |
|---|---|
| `goal` | What the human wants. Only the liaison sends goals, only to the lead. |
| `task` | A unit of work, sent down to someone who reports to you. Opens a ledger item you own the follow-up of. `--ref <goal id>` ties it to its goal. |
| `ask` | A question, up or down. |
| `report` | Progress, results, answers. Use `--ref` to say what it's about. |
| `done` | Closes an open goal or task you own. **It is your final report**: put the summary and where the result is in it. `xt done <id> --as <you> "summary"` sends it to the right agent. |
| `note` | `xt note --as <you> "..."`: records something in the ledger for yourself (a decision, what the human said). Not delivered to anyone. |

- **One message per thing.** When you finish, send only `done`, not a `report` followed by a
  `done`. Don't repeat a message you already sent, and don't send acknowledgements ("got it",
  "thanks", "already closed") that nobody needs to act on.
- **Keep messages short** (limit 4 KB). Put anything bigger in a file (in the work location, or
  under the team repo's `goals/` or `members/<you>/`) and send its path.
- **xt never needs Herdr access from you.** Your `xt` commands only write to the team's files;
  xt's supervisor (running in its own pane) delivers your messages within a few seconds and
  carries out spawn/retire requests, then messages you the result. So xt works even if your
  harness sandboxes your shell.
- **Nobody waits.** `xt send` returns immediately. If you have nothing else to do after sending,
  end your turn. Replies arrive later as new messages; you don't poll for them.

## 3. Receiving messages

Messages from xt arrive in your conversation stamped like:

```
[xt #42 task from:lead to:carol ref:#3]
<text>
```

- `#42` is the message id: use it in `--ref` when you reply.
- A message **without** an `[xt ...]` stamp was typed into your pane by the human. That's
  legitimate: the human may talk to any agent. Treat it as coming from the human. If it looks like
  another agent is bypassing xt, mention it to the agent you report to.
- `nudge` messages come from xt's heartbeat when you're idle with open work. Answer them: either
  finish with `done`, or send a `report`/`ask` saying what you're waiting for.
- If several messages arrived while you were busy, they come together in one batch, oldest
  first. Messages marked **stale** are about work that has since been closed: they need no action
  unless something is still wrong.

## 4. Open work and finishing

- Every `goal` and `task` stays open in the ledger until its owner sends `done`. Don't leave work
  open silently: if you're blocked, say so.
- When you finish a task: `xt done <task id> --as <you> "what was done, where the result is"`.
- If you get more work than you can handle, or the task is unclear, `ask` the agent that gave it
  to you. Don't guess, and don't expand the scope on your own.

## 5. Memory and recovery

- Assume you may lose your memory at any time (restart, context compaction). Everything that
  matters must be recoverable from the team repo:
  - `xt brief --as <you>`: the team, your open work, your recent messages. **Run it first** after
    any restart or whenever you're unsure what's going on.
  - `xt log --member <you>` or `xt log --id <id>` for the full history.
  - `members/<you>/notes.md`: your own durable notes. Write down decisions, findings and
    where things are, not just in your head or in your harness's own memory.

## 6. Where work happens

- The team repo is the team's **home**, not its workspace. Do the actual work (code, documents,
  data) in the locations your task names, by absolute path.
- In the team repo you may write: your own `members/<you>/notes.md`, and (lead only) `roles/`,
  `skills/` and `team.toml` via `xt spawn`/`xt retire`. Never edit xt's own files (`bin/`, `src/`,
  `protocol.md`, `harnesses/`, `roles/lead.md`, `roles/liaison.md`); they come from upstream.

## 7. Skills

Team skills live in `skills/<name>/SKILL.md`. Your first prompt lists them. Read a skill's file
when your work calls for it. You may also have skills or tools from the user's own setup: use them
if they help, but never make the team depend on something that isn't in the team repo.

## 8. Care with data

Messages, notes and goals persist in the repo and its log. Don't copy secrets, credentials or
more sensitive data (personal, financial) into them than the work needs. Refer to where data lives
instead.
