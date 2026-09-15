# Merge map: colleague's Open Loops share vs this repo

Compared: `C:\Users\oscarc\Downloads\Open-Loops-share` (colleague, dated 15 Sep 2026) against
branch `combining-feature-updates` (HEAD `6c0e8c0`). Three-way, using `ed97a64` (v0.1) as the base.

> **Status (15 Sep 2026):** everything in sections 1 and 5 is implemented on this branch, including
> optional Day log and Roadmap cards designed fresh (no external folders needed; Miro via the official
> Claude plugin). See `docs/superpowers/specs/2026-09-15-colleague-merge-daylog-roadmap-design.md`.

## Headline

**Their copy forked from a pre-v0.1 internal build, not from v0.1.** It has no `agent.py`,
`people.py`, `gmail_mcp.py`, `standing.py`, no Mac support, no tabs/wizard, flat layout, and the
job scripts call `claude -p` inline. Almost every "difference" is v0.1+ work they never received.
Nothing can be merged as a patch; each of their features has to be re-implemented on top of
`agent.run()` / `paths.ROOT` / the `openloops/` package.

Their genuine additions are small and mostly good. Two are real bug fixes we still have.

| Colleague addition | Verdict | Effort |
|---|---|---|
| `--slack-only` refresh with a second cursor, "Update Slack" button | **Adopt** (port) | ~1 hr |
| `norm_date()` zero-padding on snooze | **Adopt** (real bug in ours) | 5 min |
| Manual items kept out of `state.json` because refresh overwrites it | **Adopt the fix, not the file** (see race below) | 30 min |
| `read_json(path, default)` helper | **Adopt** | 15 min |
| Generic job/log painting in `render()` | **Adopt** | 15 min |
| "+ to-do" button on a loop card | **Adopt** (as "+ note" pre-filling owner/ask) | 20 min |
| HANDOVER.md "read before installing" gotcha list | **Adopt the format** | 20 min |
| `cursor:wait` on disabled buttons, `.pill/.warn/.bad/.good` CSS | Adopt, cosmetic | 5 min |
| To-dos as a standalone checklist section | Skip (ours: note loops in Needs me) | – |
| Clickable links in notes (theirs renders notes as raw HTML) | **Adopt safely**: escape, then linkify URLs | 20 min |
| Roadmap card: paste standup notes, parse to rows, preview, add cards to the Miro board | **Port as optional module** once we have the `roadmap/` tool folder from the colleague | ~2 hr + the tool |
| Day log card (`../dayreport/dayreport.py`) | Same: optional, needs the `dayreport/` folder | ~1 hr + the tool |
| Install path `~/.claude/automations/openloops` | **Do not merge** (keep `%LOCALAPPDATA%\OpenLoops`) | – |
| Hard-coded `mcp__claude_ai_Slack__*` tool ids | Do not merge, but **fix our mirror-image problem** | 45 min |
| Real company domains / vendor names in `config.template.json` | **Do not merge** | – |
| Their `setup.ps1`, `Open Loops.cmd`, `run-refresh.ps1`, docs | Do not merge (all pre-v0.1) | – |

---

## 1. Features to port

### 1a. Slack-only refresh ("Update Slack")

**What they built.** `refresh.py --slack-only` passes only the Slack tools, filters open loops to
`channel == "slack"`, and keeps a second cursor so the quick pass never advances the Gmail cursor
(otherwise email asks between two Slack runs are skipped forever). App exposes it as
`POST /api/refresh {slack_only: true}`; the page has a second header button and shows
`· slack <time>` in the meta line from `last_slack_refresh`.

Their cursor logic (`Open-Loops-share/refresh.py:85,145-156`):

```python
slack_since = s.get("slack_cursor") or s["cursor"]     # Slack search window
# ... on write:
if SLACK_ONLY:
    s["slack_cursor"] = now; s["last_slack_refresh"] = now
else:
    s["cursor"] = now; s["slack_cursor"] = now
    s["last_refresh"] = now; s["gmail_available"] = ...
```

**How to port onto ours** (`openloops/refresh.py`, `openloops/app.py`, `openloops/index.html`):

