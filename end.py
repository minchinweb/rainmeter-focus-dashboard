"""End whatever is running: the focus, a time block covering now, TaskNotes timers and TimeTagger records.

Run by the End button on the Current task skin (bin/end.cmd). Each kind is ended the way its
owner expects:

    focus               focus.json is removed and its time block is closed (same as Clear).
    time block          the block covering now in today's daily note gets endTime = now.
    TaskNotes timers    entries with no endTime in the note's timeEntries get endTime = now,
                        then _scripts/tasknotes_to_timetagger.py runs so TimeTagger follows.
                        Timers older than MAX_RUNNING_HOURS are left alone (abandoned, as the
                        sync script treats them), so a forgotten timer does not log days.
    TimeTagger          running records not synced from TaskNotes get t2 = now. Synced records
                        (tnsync keys) are left to the sync, since the vault is the source.

What happened is appended to end.log next to this script, because the button runs without a window.
"""

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

import collect
import focus
import timeblocks

HERE = Path(__file__).resolve().parent
LOG = HERE / "end.log"
MAX_RUNNING_HOURS = collect.MAX_RUNNING_HOURS
VAULT = collect.VAULT
SYNC_SCRIPT = VAULT / "_scripts" / "tasknotes_to_timetagger.py"
SYNC_TIMEOUT = 300
ENDED_VALUES = ("", "null", "~")


def _read(path):
    with open(path, encoding="utf-8", newline="") as fh:
        raw = fh.read()
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def _write(path, text, nl):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text.replace("\n", nl))


def _start_of(item):
    for line in item:
        match = re.match(r"^\s*(?:-\s+)?startTime:\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip("\"'")
    return None


def _ended(item):
    for line in item:
        match = re.match(r"^\s*(?:-\s+)?endTime:\s*(.*?)\s*$", line)
        if match:
            return match.group(1) not in ENDED_VALUES
    return False


def _close_running(text, stamp, now):
    """Close running timeEntries in a note's frontmatter. Returns (text, closed, stale)."""
    lines = text.split("\n")
    if not lines or lines[0] != "---":
        return text, 0, 0
    close = next((j for j in range(1, len(lines)) if lines[j].rstrip() == "---"), None)
    top = next((i for i in range(1, close or 0) if lines[i].startswith("timeEntries:")), None)
    if close is None or top is None:
        return text, 0, 0
    end = top + 1
    while end < close and (not lines[end].strip() or lines[end][:1] in (" ", "\t") or lines[end].startswith("-")):
        end += 1
    starts = [i for i in range(top + 1, end) if re.match(r"\s*-\s", lines[i])]
    edits, closed, stale = [], 0, 0
    for n, s in enumerate(starts):
        stop = starts[n + 1] if n + 1 < len(starts) else end
        item = lines[s:stop]
        start_text = _start_of(item)
        if start_text is None or _ended(item):
            continue
        try:
            started = datetime.fromisoformat(start_text)
        except ValueError:
            continue
        if not started.tzinfo:
            started = started.astimezone()
        if (now - started).total_seconds() > MAX_RUNNING_HOURS * 3600:
            stale += 1
            continue
        # replace an empty/null endTime in place, otherwise add one after the last line of the entry
        for k, line in enumerate(item):
            match = re.match(r"^(\s*(?:-\s+)?)endTime:", line)
            if match:
                edits.append((s + k, f"{match.group(1)}endTime: {stamp}", None))
                break
        else:
            body = [k for k, line in enumerate(item) if line.strip()]
            last = body[-1] if body else len(item) - 1
            key_indent = re.match(r"^\s*(?:-\s+)?", item[0]).group(0)
            if item[0].lstrip().startswith("-"):
                key_indent = " " * len(key_indent)
            edits.append((s + last, None, f"{key_indent}endTime: {stamp}"))
        closed += 1
    for index, replace, insert in sorted(edits, key=lambda e: e[0], reverse=True):
        if replace is not None:
            lines[index] = replace
        else:
            lines.insert(index + 1, insert)
    return "\n".join(lines), closed, stale


def close_task_timers(now):
    """Close running TaskNotes timers in the vault. Returns (closed {path: n}, stale [paths])."""
    stamp = now.isoformat(timespec="milliseconds")
    closed, stale = {}, []
    for path in VAULT.rglob("*.md"):
        rel = path.relative_to(VAULT)
        if any(part in collect.SKIP_DIRS for part in rel.parts):
            continue
        try:
            text, nl = _read(path)
        except OSError:
            continue
        if "timeEntries:" not in text:
            continue
        new_text, count, old = _close_running(text, stamp, now)
        if old:
            stale.append(str(rel))
        if count:
            _write(path, new_text, nl)
            closed[str(rel)] = count
    return closed, stale


def run_sync():
    """Run the TaskNotes -> TimeTagger sync with the vault's own Python if it has one. Returns the exit code."""
    venv = VAULT / ".venv" / "Scripts" / "python.exe"
    python = str(venv) if venv.exists() else sys.executable
    try:
        result = subprocess.run([python, str(SYNC_SCRIPT), str(VAULT)], timeout=SYNC_TIMEOUT,
                                capture_output=True, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return -1
    return result.returncode


def _synced_key(key):
    # the sync script's own records: "tnsync" + 12 hex chars
    return str(key).startswith("tnsync") and len(str(key)) == 18


def end_timetagger(now):
    """Set t2 = now on running TimeTagger records that are not synced from TaskNotes. Returns the count."""
    found = collect.timetagger_running_records()
    if found is None:
        raise RuntimeError("TimeTagger can't be reached")
    url, token, running = found
    body = [
        {"key": rec["key"], "t1": rec["t1"], "t2": now.timestamp(), "ds": rec.get("ds", "")}
        for rec in running if not _synced_key(rec.get("key"))
    ]
    if not body:
        return 0
    req = urllib.request.Request(url.rstrip("/") + "/records", data=json.dumps(body).encode("utf-8"),
                                 method="PUT", headers={"authtoken": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20):
        pass
    return len(body)


def end_all(now=None):
    """End everything active. Returns the lines describing what was ended."""
    now = now or datetime.now().astimezone()
    report = []

    title = focus.clear_focus()
    if title:
        report.append(f"focus ended: {title}")

    block = timeblocks.current_block(VAULT, now)
    if block and block["id"]:
        timeblocks.end_block(VAULT, {"path": block["path"], "id": block["id"]}, now)
        report.append(f"time block ended: {block['title']}")

    try:
        closed, stale = close_task_timers(now)
        if closed:
            code = run_sync()
            names = ", ".join(f"{path} ({n})" for path, n in closed.items())
            report.append(f"TaskNotes timer ended: {names}")
            if code != 0:
                report.append(f"  sync to TimeTagger failed (exit {code}); run `invoke timetagger` in the vault")
        for path in stale:
            report.append(f"left running (older than {MAX_RUNNING_HOURS}h): {path}")
    except OSError as exc:
        report.append(f"TaskNotes timers not ended: {exc}")

    try:
        count = end_timetagger(now)
        if count:
            report.append(f"TimeTagger record ended: {count}")
    except (OSError, ValueError, RuntimeError) as exc:
        report.append(f"TimeTagger not ended: {exc}")

    if not report:
        report.append("nothing active to end")
    collect_refresh()
    return report


def collect_refresh():
    try:
        subprocess.run([sys.executable, str(HERE / "collect.py")], timeout=120, check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def main():
    now = datetime.now().astimezone()
    report = end_all(now)
    line = f"{now:%Y-%m-%d %H:%M}  " + "; ".join(report)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
    print("\n".join(report))


if __name__ == "__main__":
    main()
