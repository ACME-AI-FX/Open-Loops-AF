"""Refresh open loops via a headless agent run (agent.py) using the Slack + Gmail tools.

Reads state.json, asks the agent to (a) find new asks the owner made since the cursor,
(b) re-check every open loop for a reply from its owner, and returns JSON which is
merged back into state.json. Never sends anything.
"""
import json, re, sys
from datetime import datetime, timedelta
from pathlib import Path

from . import agent
from .paths import ROOT
STATE = ROOT / "state.json"
LOG = ROOT / "state" / "logs"
LOG.mkdir(parents=True, exist_ok=True)
CFG = json.loads((ROOT / "config.json").read_text(encoding="utf-8-sig"))
SELF_ID = CFG.get("slack_self_id") or ""

# Sources are pluggable: Slack needs the owner's id to find their messages, Gmail doesn't.
# A source that isn't connected simply has no tools in the session; the prompt says "if available".
GMAIL_TOOLS = ["gmail.search_threads", "gmail.get_thread"]
SLACK_TOOLS = ["slack.read_channel", "slack.read_thread", "slack.search_public_and_private", "slack.search_users"]

PROMPT = """UNATTENDED RUN - nobody can answer questions. Do not ask any. Output only what is requested.

You maintain {name}'s "open loops": requests they made to a named person that have not yet
been actioned.{slack_note} Today is {today}.

## Existing open loops (JSON)
{loops}

## Task
1. NEW ASKS. Search {name}'s own outbound messages since {since}:
{sources}
   Keep only messages that ask a specific named person/vendor for an action or answer
   (imperatives, "can you ...", "please ...", "let me know ..."). Drop chatter, FYIs,
   broadcast reminders, anything to these people: {exclude_people}; these topics: {exclude_topics};
   and anything that duplicates an existing loop (same owner + same subject => attach to the
   existing loop instead of creating a new one).
{inbound}
2. REPLIES. For every existing loop with status "waiting" or "needs_me", re-read its thread/DM
   (Slack: read the DM/channel with the id in `thread`; Gmail: search the subject in `thread`).
   Report the newest message from the owner AFTER {name}'s ask, and whether {name} has replied since.
   Loops with status "done" are listed too (closed in the last few days): for those ONLY report an update
   if the owner posted a NEW question or request after `closed_at` -> status "needs_me" (reopen). Otherwise omit.
   Rules: owner replied and {name} has not answered since -> "needs_me".
          owner replied with a clear completion ("done", "sorted", delivered the thing) -> "done".
          {name} replied after them with a new ask -> "waiting" (update asked_at).
          inbound loops (marked "inbound"): once {name} has replied -> "done", unless that reply
          asks them for something new -> "waiting".
          nothing new -> leave unchanged (omit from updates).

## Output
Reply with ONLY a JSON object between the markers, nothing else:
<<<OPENLOOPS>>>
{{
  "new_loops": [{{"id": "<owner-slug>-<topic-slug>", "owner": "...", "owner_email": "... or null",
                  "ask": "one line", "channel": "slack|email", "thread": "DM <name> <channel id> | #channel | email subject",
                  "link": "slack://channel?team=&id=<id> or gmail search url", "asked_at": "ISO datetime",
                  "status": "waiting, or needs_me for inbound", "inbound": false, "notes": ""}}],
  "updates": [{{"id": "<existing id>", "status": "waiting|needs_me|done", "last_reply_at": "ISO or null",
                "reply_snippet": "<=120 chars", "asked_at": "ISO (only if a new ask by {name})"}}],
  "gmail_available": true
}}
<<<END>>>
"""


