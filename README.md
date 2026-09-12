# Open Loops

<p align="center"><img src="docs/logo-512.png" width="128" alt="Open Loops"></p>

<p align="center">The list of things you asked people for — and the things they are waiting on you for — on your computer, in your words.</p>

<p align="center"><img src="docs/home.png" alt="Open Loops home: Needs me, Waiting on them, add a note"></p>

Runs locally. Uses the Claude or Grok subscription you already have. No API keys.

**What it does**

- Shows who has not come back to you, and who is waiting on you.
- Writes the “just checking in…” chase in your voice, as a **draft** you send.
- Lets you add your own to-dos (contact optional) so they sit next to the real threads.
- Can read open items from a `standing-items.md` notes file, if you keep one.
- Never sends unless you tick that on. Off = drafts.

**Install** (1–3 minutes)

1. **Windows:** double-click `Open Loops.cmd`. **Mac:** double-click `Open Loops.command` (if macOS blocks it, right-click → Open).
2. Tick the checklist: sign in, connect Slack and/or Gmail (one is enough).
3. Open **Open Loops** from the Desktop each morning (Mac: orange-loop app — drag it to the Dock).

Guides: [GETTING-STARTED.md](GETTING-STARTED.md) · [INSTALL.md](INSTALL.md) (Grok Gmail step is here).

**Ground rules**

- Reads your own sent messages and the threads they sit in. Nothing else.
- Sends only if you tick *Send to internal* / *Send to external*.
- Your list stays in `state.json` on this machine. Tokens and settings are gitignored.

MIT licence. WhatsApp is not possible (no API for personal accounts).
