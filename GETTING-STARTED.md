# Open Loops — getting started (5 minutes)

**What it is.** You ask people for things all day — on Slack, by email. Some of them never come back to you.
Open Loops keeps a list of everything you're waiting on, tells you the moment someone replies, and can write
the "just checking in…" message for you in your own words.

**What it needs.** Permission to look at the messages *you* send, and at replies to them. It runs on your
computer only. It never sends anything unless you turn that on.

---

## 1. Install

1. Open the **OpenLoops** folder you were given.
2. **Windows**: double-click **Open Loops.cmd**. **Mac**: double-click **Open Loops.command** — if you see a
   warning that it's from an unidentified developer, right-click it and choose **Open** instead, just this once.
3. A window appears. It may ask for your first name. Let it finish (1–3 minutes). It installs two
   helper programs if you don't have them (Python and Claude), puts an **Open Loops** icon on your Desktop,
   and opens the app.

## 2. Connect your accounts (one-off)

The app opens with a checklist. It watches itself and ticks things off as you go — you don't need to press anything to update it.

| Tick | What to do |
|---|---|
| **Signed in to Claude** | Press **Open Claude**. A black window opens. If it shows a sign-in link, open it and sign in with your **work Google account**. |
| **Slack connected** *(optional)* | In that same black window, type `/mcp` and press Enter. Pick **Slack** → **Authenticate** → click **Allow** in the browser. |
| **Gmail connected** *(optional)* | Same again: `/mcp` → **claude.ai Gmail** → **Authenticate** → **Allow**. |
| **At least one source connected** | Ticks by itself once Slack or Gmail is connected — you only need the one(s) you actually use. |
| **Knows who you are on Slack** | Fills in by itself (only matters if you use Slack). |

When the required rows are ticked the checklist disappears and your list starts building (first fill takes about 2 minutes).

## 3. Every day

- Double-click **Open Loops** on the Desktop. It refreshes itself every weekday morning at 09:15, so it's ready when you sit down.
- **Needs me** — people who've replied and are waiting on *you*.
- **Waiting on them** — things you've asked for. Green = recent, amber = a few days, red = getting old.
- **draft chase** — writes a friendly nudge in your voice and puts it in the conversation as an unsent draft. You read it, you press send.
- **done** when it's sorted. **snooze** to hide it for a bit.

## 4. Make it sound like you

Open ⚙ **Settings** (bottom of the page) → **Learn my tone**. It reads how you write to a few people and
copies your style — relaxed with mates, a lighter touch with the boss. Add people and whether they're
*senior / peer / junior* in the box above it.

## 5. Optional — let it send for you

Also in Settings. Two boxes: **Send to internal people** and **Send to external contacts**. Off, it drafts.
On, it sends without showing you first. There's also a **Timer** that chases anything quiet for a few days
automatically; every item has an *auto: on/off* switch so you can leave one alone.

---

### Things to know
- Nothing runs in the cloud. Your list is a file on your computer.
- It only ever looks at your own sent messages, and at the threads they're in.
- It uses your normal Claude subscription — no extra accounts, no API keys.
- WhatsApp isn't supported (WhatsApp doesn't allow it).
- If something looks wrong, ⚙ Settings → the "Last job output" box shows what happened, and the `state/logs` folder keeps a record.
