# Open Loops

Keeps track of everything you've asked people for — on Slack and by email — until they reply, then reminds you until *you* reply. Writes the "just checking in…" nudge in your own words. Runs on your computer, uses the AI subscription you already have — **Claude** (default) or **Grok** — no API keys.

Switch AI in ⚙ Settings → *Your AI* (`"agent"` in `config.json`). The connection checklist adapts to whichever you pick; with Grok, Gmail needs one extra one-off step (see **Gmail with Grok** in [INSTALL.md](INSTALL.md)) and email chases are always drafts, never sent.

## I'm a person — how do I install it?

1. **Windows**: double-click **`Open Loops.cmd`**. **Mac**: double-click **`Open Loops.command`** (if macOS warns it's from an unidentified developer, right-click it → **Open** instead). Either is the only file you need to touch. Let it finish (1–3 min).
2. The app opens with a checklist. Do what each unticked row says (it's: press **Open Claude**, sign in, type `/mcp`, connect **Slack** and/or **Gmail** — whichever you use, one is enough). The ticks appear by themselves.
3. Double-click **Open Loops** on your Desktop every morning.

Full plain-language guide: **[GETTING-STARTED.md](GETTING-STARTED.md)**. Technical detail / rules it follows: **[INSTALL.md](INSTALL.md)**.

## I'd rather Claude did it — what do I paste?

If you have Claude Code, open it in this folder and paste this:

> Install Open Loops for me. Read `INSTALL.md` and `GETTING-STARTED.md` in this folder first. Then run `setup.ps1` on Windows or `install.sh` on Mac (these are what `Open Loops.cmd` / `Open Loops.command` run on first use) with my first name — ask me if you don't know it, confirm the Desktop icon and the weekday scheduled task exist, and open the app. If the app's checklist shows Slack or Gmail not connected, tell me the exact steps to do in `/mcp` — you can't do that part for me. When everything is green, run `python refresh.py` then `python voice.py`, and show me what it found. Don't turn on sending or the timer.

If something breaks later, paste this:

> Open Loops (in `~/.claude/automations/openloops`) isn't working: <what you saw>. Read `INSTALL.md`, run `python doctor.py`, check the newest file in `state/logs/`, and tell me what's wrong in plain language before changing anything.

## What's in the folder

| File | What it does |
|---|---|
| `setup.ps1` / `install.sh` | one-click installer (Python + Claude Code if missing, Desktop icon, morning task) — Windows / Mac |
| `app.py` | the page at http://localhost:8765 — double-click the Desktop icon |
| `doctor.py` | the automatic "are you connected?" check the page shows on first run |
| `agent.py` | which AI runs the jobs (Claude or Grok) and how each one is invoked |
| `gmail_auth.py` | Gmail sign-in for non-Claude agents (Claude uses its own connector) |
| `gmail_mcp.py` | the bundled Gmail MCP server those agents run (search, read, draft — never send) |
| `qa.py` | new-user walkthrough test: throwaway install → connect → who's who → tone → first scan, asserting each stage (`python qa.py`, ~5 min) |
| `refresh.py` | finds your new asks and checks every open thread for replies |
| `chase.py` | writes a nudge for one loop — draft by default; sends only if you tick the boxes in Settings |
| `autochase.py` | the optional timer: chases anything quiet for N workdays |
| `voice.py` | learns how you write to each person so nudges sound like you |
| `config.json` | your settings (edited from ⚙ Settings in the page) · `config.template.json` is the blank one new installs get |
| `state.json` | your list · `state/logs/` one log per run |
| `scripts/` | the scheduled-task helpers — Task Scheduler (`*.ps1`) on Windows, `launchd` (`*.sh`) on Mac |

## Ground rules (the short version)
- Reads only **your own sent messages** and the threads they're in.
- **Never sends** unless you tick *Send to internal* / *Send to external* in Settings. Off = drafts you press send on.
- Nothing leaves your computer except via the Slack / Gmail connections you authorised.
- WhatsApp isn't possible (no API for personal accounts).
