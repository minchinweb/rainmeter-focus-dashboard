Rainmeter Focus Dashboard
=========================

A small Windows desktop dashboard: Rainmeter skins and a few Python scripts
that show what you are working on, how much of your coding-agent limits you
have used, and the time.

Skins
-----

The skins live in ``skin/DesktopDashboard/``. Each one is its own Rainmeter
config, all in the ``DesktopDashboard`` group.

**Current Task** (``TaskPriority``)
    The running or focused task, its priority and start time, with an *End*
    button that stops whatever is running (see ``end.py``).

**Agent Limits** (``AgentUsage``)
    Claude session (5 h) and week (7 d) usage, Codex / ChatGPT usage and reset
    times, with a 7-day bar marking each day, and Antigravity quota buckets.
    While it is loaded, it re-runs ``collect.py`` (through ``uvw``) whenever
    the data is more than 5 minutes old, so nothing else needs to be running.

**Classic Clock** (``ClassicClock``)
    A 210 x 210 px analog clock, sized to sit beside the illustro skins: brass
    rim, cream dial, Roman numerals, spade hands and a red second hand.

**Now Playing** (``NowPlaying``)
    Track, artist, album, position and progress from the media player, at the
    360 px Current Task width with the same dark panel. Based on Enigma Music
    and reads its button icons from the Enigma skin folder, so Enigma must be
    installed. The player is set by ``MusicPlayer`` in the skin's variables
    (``CAD`` for MusicBee).

**VU Meter** (``VUMeter``)
    A 210 x 160 px analog VU meter audio visualizer, sized to sit beside the
    Classic Clock and illustro skins. Reacts to system audio via Rainmeter's
    AudioLevel plugin (both stereo channels averaged). Scroll the mouse wheel
    over the meter to adjust sensitivity on the fly; middle-click resets to default.

Current Task and Agent Limits read ``@Resources/state.inc``, which
``collect.py`` writes. Classic Clock and VU Meter need nothing but Rainmeter.

Scripts
-------

``collect.py``
    Gathers agent limits and the current task into ``state.json`` and the
    skins' ``state.inc``, then refreshes the ``DesktopDashboard`` group. The
    task comes from, in order: the focus set with ``focus.py``, a running
    TaskNotes timer in the Obsidian vault, a running TimeTagger record, or the
    time block covering now in today's daily note. Its dependencies are
    declared inline, so ``uv run collect.py`` works on its own.

``agents_window.py``
    The agent limits as an ordinary window (so it stays on the virtual desktop
    you put it on). Re-runs ``collect.py`` every 5 minutes.

``focus.py``
    A picker to set the current task without starting a timer. Each focus also
    opens a TaskNotes time block in today's daily note. ``bin/focus.cmd`` runs
    it without a console window, or sets the focus from the command line:
    ``focus "my new thing"``.

``end.py``
    Ends whatever is running: the focus, the current time block, TaskNotes
    timers and TimeTagger records. Run by the *End* button through
    ``bin/end.cmd``, and logs to ``end.log``.

``timeblocks.py``
    Reads and edits TaskNotes time blocks in the daily note (used by the
    scripts above).

``make_classic_clock.py``
    Generates the Classic Clock skin (see below).

``make_vu_meter.py``
    Generates the VU Meter skin and resamples images to 210 px width from
    the original adni18 skin (see below).

Setup
-----

1. Install `Rainmeter <https://www.rainmeter.net/>`_ and
   `uv <https://docs.astral.sh/uv/>`_ (the Agent Limits skin runs
   ``collect.py`` with ``uvw``, which needs to be on ``PATH``). The other
   scripts need Python 3.11 or newer with PyYAML.
2. Link the skin folder into Rainmeter's ``Skins`` folder, so the skins show
   up as ``DesktopDashboard\...``::

       mklink /J "%USERPROFILE%\Documents\Rainmeter\Skins\DesktopDashboard" "<repo>\skin\DesktopDashboard"

3. Copy ``config.example.json`` to ``config.json`` and set your paths:

   - ``vault``: your Obsidian vault (for TaskNotes).
   - ``skin_dir``: the ``DesktopDashboard`` folder in Rainmeter's ``Skins``.
   - ``rainmeter_exe``: optional; defaults to
     ``C:\Program Files\Rainmeter\Rainmeter.exe``.

   ``config.json`` is git-ignored.

4. Load the skins from Rainmeter's *Manage* window. Agent Limits runs
   ``collect.py`` within a minute of loading and keeps the data fresh.

TimeTagger is optional: ``collect.py`` uses ``TIMETAGGER_URL`` and
``TIMETAGGER_TOKEN`` if set, otherwise the ``timetagger_cli`` config.

Changing the clock
------------------

``ClassicClock.ini`` and the numeral images in ``ClassicClock/@Resources`` are
generated. Edit ``make_classic_clock.py`` (colours, sizes and the hand shapes
are constants and arguments near the top and in ``hands()``), then::

    uv run make_classic_clock.py

or run it with any Python that has Pillow. The numerals use Times New Roman
Bold from ``C:\Windows\Fonts``. Reload the skin afterwards.

Rainmeter can't rotate text, so each numeral is a Pillow-rendered image. The
hands are stacks of 1 px ``ROUNDLINE`` meters whose widths follow the hand's
outline. Note that ``LineLength`` is the radius where a line *ends*, not its
length.

Changing the VU meter
---------------------

``VUMeter.ini`` and the scaled images in ``VUMeter/@Resources/Images`` are
generated from ``VU METER by adni18``. Edit ``make_vu_meter.py`` (dimensions,
default gain, or rotation angles), then::

    python make_vu_meter.py

Reload the skin afterwards.


License
-------

MIT. See ``LICENSE``.