- `SLACK_ONLY = "--slack-only" in sys.argv`; if not `slack_on`, print `SKIPPED` and `sys.exit(2)`
  like chase does.
- Filter `open_loops` to Slack on top of the existing `from_mail()` filter.
- Keep our `{sources}` list-building. In slack-only: omit the Gmail line and the inbound block,
  prepend their one-sentence `mode_note`.
- Split the date: Slack `after:` from `slack_cursor`, Gmail and inbound `after:` from `cursor`.
  Ours currently uses one `since_date` for all three searches.
- Tools: `SLACK_TOOLS` only in slack-only, never `GMAIL_TOOLS`.
- State write block: mirror theirs exactly. Keep their `channel != "slack"` guard on new loops.
- Drop their "tell the model to set gmail_available true" hack; just don't read it in slack-only.
- Log file name `refresh-slack-<stamp>.log`.
- App: `args += ["--slack-only"]` when the body says so; both refresh buttons disabled while
  `J.refresh` runs. Page: second button, `last_slack_refresh` in `#meta`.

### 1b. Snooze date normalisation (bug in ours)

Ours (`openloops/app.py:243`) stores `body["until"]` raw. Snooze checks are string comparisons in
app, page and autochase, so `2026-9-5` sorts after `2026-09-10` and the loop hides for weeks.
Port their `norm_date()` and return 400 on an unparseable date.

### 1c. State-overwrite race (bug in ours)

Their comment is right and it now bites us harder than it bit them. `openloops/refresh.py:70`
loads `state.json`, runs the agent for minutes, then `:140` writes the stale copy back. Anything the
page wrote meanwhile is lost. In ours that means **manual note loops** (`/api/action add`),
**vault standing saves** on `/api/state`, and snooze/done clicks made during a refresh.

They solved it by moving to-dos into a separate `todos.json`. Better fix for us, no new file:
re-read `state.json` immediately before writing in `refresh.py`, `chase.py` and `autochase.py`, and
merge the agent's `loops` into the fresh copy by loop id. A small `state.py` with
`load()` / `save(mutator)` that does read-mutate-write under one function would cover all three
scripts and app.py.

### 1d. Helpers and small UX

- `read_json(path, default)` with `utf-8-sig` and try/except. Ours repeats the
  `json.loads(...read_text(encoding="utf-8-sig"))` idiom 10 times in `app.py` alone. Pair it with
  `write_json(path, obj)` for the six `json.dumps(..., indent=2, ensure_ascii=False)` writes.
- `render()`: build the `#log` pane from `Object.keys(J)` and drive buttons from a
  `[id, key, idleLabel, busyLabel]` table, so `standing` and any future job stop needing a list edit.
  Keep our `--- name` log prefix and keep the pane collapsed.
- "+ to-do" on a card: port as "+ note" that opens our Needs-me add form pre-filled with the loop's
  owner and ask. Keep our note UX (owner, ask, notes); theirs is a bare checkbox list.
- CSS: `button:disabled{cursor:wait}` reads better than `not-allowed` while a job runs.

### 1e. Links in notes (Drive, Miro, Notion URLs)

The share contains no code that writes Drive URLs into notes. The refresh prompt, the allowed
tools (Slack and Gmail only) and the `note` action are the same as ours. What differs is the
card: theirs renders `l.notes` as raw HTML (`Open-Loops-share/index.html:165`), so any link text
or anchor that she or Claude puts in a note becomes clickable. Ours escapes notes
(`openloops/index.html:284`), so a pasted URL is plain text. The behaviour observed is almost
certainly Claude with the Drive connector writing the URL into the loop's note.

To get the same result without the XSS hole:

- `linkify(text)` on the page: `esc()` first, then wrap `https?://\S+` in
  `<a target="_blank" rel="noopener">`. Apply to notes on cards and to note loops.
  Show a Drive/Miro/Notion host as the link label so long URLs don't swamp the card.
- Add a `links` array on loops with `/api/action add_link {url, label}`, rendered as chips
  next to "open". Notes stay prose; links stay structured and survive note edits.
- Refresh prompt, one line under REPLIES: "If the thread mentions a document URL (Google
  Drive/Docs, Miro, Notion, Figma), include it in `links` for that loop." The model already reads
  the thread; this costs nothing extra.
