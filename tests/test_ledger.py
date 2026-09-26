import gzip

from xt.ledger import Ledger


def test_ids_are_sequential_and_items_open_and_close(ctx):
    g = ctx.ledger.append("liaison", "lead", "goal", "Build a thing\nmore")
    t = ctx.ledger.append("lead", "carol", "task", "do part", ref=g["id"])
    assert (g["id"], t["id"]) == (1, 2)
    items = {i["id"]: i for i in ctx.ledger.open_items()}
    assert items[1]["title"] == "Build a thing"
    assert items[2]["goal"] == 1 and items[2]["owner"] == "carol"
    ctx.ledger.append("carol", "lead", "done", "finished", ref=2)
    assert [i["id"] for i in ctx.ledger.open_items()] == [1]


def test_owner_reports_update_last_from_owner(ctx):
    t = ctx.ledger.append("lead", "carol", "task", "x")
    ctx.ledger.append("lead", "carol", "ask", "any news?", ref=t["id"])
    assert ctx.ledger.item(t["id"])["last_from_owner"] is None
    r = ctx.ledger.append("carol", "lead", "report", "halfway", ref=t["id"])
    assert ctx.ledger.item(t["id"])["last_from_owner"] == r["ts"]


def test_snapshot_rebuilds_from_logs(ctx, paths, clock):
    ctx.ledger.append("liaison", "lead", "goal", "g")
    ctx.ledger.append("lead", "carol", "task", "t", ref=1)
    (paths.state / "ledger.json").unlink()
    fresh = Ledger(paths, clock=clock)
    assert [i["id"] for i in fresh.open_items()] == [1, 2]
    assert fresh.append("x", "y", "report", "z")["id"] == 3


def test_rotation_archives_without_losing_open_items(ctx, paths, clock):
    ctx.ledger.append("liaison", "lead", "goal", "old goal")
    clock.advance(days=40)
    ctx.ledger.append("lead", "liaison", "report", "still going", ref=1)
    done = ctx.ledger.rotate(raw_days=30, delete_after_days=0)
    assert done == ["archived 2026-09-26.jsonl"]
    assert (paths.archive / "2026-09-26.jsonl.gz").exists()
    with gzip.open(paths.archive / "2026-09-26.jsonl.gz", "rt") as fh:
        assert "old goal" in fh.read()
    assert [m["id"] for m in ctx.ledger.messages()] == [1, 2]
    (paths.state / "ledger.json").unlink()
    assert [i["id"] for i in Ledger(paths, clock=clock).open_items()] == [1]


def test_delete_after_days(ctx, paths, clock):
    ctx.ledger.append("a", "b", "report", "x")
    clock.advance(days=40)
    ctx.ledger.rotate(30, 0)
    clock.advance(days=400)
    assert ctx.ledger.rotate(30, 365) == ["deleted 2026-09-26.jsonl.gz"]
