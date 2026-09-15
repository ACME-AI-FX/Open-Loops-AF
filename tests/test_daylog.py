"""Day log: digest filtering/counting, HTML rendering, status() against a temp state file.

    python3 tests/test_daylog.py    # fast; no Slack/Gmail/agent.
"""
import json, sys, tempfile, time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
t0 = time.time()


def say(msg):
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    say(f"ok   {what}")


from openloops import daylog, store  # noqa: E402

DAY = "2026-09-15"
STATE = {"cursor": "2026-09-15T08:00", "loops": [
    {"id": "a", "owner": "Ana", "ask": "send the <plates>", "channel": "slack", "status": "waiting",
     "asked_at": "2026-09-15T09:10", "snooze_until": None},
    {"id": "b", "owner": "Ben", "ask": "old ask", "channel": "email", "status": "waiting",
     "asked_at": "2026-09-01T09:00", "last_chase_at": "2026-09-15T10:00", "snooze_until": None},
    {"id": "c", "owner": "Cy", "ask": "closed one", "channel": "slack", "status": "done",
     "asked_at": "2026-09-10T09:00", "closed_at": "2026-09-15T11:00"},
    {"id": "d", "owner": "Di", "ask": "snoozed", "channel": "slack", "status": "waiting",
     "asked_at": "2026-09-02T09:00", "snooze_until": "2026-09-20"},
    {"id": "e", "owner": "Ed", "ask": "snooze passed", "channel": "email", "status": "needs_me",
     "asked_at": "2026-09-02T09:00", "snooze_until": "2026-09-14"},
    {"id": "vault-A1", "owner": "", "ask": "vault item", "channel": "vault", "status": "needs_me",
     "asked_at": "2026-09-15T00:00"},
    {"id": "f", "owner": "Fay", "ask": "yesterday", "channel": "slack", "status": "needs_me",
     "asked_at": "2026-09-14T09:00", "snooze_until": None},
]}

d = daylog.digest(STATE, DAY)
check([x["id"] for x in d["opened"]] == ["a"], "opened = loops asked today, vault excluded")
check([x["id"] for x in d["closed"]] == ["c"], "closed = loops closed today")
check([x["id"] for x in d["chased"]] == ["b"], "chased = loops chased today")
check(d["waiting"] == 2, f"waiting counts a + b, not snoozed d (got {d['waiting']})")
check(d["needs_me"] == 2, f"needs_me counts e (snooze passed) + f, not vault (got {d['needs_me']})")
check(d["opened"][0] == {"id": "a", "owner": "Ana", "ask": "send the <plates>", "channel": "slack", "status": "waiting"}, "item shape")
check(daylog.digest({}, DAY) == {"opened": [], "closed": [], "chased": [], "waiting": 0, "needs_me": 0}, "empty state digests cleanly")

entry = {"date": DAY, "digest": d, "highlights": ["Got <the> plates moving"],
         "text": "Done\n- shipped the thing\n\nMoved\n- nothing\n\nWaiting on\n- Ana for plates",
         "written_at": "2026-09-15T17:00"}
h = daylog.render_html(entry)
check("<script" not in h.lower(), "no scripts in the page")
check(DAY in h, "page shows the date")
check("send the &lt;plates&gt;" in h, "ask text is escaped")
check("Got &lt;the&gt; plates moving" in h, "highlight text is escaped")
check("<li>shipped the thing</li>" in h and "<h2>Done</h2>" in h, "prose becomes headings + bullets")
check("prefers-color-scheme:dark" in h, "dark mode palette present")
h2 = daylog.render_html({"date": DAY, "digest": d, "text": None})
check("Write it up" in h2, "digest-only page explains how to get prose")

# status() against a temp install: point the module's file locations at a scratch folder
tmp = Path(tempfile.mkdtemp(prefix="openloops-daylog-"))
store.STATE = tmp / "state.json"
daylog.DIR = tmp / "state" / "daylog"
store.STATE.write_text(json.dumps(STATE), encoding="utf-8")
st = daylog.status(DAY)
check(st["date"] == DAY and st["text"] is None and st["highlights"] == [] and st["has_page"] is False, "status without a saved entry")
check(st["digest"]["waiting"] == 2, "status digest comes from the state file")
daylog.DIR.mkdir(parents=True)
store.write_json(daylog.entry_path(DAY), entry)
daylog.page_path(DAY).write_text(h, encoding="utf-8")
st = daylog.status(DAY)
check(st["text"].startswith("Done") and st["highlights"] == entry["highlights"] and st["written_at"] == "2026-09-15T17:00" and st["has_page"], "status with a saved entry + page")
say("all good")
