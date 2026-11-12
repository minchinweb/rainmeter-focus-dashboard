"""Pick the current task without starting a timer.

Search open TaskNotes tasks (or type free text), press Enter or double-click to set the
focus. The focus is saved to focus.json, which collect.py reads first. Clear removes it.
"""

import json
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path

import collect

HERE = Path(__file__).resolve().parent
FOCUS = HERE / "focus.json"
BG = "#101010"
FG = "#ebebeb"
MUTED = "#9a9a9a"
ENTRY_BG = "#1e1e1e"


def open_tasks():
    """(title, priority letter, label, vault-relative path) for every open TaskNotes task."""
    rows = []
    for path in collect.VAULT.rglob("*.md"):
        if any(part in collect.SKIP_DIRS for part in path.relative_to(collect.VAULT).parts):
            continue
        try:
            if "tasknote: true" not in path.read_text(encoding="utf-8", errors="replace"):
                continue
        except OSError:
            continue
        meta = collect.frontmatter(path)
        if not meta or meta.get("task_status") in ("30-done", "50-cancelled", "60-duplicate", "40-someday"):
            continue
        code, label = collect.priority_info(meta.get("priority"))
        if code == "Z":  # "Z someday" priority counts as not open
            continue
        rows.append((str(meta.get("title") or path.stem), code, label, str(path.relative_to(collect.VAULT))))
    # highest priority first (A, B, C, D, P, N, ...), then title
    order = "ABCDNPWVYZ"
    rows.sort(key=lambda r: (order.find(r[1]) if r[1] in order else len(order), r[0].lower()))
    return rows


def write_focus(data):
    tmp = FOCUS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FOCUS)
    refresh_skin()


