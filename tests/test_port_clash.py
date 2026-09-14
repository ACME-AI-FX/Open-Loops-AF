"""Port-clash regression test.

    python3 tests/test_port_clash.py    # fast; no Slack/Gmail/Claude needed.

Guards the bug where a stray `python -m http.server 8765` (or any other local server) on Open Loops'
port made the launcher think Open Loops was already running, so double-clicking the icon opened a
"Directory listing for /" page instead of the app.

  1. Something else on the port -> Open Loops must start on the next free port, not exit.
  2. Stray still there and Open Loops on the next port -> relaunching must find the running instance
     (Server: OpenLoops) and exit 0 instead of starting a third server.
Builds a fresh install in a temp folder and cleans up. Exit code 0 = both hold.
"""
import http.server, json, os, shutil, socket, subprocess, sys, tempfile, threading, time, urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PORT = 8787
t0 = time.time()


def say(msg):
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    say(f"ok   {what}")


def listening(port):
    with socket.socket() as sk:
        return sk.connect_ex(("127.0.0.1", port)) == 0


def wait_for(port, up=True, tries=50):
    for _ in range(tries):
        if listening(port) == up:
            return True
        time.sleep(0.1)
    return False


def server_header(port):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=3) as r:
        return r.headers.get("Server", "")


tmp = Path(tempfile.mkdtemp(prefix="openloops-portclash-"))
say(f"fresh install in {tmp}")
shutil.copytree(REPO / "openloops", tmp / "openloops")
shutil.copy(REPO / "config.template.json", tmp / "config.template.json")
(tmp / "config.json").write_text((tmp / "config.template.json").read_text(encoding="utf-8-sig"), encoding="utf-8")
env = dict(os.environ, OPENLOOPS_PORT=str(PORT))

def launch():
    return subprocess.Popen([sys.executable, "-m", "openloops.app", "--no-browser"], cwd=tmp, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

# 1. A foreign server (plain directory listing) squats on the port.
stray = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), http.server.SimpleHTTPRequestHandler)
threading.Thread(target=stray.serve_forever, daemon=True).start()
check(wait_for(PORT) and not server_header(PORT).startswith("OpenLoops"), "stray http.server is on the port")

app = None
app2 = None
try:
    app = launch()
    check(wait_for(PORT + 1), "Open Loops moved to the next free port instead of quitting")
    check(server_header(PORT + 1).startswith("OpenLoops"), "Server: OpenLoops header identifies the app")
    check(app.poll() is None, "Open Loops is still serving (did not mistake the stray for itself)")

    # 2. Stray still on the preferred port, Open Loops on the next one: relaunching with the same
    #    preferred port must find the running instance and exit 0, not start a third server.
    app2 = launch()
    try:
        out, _ = app2.communicate(timeout=15)
    except subprocess.TimeoutExpired:
        app2.kill()
        raise SystemExit("FAIL: second launch did not exit when Open Loops was already running")
    check(app2.returncode == 0, "second launch exits 0 when Open Loops already owns the port")
    check(not listening(PORT + 2), "second launch did not start a duplicate server on another port")
    check("localhost" in out, "second launch printed the page address")
    stray.shutdown(); stray.server_close()
    say("PASS")
finally:
    for p in (app, app2):
        if p and p.poll() is None:
            p.kill()
            p.wait()
    try:
        stray.shutdown(); stray.server_close()
    except Exception:
        pass
    shutil.rmtree(tmp, ignore_errors=True)
