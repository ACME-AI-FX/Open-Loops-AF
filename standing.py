"""Read/write ClaudeCloud standing-items.md. Line format must stay Telegram-compatible.

    - [ ] A1 | project | action | added YYYY-MM-DD [| snoozed-until YYYY-MM-DD]
    - [x] A1 | project | action | added YYYY-MM-DD | done YYYY-MM-DD
    - [-] A1 | project | action | added YYYY-MM-DD | dropped YYYY-MM-DD
"""
import hashlib, json, re
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
ITEM_RE = re.compile(
    r"^- \[([ x-])\] (A\d+) \| ([^|]+?) \| (.+?) \| added (\d{4}-\d{2}-\d{2})(.*)$"
)


def vault_root():
    cfg = {}
    if CONFIG.exists():
        cfg = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    p = (cfg.get("vault_path") or "").strip()
    return Path(p).expanduser() if p else Path.home() / "ClaudeCloud"


def standing_path():
    return vault_root() / "02-Research" / "standing-items.md"


def _today():
    return date.today().isoformat()


def _read():
    p = standing_path()
    if not p.exists():
        return None
    return p.read_text(encoding="utf-8").splitlines()


def _write(lines):
    out = []
    for ln in lines:
        if ln.startswith("updated:"):
            out.append(f"updated: {_today()}")
        else:
            out.append(ln)
    p = standing_path()
    tmp = p.with_suffix(".md.tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    tmp.replace(p)


def _snoozed_future(suffix, today):
    m = re.search(r"snoozed-until (\d{4}-\d{2}-\d{2})", suffix or "")
    return bool(m and m.group(1) >= today)


def open_items(today=None):
    """Open, not-snoozed standing items as dicts."""
    today = today or _today()
    lines = _read()
    if lines is None:
        return []
    items = []
    for ln in lines:
        m = ITEM_RE.match(ln)
        if not m or m.group(1) != " ":
            continue
        if _snoozed_future(m.group(6), today):
            continue
        items.append({
            "id": m.group(2).upper(),
            "project": m.group(3).strip(),
            "action": m.group(4).strip(),
            "added": m.group(5),
        })
    return items


def _fp(it):
    return hashlib.sha1(f"{it['project']}|{it['action']}|{it['added']}".encode()).hexdigest()[:12]


def _source_label():
    p = standing_path()
    try:
        rel = p.resolve().relative_to(vault_root().resolve())
        return f"ClaudeCloud / {rel.as_posix()}"
    except Exception:
        return str(p)


def touch_seen(state, items):
    """Record first-seen / wording-changed in state.json['vault_seen']. Returns flags + dirty."""
    now = datetime.now().astimezone().isoformat(timespec="minutes")
    today = now[:10]
    seen = dict(state.get("vault_seen") or {})
    flags, dirty = {}, False
    live = set()
    for it in items:
        live.add(it["id"])
        fp = _fp(it)
        prev = seen.get(it["id"])
        if not prev:
            seen[it["id"]] = {"fp": fp, "first_seen": now, "changed_at": None, "action": it["action"]}
            flags[it["id"]] = "new"
            dirty = True
        elif prev.get("fp") != fp:
            prev["fp"] = fp
            prev["changed_at"] = now
            prev["action"] = it["action"]
            flags[it["id"]] = "updated"
            dirty = True
        else:
            fs = (prev.get("first_seen") or "")[:10]
            ch = (prev.get("changed_at") or "")[:10]
            if ch == today:
                flags[it["id"]] = "updated"
            elif fs == today:
                flags[it["id"]] = "new"
            else:
                flags[it["id"]] = ""
    for k in list(seen):
        if k not in live:
            del seen[k]
            dirty = True
    if dirty:
        state["vault_seen"] = seen
    else:
        state.setdefault("vault_seen", seen)
    return flags, dirty


def as_loops(state=None):
    """Cards for the Home list. Not stored as loops. Updates vault_seen when state is passed."""
    items = open_items()
    flags = {}
    dirty = False
    if state is not None:
        flags, dirty = touch_seen(state, items)
    src = _source_label()
    p = standing_path()
    mtime = None
    if p.exists():
        mtime = datetime.fromtimestamp(p.stat().st_mtime).astimezone().isoformat(timespec="minutes")
    out = []
    recs = (state or {}).get("vault_seen") or {}
    for it in items:
        rec = recs.get(it["id"]) or {}
        out.append({
            "id": f"vault-{it['id']}",
            "owner": it["project"],
            "owner_email": None,
            "ask": it["action"],
            "channel": "vault",
            "vault_id": it["id"],
            "source": src,
            "vault_mtime": mtime,
            "vault_flag": flags.get(it["id"]) or "",
            "vault_first_seen": rec.get("first_seen"),
            "vault_changed_at": rec.get("changed_at"),
            "thread": None,
            "link": None,
            "asked_at": f"{it['added']}T09:00:00",
            "status": "needs_me",
            "inbound": True,
            "manual": True,
            "notes": it["id"],
            "last_reply_at": None,
            "reply_snippet": None,
            "chases": 0,
            "snooze_until": None,
        })
    return out, dirty


def _move_to_closed(lines, idx, new_line):
    del lines[idx]
    closed_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "## closed":
            closed_idx = i
            break
    if closed_idx is None:
        lines += ["", "## Closed", "", new_line]
        return lines
    insert_at = closed_idx + 1
    if insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    if insert_at < len(lines) and lines[insert_at].strip().lower() == "(none yet)":
        del lines[insert_at]
    lines.insert(insert_at, new_line)
    return lines


def _append_closure_note(lines, item_id, closure, extra=""):
    """Append a parse-friendly line under ## Closure notes (created if missing)."""
    note = (closure or "").replace("|", "—").replace("\n", " ").strip()
    if extra:
        note = f"{note} {extra.replace('|', '—').replace(chr(10), ' ').strip()}".strip()
    entry = f"- {item_id} | {_today()} | {note}"
    heading = None
    for i, ln in enumerate(lines):
        if ln.strip().lower() == "## closure notes":
            heading = i
            break
    if heading is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines += ["## Closure notes", "", entry]
        return lines
    insert_at = heading + 1
    if insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, entry)
    return lines


