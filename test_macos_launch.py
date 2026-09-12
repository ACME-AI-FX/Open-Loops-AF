"""macOS non-interactive-launch regression test.

    python3 test_macos_launch.py    # fast; no Slack/Gmail. Needs Claude Code installed and signed in.

Guards the two bugs that broke Desktop double-click and the launchd weekday refresh:
  1. shell=True with a list of args on POSIX runs only args[0] and silently drops the rest -
     doctor/refresh/chase/voice/people must use shell=WIN.
  2. launchd (and a thin Finder shell) hand children PATH=/usr/bin:/bin:/usr/sbin:/sbin, where
     claude never lives - the three shell entry points must export the fixed PATH before python3.
Builds everything in a temp folder, stubs launchctl so nothing real is registered, and cleans up.
Exit code 0 = both fixes still hold.
"""
import json, os, re, shutil, socket, stat, subprocess, sys, tempfile, time, urllib.request
from pathlib import Path

if sys.platform != "darwin":
    print(f"SKIP: macOS-only test (Finder/launchd launch context) - nothing to do on {sys.platform}")
    sys.exit(0)

SRC = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC))
import doctor

MINIMAL = "/usr/bin:/bin:/usr/sbin:/sbin"  # what launchd gives its children
FIXED = f"{os.environ['HOME']}/.local/bin:/opt/homebrew/bin:/usr/local/bin:{MINIMAL}"
PORT_INSTALL, PORT_LIVE = 8797, 8798
FILES = ["app.py", "standing.py", "close_standing.py", "refresh.py", "chase.py", "voice.py", "people.py", "doctor.py", "autochase.py", "index.html", "config.template.json"]
SHELL_FILES = ["doctor.py", "refresh.py", "chase.py", "voice.py", "people.py"]
LABEL = "com.openloops.refresh"
t0 = time.time()


def say(msg):
    print(f"[{time.time() - t0:5.0f}s] {msg}", flush=True)


def check(cond, what):
    if not cond:
        raise SystemExit(f"FAIL: {what}")
    say(f"ok   {what}")


