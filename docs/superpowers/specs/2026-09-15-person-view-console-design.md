# Design: person rows, priority, a calmer connection check, and a Console

Date: 2026-09-15. Branch: `combining-feature-updates` (PR #4). Follows the collapsible Home sections.

## Goal

Three things a first-time user hit or asked for, in one pass:

1. **The lists group by person.** One row per person, a small colour block per loop, and a short
   summary of what the loops are about. Click the person to open the cards. Nothing to configure.
2. **Priority.** The refresh judges each loop `high`, `normal` or `low` and names its theme in a few
   words. A person can correct the priority on the card, and their setting sticks: the AI never
   changes a priority marked as theirs.
3. **When the connection check itself fails, the page says so in plain words** and keeps working.
   A **Console** at the bottom of the page records what the page did, with Copy / Copy all / Clear,
   so a bug report is a paste rather than a screenshot.

## Person rows (`#needs`, `#waiting`)

- Grouping key: `owner`, else "Notes to self" (typed notes) or "Your to-do file" (vault lines).
  Automatic: it is not a filter and there is nothing to switch on.
- Row layout: **name** | **blocks** | summary | `n · oldest Nwd ▾`. One block per loop, coloured
  by **age**: green under two workdays, amber two to four, red beyond. Age is how long the ball has
  sat in someone's court: for *Waiting on them* since the ask or the last chase, for *Needs me*
  since they replied (or since the note was written).
- Summary: one loop shows the full ask plus its theme as a pill. Two or more show up to four
  lines of `theme · ask`; five or more show three lines and "+N more".
- A red `!` after the name means at least one loop is high priority.
- Click (or Enter / Space) toggles the person open; the cards render below the row unchanged.
  Open people are remembered in `localStorage` (`ol.person.open`) per section.
- Sort toggle at the top of each section when it has more than one loop: **oldest first**
  (default) or **priority** (high first, then oldest). Remembered in `ol.sort`.
- Section subtitle gains the people count: `10 · 4 people · …`.

## Priority and theme

- Loop fields: `priority` (`high|normal|low`), `priority_by` (`ai|you`), `theme` (≤40 chars).
- `refresh.py` prompt step 3 asks for both on every new loop; existing loops without a theme get
  one in their update; priority changes only when the thread clearly changed and never on loops
  marked `priority_by: you`. `apply()` enforces the same rules regardless of what the agent returns,
  and an unknown priority word falls back to `normal`.
- Card control: a small `priority` select under the channel line, with "AI" or "you" after it.
  Changing it posts `/api/action {action: "priority", priority}` which sets `priority_by: "you"`.
  Anything but the three words is a 400.

## The connection check failing

- Server (`/api/doctor`): a check that produced no output is run once more after two seconds.
  If it still cannot be parsed the cached result is `{all_ok: false, error: <why>, steps: [], rc}`.
  The old fake "Check failed" step is gone. The raw record stays in `state/logs/doctor-last.log`.
- Page (`doctor()`):
  - With a previous good answer: keep it, stay on the lists, one quiet toast ("Couldn't re-check
    your connections just now. Trying again in a moment."), retry every 15 s up to three times,
    then the normal once-a-minute rhythm.
  - Without one: stage `checkfail`. The `#st_checkfail` box says "I couldn't run the connection
    check. Nothing is wrong with your Slack or email…" with a **Retry** button and a link to the
    Console. The steps bar treats it as step 1. No exit codes or paths on the page.
  - Every attempt and outcome is a Console line.

## Console (`#console_wrap`)

- A collapsed section at the bottom of both tabs. Lines are `YYYY-MM-DD HH:MM:SS  message`, kept
  in `localStorage` (`ol.console`, last 400) so they survive a reload.
- What is logged: page open (host + page id), every failed request, every toast (errors prefixed
  `error:`), banner text, stage changes, connection-check outcomes (when they change), job start
  and finish with exit code and last output line, script errors and unhandled rejections.
- Buttons: **Copy** (the lines), **Copy all** (lines plus `GET /api/diag`: Python, platform, port,
  root, build stamp, start time, agent, model, page count, per-job rc + tail, last check result,
  tail of `doctor-last.log`), **Clear**. Clipboard via `navigator.clipboard`, `execCommand` fallback,
  and a "select the text and press Ctrl+C" note if both refuse.

## Tests

- `test_api_extras.py`: priority action (valid / invalid / marks `you`), `/api/diag` shape, page
  needles for the Console, checkfail box, person rows, priority select; no "Check failed" text.
- `test_refresh_apply.py`: new-loop defaults, agent priority + theme kept (theme capped), unknown
  priority → normal, update fills missing priority/theme, update never overrides `priority_by: you`.

## Out of scope

Filtering by person or theme; drag-to-reorder; priority on Snoozed / done cards; sending Console
contents anywhere automatically.