- Optional: if a Drive connector is present in `claude mcp list`, doctor records it and refresh
  passes its search tool so the model can attach the doc a reply refers to by name.

### 1f. Roadmap and Day log: real, but they need two more folders

The Roadmap card is not dead. `app.py:107-121, 197-236` and `index.html:254-300` are a working
bridge to a sibling `roadmap/` folder: `parse_notes.py` turns pasted standup notes into rows,
`append_cards.py --json` previews and `--go` adds cards to the shared Miro board (add-only,
two-click confirm). `spec.json`, `as_built.json` and `created_ids.txt` supply the live frame
title, lanes and week columns. Day log likewise drives `dayreport/dayreport.py --write-prose`
and serves the day's HTML through the app. Neither folder is in the share, which is why the
handover says the buttons show "not installed".

If we want them:

- Ask the colleague for `~/.claude/automations/roadmap` and `~/.claude/automations/dayreport`,
  including how `append_cards.py` authenticates to Miro (token, board id, frame id).
- Port as an optional module: `openloops/roadmap.py` behind a `roadmap_path` config key
  (default empty). Routes and the card only appear when the folder exists. Do not move our
  install into `~/.claude/automations` for it; resolve the folder from config instead.
- Keep their staging-rows-outside-state.json decision. Same race as 1c.
- Their `/api/roadmap save` writes unvalidated client rows to `notes.json`; validate lane and
  week against `spec.json` when porting.

### 1g. Slack tool prefix: fix our mirror-image of their gotcha

Their HANDOVER item 1: scripts pin the **claude.ai connector** prefix `mcp__claude_ai_Slack__`, and
with the wrong prefix "a refresh silently finds nothing". Ours pins the **plugin** prefix
`mcp__plugin_slack_slack__` in `openloops/agent.py:_FMT`, so connector users hit the identical
silent failure. Fix:

- Add a config key (`slack_source: "plugin" | "connector"`) read by `_FMT` for the Claude row.
- Have `doctor.py` detect which server `claude mcp list` shows (`plugin_slack` vs
  `claude_ai_Slack`) and write the key back, the way it already writes `slack_self_id`.
- Document it in INSTALL.md.

---

## 2. Regressions in their copy: do not carry across

| Item | Why |
|---|---|
| Inline `subprocess.run(["claude","-p",...], shell=True)` in four scripts | Breaks Mac/Linux, loses Grok, four places to edit prefixes. Ours has `agent.run()` and `shell=WIN`. |
| `CFG["slack_self_id"]` hard index | KeyError for Gmail-only users. |
| `autochase.py` reads config/state with `encoding="utf-8"` | Crashes on a BOM file, contradicts their own HANDOVER item 7. |
| Bare-JSON fallback regex removed from refresh/voice | Ours keeps it. |
| `chase.py` passes both connectors' tools regardless of loop channel | Ours narrows to the loop's channel. |
| `doctor.py` requires Slack **and** Gmail | Ours supports either source. |
| `card()` interpolates owner/ask/notes unescaped | XSS from message content. Ours uses `esc()`. This is also what makes links in their notes clickable; see 1e for the safe version. |
| Raw `fetch` that ignores HTTP errors | Ours has `api()` that throws into the banner. |
| Hard-coded port 8765, `webbrowser.open` | Ours has `pick_port`, server-header check, tests. |
| `setup.ps1` writes config/state with a BOM (`Set-Content -Encoding UTF8`); no "already installed" guard; no name prompt loop | Ours writes BOM-less and reads `utf-8-sig`. |
| `Open Loops.cmd` runs in place with `start ""` (swallows errors) | Ours installs on first run. |
| `config.template.json` with four real company domains and two vendor names | Public template must stay `example.com`. |
| Settings in a `<details>` at page bottom, no tabs/wizard | Pre-v0.1 UI. |

Minor code-quality notes in theirs, for whoever reads it: `global doctor_cache` declared inside an
`if` branch; `/api/roadmap save` writes unvalidated client rows; to-do ids are `"t%d" % ms`.

---

## 3. HANDOVER.md items, checked against ours

