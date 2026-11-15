@echo off
rem End everything that is running (focus, time block, TaskNotes timers, TimeTagger). No window.
rem uv supplies pyyaml, so this does not depend on which pythonw is first on PATH.
start "" uvw run --no-project --with pyyaml --gui-script "%~dp0..\end.py"