def refresh_skin():
    """Run the collector so the Rainmeter skin shows the new focus right away."""
    try:
        subprocess.run([sys.executable, str(HERE / "collect.py")], timeout=120, check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        pass


def current_focus_text():
    try:
        data = json.loads(FOCUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "Current focus: none"
    if not data.get("title"):
        return "Current focus: none"
    return f"Current focus: [{data.get('priority') or '-'}] {data['title']}"


TASKNOTES_DATA = collect.VAULT / ".obsidian" / "plugins" / "tasknotes" / "data.json"


def tasknotes_settings():
    """Folder, filename, defaults and field names from the TaskNotes plugin config.

    Falls back to the values this vault currently uses if the config can't be read.
    """
    defaults = {
        "folder": "GTD/tasks/{year}/{month}",
        "filename": "task-{year}{month}{day}{hour}{minute}",
        "priority": "P",
        "status": "10-open",
        "fields": {"title": "title", "status": "task_status", "priority": "priority"},
    }
    try:
        data = json.loads(TASKNOTES_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return defaults
    fields = dict(defaults["fields"])
    fields.update({k: v for k, v in (data.get("fieldMapping") or {}).items() if k in fields})
    return {
        "folder": (data.get("tasksFolder") or defaults["folder"]).replace("{{", "{").replace("}}", "}"),
        "filename": (data.get("customFilenameTemplate") if data.get("taskFilenameFormat") == "custom"
                     else None) or defaults["filename"],
        "priority": data.get("defaultTaskPriority") or defaults["priority"],
        "status": data.get("defaultTaskStatus") or defaults["status"],
        "fields": fields,
    }


def create_task(title):
    """Create a TaskNotes task note using the plugin's folder, filename and field settings."""
    cfg = tasknotes_settings()
    now = datetime.now().astimezone()
    parts = {
        "year": f"{now:%Y}", "month": f"{now:%m}", "day": f"{now:%d}",
        "hour": f"{now:%H}", "minute": f"{now:%M}", "second": f"{now:%S}",
    }
    folder = collect.VAULT / cfg["folder"].format(**parts)
    folder.mkdir(parents=True, exist_ok=True)
    stem = cfg["filename"].format(**parts)
    path = folder / f"{stem}.md"
    counter = 1
    while path.exists():  # two tasks in the same minute
        path = folder / f"{stem}{counter:02d}.md"
        counter += 1
    stamp_iso = now.strftime("%Y-%m-%dT%H:%M:%S%z")
    f = cfg["fields"]
    text = (
        "---\n"
        f"{f['title']}: {json.dumps(title, ensure_ascii=False)}\n"
        f"{f['priority']}: {cfg['priority']}\n"
        f"date: {stamp_iso}\n"
        f"modified: {stamp_iso}\n"
        "category: tasks\n"
        "tags:\n"
        "  - task\n"
        "contexts:\n"
        f"{f['status']}: {cfg['status']}\n"
        "tasknote: true\n"
        "---\n"
    )
    path.write_text(text, encoding="utf-8")
    return path


class App:
    def __init__(self, root):
        self.root = root
        self.tasks = open_tasks()
        self.visible = []
        root.title("Current task")
        root.configure(bg=BG)
        root.geometry("460x420")

        self.current = tk.Label(root, text=current_focus_text(), bg=BG, fg=FG,
                                font=("Segoe UI", 10, "bold"), anchor="w", wraplength=430, justify="left")
        self.current.pack(fill="x", padx=12, pady=(10, 4))
        tk.Label(root, text="Search tasks, or type a free-text task and press Enter",
                 bg=BG, fg=MUTED, font=("Segoe UI", 8), anchor="w").pack(fill="x", padx=12, pady=(10, 2))
        self.query = tk.Entry(root, bg=ENTRY_BG, fg=FG, insertbackground=FG, relief="flat",
                              font=("Segoe UI", 11))
        self.query.pack(fill="x", padx=12, ipady=4)
        self.query.bind("<KeyRelease>", lambda e: self.filter())
        self.query.bind("<Return>", lambda e: self.choose())
        self.query.bind("<Down>", lambda e: self.listbox.focus_set())

        self.listbox = tk.Listbox(root, bg=ENTRY_BG, fg=FG, selectbackground="#d97757",
                                  selectforeground="#101010", relief="flat", borderwidth=0,
                                  font=("Segoe UI", 10), activestyle="none")
        self.listbox.pack(fill="both", expand=True, padx=12, pady=8)
        self.listbox.bind("<Double-Button-1>", lambda e: self.choose())
        self.listbox.bind("<Return>", lambda e: self.choose())

        buttons = tk.Frame(root, bg=BG)
        buttons.pack(fill="x", padx=12, pady=(0, 10))
        tk.Button(buttons, text="Set focus", command=self.choose, bg="#2a2a2a", fg=FG,
                  relief="flat", padx=10).pack(side="left")
        tk.Button(buttons, text="Create task from text", command=self.create_from_text, bg="#2a2a2a",
                  fg=FG, relief="flat", padx=10).pack(side="left", padx=8)
        tk.Button(buttons, text="Clear focus", command=self.clear, bg="#2a2a2a", fg=FG,
                  relief="flat", padx=10).pack(side="left")
        self.status = tk.Label(buttons, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.status.pack(side="right")

        self.filter()
        self.query.focus_set()

    def filter(self):
        text = self.query.get().strip().lower()
        self.visible = [t for t in self.tasks if not text or text in t[0].lower() or text in t[3].lower()][:300]
        self.listbox.delete(0, "end")
        for title, code, _label, _path in self.visible:
            self.listbox.insert("end", f"[{code or '-'}]  {title}")
        self.status.config(text=f"{len(self.tasks)} open tasks")

    def choose(self):
        selection = self.listbox.curselection()
        if selection:
            title, code, label, path = self.visible[selection[0]]
            data = {"title": title, "priority": code, "priority_label": label, "path": path}
        else:
            text = self.query.get().strip()
            if not text:
                return
            data = {"title": text, "priority": "", "priority_label": "-", "path": "free text"}
        data["set_at"] = datetime.now().isoformat(timespec="minutes")
        write_focus(data)
        self.current.config(text=current_focus_text())
        self.query.delete(0, "end")
        self.filter()
        self.status.config(text=f"Focus set: {data['title'][:40]}")

    def create_from_text(self):
        """Create a vault task from the typed text, then focus on it."""
        text = self.query.get().strip()
        if not text:
            self.status.config(text="Type a task first")
            return
        path = create_task(text)
        code = tasknotes_settings()["priority"]
        data = {"title": text, "priority": code, "priority_label": collect.priority_info(code)[1],
                "path": str(path.relative_to(collect.VAULT)),
                "set_at": datetime.now().isoformat(timespec="minutes")}
        write_focus(data)
        self.tasks = open_tasks()
        self.current.config(text=current_focus_text())
        self.query.delete(0, "end")
        self.filter()
        self.status.config(text=f"Created {path.name}")

    def clear(self):
        FOCUS.unlink(missing_ok=True)
        refresh_skin()
        self.current.config(text=current_focus_text())
        self.status.config(text="Focus cleared")


def cli(args):
    """focus "text" sets a free-text focus; focus --clear removes it. No window."""
    if args == ["--clear"]:
        FOCUS.unlink(missing_ok=True)
        refresh_skin()
        print("Focus cleared")
        return
    text = " ".join(args).strip()
    if not text:
        print('usage: focus "task text"   or   focus --clear')
        return
    write_focus({"title": text, "priority": "", "priority_label": "-", "path": "free text",
                 "set_at": datetime.now().isoformat(timespec="minutes")})
    print(f"Focus set: {text}")


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    if sys.argv[1:]:
        cli(sys.argv[1:])
    else:
        main()