| # | Their note | Status in ours |
|---|---|---|
| 1 | Slack prefix pinned; wrong prefix = silent empty refresh | Same class of problem, opposite prefix. Fix per 1e. |
| 2 | Fill `slack_self_id`, `internal_domains`, `people` before first refresh | True. Ours adds the people scan and doctor auto-fills the id. |
| 3 | Sends ship OFF | True, documented. |
| 4 | Day log / Roadmap buttons show "not installed" | True only because the two tool folders are not in the share. See 1f. |
| 5 | Changing `refresh_time` in Settings only updates config | Already fixed: `/api/schedule` re-registers the task. |
| 6 | Restart after editing app.py; second launch just opens browser | Still true by design. Add one line to INSTALL troubleshooting. |
| 7 | JSON may carry a BOM; readers use `utf-8-sig` | Already true; installer also avoids writing one. Add a contributor note. |

---

## 4. Things we have that they lack (so they can update from us)

- Agent abstraction (`agent.py`): Claude or Grok, logical tool names, `use_slack`, Grok job env.
- Bundled Gmail MCP server (`gmail_mcp.py`, `gmail_auth.py`) for non-Claude agents.
- `people.py` two-way contact scan feeding the Who's who picker.
- Inbound loops: unanswered asks *of you* land as `needs_me` cards.
- Manual note loops, vault standing items (`standing.py`, `close_standing.py`), `history_days`.
- Dynamic port fallback, already-running detection, `--no-browser`, `OPENLOOPS_PORT`.
- Mac: `install.sh`, `Open Loops.command`, `.app` bundle, launchd scripts.
- Tabs, 4-stage wizard, people picker, `esc()` in cards, `api()` error banner.
- `tests/` (port clash, manual notes, standing, Mac launch), docs site, ROADMAP, README "why".

---

## 5. Optimisations surfaced by the comparison (ours, independent of their code)

- **Task time mismatch.** `scripts/register-task.ps1` and `run-refresh.ps1` default and document
  `08:40`; `setup.ps1`, GETTING-STARTED and the page say `09:15`. Align to 09:15.
- **Task time limit.** `register-task.ps1` sets a 20 min limit; a first refresh with
  `history_days` near 365 can exceed it. Raise to 45–60 min or parameterise.
- **Install copy.** `setup.ps1` excludes by top-level name only, so `docs/`, `tests/`, `.grok/`
  land in `%LOCALAPPDATA%\OpenLoops`. Switch to an include list.
- **Launcher error swallowing.** `Open Loops.cmd` uses `start "" pythonw`; add a
  `where pythonw` guard so a missing Python is visible.
- **Job-script duplication.** refresh/chase/voice/people each repeat config load, log dir mkdir,
  log write and the marker-or-bare-JSON regex. A `jobs.py` (`load_cfg`, `write_log`,
  `extract_block`) removes ~30 lines and makes the slack-only log naming trivial.
- **`since_for(source)` helper** in refresh.py once the two cursors exist.
- **`agent.can_send_email()`** so chase.py and a future UI toggle agree on the non-Claude guard.
- **README file table.** Restore a compact "what's in the folder" table naming
  `python -m openloops.doctor` etc., so support prompts have somewhere to point.
- **Gotchas section** in INSTALL.md (HANDOVER style): Slack plugin vs connector, second launch only
  opens the browser, BOM rule, OneDrive-synced folders lock files.

---

## 6. Suggested order of work on this branch

1. `norm_date` on snooze (tiny, isolated).
2. `read_json` / `write_json` helpers in app.py.
3. State re-read-before-write in refresh/chase/autochase (fixes the race for notes and vault saves).
4. `--slack-only` refresh with two cursors, app flag, "Update Slack" button, meta line.
5. `linkify` notes, `links` array on loops, one-line prompt change (1e).
6. Generic job/log painting; "+ note" on cards; `cursor:wait`.
7. `slack_source` config key with doctor detection.
8. Housekeeping: 09:15 alignment, task time limit, install include list, cmd guard, INSTALL gotchas.
9. Ask the colleague for the `roadmap/` and `dayreport/` folders, then port both as optional
   modules (1f). Send them section 4 so they can rebase onto the public repo.
