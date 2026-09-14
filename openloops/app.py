"""Open Loops - tiny local web app. stdlib only.

    python3 -m openloops.app            -> http://localhost:8765
                                           (or the next free port if 8765 is taken; OPENLOOPS_PORT overrides)
"""
import json, re, shlex, socket, subprocess, sys, threading, time, webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .paths import PKG, ROOT
STATE = ROOT / "state.json"
INDEX = PKG / "index.html"
CONFIG = ROOT / "config.json"
VOICEF = ROOT / "voice.json"
EDITABLE = ("agent", "use_slack", "history_days", "owner_name", "chase_external_email", "send_internal", "send_external", "internal_domains", "auto_chase", "tone", "people", "exclude_people", "exclude_topics", "voice_sample_people", "escalation", "vault_path")
import os
PORT = int(os.environ.get("OPENLOOPS_PORT", "8765"))
WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"

IDLE_EXIT_S = 3 * 3600  # server quits after 3h with no page activity
last_seen = time.time()
PEOPLEF = ROOT / "people_suggested.json"

def history_days():
    """How far back the AI reads (Settings > History). Drives the first-scan cursor and who's-who."""
    try:
        return min(int(json.loads(CONFIG.read_text(encoding="utf-8-sig")).get("history_days") or 30), 365)
    except Exception:
        return 30


def fresh_state():
    from datetime import timedelta
    return json.dumps({"cursor": (datetime.now().astimezone() - timedelta(days=history_days())).isoformat(timespec="minutes"),
                       "last_refresh": None, "loops": []}, indent=2)


# First run on a new machine: make sure config.json and state.json exist so nothing 500s.
if not CONFIG.exists():
    tpl = ROOT / "config.template.json"
    CONFIG.write_text(tpl.read_text(encoding="utf-8-sig") if tpl.exists() else "{}", encoding="utf-8")
if not STATE.exists():
    STATE.write_text(fresh_state(), encoding="utf-8")
(ROOT / "state" / "logs").mkdir(parents=True, exist_ok=True)

doctor_cache = {"at": 0, "result": None}
jobs = {"refresh": {"running": False, "log": ""}, "chase": {"running": False, "log": ""}, "voice": {"running": False, "log": ""}, "people": {"running": False, "log": ""}, "standing": {"running": False, "log": ""}}


def load():
    return json.loads(STATE.read_text(encoding="utf-8-sig"))


def save(s):
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")


JOB_MOD = {"refresh": "refresh", "chase": "chase", "voice": "voice", "people": "people", "standing": "close_standing"}

def run_job(name, extra=None):
    if jobs[name]["running"]:
        return False
    jobs[name] = {"running": True, "log": ""}
    args = [sys.executable, "-m", f"openloops.{JOB_MOD[name]}", *(extra or [])]

    def go():
        p = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        jobs[name] = {"running": False, "log": (p.stdout + p.stderr)[-4000:], "rc": p.returncode}

    threading.Thread(target=go, daemon=True).start()
    return True


