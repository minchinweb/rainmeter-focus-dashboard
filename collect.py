"""Collect limits and the active task into state.json for the desktop dashboard.

Sources
    Claude session/week : Anthropic OAuth usage endpoint (token from ~/.claude/.credentials.json).
                          Cached; refreshed at most every CLAUDE_REFRESH_SECONDS.
    Codex               : newest ~/.codex/sessions rollout that contains rate_limits.
    Active task         : TaskNotes notes in the Obsidian vault whose timeEntries has an
                          entry with no endTime (a running timer). Priority from frontmatter.

Output: state.json next to this script (written atomically).
"""

import json
import os
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
OUT = HERE / "state.json"
CREDS = Path.home() / ".claude" / ".credentials.json"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
VAULT = Path(r"PATH/TO/obsidian-vault")
SKIP_DIRS = {".obsidian", ".trash", ".git", ".venv", "__pycache__", "_rendered", "_templates", "_types", "_scripts"}
CLAUDE_REFRESH_SECONDS = 3600
SKIN_DIR = Path(r"PATH/TO/Rainmeter/Skins/DesktopDashboard")
RAINMETER_EXE = Path(r"C:\Program Files\Rainmeter\Rainmeter.exe")

PRIORITY_LABELS = {
    "A": "A today", "B": "B this week", "C": "C this month", "D": "D high",
    "P": "P normal", "N": "N next", "W": "W waiting", "V": "V low",
    "Y": "Y none", "Z": "Z someday",
}


WORD_PRIORITY = {"high": "D", "normal": "P", "low": "V", "none": "Y"}


def priority_info(raw):
    """Map a TaskNotes priority (letter or word) to (letter, label)."""
    raw = str(raw or "").strip()
    code = WORD_PRIORITY.get(raw.lower(), raw[:1].upper())
    return code, PRIORITY_LABELS.get(code, raw or "none")


