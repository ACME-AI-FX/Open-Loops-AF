"""Timer-driven chasing. Run after refresh (the 08:40 task does this).

For every loop that is: waiting, not snoozed, not marked auto-off, and quiet for at least
config.auto_chase.after_workdays since the ask (or since the last chase), run chase.py on it.
Whether that chase is a draft or a real send is decided by the send_internal / send_external
tick boxes exactly as for a manual chase. Off unless config.auto_chase.enabled is true.
"""
import json, subprocess, sys
from datetime import date, datetime
from pathlib import Path

from .paths import ROOT
STATE = ROOT / "state.json"
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))


def workdays_since(iso):
    d, today, n = datetime.fromisoformat(iso).date(), date.today(), 0
    while d < today:
        d = date.fromordinal(d.toordinal() + 1)
        if d.weekday() < 5:
            n += 1
    return n


def main():
    ac = CFG.get("auto_chase", {})
    if not ac.get("enabled"):
        print("auto-chase off"); return
    if date.today().weekday() >= 5:
        print("weekend - skipped"); return
    after = int(ac.get("after_workdays", 3))
    max_n = int(ac.get("max_chases", 3))
    s = json.loads(STATE.read_text(encoding="utf-8-sig"))
    today = date.today().isoformat()
    due = []
    for l in s["loops"]:
        if l["status"] != "waiting" or l.get("auto_off"):
            continue
        if l.get("snooze_until") and l["snooze_until"] > today:
            continue
        if l.get("chases", 0) >= max_n:
            continue
        if l.get("last_chase_at") and l["last_chase_at"][:10] == today:
            continue
        since = l.get("last_chase_at") or l["asked_at"]
        if workdays_since(since) >= after:
            due.append(l["id"])
    print(f"auto-chase: {len(due)} due (after {after} workdays): {', '.join(due) or '-'}")
    for lid in due:
        r = subprocess.run([sys.executable, "-m", "openloops.chase", lid], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace")
        print(f"  {lid}: rc={r.returncode} " + (r.stdout.strip().splitlines() or ["?"])[-1][:120])


if __name__ == "__main__":
    main()
