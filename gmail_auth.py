"""Connect Open Loops to Gmail directly - needed when the agent is NOT Claude.

Claude has its own Gmail connector (claude.ai Gmail in /mcp). Other agents talk to
Google's hosted Gmail MCP server (gmailmcp.googleapis.com), whose OAuth doesn't allow
agents to self-register - so this script does the sign-in itself and hands the agent a
short-lived access token per run. Stdlib only, like the rest of the app.

One-off setup (see INSTALL.md "Gmail with Grok"):
  1. In Google Cloud Console create an OAuth client of type "Desktop app",
     enable the Gmail API, and add yourself as a test user.
  2. Download its JSON and save it as  google_oauth_client.json  in this folder.
  3. Run:  python3 gmail_auth.py connect   (opens your browser once)

    python3 gmail_auth.py connect   -> browser sign-in, stores a refresh token
    python3 gmail_auth.py token     -> prints a valid access token (auto-refreshes)
    python3 gmail_auth.py status    -> {"connected": true/false, "email": ...}
"""
import base64, hashlib, json, secrets, sys, time, urllib.parse, urllib.request, webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CLIENT = ROOT / "google_oauth_client.json"
STORE = ROOT / "state" / "google_oauth.json"
SCOPES = "https://www.googleapis.com/auth/gmail.modify openid email"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def _post(url, data):
    req = urllib.request.Request(url, urllib.parse.urlencode(data).encode(),
                                 {"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _load_store():
    return json.loads(STORE.read_text(encoding="utf-8-sig")) if STORE.exists() else None


def _save_store(d):
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(d, indent=2), encoding="utf-8")
    try:
        STORE.chmod(0o600)
    except OSError:
        pass


def connect():
    if not CLIENT.exists():
        print(f"!! {CLIENT.name} not found. Create a 'Desktop app' OAuth client in Google Cloud "
              "Console (with the Gmail API enabled), download its JSON, save it under that name "
              "in this folder, then run this again. Steps: INSTALL.md 'Gmail with Grok'.")
        sys.exit(1)
    raw = json.loads(CLIENT.read_text(encoding="utf-8-sig"))
    c = raw.get("installed") or raw.get("web") or raw
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()

    got = {}

    class Cb(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            got.update(urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query))
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("<h2>Open Loops is connected to Gmail.</h2>You can close this tab.".encode())

    srv = HTTPServer(("127.0.0.1", 0), Cb)
    redirect = f"http://127.0.0.1:{srv.server_port}"
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": c["client_id"], "redirect_uri": redirect, "response_type": "code",
        "scope": SCOPES, "access_type": "offline", "prompt": "consent",
        "code_challenge": challenge, "code_challenge_method": "S256"})
    print("Opening your browser for the Google sign-in. Pick the Gmail account Open Loops should read.")
    webbrowser.open(url)
    srv.timeout = 300
    while "code" not in got and "error" not in got:
        srv.handle_request()
    srv.server_close()
    if "error" in got:
        print("!! Google said:", got["error"][0])
        sys.exit(1)
    tok = _post(TOKEN_URL, {"client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
                            "code": got["code"][0], "code_verifier": verifier,
                            "grant_type": "authorization_code", "redirect_uri": redirect})
    email = ""
    idt = tok.get("id_token", "")
    if idt.count(".") == 2:  # email lives in the JWT's middle segment
        pay = idt.split(".")[1]
        email = json.loads(base64.urlsafe_b64decode(pay + "=" * (-len(pay) % 4))).get("email", "")
    _save_store({"client_id": c["client_id"], "client_secret": c.get("client_secret", ""),
                 "refresh_token": tok["refresh_token"], "email": email,
                 "access_token": tok["access_token"], "expires_at": time.time() + tok.get("expires_in", 3600)})
    print(f"done: Gmail connected as {email or 'your account'}")


def token():
    """A valid access token, refreshing if needed; None when not connected."""
    d = _load_store()
    if not d:
        return None
    if time.time() < d.get("expires_at", 0) - 120:
        return d["access_token"]
    try:
        tok = _post(TOKEN_URL, {"client_id": d["client_id"], "client_secret": d.get("client_secret", ""),
                                "refresh_token": d["refresh_token"], "grant_type": "refresh_token"})
    except Exception as e:  # revoked / offline - report as not connected
        print(f"gmail_auth: token refresh failed ({e})", file=sys.stderr)
        return None
    d["access_token"] = tok["access_token"]
    d["expires_at"] = time.time() + tok.get("expires_in", 3600)
    _save_store(d)
    return d["access_token"]


def status():
    d = _load_store()
    return {"connected": bool(d and token()), "email": (d or {}).get("email", "")}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "connect":
        connect()
    elif cmd == "token":
        t = token()
        print(t or "")
        sys.exit(0 if t else 1)
    else:
        print(json.dumps(status()))
