"""Open Loops - tiny local web app. stdlib only.

    python3 -m openloops.app            -> http://localhost:8765
                                           (or the next free port if 8765 is taken; OPENLOOPS_PORT overrides)
"""
import json, re, shlex, socket, subprocess, sys, threading, time, webbrowser
from datetime import date, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .paths import PKG, ROOT
from .store import load_cfg, norm_date, read_json, write_json
STATE = ROOT / "state.json"
INDEX = PKG / "index.html"
CONFIG = ROOT / "config.json"
VOICEF = ROOT / "voice.json"
EDITABLE = ("agent", "use_slack", "history_days", "owner_name", "chase_external_email", "send_internal", "send_external", "internal_domains", "auto_chase", "tone", "people", "exclude_people", "exclude_topics", "voice_sample_people", "escalation", "vault_path", "slack_source", "miro_source", "roadmap_board", "roadmap_frame")
import os
PORT = int(os.environ.get("OPENLOOPS_PORT", "8765"))
WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"

IDLE_EXIT_S = 3 * 3600  # backstop: server quits after 3h with no page activity
last_seen = time.time()
# Pages that are open right now: page id -> last request time. Each page invents an id, sends it on
# every request, and says goodbye (sendBeacon) when it closes. Once no page is left, the server quits
# after a short grace (a reload is a goodbye followed by a hello within a second). Pages that vanish
# without a goodbye (browser crash, laptop closed) are forgotten after PAGE_STALE_S.
pages = {}
bye_at = 0.0
quit_requested = False
PAGE_GRACE_S = 4
PAGE_STALE_S = 15 * 60
PEOPLEF = ROOT / "people_suggested.json"

def cfg():
    return load_cfg()


def history_days():
    """How far back the AI reads (Settings > History). Drives the first-scan cursor and who's-who."""
    try:
        return min(int(cfg().get("history_days") or 30), 365)
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
JOB_MOD = {"refresh": "refresh", "chase": "chase", "voice": "voice", "people": "people", "standing": "close_standing",
           "daylog": "daylog", "roadmap": "roadmap"}
jobs = {k: {"running": False, "log": ""} for k in JOB_MOD}


def load():
    return read_json(STATE, {"cursor": None, "last_refresh": None, "loops": []})