def main():
    s = json.loads(STATE.read_text(encoding="utf-8-sig"))
    recent = (datetime.now() - timedelta(days=5)).isoformat()
    def from_mail(l):
        # typed reminders (channel "note") stay until the owner marks them done
        return not l.get("manual") and l.get("channel") not in ("note", "vault")

    open_loops = [l for l in s["loops"] if from_mail(l) and (
        l["status"] in ("waiting", "needs_me")
        or (l["status"] == "done" and (l.get("closed_at") or "") >= recent))]
    cursor = datetime.fromisoformat(s["cursor"])
    since_date = (cursor - timedelta(days=1)).date().isoformat()
    sources = []
    slack_on = bool(SELF_ID) and agent.slack_enabled()
    if slack_on:
        sources.append(f'   - Slack (if the Slack tools are available): slack_search_public_and_private query "from:<@{SELF_ID}> after:{since_date}" sort=timestamp, paginate until you pass the cursor.')
    sources.append(f'   - Gmail (if the Gmail tools are available): search_threads query "in:sent after:{since_date.replace("-", "/")}".')
    inbound = ("1b. ASKS OF {n} (inbound). Gmail (if available): search_threads query "
               '"in:inbox after:{g} -category:promotions -category:social". Keep only mail from real people '
               "(not newsletters, marketing, notifications, receipts, no-reply) where the thread's LATEST message "
               "asks {n} for a specific action or answer and {n} has not replied since. These become new loops with "
               '"status": "needs_me" and "inbound": true - owner is the person asking; ask = one line on what they '
               "need from {n}. The same exclusions and duplicate rule apply.").format(
                   n=CFG.get("owner_name") or "the owner", g=since_date.replace("-", "/"))
    prompt = PROMPT.format(
        name=CFG.get("owner_name") or "the owner",
        inbound=inbound,
        slack_note=f" {CFG.get('owner_name') or 'The owner'}'s Slack user id is <@{SELF_ID}>." if slack_on else "",
        sources="\n".join(sources),
        today=datetime.now().strftime("%Y-%m-%d %H:%M"),
        loops=json.dumps([{k: l[k] for k in ("id", "owner", "ask", "channel", "thread", "asked_at", "status", "closed_at") if k in l} for l in open_loops], indent=1, ensure_ascii=False),
        since=s["cursor"],
        exclude_people=", ".join(CFG.get("exclude_people", [])) or "none",
        exclude_topics="; ".join(CFG.get("exclude_topics", [])) or "none",
    )
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    print(f"[{stamp}] refresh: {len(open_loops)} open loops, cursor {s['cursor']}")
    p = agent.run(prompt, (SLACK_TOOLS if slack_on else []) + GMAIL_TOOLS)
    (LOG / f"refresh-{stamp}.log").write_text(p.stdout + "\n--- stderr ---\n" + p.stderr, encoding="utf-8")
    # some agents drop the markers and emit bare JSON - accept that too
    m = re.search(r"<<<OPENLOOPS>>>(.*?)<<<END>>>", p.stdout, re.S) or re.search(r'(\{\s*"new_loops"\s*:.*\})', p.stdout, re.S)
    if not m:
        print("!! no OPENLOOPS block in output (rc %s). See log." % p.returncode)
        print(p.stdout[-1500:])
        sys.exit(1)
    out = json.loads(m.group(1))

    by_id = {l["id"]: l for l in s["loops"]}
    n_new = n_upd = 0
    for nl in out.get("new_loops", []):
        if nl["id"] in by_id:
            continue
        nl.setdefault("status", "waiting")
        nl.update({"last_reply_at": None, "reply_snippet": None, "chases": 0, "snooze_until": None})
        s["loops"].append(nl)
        by_id[nl["id"]] = nl
        n_new += 1
    for u in out.get("updates", []):
        l = by_id.get(u["id"])
        if not l:
            continue
        for k in ("status", "last_reply_at", "reply_snippet", "asked_at"):
            if u.get(k):
                l[k] = u[k]
        if l["status"] == "needs_me":
            l["snooze_until"] = None
            l.pop("closed_at", None)
        n_upd += 1
    s["cursor"] = datetime.now().astimezone().isoformat(timespec="minutes")
    s["last_refresh"] = s["cursor"]
    s["gmail_available"] = bool(out.get("gmail_available"))
    STATE.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"done: {n_new} new, {n_upd} updated, gmail={'yes' if s['gmail_available'] else 'NO'}")


if __name__ == "__main__":
    main()