def load_previous():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def claude_usage(previous):
    """Return the Claude block, reusing the cached value when it is fresh enough."""
    cached = previous.get("claude")
    if cached and time.time() - cached.get("fetched_at", 0) < CLAUDE_REFRESH_SECONDS:
        return cached
    try:
        token = json.loads(CREDS.read_text(encoding="utf-8"))["claudeAiOauth"]["accessToken"]
        req = urllib.request.Request(
            "https://api.anthropic.com/api/oauth/usage",
            headers={"Authorization": f"Bearer {token}", "anthropic-beta": "oauth-2025-04-20"},
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
    except (OSError, KeyError, ValueError, urllib.error.URLError) as exc:
        if cached:
            return {**cached, "error": str(exc)[:120], "stale": True}
        return {"error": str(exc)[:120], "fetched_at": time.time()}
    result = {"fetched_at": time.time()}
    for key in ("five_hour", "seven_day"):
        window = data.get(key) or {}
        result[key] = {"used_percent": window.get("utilization"), "resets_at": window.get("resets_at")}
    return result


def codex_limits():
    """Newest Codex rollout that reports rate_limits; returns None if none found."""
    if not CODEX_SESSIONS.exists():
        return None
    files = sorted(CODEX_SESSIONS.rglob("rollout-*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in files[:15]:
        last = None
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"rate_limits"' in line:
                    last = line
        if last is None:
            continue
        try:
            payload = json.loads(last)
        except ValueError:
            continue
        found = _find_key(payload, "rate_limits")
        if not found:
            continue
        primary = found.get("primary") or {}
        return {
            "used_percent": primary.get("used_percent"),
            "window_minutes": primary.get("window_minutes"),
            "resets_at": primary.get("resets_at"),
            "log_modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes"),
        }
    return None


def _find_key(obj, key):
    """Depth-first search for the first dict stored under `key`."""
    if isinstance(obj, dict):
        if isinstance(obj.get(key), dict):
            return obj[key]
        for value in obj.values():
            hit = _find_key(value, key)
            if hit:
                return hit
    elif isinstance(obj, list):
        for value in obj:
            hit = _find_key(value, key)
            if hit:
                return hit
    return None


def frontmatter(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None
    end = text.find("\n---", 3)
    if end == -1:
        return None
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def active_task():
    """Return the running TaskNotes timer (entry with no endTime), newest start wins."""
    best = None
    for path in VAULT.rglob("*.md"):
        if any(part in SKIP_DIRS for part in path.relative_to(VAULT).parts):
            continue
        try:
            if "timeEntries" not in path.read_text(encoding="utf-8", errors="replace"):
                continue
        except OSError:
            continue
        meta = frontmatter(path)
        if not meta or meta.get("task_status") in ("30-done", "50-cancelled", "60-duplicate"):
            continue
        for entry in meta.get("timeEntries") or []:
            if not isinstance(entry, dict) or entry.get("endTime"):
                continue
            start = str(entry.get("startTime", ""))
            if best is None or start > best["started"]:
                priority, label = priority_info(meta.get("priority"))
                best = {
                    "title": str(meta.get("title") or path.stem),
                    "started": start,
                    "priority": priority,
                    "priority_label": label,
                    "status": meta.get("task_status"),
                    "path": str(path.relative_to(VAULT)),
                    "source": "TaskNotes",
                }
    return best


TIMETAGGER_CONFIG = Path(os.environ.get("TIMETAGGER_CONFIG", "") or Path(os.environ.get("LOCALAPPDATA", "")) / "timetagger_cli" / "config.txt")
MAX_RUNNING_HOURS = 12  # same abandonment rule as _scripts/tasknotes_to_timetagger.py


def timetagger_settings():
    """URL and token from TIMETAGGER_URL/TIMETAGGER_TOKEN, else the timetagger CLI config."""
    url, token = os.environ.get("TIMETAGGER_URL"), os.environ.get("TIMETAGGER_TOKEN")
    if url and token:
        return url, token
    with TIMETAGGER_CONFIG.open("rb") as fh:
        cfg = tomllib.load(fh)
    return url or cfg["api_url"], token or cfg["api_token"]


def timetagger_running():
    """Running TimeTagger record (t1 == t2, not hidden, not abandoned), newest start wins."""
    try:
        url, token = timetagger_settings()
        now = time.time()
        req = urllib.request.Request(
            url.rstrip("/") + f"/records?timerange=0-{int(now + 3600)}",
            headers={"authtoken": token},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            records = json.load(resp).get("records", [])
    except (OSError, KeyError, ValueError, urllib.error.URLError):
        return None
    running = [
        r for r in records
        if r.get("t1") == r.get("t2")
        and not str(r.get("ds", "")).startswith("HIDDEN")
        and now - float(r.get("t1", 0)) <= MAX_RUNNING_HOURS * 3600
    ]
    if not running:
        return None
    rec = max(running, key=lambda r: r["t1"])
    text = str(rec.get("ds", ""))
    # ds is "<title>[ – <description>] #tag ..."; tags are dropped for the skin
    title = text.split(" – ")[0]
    title = " ".join(word for word in title.split() if not word.startswith("#")) or "(untitled)"
    started = datetime.fromtimestamp(float(rec["t1"])).isoformat(timespec="minutes")
    return {
        "title": title,
        "started": started,
        "priority": "",
        "priority_label": "-",
        "status": "-",
        "path": "TimeTagger",
        "source": "TimeTagger",
    }


FOCUS = HERE / "focus.json"


def focus_task():
    """Task chosen in focus.py (no timer needed); it overrides the timers until cleared."""
    try:
        data = json.loads(FOCUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not data.get("title"):
        return None
    return {
        "title": data["title"],
        "started": data.get("set_at", ""),
        "priority": data.get("priority", ""),
        "priority_label": data.get("priority_label", "-"),
        "status": "focus (not timed)",
        "path": data.get("path", ""),
        "source": "Focus",
    }


def write_atomic(data):
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, OUT)


def rainmeter_text(value):
    """Strip characters Rainmeter treats as syntax in variable values."""
    return "".join(ch for ch in str(value) if ch not in "#[];\"=") or "-"


def write_skin_variables(state):
    """Write the task/priority values for the Rainmeter skin and ask Rainmeter to redraw it."""
    task = state.get("task") or {}
    lines = [
        "[Variables]",
        f"TaskTitle={rainmeter_text(task.get('title', 'No task running'))}",
        f"TaskPriority={rainmeter_text(task.get('priority_label', '-'))}",
        f"TaskStatus={rainmeter_text(task.get('status', '-'))}",
        f"TaskStarted={rainmeter_text(task.get('started', '-')[:16].replace('T', ' ') or '-')}",
        f"TaskSource={rainmeter_text(task.get('source', '-'))}",
        f"Updated={rainmeter_text(datetime.now().strftime('%H:%M'))}",
    ]
    resources = SKIN_DIR / "@Resources"
    resources.mkdir(parents=True, exist_ok=True)
    (resources / "state.inc").write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        subprocess.run([RAINMETER_EXE, "!RefreshGroup", "DesktopDashboard"], timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def main():
    previous = load_previous()
    state = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "claude": claude_usage(previous),
        "codex": codex_limits(),
        "task": focus_task() or active_task() or timetagger_running(),
    }
    write_atomic(state)
    write_skin_variables(state)
    if "--print" in sys.argv:
        print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
