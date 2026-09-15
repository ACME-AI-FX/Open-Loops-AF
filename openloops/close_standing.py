"""After a vault standing item is closed in Open Loops, ask the agent whether
the owner's closure note implies edits to any *other* open items. The closed
item itself is already marked done in standing-items.md by standing.close_item.

    python close_standing.py
Reads state/standing-close.json written by app.py.
"""
import json, os, re, sys
from pathlib import Path

from . import agent
from . import standing
from .paths import ROOT
PAYLOAD = ROOT / "state" / "standing-close.json"

PROMPT = """UNATTENDED RUN - nobody can answer questions. Output only the JSON block.

{name} just closed standing item {item_id} ({project}):
{action}

How he closed it:
{closure}

Remaining open standing items:
{open_items}

If that explanation clearly changes another open item, return updates.
Only touch an item {name} named by ID (A7, A8, …) or described so it can only be one of the list.
Prefer "edit" (rewrite the action) over "done" or "drop". Do not invent work. Do not re-close {item_id}.

<<<STANDING>>>
{{"updates": [{{"id": "A8", "verb": "edit|done|drop", "action": "new action text if verb is edit", "note": "one line why"}}]}}
<<<END>>>
If nothing else changes: {{"updates": []}}
"""


def main():
    if not PAYLOAD.exists():
        print("no standing-close.json"); sys.exit(1)
    body = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    item_id = (body.get("id") or "").upper()
    closure = (body.get("closure") or "").strip()
    project = body.get("project") or ""
    action = body.get("action") or ""
    if os.environ.get("OPENLOOPS_SKIP_AGENT"):
        print(f"skip agent: {item_id} already closed")
        return
    remaining = standing.open_items()
    open_txt = "\n".join(f"- {x['id']} | {x['project']} | {x['action']}" for x in remaining) or "(none)"
    from .store import load_cfg
    prompt = PROMPT.format(
        name=load_cfg().get("owner_name") or "The owner",
        item_id=item_id, project=project, action=action,
        closure=closure, open_items=open_txt,
    )
    p = agent.run(prompt, [])
    log = ROOT / "state" / "logs"
    log.mkdir(parents=True, exist_ok=True)
    from datetime import datetime
    (log / f"standing-{item_id}-{datetime.now():%Y-%m-%d_%H%M}.log").write_text(
        p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
    m = re.search(r"<<<STANDING>>>(.*?)<<<END>>>", p.stdout, re.S) or re.search(
        r'(\{\s*"updates"\s*:.*\})', p.stdout, re.S)
    if not m:
        print(f"{item_id} closed; agent returned no updates block (rc {p.returncode})")
        print(p.stdout[-800:])
        return
    out = json.loads(m.group(1))
    updates = [u for u in (out.get("updates") or []) if str(u.get("id") or "").upper() != item_id]
    applied = standing.apply_updates(updates)
    print(f"{item_id} closed; knock-ons: {', '.join(applied) or 'none'}")


if __name__ == "__main__":
    main()
