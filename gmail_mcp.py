"""Open Loops' own Gmail MCP server - stdio, stdlib only.

Lets any agent (Grok, Gemini, ...) read sent mail and create reply drafts through the
plain Gmail REST API, using the token from gmail_auth.py. Exists because Google's hosted
Gmail MCP endpoint currently requires Workspace Developer Preview enrolment, and Claude's
Gmail connector is Claude-only. Tool names match those connectors, so the job prompts
work unchanged: search_threads, get_thread, create_draft.

Run by the agent CLI (see .grok/config.toml), not by hand. Speaks newline-delimited
JSON-RPC on stdin/stdout; never print to stdout here except protocol replies.
"""
import base64, json, sys, urllib.error, urllib.parse, urllib.request
from email.message import EmailMessage

import gmail_auth

API = "https://gmail.googleapis.com/gmail/v1/users/me"
BODY_CAP = 4000  # chars of message body returned per message

TOOLS = [
    {"name": "search_threads",
     "description": "Search Gmail threads with normal Gmail query syntax (e.g. \"in:sent after:2026/01/01\", \"subject:invoice\"). Returns thread ids and snippets only — call get_thread for from/to/subject/body.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string", "description": "Gmail search query"},
         "max_results": {"type": "integer", "description": "max threads (default 25)"}},
         "required": ["query"]}},
    {"name": "get_thread",
     "description": "Read one Gmail thread: every message's from/to/date/subject and plain-text body.",
     "inputSchema": {"type": "object", "properties": {
         "thread_id": {"type": "string", "description": "thread id from search_threads"}},
         "required": ["thread_id"]}},
    {"name": "create_draft",
     "description": "Create a Gmail draft (never sends). Pass reply_to_message_id to draft a reply in that message's thread - recipients and subject then default to replying to its sender.",
     "inputSchema": {"type": "object", "properties": {
         "to": {"type": "array", "items": {"type": "string"}, "description": "recipient emails (optional when replying)"},
         "cc": {"type": "array", "items": {"type": "string"}},
         "subject": {"type": "string"},
         "body": {"type": "string", "description": "plain-text body"},
         "reply_to_message_id": {"type": "string", "description": "message id to reply to"}},
         "required": ["body"]}},
]


def api(path, payload=None):
    tok = gmail_auth.token()
    if not tok:
        raise RuntimeError("Gmail not connected - run: python3 gmail_auth.py connect")
    req = urllib.request.Request(f"{API}/{path}", json.dumps(payload).encode() if payload else None,
                                 {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Gmail API {e.code}: {e.read().decode(errors='replace')[:300]}")


def headers_of(msg):
    return {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}


def body_of(payload):
    """Best plain-text part of a message payload, decoded and capped."""
    if payload.get("mimeType", "").startswith("text/") and payload.get("body", {}).get("data"):
        text = base64.urlsafe_b64decode(payload["body"]["data"] + "==").decode("utf-8", "replace")
        return text[:BODY_CAP]
    best = ""
    for part in payload.get("parts", []) or []:
        text = body_of(part)
        if text and (not best or part.get("mimeType") == "text/plain"):
            best = text
            if part.get("mimeType") == "text/plain":
                break
    return best


def search_threads(a):
    # One list call only — do not GET each thread here (that was N+1 HTTP).
    q = urllib.parse.urlencode({"q": a["query"], "maxResults": min(int(a.get("max_results") or 25), 50)})
    out = [{"thread_id": t["id"], "snippet": t.get("snippet", "")}
           for t in api(f"threads?{q}").get("threads", [])]
    return {"threads": out}


def get_thread(a):
    t = api(f"threads/{a['thread_id']}?format=full")
    msgs = []
    for m in t.get("messages", []):
        h = headers_of(m)
        msgs.append({"message_id": m["id"], "from": h.get("from", ""), "to": h.get("to", ""), "cc": h.get("cc", ""),
                     "date": h.get("date", ""), "subject": h.get("subject", ""), "body": body_of(m.get("payload", {}))})
    return {"thread_id": a["thread_id"], "messages": msgs}


def create_draft(a):
    m = EmailMessage()
    m.set_content(a["body"])
    thread_id = None
    if a.get("reply_to_message_id"):
        orig = api(f"messages/{a['reply_to_message_id']}?format=metadata&metadataHeaders=From&metadataHeaders=To&metadataHeaders=Cc&metadataHeaders=Subject&metadataHeaders=Message-ID&metadataHeaders=References")
        h = headers_of(orig)
        thread_id = orig.get("threadId")
        if h.get("message-id"):
            m["In-Reply-To"] = h["message-id"]
            m["References"] = (h.get("references", "") + " " + h["message-id"]).strip()
        subj = a.get("subject") or h.get("subject", "")
        m["Subject"] = subj if subj.lower().startswith("re:") else f"Re: {subj}"
        m["To"] = ", ".join(a["to"]) if a.get("to") else h.get("from", "")
    else:
        if not a.get("to"):
            raise RuntimeError("create_draft needs 'to' (or a reply_to_message_id)")
        m["To"] = ", ".join(a["to"])
        m["Subject"] = a.get("subject", "")
    if a.get("cc"):
        m["Cc"] = ", ".join(a["cc"])
    raw = base64.urlsafe_b64encode(m.as_bytes()).decode()
    msg = {"raw": raw}
    if thread_id:
        msg["threadId"] = thread_id
    d = api("drafts", {"message": msg})
    return {"draft_id": d.get("id"), "thread_id": d.get("message", {}).get("threadId"), "status": "draft created - not sent"}


CALLS = {"search_threads": search_threads, "get_thread": get_thread, "create_draft": create_draft}


def reply(id_, result=None, error=None):
    out = {"jsonrpc": "2.0", "id": id_}
    out.update({"error": error} if error else {"result": result})
    sys.stdout.write(json.dumps(out) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        method, id_ = req.get("method", ""), req.get("id")
        if id_ is None:  # notification (e.g. notifications/initialized) - no response
            continue
        if method == "initialize":
            reply(id_, {"protocolVersion": req.get("params", {}).get("protocolVersion", "2025-06-18"),
                        "capabilities": {"tools": {}}, "serverInfo": {"name": "openloops-gmail", "version": "1.0"}})
        elif method == "tools/list":
            reply(id_, {"tools": TOOLS})
        elif method == "tools/call":
            name = req.get("params", {}).get("name", "")
            try:
                fn = CALLS[name]
                result = fn(req.get("params", {}).get("arguments", {}) or {})
                reply(id_, {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}], "isError": False})
            except Exception as e:  # tool errors go back as content, per MCP
                reply(id_, {"content": [{"type": "text", "text": str(e)}], "isError": True})
        elif method == "ping":
            reply(id_, {})
        else:
            reply(id_, error={"code": -32601, "message": f"method not found: {method}"})


if __name__ == "__main__":
    main()