def save(s):
    write_json(STATE, s)


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
        pid = self.headers.get("X-OL-Page")
        if pid:
            pages[pid] = last_seen
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
            self._json({"state": s, "jobs": jobs, "today": date.today().isoformat(),
                        "pages": len(pages), "quitting": quit_requested})  # who is holding the server up
        elif self.path == "/api/config":
            self._json({"config": cfg(), "voice": read_json(VOICEF), "people_suggested": read_json(PEOPLEF)})
        elif self.path.split("?")[0] == "/api/daylog":
            from . import daylog
            q = self._query()
            self._json(daylog.status(q.get("date") or None))
        elif self.path.split("?")[0] == "/api/daylog/page":
            # served through the app: a file:// link from an http:// page is blocked by browsers
            from . import daylog
            q = self._query()
            day = q.get("date") or date.today().isoformat()
            pg = daylog.page_path(day)
            if not pg.exists():
                return self._json({"error": f"no day log for {day} yet - press Write it up"}, 404)
            b = pg.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        elif self.path == "/api/roadmap":
            from . import roadmap
            st, conf = roadmap.load(), roadmap.configured()
            # the board may be known by link from Settings before it has ever been read
            embed = roadmap.embed_url(st["board"].get("url") or conf["board"], st["board"].get("frame_id"))
            self._json({"store": st, "configured": conf, "embed": embed,
                        "miro": bool((doctor_cache.get("result") or {}).get("miro"))})
        else:
            self._json({"error": "not found"}, 404)

    def _query(self):
        from urllib.parse import parse_qs, urlsplit
        return {k: v[0] for k, v in parse_qs(urlsplit(self.path).query).items()}

    def do_POST(self):
        global doctor_cache
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/bye":  # a page closed (or reloaded: its successor says hello within a second)
            global bye_at
            pages.pop(str(body.get("page") or ""), None)
            bye_at = time.time()
            return self._json({"ok": True, "pages": len(pages)})
        if self.path == "/api/quit":  # Settings button or `python -m openloops.app --stop`
            global quit_requested
            quit_requested = True
            busy = [k for k, j in jobs.items() if j["running"]]
            return self._json({"ok": True, "after_jobs": busy})
        if self.path == "/api/refresh":
            return self._json({"started": run_job("refresh", ["--slack-only"] if body.get("slack_only") else None)})
        if self.path == "/api/daylog":
            return self._json({"started": run_job("daylog", ["--digest-only"] if body.get("digest_only") else None)})
        if self.path == "/api/roadmap":
            from . import roadmap
            mode = body.get("mode")
            if mode == "save":
                # staging rows live in state/roadmap.json, never in state.json (refresh rewrites that)
                roadmap.stage(rows=body.get("rows"), pasted=body.get("pasted"))
                return self._json({"ok": True})
            if mode not in roadmap.MODES:
                return self._json({"ok": False, "error": "unknown mode"}, 400)
            if not roadmap.configured()["ok"]:
                return self._json({"ok": False, "error": "set the board and frame in Settings first"}, 400)
            if mode == "parse" and body.get("pasted") is not None:
                roadmap.stage(pasted=body.get("pasted"))
            if mode == "build" and not body.get("confirm"):
                # adds cards to a board other people share - the page arms this for a few seconds after a preview
                return self._json({"ok": False, "error": "confirm required"}, 400)
            return self._json({"started": run_job("roadmap", [mode] + (["--confirm"] if mode == "build" else []))})
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
                c = cfg()
                c["refresh_time"] = t
                write_json(CONFIG, c)
            return self._json({"ok": r.returncode == 0, "out": (r.stdout + r.stderr)[-500:]})
        if self.path == "/api/voice":
            return self._json({"started": run_job("voice")})
        if self.path == "/api/people":
            return self._json({"started": run_job("people")})
        if self.path == "/api/config":
            c = cfg()
            for k, v in body.items():
                if k in EDITABLE:
                    c[k] = v
            write_json(CONFIG, c)
            return self._json({"ok": True})
        if self.path == "/api/reset":
            # "Start over": back to the state a brand-new user sees, keeping only name/domains/tone settings.
            for f in (STATE, VOICEF, PEOPLEF):
                if f.exists():
                    f.unlink()
            c = cfg()
            for k in ("people", "voice_sample_people", "slack_self_id"):
                c[k] = {} if k == "people" else ([] if k == "voice_sample_people" else "")
            write_json(CONFIG, c)
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
                email = None
                for name, p in (cfg().get("people") or {}).items():
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
                    "notes": notes, "links": [], "last_reply_at": None, "reply_snippet": None,
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
                        try:
                            lp["snooze_until"] = norm_date(body.get("until"))
                        except ValueError as e:
                            return self._json({"error": str(e)}, 400)
                    elif act == "unsnooze":
                        lp["snooze_until"] = None
                    elif act == "auto_off":
                        lp["auto_off"] = True
                    elif act == "auto_on":
                        lp["auto_off"] = False
                    elif act == "note":
                        lp["notes"] = (body.get("notes") or "").strip()[:2000]
                    elif act == "add_link":
                        url = (body.get("url") or "").strip()
                        if not url.startswith("http"):
                            return self._json({"error": "link must start with http"}, 400)
                        links = lp.setdefault("links", [])
                        if not any(x.get("url") == url for x in links):
                            links.append({"url": url, "label": (body.get("label") or "").strip()[:60]})
                    elif act == "drop_link":
                        lp["links"] = [x for x in lp.get("links") or [] if x.get("url") != body.get("url")]
            save(s)
            return self._json({"ok": True})
        self._json({"error": "not found"}, 404)


def port_busy(port=None):
    with socket.socket() as sk:
        sk.settimeout(0.3)  # loopback answers instantly when something listens; Windows takes ~2 s to give up otherwise
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


def stop_running():
    """`python -m openloops.app --stop`: ask the running instance (if any) to quit. Exit 0 if one was told."""
    import urllib.request
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(20) as ex:  # probe the whole range at once: closed ports take the full timeout each
        busy = [p for p, b in zip(range(PORT, PORT + 20), ex.map(port_busy, range(PORT, PORT + 20))) if b]
    for p in busy:
        if already_running(p):
            req = urllib.request.Request(f"http://127.0.0.1:{p}/api/quit", data=b"{}",
                                         headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                out = json.loads(r.read() or b"{}")
            after = out.get("after_jobs") or []
            print(f"Open Loops on port {p}: stopping" + (f" once {', '.join(after)} finishes" if after else ""))
            return 0
    print("Open Loops is not running")
    return 1


if __name__ == "__main__":
    if "--stop" in sys.argv:
        sys.exit(stop_running())
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
            time.sleep(1)
            now = time.time()
            for pid, seen in list(pages.items()):
                if now - seen > PAGE_STALE_S:
                    pages.pop(pid, None)
            if any(j["running"] for j in jobs.values()):
                continue  # never pull the rug from under a refresh/chase; check again once it is done
            no_pages = bye_at and not pages and now - bye_at > PAGE_GRACE_S and now - last_seen > PAGE_GRACE_S
            if quit_requested or no_pages or now - last_seen > IDLE_EXIT_S:
                srv.shutdown()
                return

    threading.Thread(target=reaper, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
