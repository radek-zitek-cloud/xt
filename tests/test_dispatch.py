import pytest

from xt.dispatch import Queue, drain, send
from xt.paths import XtError

from .conftest import add_member


def test_policy_allows_only_the_reports_to_chain(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dave")
    for a in ("liaison", "lead", "carol", "dave"):
        ctx.herdr.add(a)
    send(ctx, "carol", "lead", "report", "hi")
    send(ctx, "lead", "carol", "task", "do it")
    with pytest.raises(XtError, match="may only message"):
        send(ctx, "carol", "dave", "ask", "psst")
    with pytest.raises(XtError, match="may only message"):
        send(ctx, "carol", "liaison", "ask", "skip the lead")
    with pytest.raises(XtError, match="tasks go downward"):
        send(ctx, "carol", "lead", "task", "boss, do this")
    with pytest.raises(XtError, match="only the liaison"):
        send(ctx, "lead", "carol", "goal", "a goal")
    send(ctx, "human", "dave", "ask", "human may talk to anyone")


def test_unknown_or_retired_agents_are_refused(ctx):
    with pytest.raises(XtError, match="not an active member"):
        send(ctx, "mallory", "lead", "report", "x")
    add_member(ctx, "carol")
    ctx.team.set_status("carol", "retired")
    ctx.team.save()
    ctx.reload_team()
    with pytest.raises(XtError, match="not an active member"):
        send(ctx, "lead", "carol", "task", "x")


def test_delivers_when_idle_with_envelope_and_reply_hint(ctx):
    add_member(ctx, "carol")
    ctx.herdr.add("carol")
    msg, status = send(ctx, "lead", "carol", "task", "parse the file")
    assert status == "delivered"
    text = ctx.herdr.last_prompt("carol")
    assert text.startswith(f"[xt #{msg['id']} task from:lead to:carol]\nparse the file")
    assert f"--as carol --type report --ref {msg['id']}" in text
    assert f"--type done --ref {msg['id']}" in text


def test_queues_when_busy_and_drains_in_order(ctx):
    add_member(ctx, "carol")
    ctx.herdr.add("carol", status="working")
    m1, s1 = send(ctx, "lead", "carol", "task", "first")
    m2, s2 = send(ctx, "lead", "carol", "task", "second")
    assert s1.startswith("queued") and s2.startswith("queued")
    assert drain(ctx) == []
    ctx.herdr.live["carol"].status = "idle"
    assert drain(ctx) == [f"delivered #{m1['id']} to carol"]
    assert "first" in ctx.herdr.last_prompt("carol")
    assert drain(ctx) == []  # carol is working again
    ctx.herdr.live["carol"].status = "done"
    assert drain(ctx) == [f"delivered #{m2['id']} to carol"]
    assert Queue(ctx).pending() == []


def test_new_message_waits_behind_queued_ones(ctx):
    add_member(ctx, "carol")
    ctx.herdr.add("carol", status="blocked")
    send(ctx, "lead", "carol", "task", "first")
    ctx.herdr.live["carol"].status = "idle"
    _, status = send(ctx, "lead", "carol", "ask", "second")
    assert "earlier messages" in status
    assert ctx.herdr.prompts == []


def test_done_rules(ctx):
    add_member(ctx, "carol")
    add_member(ctx, "dave")
    for a in ("lead", "carol", "dave"):
        ctx.herdr.add(a)
    t, _ = send(ctx, "lead", "carol", "task", "x")
    with pytest.raises(XtError, match="needs --ref"):
        send(ctx, "carol", "lead", "done", "ok")
    with pytest.raises(XtError, match="owned by carol"):
        send(ctx, "dave", "lead", "done", "mine now", ref=t["id"])
    send(ctx, "carol", "lead", "done", "ok", ref=t["id"])
    assert ctx.ledger.item(t["id"]) is None
    with pytest.raises(XtError, match="not an open"):
        send(ctx, "carol", "lead", "done", "again", ref=t["id"])


def test_message_size_limit(ctx):
    ctx.herdr.add("lead")
    with pytest.raises(XtError, match="over the 4096 limit"):
        send(ctx, "liaison", "lead", "report", "x" * 5000)


def test_messages_to_human_are_not_delivered_via_herdr(ctx):
    ctx.herdr.add("liaison")
    _, status = send(ctx, "liaison", "human", "report", "hello human")
    assert "human" in status and ctx.herdr.prompts == []