def api(path, body=None):
    req = urllib.request.Request(f"http://127.0.0.1:{PORT_LIVE}{path}", data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json"}, method="POST" if body is not None else "GET")
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def wait_up(limit=20):
    t = time.time()
    while time.time() - t < limit:
        try:
            return api("/api/state")
        except Exception:
            time.sleep(0.3)
    raise SystemExit("FAIL: app.py did not come up")


def port_free(p):
    with socket.socket() as sk:
        return sk.connect_ex(("127.0.0.1", p)) != 0


def refresh_job_registered():
    r = subprocess.run(["launchctl", "print", f"gui/{os.getuid()}/{LABEL}"], capture_output=True, text=True)
    return r.returncode == 0


def script(path, text):
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


tmp = Path(tempfile.mkdtemp(prefix="openloops-maclaunch-"))
home = tmp / "home"          # throwaway $HOME - the real ~/Desktop, ~/Library and launchd stay untouched
fakebin = tmp / "bin"        # argv-recording claude + launchctl stub for the install run
frag = tmp / "frag.sh"
argv_file = tmp / "argv.txt"
launchctl_log = tmp / "launchctl.log"
for d in (home / ".local" / "bin", home / "Desktop", fakebin):
    d.mkdir(parents=True)
script(fakebin / "claude", f'#!/bin/bash\nprintf \'%s\\n\' "$@" > "{argv_file}"\n')
script(fakebin / "launchctl", f'#!/bin/bash\necho "$*" >> "{launchctl_log}"\n')
script(home / ".local" / "bin" / "claude", "#!/bin/bash\nexit 0\n")
job_was_registered = refresh_job_registered()

srv = hold = None
try:
    check(port_free(PORT_INSTALL) and port_free(PORT_LIVE), f"spare ports {PORT_INSTALL}/{PORT_LIVE} free")

    say("1. shell=WIN regression - list args must all survive on POSIX")
    for name in SHELL_FILES:
        code = "\n".join(ln.split("#")[0] for ln in (SRC / name).read_text().splitlines())
        flags = re.findall(r"shell=(\w+)", code)
        check(flags and all(f == "WIN" for f in flags), f"{name}: every subprocess call uses shell=WIN")
    args = ["-p", "--output-format", "text", "--allowedTools", "mcp__plugin_slack_slack__slack_search_users"]
    rc, _ = doctor.run(["claude", *args], input="ping", env={"PATH": f"{fakebin}:{MINIMAL}", "HOME": str(home)})
    got = argv_file.read_text().splitlines() if argv_file.exists() else []
    check(rc == 0 and got == args, f"doctor.run passed all {len(args)} args through to claude (got {got})")

    say("2. PATH export in the shell entry points - launchd-like minimal environment")
    r = subprocess.run(["/bin/bash", "-c", "command -v claude"], env={"PATH": MINIMAL, "HOME": str(home)}, capture_output=True, text=True)
    check(r.returncode != 0, "sanity: claude is invisible on launchd's minimal PATH (the bug scenario)")

    def path_export_works(path, label):
        lines = path.read_text().splitlines()
        cut = next((i for i, ln in enumerate(lines) if ln.strip().startswith("export PATH=")), None)
        check(cut is not None, f"{label}: PATH export line present")
        # run only up to the export, then probe - proves the line executes, not that it merely exists
        frag.write_text("\n".join(lines[:cut + 1]) + "\ncommand -v claude >/dev/null 2>&1\n")
        r = subprocess.run(["/bin/bash", str(frag)], env={"PATH": MINIMAL, "HOME": str(home)}, capture_output=True, text=True)
        check(r.returncode == 0, f"{label}: export makes claude resolvable under the minimal PATH")

    path_export_works(SRC / "Open Loops.command", "Open Loops.command")
    path_export_works(SRC / "scripts" / "run-refresh.sh", "scripts/run-refresh.sh")

    # throwaway install to get the Desktop launcher install.sh writes; launchctl is stubbed and the
    # held port makes the installer's nohup'd app.py exit by itself (port-busy branch)
    hold = socket.socket()
    hold.bind(("127.0.0.1", PORT_INSTALL))
    hold.listen(1)
    inst_env = dict(os.environ, HOME=str(home), PATH=f"{fakebin}:{os.environ['PATH']}",
                    OPENLOOPS_PORT=str(PORT_INSTALL), BROWSER="/usr/bin/true")
    r = subprocess.run(["bash", str(SRC / "install.sh"), "--name", "Testuser", "--at", "09:15"],
                       env=inst_env, capture_output=True, text=True, timeout=180)
    check(r.returncode == 0, f"install.sh completed in throwaway HOME ({(r.stdout + r.stderr)[-200:].strip() if r.returncode else 'ok'})")
    check((home / "Library" / "LaunchAgents" / f"{LABEL}.plist").exists() and "bootstrap" in launchctl_log.read_text(),
          "register-task.sh went through the launchctl stub (real launchd untouched)")
    launcher = home / "Desktop" / "Open Loops.app" / "Contents" / "MacOS" / "openloops"
    check(launcher.exists(), "Desktop Open Loops.app written")
    check((home / "Applications" / "Open Loops.app" / "Contents" / "Resources" / "AppIcon.icns").exists(),
          "app icon is in the bundle")
    path_export_works(launcher, "Desktop Open Loops.app launcher")
    hold.close()
    hold = None

    say("3. live end-to-end - /api/doctor login row under broken then fixed PATH")
    app = tmp / "app"
    app.mkdir()
    for f in FILES:
        shutil.copy(SRC / f, app / f)
    shutil.copytree(SRC / "scripts", app / "scripts")
    tpl = json.loads((app / "config.template.json").read_text(encoding="utf-8-sig"))
    tpl["owner_name"] = "Testuser"
    (app / "config.json").write_text(json.dumps(tpl, indent=2), encoding="utf-8")
    (app / "state.json").write_text(json.dumps({"cursor": "2026-01-01T00:00", "last_refresh": None, "loops": []}), encoding="utf-8")
    # launchd supplies HOME/USER but only the minimal PATH - that is the exact bug environment
    base = {"HOME": os.environ["HOME"], "USER": os.environ.get("USER", ""), "LOGNAME": os.environ.get("LOGNAME", ""),
            "OPENLOOPS_PORT": str(PORT_LIVE), "BROWSER": "/usr/bin/true"}

    srv = subprocess.Popen([sys.executable, "app.py", "--no-browser"], cwd=app, env=dict(base, PATH=MINIMAL),
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_up()
    steps = {s["id"]: s for s in api("/api/doctor", {"force": True})["steps"]}
    check(not steps["claude"]["ok"], "broken PATH: doctor cannot find claude (bug reproduced)")
    check(not steps["login"]["ok"], "broken PATH: 'Signed in to Claude' row is red (bug reproduced)")
    srv.kill()
    srv.wait()

    env_fixed = dict(base, PATH=FIXED)
    r = subprocess.run(["claude", "auth", "status"], env=env_fixed, capture_output=True, text=True, timeout=60)
    truth = bool(re.search(r'"loggedIn"\s*:\s*true', r.stdout + r.stderr))
    check(truth, "claude auth status reports signed in (this live check needs a signed-in machine)")
    srv = subprocess.Popen([sys.executable, "app.py", "--no-browser"], cwd=app, env=env_fixed,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    wait_up()
    steps = {s["id"]: s for s in api("/api/doctor", {"force": True})["steps"]}
    check(steps["claude"]["ok"], "fixed PATH: doctor finds claude")
    check(steps["login"]["ok"], "fixed PATH: login row ok: true, matching claude auth status")

    check(refresh_job_registered() == job_was_registered, "real launchd registration state unchanged")
    say("PASS - non-interactive macOS launch keeps full claude args and a working PATH")
finally:
    if srv and srv.poll() is None:
        srv.kill()
        srv.wait()
    if hold:
        hold.close()
    for port in (PORT_INSTALL, PORT_LIVE):
        subprocess.run(["/bin/bash", "-c", f"lsof -ti tcp:{port} | xargs kill 2>/dev/null"], capture_output=True)
    shutil.rmtree(tmp, ignore_errors=True)