def close_item(item_id, closure):
    """Mark one open item done and record how it was closed. Raises ValueError on bad input."""
    item_id = (item_id or "").upper()
    closure = (closure or "").strip()
    if not re.fullmatch(r"A\d+", item_id):
        raise ValueError("not a standing item")
    if not closure:
        raise ValueError("say how you are closing it")
    lines = _read()
    if lines is None:
        raise ValueError("no standing-items file in the vault")
    idx, match = None, None
    for i, ln in enumerate(lines):
        m = ITEM_RE.match(ln)
        if m and m.group(2).upper() == item_id:
            idx, match = i, m
            break
    if idx is None:
        raise ValueError(f"unknown item {item_id}")
    if match.group(1) != " ":
        raise ValueError(f"{item_id} is already closed")
    project, action, added = match.group(3).strip(), match.group(4).strip(), match.group(5)
    new_line = f"- [x] {item_id} | {project} | {action} | added {added} | done {_today()}"
    lines = _move_to_closed(lines, idx, new_line)
    lines = _append_closure_note(lines, item_id, closure)
    _write(lines)
    return {"id": item_id, "project": project, "action": action}


def apply_updates(updates):
    """Apply agent knock-ons to other standing items. updates: [{id, verb, action?}]."""
    if not updates:
        return []
    lines = _read()
    if lines is None:
        return []
    applied = []
    today = _today()
    for u in updates:
        item_id = str(u.get("id") or "").upper()
        verb = (u.get("verb") or "").strip().lower()
        if not re.fullmatch(r"A\d+", item_id) or verb not in ("edit", "done", "drop"):
            continue
        idx, match = None, None
        for i, ln in enumerate(lines):
            m = ITEM_RE.match(ln)
            if m and m.group(2).upper() == item_id:
                idx, match = i, m
                break
        if idx is None or match.group(1) != " ":
            continue
        project, action, added = match.group(3).strip(), match.group(4).strip(), match.group(5)
        suffix = match.group(6) or ""
        if verb == "edit":
            new_action = (u.get("action") or "").strip()
            if not new_action or new_action == action:
                continue
            lines[idx] = f"- [ ] {item_id} | {project} | {new_action} | added {added}{suffix}"
            applied.append(item_id)
        elif verb == "done":
            new_line = f"- [x] {item_id} | {project} | {action} | added {added} | done {today}"
            lines = _move_to_closed(lines, idx, new_line)
            why = (u.get("note") or "closed as a knock-on of another item").strip()
            lines = _append_closure_note(lines, item_id, why)
            applied.append(item_id)
        elif verb == "drop":
            new_line = f"- [-] {item_id} | {project} | {action} | added {added} | dropped {today}"
            lines = _move_to_closed(lines, idx, new_line)
            applied.append(item_id)
    if applied:
        _write(lines)
    return applied
