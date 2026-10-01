"""v0.19.0 card #135: the board watch tells the lead when a card enters the watched column."""

import io
import json
import sys
import time

import pytest
import tomlkit

from xt import boardwatch, cli
from xt.alerts import Alerts
from xt.boardwatch import BoardWatch, parse
from xt.dispatch import Queue
from xt.watch import Supervisor

PY = sys.executable


def _watch(ctx, command, **extra):
    table = tomlkit.table()
    table["command"] = command
    for k, v in extra.items():
        table[k] = v
    ctx.team.doc["board_watch"] = table
    ctx.team.save()
    ctx.reload_team()


def _board(ctx, cards):
    """A fake board command printing what's in cards.json (rewritten by the test between runs)."""
    f = ctx.paths.root / "cards.json"
    f.write_text(json.dumps(cards))
    _watch(ctx, [PY, "-c", f"import sys; sys.stdout.write(open({str(f)!r}).read())"], column="Ready to build")
    return f


def _run(bw, now):
    """One run: start it, then tick until the command has finished and its result is read."""
    lines = bw.tick(now)
    deadline = time.monotonic() + 20
    while bw.proc is not None and time.monotonic() < deadline:
        time.sleep(0.02)
        lines += bw.tick(now + 0.001)
    assert bw.proc is None
    return lines


def _to_lead(ctx):
    return [m["body"] for m in ctx.ledger.messages() if m["to"] == "lead" and m["from"] == "xt"]


def test_parse_follows_the_contract():
    assert parse(b'[{"number": 129, "title": "Flow"}, {"number": "130"}]') == {"129": "Flow", "130": ""}
    assert parse(b"[]") == {}
    for bad in (b"{}", b"[1]", b'[{"title": "x"}]', b'[{"number": true}]', b"not json", b'[{"number": 1.5}]'):
        with pytest.raises(ValueError):
            parse(bad)
    with pytest.raises(ValueError, match="over 64 KB"):
        parse(b"[" + b" " * (64 * 1024) + b"]")


def test_a_team_without_board_watch_runs_nothing(ctx, monkeypatch):
    monkeypatch.setattr(boardwatch.subprocess, "Popen", lambda *a, **k: pytest.fail("ran a command"))
    assert BoardWatch(ctx).tick(time.time()) == []
    assert boardwatch.status_line(ctx) is None


def test_first_run_records_the_baseline_and_tells_no_one(ctx):
    _board(ctx, [{"number": 127, "title": "Old"}])
    lines = _run(BoardWatch(ctx), 1000.0)
    assert lines == ["board watch: baseline of 1 card(s) recorded"]
    assert _to_lead(ctx) == []


def test_a_card_entering_reaches_the_lead_once(ctx):
    f = _board(ctx, [{"number": 127, "title": "Old"}])
    bw = BoardWatch(ctx)
    _run(bw, 1000.0)
    f.write_text(json.dumps([{"number": 127, "title": "Old"}, {"number": 129, "title": "Work outline"}]))
    assert bw.tick(1000.0 + 10) == []  # not due yet (interval 5m)
    _run(bw, 1000.0 + 300)
    assert _to_lead(ctx) == ["Card 129 (Work outline) is now in Ready to build (seen by the board watch)"]
    assert [i["to"] for i in Queue(ctx).pending()] == ["lead"]  # delivered like any message
    _run(bw, 1000.0 + 600)  # still there: not posted again
    assert len(_to_lead(ctx)) == 1


def test_a_card_leaving_causes_nothing(ctx):
    f = _board(ctx, [{"number": 127}, {"number": 128}])
    bw = BoardWatch(ctx)
    _run(bw, 0.0)
    f.write_text(json.dumps([{"number": 127}]))
    assert _run(bw, 300.0) == []
    assert _to_lead(ctx) == []


def test_a_restart_replays_nothing(ctx):
    f = _board(ctx, [{"number": 127}])
    _run(BoardWatch(ctx), 0.0)
    f.write_text(json.dumps([{"number": 127}, {"number": 129}]))
    _run(BoardWatch(ctx), 0.0)  # a new supervisor: its first run is a baseline again
    assert _to_lead(ctx) == []


