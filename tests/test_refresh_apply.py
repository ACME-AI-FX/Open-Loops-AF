"""refresh.apply(): the pure merge of the agent's JSON into state.

    python3 tests/test_refresh_apply.py    # fast; no Slack/Gmail/Claude.

Slack-only runs must advance only slack_cursor and must never admit an email loop; full runs
advance both cursors; links merge without duplicates; needs_me clears a snooze.
"""
import sys, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from openloops import refresh  # noqa: E402

t0 = time.time()


def say(msg):
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    say(f"ok   {what}")


def base():
    return {"cursor": "2026-09-01T09:00+01:00", "slack_cursor": "2026-09-10T12:00+01:00", "loops": [
        {"id": "sam-deck", "owner": "Sam", "ask": "send the deck", "channel": "slack", "status": "waiting",
         "snooze_until": "2099-01-01", "links": [{"url": "https://docs.google.com/d/1", "label": "deck"}]},
        {"id": "ana-invoice", "owner": "Ana", "ask": "invoice", "channel": "email", "status": "waiting"},
    ]}


out = {"new_loops": [
            {"id": "bo-brief", "owner": "Bo", "ask": "brief", "channel": "slack", "thread": "DM Bo D1",
             "links": [{"url": "https://miro.com/app/board/x", "label": "board"}, {"url": "notaurl"}]},
            {"id": "cy-quote", "owner": "Cy", "ask": "quote", "channel": "email", "thread": "Quote"}],
       "updates": [
            {"id": "sam-deck", "status": "needs_me", "last_reply_at": "2026-09-15T10:00", "reply_snippet": "here",
             "links": [{"url": "https://docs.google.com/d/1", "label": "dup"}, {"url": "https://docs.google.com/d/2", "label": "v2"}]},
            {"id": "ghost", "status": "done"}],
       "gmail_available": True}

# --- slack-only
s = base()
n_new, n_upd = refresh.apply(s, out, slack_only=True, now="2026-09-15T14:00+01:00")
ids = [l["id"] for l in s["loops"]]
check("bo-brief" in ids and "cy-quote" not in ids, "slack-only admits the Slack loop and drops the email one")
check((n_new, n_upd) == (1, 1), f"slack-only counts new=1 upd=1 (got {n_new},{n_upd})")
check(s["cursor"] == "2026-09-01T09:00+01:00", "slack-only leaves the Gmail cursor alone")
check(s["slack_cursor"] == "2026-09-15T14:00+01:00" and s["last_slack_refresh"] == s["slack_cursor"], "slack-only advances slack_cursor + last_slack_refresh")
check("last_refresh" not in s and "gmail_available" not in s, "slack-only does not touch last_refresh / gmail_available")
sam = next(l for l in s["loops"] if l["id"] == "sam-deck")
check(sam["status"] == "needs_me" and sam["snooze_until"] is None, "needs_me update clears the snooze")
check([x["url"] for x in sam["links"]] == ["https://docs.google.com/d/1", "https://docs.google.com/d/2"], "links merge without duplicating a url")
check(sam["links"][0]["label"] == "deck", "an existing link keeps its label")
bo = next(l for l in s["loops"] if l["id"] == "bo-brief")
check(bo["links"] == [{"url": "https://miro.com/app/board/x", "label": "board"}], "new loop keeps http links only")
check(bo["status"] == "waiting" and bo["chases"] == 0 and bo["snooze_until"] is None, "new loop gets the default fields")
check(bo["priority"] == "normal" and bo["priority_by"] == "ai" and bo["theme"] == "", "new loop without a judgement: normal priority, marked AI, no theme")

# --- priority + theme: the agent judges, the person's own setting always stands
s = base()
s["loops"][1].update({"priority": "low", "priority_by": "you", "theme": "old theme"})   # Ana: set by hand
pt = {"new_loops": [{"id": "di-plan", "owner": "Di", "ask": "plan", "channel": "slack", "thread": "DM Di", "priority": "high", "theme": "Q4 budget planning and more words"},
                    {"id": "ed-x", "owner": "Ed", "ask": "x", "channel": "slack", "thread": "DM Ed", "priority": "urgent"}],
      "updates": [{"id": "sam-deck", "status": "waiting", "priority": "high", "theme": "the deck"},
                  {"id": "ana-invoice", "status": "waiting", "priority": "high", "theme": "new theme"}]}
refresh.apply(s, pt, slack_only=True, now="2026-09-15T16:00+01:00")
di = next(l for l in s["loops"] if l["id"] == "di-plan"); ed = next(l for l in s["loops"] if l["id"] == "ed-x")
check(di["priority"] == "high" and di["priority_by"] == "ai" and di["theme"] == "Q4 budget planning and more words"[:40], "new loop keeps the agent's priority + theme (theme capped at 40)")
check(ed["priority"] == "normal", "an unknown priority word falls back to normal")
s2 = base(); refresh.apply(s2, {"new_loops": [{"id": "Fi')<b>;x", "owner": "Fi", "ask": "y", "channel": "slack", "thread": "DM Fi"}]}, slack_only=True, now="2026-09-15T16:00+01:00")
check(s2["loops"][-1]["id"] == "fi-b-x", "an agent-written id is reduced to a slug before it reaches the page")
sam = next(l for l in s["loops"] if l["id"] == "sam-deck"); ana = next(l for l in s["loops"] if l["id"] == "ana-invoice")
check(sam["priority"] == "high" and sam["priority_by"] == "ai" and sam["theme"] == "the deck", "an update sets priority + theme on a loop that had neither")
check(ana["priority"] == "low" and ana["priority_by"] == "you" and ana["theme"] == "old theme", "an update never overrides a priority or theme the person set")

# --- full run
s = base()
refresh.apply(s, out, slack_only=False, now="2026-09-15T15:00+01:00")
ids = [l["id"] for l in s["loops"]]
check("cy-quote" in ids and "bo-brief" in ids, "full run admits both channels")
check(s["cursor"] == s["slack_cursor"] == s["last_refresh"] == "2026-09-15T15:00+01:00", "full run advances both cursors and last_refresh")
check(s["gmail_available"] is True, "full run records gmail_available")

# --- in_scope: slack-only ignores email + typed loops; recent done loops stay in scope
recent = "2026-09-12T00:00"
check(refresh.in_scope({"channel": "slack", "status": "waiting"}, True, recent), "slack waiting loop in scope for slack-only")
check(not refresh.in_scope({"channel": "email", "status": "waiting"}, True, recent), "email loop out of scope for slack-only")
check(not refresh.in_scope({"channel": "note", "status": "needs_me", "manual": True}, False, recent), "typed note never goes to the agent")
check(refresh.in_scope({"channel": "email", "status": "done", "closed_at": "2026-09-14T09:00"}, False, recent), "recently closed loop is re-checked")
check(not refresh.in_scope({"channel": "email", "status": "done", "closed_at": "2026-08-01T09:00"}, False, recent), "old closed loop is not")
say("ALL OK")
