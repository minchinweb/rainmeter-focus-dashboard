"""TaskNotes time blocks in the daily note.

A time block is an entry in the `timeblocks:` list of the day's daily note frontmatter, in the
shape TaskNotes writes it:

    timeblocks:
      - id: tb-1768231867794-op223azjg
        title: "Create issue for packaging"
        startTime: 08:30
        endTime: 09:43
        priority: A          # written by focus.py; not a TaskNotes field
        color: "#6366f1"

focus.py opens one block per focus. It stays open until the next focus or a clear, so its
endTime is a placeholder (OPEN_END) until then; TaskNotes expects an endTime on every block.
collect.py falls back to the block that covers the current time when nothing else is running.

Edits are line-based so the rest of the note is left exactly as it was.
"""

import json
import random
import re
import string
from pathlib import Path

import yaml

OPEN_END = "23:59"  # placeholder endTime while a focus block is still open
DEFAULT_COLOR = "#6366f1"
DEFAULT_DAILY = {"folder": "journal", "format": "YYYY/MM/YYYY-MM-DD"}


def plugin_setting(vault, key, default):
    """One value from the TaskNotes plugin settings, or default if unreadable or unset."""
    try:
        data = json.loads((Path(vault) / ".obsidian/plugins/tasknotes/data.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default
    return data.get(key) or default


def daily_note_path(vault, day):
    """Path of the daily note for day, from the periodic-notes folder and format (YYYY, MM, DD tokens)."""
    try:
        data = json.loads((Path(vault) / ".obsidian/plugins/periodic-notes/data.json").read_text(encoding="utf-8"))
        cfg = data.get("daily") or {}
    except (OSError, ValueError, AttributeError):
        cfg = {}
    fmt = cfg.get("format") or DEFAULT_DAILY["format"]
    rel = fmt.replace("YYYY", f"{day:%Y}").replace("MM", f"{day:%m}").replace("DD", f"{day:%d}")
    return Path(vault) / (cfg.get("folder") or DEFAULT_DAILY["folder"]) / f"{rel}.md"


def _daily_config(vault):
    try:
        data = json.loads((Path(vault) / ".obsidian/plugins/periodic-notes/data.json").read_text(encoding="utf-8"))
        return data.get("daily") or {}
    except (OSError, ValueError, AttributeError):
        return {}


DATE_TOKEN = re.compile(r"\{\{date(?::([^}]*))?\}\}")
MOMENT_TOKEN = re.compile(r"YYYY|MMMM|MM|M|DD|D|HH|mm|ss|ZZ")


def _moment(now, fmt):
    """Format with the Moment tokens the daily template uses (a subset of Obsidian's date syntax)."""
    values = {
        "YYYY": f"{now:%Y}", "MMMM": f"{now:%B}", "MM": f"{now:%m}", "M": str(now.month),
        "DD": f"{now:%d}", "D": str(now.day), "HH": f"{now:%H}", "mm": f"{now:%M}",
        "ss": f"{now:%S}", "ZZ": f"{now:%z}",
    }
    return MOMENT_TOKEN.sub(lambda m: values[m.group(0)], fmt)


def _new_note_text(vault, now):
    """The daily template rendered for now, or a minimal note if the template is missing."""
    template = Path(vault) / (_daily_config(vault).get("template") or "_templates/Daily Note.md")
    try:
        raw = _read(template)[0]
    except OSError:
        return f"---\ndate: {now:%Y-%m-%d}\n---\n# Today -- {now:%B} {now.day}, {now:%Y}\n"
    return DATE_TOKEN.sub(lambda m: _moment(now, m.group(1) or "YYYY-MM-DD"), raw)


def clock_minutes(value):
    """Minutes after midnight for an HH:mm value, or None.

    YAML 1.1 reads an unquoted 15:00 as the sexagesimal integer 900, so an int is already minutes.
    """
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
    if not match:
        return None
    return int(match[1]) * 60 + int(match[2])


# ---- reading -------------------------------------------------------------------------------

def _read(path):
    """Text with LF newlines, and the newline style to write it back with."""
    with open(path, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def _split(text):
    """(frontmatter lines, lines from the closing fence on), or None when there is no frontmatter."""
    lines = text.split("\n")
    if lines[0] == "---":
        for j in range(1, len(lines)):
            if lines[j].rstrip() == "---":
                return lines[1:j], lines[j:]
    return None


def _meta(path):
    parts = _split(_read(path)[0])
    if not parts:
        return {}
    try:
        data = yaml.safe_load("\n".join(parts[0]))
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def current_block(vault, now):
    """The block in today's daily note that covers now (latest start wins), or None.

    Returns {"title", "start" ("HH:mm"), "priority" (letter or None), "path" (vault-relative)}.
    A block without an endTime runs to the end of the day.
    """
    path = daily_note_path(vault, now.date())
    if not path.exists():
        return None
    minute = now.hour * 60 + now.minute
    best = None
    for block in _meta(path).get("timeblocks") or []:
        if not isinstance(block, dict):
            continue
        start = clock_minutes(block.get("startTime"))
        end = clock_minutes(block.get("endTime"))
        if start is None:
            continue
        if end is None:
            end = 24 * 60
        if start <= minute < end and (best is None or start > best[0]):
            best = (start, block)
    if best is None:
        return None
    start, block = best
    return {
        "id": str(block.get("id") or ""),
        "title": str(block.get("title") or "(untitled)"),
        "start": f"{start // 60:02d}:{start % 60:02d}",
        "priority": str(block["priority"]).strip() if block.get("priority") else None,
        "path": str(path.relative_to(vault)),
    }


# ---- writing -------------------------------------------------------------------------------

def _item(block):
    lines = [
        f"  - id: {block['id']}",
        f"    title: {json.dumps(block['title'], ensure_ascii=False)}",
        f"    startTime: {block['startTime']}",
    ]
    if block.get("endTime"):
        lines.append(f"    endTime: {block['endTime']}")
    if block.get("priority"):
        lines.append(f"    priority: {block['priority']}")
    if block.get("color"):
        lines.append(f"    color: {json.dumps(block['color'])}")
    return lines


def _region(front):
    """(index of the timeblocks key, index just past its list), or (None, None)."""
    for idx, line in enumerate(front):
        if line.startswith("timeblocks:"):
            end = idx + 1
            while end < len(front) and (
                not front[end].strip() or front[end][:1] in (" ", "\t") or front[end].startswith("-")
            ):
                end += 1
            return idx, end
    return None, None


def _add(front, block):
    idx, end = _region(front)
    if idx is None:
        return front + ["timeblocks:"] + _item(block)
    front[idx] = "timeblocks:"  # also turns an empty `timeblocks: []` into a list
    while end > idx + 1 and not front[end - 1].strip():
        end -= 1
    return front[:end] + _item(block) + front[end:]


def _set_end(front, block_id, value):
    """Set endTime on the block with block_id. Returns the new lines, or None if not found."""
    idx, end = _region(front)
    if idx is None:
        return None
    for start in range(idx + 1, end):
        match = re.match(r"^\s*-\s+id:\s*(.*?)\s*$", front[start])
        if match and match.group(1).strip("\"'") == block_id:
            break
    else:
        return None
    item_indent = len(front[start]) - len(front[start].lstrip())
    stop = start + 1
    while stop < end and not (
        front[stop].strip().startswith("-")
        and len(front[stop]) - len(front[stop].lstrip()) <= item_indent
    ):
        stop += 1
    for i in range(start + 1, stop):
        if re.match(r"\s+endTime:", front[i]):
            indent = front[i][: len(front[i]) - len(front[i].lstrip())]
            front[i] = f"{indent}endTime: {value}"
            return front
    return front[: start + 1] + [f"    endTime: {value}"] + front[start + 1:]


def _edit(vault, path, now, change):
    """Apply change(frontmatter lines) to the note, creating today's daily note from the template if missing.

    change returns the new lines, or None to leave the note alone.
    """
    if path.exists():
        text, nl = _read(path)
    else:
        text, nl = _new_note_text(vault, now), "\n"
    parts = _split(text)
    if parts is None:
        front, rest = [], text.split("\n")
        new_front = change(front)
        if new_front is None:
            return False
        lines = ["---", *new_front, "---", *rest]
    else:
        front, rest = parts
        new_front = change(list(front))
        if new_front is None:
            return False
        lines = ["---", *new_front, *rest]
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(lines).replace("\n", nl))
    return True


def _new_id(now):
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=9))
    return f"tb-{int(now.timestamp() * 1000)}-{suffix}"


def start_block(vault, title, priority, now):
    """Open a block for a focus from now until closed. Returns its reference {"path", "id"}."""
    path = daily_note_path(vault, now.date())
    block = {
        "id": _new_id(now),
        "title": title,
        "startTime": f"{now:%H:%M}",
        "endTime": OPEN_END,
        "priority": priority or None,
        "color": plugin_setting(vault, "defaultTimeblockColor", DEFAULT_COLOR),
    }
    _edit(vault, path, now, lambda front: _add(front, block))
    return {"path": str(path.relative_to(vault)), "id": block["id"]}


def end_block(vault, ref, now):
    """Close the block ref names at now. Does nothing if the note or block is gone."""
    path = Path(vault) / ref["path"]
    if not path.exists():
        return
    end = f"{now:%H:%M}"
    _edit(vault, path, now, lambda front: _set_end(front, ref["id"], end))
