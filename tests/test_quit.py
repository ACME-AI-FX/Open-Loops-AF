"""Stopping the app: closing the tab, the Quit button, and `--stop`.

    python3 tests/test_quit.py    # ~30 s; no Slack/Gmail/Claude. Temp install, spare port.

  1. A page says hello (X-OL-Page header) then goodbye (/api/bye) -> the server exits within a few seconds.
  2. Goodbye followed by a new page's hello (a reload) -> the server stays up.
  3. POST /api/quit (the Settings button) -> exits.
  4. `python -m openloops.app --stop` -> exits; run again -> "not running", exit 1.
Nothing here ever needs a running job, so the "wait for jobs first" branch is not exercised.
"""
import json, os, shutil, socket, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = 8799
t0 = time.time()


def say(msg):
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    say(f"ok   {what}")


def api(path, body=None, page=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"}
    if page:
        h["X-OL-Page"] = page
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}{path}", data=data, headers=h,
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def up():
    return socket.socket().connect_ex(("127.0.0.1", PORT)) == 0


tmp = Path(tempfile.mkdtemp(prefix="openloops-quit-"))
say(f"fresh install in {tmp}")
shutil.copytree(REPO / "openloops", tmp / "openloops")
shutil.copy(REPO / "config.template.json", tmp / "config.template.json")
(tmp / "config.json").write_text((tmp / "config.template.json").read_text(encoding="utf-8-sig"), encoding="utf-8")
env = dict(os.environ, OPENLOOPS_PORT=str(PORT))
procs = []


def start():
    p = subprocess.Popen([sys.executable, "-m", "openloops.app", "--no-browser"], cwd=tmp, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    for _ in range(50):
        if up():
            return p
        time.sleep(0.1)
    raise SystemExit("FAIL: openloops.app did not come up")


def gone(p, secs):
    """True if the process exits within secs and the port is free."""
    try:
        p.wait(secs)
    except subprocess.TimeoutExpired:
        return False
    return not up()


try:
    # 1. hello + goodbye -> exit
    p = start()
    api("/api/state", page="tab1")
    time.sleep(6)
    check(up() and p.poll() is None, "a page that is open keeps the server up (6 s)")
    out = api("/api/bye", {"page": "tab1"})
    check(out["pages"] == 0, "goodbye drops the page")
    check(gone(p, 10), "server exits within 10 s of the last page's goodbye")

    # 2. goodbye then a new hello (reload) -> stays up
    p = start()
    api("/api/state", page="tab2")
    api("/api/bye", {"page": "tab2"})
    api("/api/state", page="tab3")  # the reloaded page, well inside the grace
    time.sleep(7)
    check(up() and p.poll() is None, "a reload (goodbye then hello) does not stop the server")
    api("/api/bye", {"page": "tab3"})
    check(gone(p, 10), "...and the reloaded page's goodbye does")

    # 3. /api/quit
    p = start()
    api("/api/state", page="tab4")
    out = api("/api/quit", {})
    check(out["ok"] is True and out["after_jobs"] == [], "quit accepted with no job running")
    check(gone(p, 10), "server exits after /api/quit")

    # 4. --stop from a terminal
    p = start()
    r = subprocess.run([sys.executable, "-m", "openloops.app", "--stop"], cwd=tmp, env=env, capture_output=True, text=True)
    check(r.returncode == 0 and "stopping" in r.stdout, f"--stop finds the running instance (out: {r.stdout.strip()!r})")
    check(gone(p, 10), "server exits after --stop")
    r = subprocess.run([sys.executable, "-m", "openloops.app", "--stop"], cwd=tmp, env=env, capture_output=True, text=True)
    check(r.returncode == 1 and "not running" in r.stdout, "--stop with nothing running says so and exits 1")

    # 5. --port beats the environment (what `npm run dev` / `npm run stop` use)
    p = subprocess.Popen([sys.executable, "-m", "openloops.app", "--no-browser", "--port", str(PORT + 1)], cwd=tmp,
                         env=dict(os.environ, OPENLOOPS_PORT="1"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    for _ in range(50):
        if socket.socket().connect_ex(("127.0.0.1", PORT + 1)) == 0:
            break
        time.sleep(0.1)
    check(socket.socket().connect_ex(("127.0.0.1", PORT + 1)) == 0, "--port N starts on N even with OPENLOOPS_PORT set")
    r = subprocess.run([sys.executable, "-m", "openloops.app", "--stop", f"--port={PORT + 1}"], cwd=tmp, capture_output=True, text=True)
    check(r.returncode == 0 and gone(p, 10), "--stop --port=N stops that instance")

    # page wiring
    html = (tmp / "openloops" / "index.html").read_text(encoding="utf-8")
    for needle in ("'X-OL-Page':PAGE", "sendBeacon('/api/bye'", 'id="quitbtn"', "e.persisted"):
        check(needle in html, f"page has {needle}")
    say("ALL OK")
finally:
    for p in procs:
        if p.poll() is None:
            p.kill()
    shutil.rmtree(tmp, ignore_errors=True)
