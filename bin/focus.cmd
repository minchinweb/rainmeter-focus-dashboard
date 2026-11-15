@echo off
rem No arguments: open the "Current task" picker without a console window.
rem With arguments: set the focus from the command line, e.g. focus "my new thing"
rem uv supplies pyyaml, so this does not depend on which python is first on PATH.
if "%~1"=="" (
    start "" uvw run --no-project --with pyyaml --gui-script "%~dp0..\focus.py"
) else (
    uv run --no-project --with pyyaml "%~dp0..\focus.py" %*
)