class H(BaseHTTPRequestHandler):
    server_version = "OpenLoops/1"  # sent as the Server: header - how the launcher recognises itself

    def log_message(self, *a):  # quiet
        pass

    def _json(self, obj, code=200):
        global last_seen
        last_seen = time.time()
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.split("?")[0] in ("/", "/index.html"):
            b = INDEX.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path == "/api/state":
            from . import standing
            s = load()
            s = dict(s)
            vault_loops, dirty = standing.as_loops(s)
            if dirty:
                save(s)
            s["loops"] = list(s.get("loops") or []) + vault_loops
            self._json({"state": s, "jobs": jobs, "today": date.today().isoformat()})
        elif self.path == "/api/config":
            voice = json.loads(VOICEF.read_text(encoding="utf-8-sig")) if VOICEF.exists() else None
            people = json.loads(PEOPLEF.read_text(encoding="utf-8-sig")) if PEOPLEF.exists() else None
            self._json({"config": json.loads(CONFIG.read_text(encoding="utf-8-sig")), "voice": voice, "people_suggested": people})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        global doctor_cache
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/refresh":
            return self._json({"started": run_job("refresh")})
        if self.path == "/api/doctor":
            import time as _t
            if body.get("force") or _t.time() - doctor_cache["at"] > 55:
                args = [sys.executable, "-m", "openloops.doctor"] + (["--detect"] if body.get("detect") else [])
                r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
                try:
                    doctor_cache = {"at": _t.time(), "result": json.loads(r.stdout.strip().splitlines()[-1])}
                except Exception:
                    doctor_cache = {"at": _t.time(), "result": {"all_ok": False, "steps": [{"id": "err", "ok": False, "title": "Check failed", "fix": (r.stdout + r.stderr)[-300:]}]}}
            return self._json(doctor_cache["result"])
        if self.path == "/api/open-claude":
            # opens a terminal running the configured agent so the user can sign in / connect
            from . import agent
            cli, title = agent.cli(), agent.display_name()
            if WIN:
                subprocess.Popen(f'start "{title}" cmd /k "{cli}"', shell=True, cwd=ROOT)
            elif MAC:
                script = f'cd {shlex.quote(str(ROOT))} && {shlex.quote(cli)}'
                subprocess.Popen(["osascript", "-e", f'tell application "Terminal" to do script "{script}"',
                                  "-e", 'tell application "Terminal" to activate'])
            else:  # Linux desktop - best effort, terminal emulator varies
                subprocess.Popen(["x-terminal-emulator", "-e", cli], cwd=ROOT)
            return self._json({"ok": True})
        if self.path == "/api/schedule":
            t = str(body.get("time", "")).strip()
            if not (len(t) == 5 and t[2] == ":" and t[:2].isdigit() and t[3:].isdigit()):
                return self._json({"ok": False, "error": "time must be HH:MM"}, 400)
            if WIN:
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                    str(ROOT / "scripts" / "register-task.ps1"), "-At", t],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
            else:
                r = subprocess.run(["bash", str(ROOT / "scripts" / "register-task.sh"), "--at", t],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0:
                cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
                cfg["refresh_time"] = t
                CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return self._json({"ok": r.returncode == 0, "out": (r.stdout + r.stderr)[-500:]})
        if self.path == "/api/voice":
            return self._json({"started": run_job("voice")})
        if self.path == "/api/people":
            return self._json({"started": run_job("people")})
        if self.path == "/api/config":
            cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            for k, v in body.items():
                if k in EDITABLE:
                    cfg[k] = v
            CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            return self._json({"ok": True})
        if self.path == "/api/reset":
            # "Start over": back to the state a brand-new user sees, keeping only name/domains/tone settings.
            for f in (STATE, VOICEF, PEOPLEF):
                if f.exists():
                    f.unlink()
            cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
            for k in ("people", "voice_sample_people", "slack_self_id"):
                cfg[k] = {} if k == "people" else ([] if k == "voice_sample_people" else "")
            CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
            STATE.write_text(fresh_state(), encoding="utf-8")
            doctor_cache = {"at": 0, "result": None}
            return self._json({"ok": True})
        if self.path == "/api/chase":
            return self._json({"started": run_job("chase", [body["id"]])})
        if self.path == "/api/action":
            s = load()
            act = body.get("action")
            vid = str(body.get("id") or "")
            if vid.startswith("vault-"):
                from . import standing
                item_id = vid.split("-", 1)[1].upper()
                if act != "done":
                    return self._json({"error": "vault items are closed with done only"}, 400)
                closure = (body.get("closure") or "").strip()
                try:
                    closed = standing.close_item(item_id, closure)
                except ValueError as e:
                    return self._json({"error": str(e)}, 400)
                (ROOT / "state").mkdir(parents=True, exist_ok=True)
                (ROOT / "state" / "standing-close.json").write_text(
                    json.dumps({"id": item_id, "closure": closure,
                                "project": closed["project"], "action": closed["action"]},
                               ensure_ascii=False), encoding="utf-8")
                started = run_job("standing")
                return self._json({"ok": True, "id": vid, "started": started})
            if act == "add":
                owner = (body.get("owner") or "").strip()[:80]
                ask = (body.get("ask") or "").strip()[:300]
                notes = (body.get("notes") or "").strip()[:2000]
                if not ask:
                    return self._json({"error": "need something to do"}, 400)
                cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
                email = None
                for name, p in (cfg.get("people") or {}).items():
                    if name.lower() == owner.lower():
                        owner = name
                        email = (p or {}).get("email")
                        break
                slug = lambda t: re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")[:32] or "x"
                now = datetime.now().astimezone()
                lid = f"note-{slug(owner or 'me')}-{slug(ask)}-{now.strftime('%Y%m%d%H%M%S')}"
                s["loops"].insert(0, {
                    "id": lid, "owner": owner, "owner_email": email, "ask": ask,
                    "channel": "note", "thread": None, "link": None,
                    "asked_at": now.isoformat(timespec="minutes"),
                    "status": "needs_me", "inbound": True, "manual": True,
                    "notes": notes, "last_reply_at": None, "reply_snippet": None,
                    "chases": 0, "snooze_until": None,
                })
                save(s)
                return self._json({"ok": True, "id": lid})
            for lp in s["loops"]:
                if lp["id"] == body["id"]:
                    if act == "done":
                        lp["status"] = "done"
                        lp["closed_at"] = datetime.now().isoformat(timespec="minutes")
                    elif act == "reopen":
                        # typed reminders belong in Needs me, not Waiting on them
                        lp["status"] = "needs_me" if lp.get("channel") == "note" or lp.get("manual") else "waiting"
                        lp["snooze_until"] = None
                    elif act == "snooze":
                        lp["snooze_until"] = body["until"]
                    elif act == "unsnooze":
                        lp["snooze_until"] = None
                    elif act == "auto_off":
                        lp["auto_off"] = True
                    elif act == "auto_on":
                        lp["auto_off"] = False
                    elif act == "note":
                        lp["notes"] = (body.get("notes") or "").strip()[:2000]
            save(s)
            return self._json({"ok": True})
        self._json({"error": "not found"}, 404)


def port_busy(port=None):
    with socket.socket() as sk:
        return sk.connect_ex(("127.0.0.1", port or PORT)) == 0


def already_running(port=None):
    """True only if the thing listening on the port is Open Loops, not some other local server
    (e.g. a stray `python -m http.server 8765`, which would otherwise show a directory listing)."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port or PORT}/", timeout=2) as r:
            return r.headers.get("Server", "").startswith("OpenLoops")
    except Exception:
        return False


def pick_port(start=None):
    """Scan from the preferred port. Returns (port, running):
    running=True  -> Open Loops already answers there (launched earlier), just open the page;
    running=False -> the port is free, start there.
    Ports held by other programs are skipped, so the app is never confused with a stray server."""
    start = start or PORT
    for p in range(start, start + 20):
        if not port_busy(p):
            return p, False
        if already_running(p):
            return p, True
    raise SystemExit(f"Open Loops: no free port between {start} and {start + 19}; set OPENLOOPS_PORT")


if __name__ == "__main__":
    PORT, running = pick_port()
    url = f"http://localhost:{PORT}"
    def open_browser():
        # os.startfile uses the Windows default-browser association, which works whether or not
        # a browser is already running; webbrowser.open is the cross-platform fallback.
        try:
            import os
            os.startfile(url)
        except Exception:
            webbrowser.open(url)

    if running:  # launched earlier today - just open the page
        print("Open Loops (already running) ->", url)
        if "--no-browser" not in sys.argv:
            open_browser()
        sys.exit(0)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), H)
    print("Open Loops ->", url)
    if str(PORT) != os.environ.get("OPENLOOPS_PORT", "8765"):
        print(f"(preferred port was taken by another program; set OPENLOOPS_PORT to choose)")
    if "--no-browser" not in sys.argv:
        threading.Timer(1.0, open_browser).start()

    def reaper():
        while True:
            time.sleep(60)
            if time.time() - last_seen > IDLE_EXIT_S and not any(j["running"] for j in jobs.values()):
                srv.shutdown()
                return

    threading.Thread(target=reaper, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
