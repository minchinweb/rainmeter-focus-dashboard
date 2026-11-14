# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Collect limits and the active task into state.json for the desktop dashboard.

Sources
    Claude session/week : Anthropic OAuth usage endpoint (token from ~/.claude/.credentials.json).
                          Cached; refreshed at most every CLAUDE_REFRESH_SECONDS.
    Codex               : newest ~/.codex/sessions rollout that contains rate_limits.
    Antigravity         : antigravity.json, written by ~/.gemini/config/statusline.py from the
                          Antigravity TUI's status line feed (only while the TUI runs).
    Active task         : TaskNotes notes in the Obsidian vault whose timeEntries has an
                          entry with no endTime (a running timer). Priority from frontmatter.
    Task priority order : focus.json, then active TaskNotes timer, then TimeTagger, then the
                          time block covering now in today's daily note (see timeblocks.py).

Output: state.json next to this script (written atomically).
"""

import json
import os
import shutil
import subprocess
import sys
import time
import tomllib
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

import timeblocks

HERE = Path(__file__).resolve().parent
OUT = HERE / "state.json"
CREDS = Path.home() / ".claude" / ".credentials.json"
CODEX_SESSIONS = Path.home() / ".codex" / "sessions"
CONFIG = HERE / "config.json"  # machine-specific paths; see config.example.json
SKIP_DIRS = {".obsidian", ".trash", ".git", ".venv", "__pycache__", "_rendered", "_templates", "_types", "_scripts"}
CLAUDE_REFRESH_SECONDS = 3600


def load_config():
    """Read config.json (gitignored). Only the vault and skin folder are required."""
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit(f"Missing {CONFIG}: copy config.example.json to config.json and set your paths.")
    missing = [key for key in ("vault", "skin_dir") if not data.get(key)]
    if missing:
        sys.exit(f"{CONFIG} is missing: {', '.join(missing)}")
    return data


_CONFIG = load_config()
VAULT = Path(_CONFIG["vault"])
SKIN_DIR = Path(_CONFIG["skin_dir"])
RAINMETER_EXE = Path(_CONFIG.get("rainmeter_exe") or r"C:\Program Files\Rainmeter\Rainmeter.exe")

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


ANTIGRAVITY_FILE = HERE / "antigravity.json"


def antigravity_limits():
    """Quota buckets last written by the Antigravity status line, or None if there are none yet."""
    try:
        data = json.loads(ANTIGRAVITY_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    buckets = data.get("quota") if isinstance(data, dict) else None
    if not isinstance(buckets, dict) or not buckets:
        return None
    return {"updated_at": data.get("updated_at"), "model": data.get("model", ""), "quota": buckets}


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


def timetagger_running_records():
    """(api url, token, running records newest first), or None if the server can't be read.

    Running = t1 == t2, not hidden, not abandoned (running longer than MAX_RUNNING_HOURS).
    """
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
    running.sort(key=lambda r: float(r["t1"]), reverse=True)
    return url, token, running


def timetagger_running():
    """Running TimeTagger record (see timetagger_running_records), newest start wins."""
    found = timetagger_running_records()
    if not found or not found[2]:
        return None
    rec = found[2][0]
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


def time_block_now():
    """Fallback when no focus, timer or TimeTagger record is running: the daily-note time block covering now.

    Its priority is the default; a block without one uses TaskNotes' defaultTaskPriority.
    """
    block = timeblocks.current_block(VAULT, datetime.now())
    if not block:
        return None
    default = timeblocks.plugin_setting(VAULT, "defaultTaskPriority", "P")
    priority, label = priority_info(block["priority"] or default)
    return {
        "title": block["title"],
        "started": f"{datetime.now():%Y-%m-%d}T{block['start']}",
        "priority": priority,
        "priority_label": label,
        "status": "time block",
        "path": block["path"],
        "source": "Time block",
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


WEEK_BAR_PX = 332  # width of the 7-day bar in AgentUsage.ini


def reset_label(value, fmt="%a %d %b %H:%M"):
    """Local time for an ISO timestamp (Claude) or epoch seconds (Codex), e.g. 'Tue 17 Nov 05:00'."""
    if value in (None, ""):
        return "-"
    try:
        when = datetime.fromtimestamp(value) if isinstance(value, (int, float)) else datetime.fromisoformat(str(value))
    except ValueError:
        return "-"
    if when.tzinfo is not None:
        when = when.astimezone()
    return when.strftime(fmt)


def percent_text(value):
    """Whole-number percent without the sign; the skin adds the % sign."""
    try:
        return str(round(float(value)))
    except (TypeError, ValueError):
        return "-"


def week_bar(seven):
    """Pixel geometry for the 7-day bar: fill width and the block for the day we are in.

    The 7-day window ends at seven.resets_at, so it started seven days earlier.
    """
    try:
        used = min(max(float(seven.get("used_percent") or 0), 0.0), 100.0)
    except (TypeError, ValueError):
        used = 0.0
    day_w = WEEK_BAR_PX / 7
    geometry = {"fill_px": round(WEEK_BAR_PX * used / 100), "day": None, "day_x": 0, "day_w": 0}
    try:
        end = datetime.fromisoformat(str(seven["resets_at"]))
    except (KeyError, TypeError, ValueError):
        return geometry
    elapsed = (datetime.now(UTC) - (end - timedelta(days=7))).total_seconds()
    if 0 <= elapsed < 7 * 86400:
        day = int(elapsed // 86400)
        geometry.update(day=day + 1, day_x=round(day * day_w), day_w=round(day_w))
    return geometry


def antigravity_text(ag):
    """One line for the skin: each quota bucket as 'name used% (day HH:MM it resets)'."""
    buckets = ag.get("quota") or {}
    if not buckets:
        return "no data yet (open the Antigravity TUI)"
    parts = []
    for name, bucket in buckets.items():
        label = str(name).replace("-weekly", "").replace("-daily", "")
        reset = reset_label(bucket.get("resets_at"), "%a %H:%M")
        parts.append(f"{label} {percent_text(bucket.get('used_percent'))}% ({reset})")
    return " | ".join(parts)


def agent_variables(state):
    """Skin variables for the Claude, Codex and Antigravity limits (AgentUsage.ini)."""
    claude = state.get("claude") or {}
    session = claude.get("five_hour") or {}
    week = claude.get("seven_day") or {}
    codex = state.get("codex") or {}
    antigravity = state.get("antigravity") or {}
    bar = week_bar(week)
    return [
        f"ClaudeSessionPct={percent_text(session.get('used_percent'))}",
        f"ClaudeSessionReset={rainmeter_text(reset_label(session.get('resets_at')))}",
        f"ClaudeWeekPct={percent_text(week.get('used_percent'))}",
        f"ClaudeWeekReset={rainmeter_text(reset_label(week.get('resets_at')))}",
        f"ClaudeWeekDay={bar['day'] or '-'}",
        f"WeekFillPx={bar['fill_px']}",
        f"WeekDayX={bar['day_x']}",
        f"WeekDayW={bar['day_w']}",
        f"CodexPct={percent_text(codex.get('used_percent'))}",
        f"CodexReset={rainmeter_text(reset_label(codex.get('resets_at')))}",
        f"AntigravityText={rainmeter_text(antigravity_text(antigravity))}",
    ]


def write_skin_variables(state):
    """Write the task and agent-limit values for the Rainmeter skins and ask Rainmeter to redraw them."""
    task = state.get("task") or {}
    lines = [
        "[Variables]",
        f"TaskTitle={rainmeter_text(task.get('title', 'No task running'))}",
        f"TaskPriority={rainmeter_text(task.get('priority_label', '-'))}",
        f"TaskStatus={rainmeter_text(task.get('status', '-'))}",
        f"TaskStarted={rainmeter_text(task.get('started', '-')[:16].replace('T', ' ') or '-')}",
        f"TaskSource={rainmeter_text(task.get('source', '-'))}",
        f"Updated={rainmeter_text(datetime.now().strftime('%H:%M'))}",
        # UTC seconds since 1601, the scale of a Rainmeter Time measure with TimeZone=0,
        # so the AgentUsage skin can tell how old this file is.
        f"UpdatedStamp={int((datetime.now(UTC) - datetime(1601, 1, 1, tzinfo=UTC)).total_seconds())}",
        f"EndCommand={rainmeter_text(HERE / 'bin' / 'end.cmd')}",
        # How the AgentUsage skin re-runs this script (uvw: uv without a console window).
        f"CollectProgram={rainmeter_text(shutil.which('uvw') or 'uvw')}",
        f"CollectScript={rainmeter_text(Path(__file__).resolve())}",
        *agent_variables(state),
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
        "updated": datetime.now(UTC).isoformat(timespec="seconds"),
        "claude": claude_usage(previous),
        "codex": codex_limits(),
        "antigravity": antigravity_limits(),
        "task": focus_task() or active_task() or timetagger_running() or time_block_now(),
    }
    write_atomic(state)
    write_skin_variables(state)
    if "--print" in sys.argv:
        print(json.dumps(state, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