@pytest.mark.parametrize("command,cause", [
    ([PY, "-c", "import sys; sys.stderr.write('auth failed: no keyring\\n'); sys.exit(3)"], "exit code 3: auth failed: no keyring"),
    ([PY, "-c", "print('hello')"], "unreadable output"),
    (["/nonexistent/board-cmd"], "the command can't be started"),
])
def test_each_failure_raises_one_alert_and_success_clears_it(ctx, command, cause):
    f = _board(ctx, [{"number": 127}])
    good = list(ctx.team.doc["board_watch"]["command"])
    bw = BoardWatch(ctx)
    _run(bw, 0.0)  # baseline
    _watch(ctx, command)
    _run(bw, 300.0)
    _run(bw, 600.0)  # a repeat
    alerts = [m for m in ctx.ledger.messages() if m["type"] == "alert"]
    assert len(alerts) == 1 and cause in alerts[0]["body"]
    assert "boardwatch" in Alerts(ctx).active()
    assert "FAILING" in boardwatch.status_line(ctx) and cause in boardwatch.status_line(ctx)
    # a card enters during the outage; the old baseline is kept and it is reported after it
    f.write_text(json.dumps([{"number": 127}, {"number": 131, "title": "Detail"}]))
    _watch(ctx, good, column="Ready to build")
    lines = _run(bw, 900.0)
    assert "board watch works again" in lines
    assert "boardwatch" not in Alerts(ctx).active()
    assert _to_lead(ctx) == ["Card 131 (Detail) is now in Ready to build (seen by the board watch)"]
    assert boardwatch.status_line(ctx).startswith("board watch: last success")


def test_a_timeout_raises_the_alert_and_kills_the_command(ctx):
    _watch(ctx, [PY, "-c", "import time; time.sleep(30)"], timeout="1s")
    bw = BoardWatch(ctx)
    assert bw.tick(0.0) == []
    proc = bw.proc
    assert bw.tick(0.5) == []  # still within the timeout
    lines = bw.tick(1.5)
    assert lines and "timed out after 1s" in lines[0]
    assert proc.poll() is not None  # killed
    assert "timed out after 1s" in Alerts(ctx).active()["boardwatch"]["text"]


def test_the_default_timeout_is_30_seconds(ctx):
    _watch(ctx, ["true"])
    cfg = boardwatch.Config(dict(ctx.team.doc["board_watch"]))
    assert (cfg.interval, cfg.timeout) == (300, 30)


def test_no_shell_runs_the_command(ctx):
    marker = ctx.paths.root / "PWNED"
    _watch(ctx, ["echo", f"[]; touch {marker}", f"$(touch {marker})"])
    bw = BoardWatch(ctx)
    lines = _run(bw, 0.0)
    assert not marker.exists()
    assert lines and "unreadable output" in lines[0]  # printed literally, which isn't the contract


def test_a_bad_section_is_reported_once(ctx):
    _watch(ctx, "fizzy card list")  # a string, not an argument list
    bw = BoardWatch(ctx)
    assert "argument list" in bw.tick(0.0)[0]
    assert bw.tick(3.0) == []
    assert "argument list" in Alerts(ctx).active()["boardwatch"]["text"]


def test_the_supervisor_runs_it_and_status_shows_it(ctx, monkeypatch, capsys):
    _board(ctx, [{"number": 127}])
    sup = Supervisor(ctx, out=lambda s: None)
    t = time.time()
    sup.tick(t)
    deadline = time.monotonic() + 20
    while sup.board.proc is not None and time.monotonic() < deadline:
        time.sleep(0.02)
        sup.watch_board(t + 1)

    class Tty(io.StringIO):
        def isatty(self):
            return True

    monkeypatch.setattr(sys, "stdin", Tty())
    monkeypatch.setattr(cli.Ctx, "load", classmethod(lambda cls, *a, **k: ctx))
    cli.cmd_status(cli.build_parser().parse_args(["status"]))
    assert "board watch: last success" in capsys.readouterr().out
