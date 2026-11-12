@echo off
rem No arguments: open the "Current task" picker without a console window.
rem With arguments: set the focus from the command line, e.g. focus "my new thing"
if "%~1"=="" (
    start "" pythonw "%~dp0..\focus.py"
) else (
    python "%~dp0..\focus.py" %*
)
