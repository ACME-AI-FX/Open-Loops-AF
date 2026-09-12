"""API test for typed Needs-me reminders (contact + note).

    python3 test_manual_notes.py    # fast; no Slack/Gmail. Temp install, spare port.

Covers: add (contact from people list + free text), notes, reopen stays in Needs me,
refresh.py skips these so the agent cannot close them.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

SRC = Path(__file__).resolve().parent
PORT = 8796
FILES = ["app.py", "standing.py", "refresh.py", "chase.py", "voice.py", "people.py", "doctor.py", "autochase.py", "index.html", "config.template.json"]
t0 = time.time()


def say(msg):
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    say(f"ok   {what}")


def api(path, body=None, method=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        f"http://127.0.0.1:{PORT}{path}", data=data,
        headers={"Content-Type": "application/json"},
        method=method or ("POST" if body is not None else "GET"))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


tmp = Path(tempfile.mkdtemp(prefix="openloops-notes-"))
say(f"fresh install in {tmp}")
for f in FILES:
    shutil.copy(SRC / f, tmp / f)
tpl = json.loads((tmp / "config.template.json").read_text(encoding="utf-8-sig"))
tpl["owner_name"] = "Oscar"
tpl["people"] = {"Alice Example": {"level": "peer", "aliases": ["Alice"], "email": "alice@example.com"}}
(tmp / "config.json").write_text(json.dumps(tpl, indent=2), encoding="utf-8")
(tmp / "state.json").write_text(json.dumps({
    "cursor": "2026-01-01T00:00", "last_refresh": "2026-01-02T00:00",
    "loops": [{"id": "alice-report", "owner": "Alice Example", "ask": "the report",
               "channel": "email", "asked_at": "2026-01-01T10:00", "status": "waiting",
               "chases": 0, "snooze_until": None, "notes": ""}],
}), encoding="utf-8")

env = dict(os.environ, OPENLOOPS_PORT=str(PORT))
srv = subprocess.Popen([sys.executable, "app.py", "--no-browser"], cwd=tmp, env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(40):
        if socket.socket().connect_ex(("127.0.0.1", PORT)) == 0:
            break
        time.sleep(0.1)
    else:
        raise SystemExit("FAIL: app.py did not come up")

    code, err = api("/api/action", {"action": "add", "owner": "", "ask": ""})
    check(code == 400 and "something to do" in err.get("error", ""), "add without a task is 400")

    code, out = api("/api/action", {"action": "add", "ask": "file the Companies House identity check"})
    check(code == 200 and out.get("ok"), "add without a contact is allowed")
    solo = next(l for l in api("/api/state")[1]["state"]["loops"] if l["id"] == out["id"])
    check(solo["owner"] == "" and solo["status"] == "needs_me" and solo["channel"] == "note",
          "no-contact reminder still lands in Needs me")

    code, out = api("/api/action", {"action": "add", "owner": "alice example",
                                    "ask": "write the brief", "notes": "due Friday, keep it short"})
    check(code == 200 and out.get("ok") and out.get("id", "").startswith("note-"), "add with known contact")
    loops = api("/api/state")[1]["state"]["loops"]
    note = next(l for l in loops if l["id"] == out["id"])
    check(note["owner"] == "Alice Example" and note["owner_email"] == "alice@example.com",
          "contact matched to people list (name + email)")
    check(note["status"] == "needs_me" and note["channel"] == "note" and note["manual"] is True,
          "lands in Needs me as a typed reminder")
    check(note["notes"] == "due Friday, keep it short", "note stored on add")

    code, _ = api("/api/action", {"id": note["id"], "action": "note", "notes": "moved to Monday"})
    check(code == 200, "edit note")
    note = next(l for l in api("/api/state")[1]["state"]["loops"] if l["id"] == note["id"])
    check(note["notes"] == "moved to Monday", "edited note persisted")

    code, _ = api("/api/action", {"action": "add", "owner": "New Client", "ask": "send the pack"})
    check(code == 200, "add with a contact not in the people list")
    free = next(l for l in api("/api/state")[1]["state"]["loops"] if l["owner"] == "New Client")
    check(free["owner_email"] is None and free["status"] == "needs_me", "unknown contact still tags the card")

    api("/api/action", {"id": note["id"], "action": "done"})
    note = next(l for l in api("/api/state")[1]["state"]["loops"] if l["id"] == note["id"])
    check(note["status"] == "done", "done")
    api("/api/action", {"id": note["id"], "action": "reopen"})
    note = next(l for l in api("/api/state")[1]["state"]["loops"] if l["id"] == note["id"])
    check(note["status"] == "needs_me", "reopen of a typed reminder goes back to Needs me, not Waiting")

    src = (tmp / "refresh.py").read_text(encoding="utf-8")
    check('not in ("note", "vault")' in src and 'l.get("manual")' in src,
          "refresh.py skips typed reminders so the agent cannot close them")
    chase_src = (tmp / "chase.py").read_text(encoding="utf-8")
    check('"note", "vault"' in chase_src, "chase.py refuses to nudge a typed reminder")

    html = (tmp / "index.html").read_text(encoding="utf-8")
    check('id="add_need"' in html and "addNeed()" in html and "editNote(" in html,
          "Home tab has the add form and a per-card note button")
finally:
    srv.terminate()
    srv.wait(timeout=5)
    shutil.rmtree(tmp, ignore_errors=True)

say("all passed")
