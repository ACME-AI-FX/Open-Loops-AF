"""Small shared helpers for the JSON files under the install root.

read_json / write_json  BOM-tolerant readers, atomic writers (tmp + replace).
load_cfg                config.json laid over config.template.json, so a copy that never went
                        through the installer (a git checkout, a hand-made config) still has every
                        default; empty strings inside tone / auto_chase / escalation fall back too.
load_state / update_state
    Every job script (refresh, chase, autochase, daylog, roadmap) runs for minutes between
    reading state.json and writing it back. update_state re-reads the file at write time and
    applies the change to that fresh copy, so anything the page wrote meanwhile - a note,
    a snooze, a vault save, a done click - survives.
norm_date               zero-pads YYYY-M-D; snooze checks are string comparisons everywhere.
"""
import json
from datetime import date
from pathlib import Path

from .paths import ROOT
STATE = ROOT / "state.json"
CONFIG = ROOT / "config.json"
TEMPLATE = ROOT / "config.template.json"


def read_json(path, default=None):
    p = Path(path)
    if not p.exists():
        return default
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except (ValueError, OSError):
        return default


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(p)


def load_cfg():
    """config.json with every missing key (and every blank entry in a nested section such as tone)
    filled from config.template.json. Keys the template does not know are kept as they are."""
    base = read_json(TEMPLATE, {}) or {}
    cfg = read_json(CONFIG, {}) or {}
    out = dict(base)
    for k, v in cfg.items():
        d = base.get(k)
        if isinstance(v, dict) and isinstance(d, dict):
            out[k] = {**d, **{kk: vv for kk, vv in v.items() if vv not in ("", None)}}
        else:
            out[k] = v
    return out


def load_state():
    return read_json(STATE, {"cursor": None, "last_refresh": None, "loops": []})


def update_state(fn):
    """Read state.json fresh, let fn mutate it in place, write it back. Returns the state."""
    s = load_state()
    s.setdefault("loops", [])
    fn(s)
    write_json(STATE, s)
    return s


def norm_date(v):
    """'2026-9-5' -> '2026-09-05'. Raises ValueError for anything that is not a date."""
    parts = str(v or "").strip().split("-")
    if len(parts) != 3 or not all(x.isdigit() for x in parts):
        raise ValueError("date must be YYYY-MM-DD")
    y, m, d = (int(x) for x in parts)
    return date(y, m, d).isoformat()
