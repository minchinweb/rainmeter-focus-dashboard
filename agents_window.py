"""Coding-agent limits window (Claude session/week, Codex).

A normal window, so Windows keeps it on the virtual desktop where you put it.
Re-runs collect.py every REFRESH_MINUTES and redraws from state.json.
"""

import json
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / "state.json"
COLLECT = HERE / "collect.py"
REFRESH_MINUTES = 5
BG = "#101010"
FG = "#ebebeb"
MUTED = "#9a9a9a"
BAR_BG = "#2a2a2a"
BAR_OK = "#d97757"
BAR_WARN = "#e0a030"
BAR_HOT = "#e04040"


def parse_time(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def until(value):
    when = parse_time(value)
    if not when:
        return "-"
    if when.tzinfo is None:
        when = when.astimezone()
    delta = when - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "resetting"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"resets in {days}d {hours}h"
    if hours:
        return f"resets in {hours}h {mins}m"
    return f"resets in {mins}m"


def load_state():
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Bar(tk.Canvas):
    def __init__(self, master, width=300, height=12):
        super().__init__(master, width=width, height=height, bg=BG, highlightthickness=0)
        self.width = width

    def set(self, percent):
        self.delete("all")
        self.create_rectangle(0, 0, self.width, 12, fill=BAR_BG, outline="")
        pct = max(0.0, min(float(percent or 0), 100.0))
        color = BAR_OK if pct < 75 else BAR_WARN if pct < 90 else BAR_HOT
        self.create_rectangle(0, 0, self.width * pct / 100, 12, fill=color, outline="")


class App:
    def __init__(self, root):
        self.root = root
        root.title("Coding agents")
        root.configure(bg=BG)
        root.resizable(False, False)
        self.frame = tk.Frame(root, bg=BG, padx=14, pady=10)
        self.frame.pack()
        self.refresh_after = None
        self.build_rows()
        self.redraw()
        self.schedule_refresh(0)

    def label(self, text, color=FG, size=9, bold=False):
        font = ("Segoe UI", size, "bold" if bold else "normal")
        lab = tk.Label(self.frame, text=text, bg=BG, fg=color, font=font, anchor="w")
        lab.pack(fill="x", anchor="w")
        return lab

    def build_rows(self):
        for child in self.frame.winfo_children():
            child.destroy()
        self.label("CLAUDE", MUTED, 8, True)
        self.claude_session = self.label("", FG, 10)
        self.bar_session = Bar(self.frame)
        self.bar_session.pack(anchor="w", pady=(2, 2))
        self.claude_session_reset = self.label("", MUTED, 8)
        self.claude_week = self.label("", FG, 10)
        self.bar_week = Bar(self.frame)
        self.bar_week.pack(anchor="w", pady=(2, 2))
        self.claude_week_reset = self.label("", MUTED, 8)
        self.label("", BG, 4)
        self.label("CODEX / CHATGPT", MUTED, 8, True)
        self.codex_line = self.label("", FG, 10)
        self.bar_codex = Bar(self.frame)
        self.bar_codex.pack(anchor="w", pady=(2, 2))
        self.codex_reset = self.label("", MUTED, 8)
        self.label("", BG, 4)
        self.footer = self.label("", MUTED, 8)

    def redraw(self):
        state = load_state()
        claude = state.get("claude") or {}
        session = claude.get("five_hour") or {}
        week = claude.get("seven_day") or {}
        codex = state.get("codex") or {}

        s_pct = session.get("used_percent")
        self.claude_session.config(text=f"Session (5h): {_pct(s_pct)}")
        self.bar_session.set(s_pct)
        self.claude_session_reset.config(text=until(session.get("resets_at")))

        w_pct = week.get("used_percent")
        self.claude_week.config(text=f"Week (7d): {_pct(w_pct)}")
        self.bar_week.set(w_pct)
        self.claude_week_reset.config(text=until(week.get("resets_at")))

        c_pct = codex.get("used_percent")
        self.codex_line.config(text=f"Usage window: {_pct(c_pct)}")
        self.bar_codex.set(c_pct)
        log_age = codex.get("log_modified")
        self.codex_reset.config(
            text=f"{until(codex.get('resets_at'))}  ·  from log {log_age}" if codex else "no Codex data"
        )

        notes = []
        if claude.get("stale"):
            notes.append("Claude data is stale")
        if claude.get("error") and not claude.get("five_hour"):
            notes.append(f"Claude: {claude['error']}")
        updated = state.get("updated", "never")
        self.footer.config(text=("  ·  ".join(notes + [f"updated {updated[:16].replace('T', ' ')} UTC"])))

    def schedule_refresh(self, delay_ms):
        if self.refresh_after:
            self.root.after_cancel(self.refresh_after)
        self.refresh_after = self.root.after(delay_ms, self.start_collect)

    def start_collect(self):
        threading.Thread(target=self.run_collect, daemon=True).start()
        self.schedule_refresh(REFRESH_MINUTES * 60 * 1000)

    def run_collect(self):
        try:
            subprocess.run([sys.executable, str(COLLECT)], timeout=120, check=False,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        except (OSError, subprocess.SubprocessError):
            pass
        self.root.after(0, self.redraw)


def _pct(value):
    return "-" if value is None else f"{float(value):.0f}%"


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
