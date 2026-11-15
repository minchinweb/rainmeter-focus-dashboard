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

    .. image:: docs/images/current-task.png
       :alt: The Current Task panel

**Agent Limits** (``AgentUsage``)
    Claude session (5 h) and week (7 d) usage, Codex / ChatGPT usage and reset
    times, with a 7-day bar marking each day, and Antigravity quota buckets.
    While it is loaded, it re-runs ``collect.py`` (through ``uvw``) whenever
    the data is more than 5 minutes old, so nothing else needs to be running.

    .. image:: docs/images/agent-limits.png
       :alt: The Agent Limits panel

**Classic Clock** (``ClassicClock``)
    A 210 x 210 px analog clock, sized to sit beside the illustro skins: brass
    rim, cream dial, Roman numerals, spade hands and a red second hand. Lit
    from the upper left, with a bevelled rim, soft shadows under the clock and
    each hand, and a faint glass reflection.

    .. image:: docs/images/classic-clock.png
       :alt: The Classic Clock

**Classic Clock (wide)** (``ClassicClockWide``)
    The same clock scaled up to 408 x 408 px, the width of the VU meter,
    recorder and text skins. ``VARIANTS`` in ``make_classic_clock.py`` sets the
    sizes; both skins are written by the one script.

    .. image:: docs/images/classic-clock-wide.png
       :alt: The wide Classic Clock

**Now Playing** (``NowPlaying``)
    Track, artist, album, position and progress from the media player, at the
    408 px Current Task width with the same dark panel. Based on Enigma Music
    and reads its button icons from the Enigma skin folder, so Enigma must be
    installed. The player is set by ``MusicPlayer`` in the skin's variables
    (``CAD`` for MusicBee).

**VU Meter** (``VUMeter``)
    A 210 x 160 px analog VU meter audio visualizer, sized to sit beside the
    Classic Clock and illustro skins. Reacts to system audio via Rainmeter's
    AudioLevel plugin (both stereo channels averaged). Scroll the mouse wheel
    over the meter to adjust sensitivity on the fly; middle-click resets to default.
    Styled to match the clock: a beaded brass frame under the same light, and
    a cream face seen through a window in a brass faceplate, backlit from
    behind the plate, which also hides the pivot. The needle has momentum: a
    damped spring tuned to the VU standard (99% of a step in 0.3 s, about 1.5%
    overshoot), set by ``NeedleOmega`` and ``NeedleDamping`` in the skin. The scale is a true VU scale (needle
    travel follows voltage, so the marks bunch up at the low end) numbered
    -20 to +3 VU, red above 0. 0 VU is set to -10 dBFS. Labels
    are set in B612, which should be installed.

    .. image:: docs/images/vu-meter.png
       :alt: The output VU meter

**Mic VU Meter** (``VUMeterMic``)
    The same meter for the microphone input, with 0 VU at -18 dBFS.

    .. image:: docs/images/vu-meter-mic.png
       :alt: The microphone VU meter

**Dual VU Meter** (``VUMeterDual``)
    The output and microphone meters on one 408 x 160 px plate: each keeps
    its own 184 px window, so the dials are the single meters' size, with one
    shared frame between them. Trim is scrolled per meter. It reads the same
    audio as the two single skins, so run it instead of them, not as well. The
    recorders are the same width.

    .. image:: docs/images/vu-meter-dual.png
       :alt: The Dual VU Meter

**System Recorder** (``SystemRecorder``)
    A 408 x 160 px chart recorder, at the width of the Dual VU Meter. Four
    pens trace CPU, RAM, network down and network up on scrolling graph
    paper. The frame is the VU meters' (``make_system_recorder.py`` reuses
    their code), with the paper in the window. The pens and readouts update
    eight times a second; the paper takes one sample a second and moves
    1 px/s, so it holds about 5 minutes. The pens sit a little in from the
    window's edge and are damped springs, as on the VU meters, so they glide;
    the numbers update once a second. Heavy rules every 30 s are labelled
    with the clock time (1:25:30), on :00 and :30. Network is on a log scale
    (``NetFloor`` to 10 ** ``NetCeilExp`` bytes/s). Needs only Rainmeter and
    the B612 font.

    .. image:: docs/images/system-recorder.png
       :alt: The System Recorder

**CPU Recorder** (``CPURecorder``)
    The same recorder for the CPU, taller: a lane for the average of all
    processors and a lane for each logical processor (12 here), each with its
    own pen, so a core that is pegged shows as a line pinned to the top of its
    lane and a hogging core stands out from the idle ones. The legend counts
    the pegged cores (at or above ``PegAt``, 90%), and names the hottest core
    and its load. ``make_system_recorder.py`` writes ``CPURecorder.ini``, with
    one lane per processor, as well as the frame and paper images; it shares
    them, and the clock script, with the System Recorder in
    ``skin/DesktopDashboard/@Resources/Recorder``.

    .. image:: docs/images/cpu-recorder.png
       :alt: The CPU Recorder

**CPU Recorder (tall)** (``CPURecorderTall``)
    The CPU Recorder with every lane twice as high (``TALL`` in
    ``make_system_recorder.py``), 408 x 388 px, so each core's trace has twice
    the vertical resolution. It reads the same measures, so run one or the
    other.

    .. image:: docs/images/cpu-recorder-tall.png
       :alt: The tall CPU Recorder

**Network Recorder** (``NetworkRecorder``)
    The same recorder for the network, on a logarithmic scale from 10 kbit/s to
    1 Gbit/s (the top), so a trickle and a full-speed transfer are both visible.
    Download and upload are two pens. The paper is log-graph paper: a heavy
    rule and a label at each decade, and faint rules at 2 to 9 times each. The
    legend shows the rates (averaged over half a second) and the machine's IP
    address, engraved on the faceplate. ``FloorExp`` and ``Decades`` set the
    scale, and must match ``NET_FLOOR_EXP`` and ``NET_DECADES`` in
    ``make_system_recorder.py``, which draws the paper.

    .. image:: docs/images/network-recorder.png
       :alt: The Network Recorder

Current Task and Agent Limits read ``@Resources/state.inc``, which
``collect.py`` writes. Classic Clock and the VU meters need nothing but Rainmeter
(and the B612 font for the VU meters' labels).

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
    Generates the three VU meter skins (see below).

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

``ClassicClock.ini`` and the images in ``ClassicClock/@Resources`` (and the
wide variant's) are
generated. Edit ``make_classic_clock.py`` (colours, sizes and the hand shapes
are constants and arguments near the top and in ``hands()``), then::

    uv run make_classic_clock.py

or run it with any Python that has Pillow. The numerals use Times New Roman
Bold from ``C:\Windows\Fonts``. Reload the skin afterwards.

Everything that doesn't move (rim, dial, track and numerals, with their
shading and shadows) is one Pillow-rendered image, ``Dial.png``, drawn at 4x
and reduced. The depth settings (light angle, shadow strengths, glare) are
constants near the top. The hands are stacks of 1 px ``ROUNDLINE`` meters
whose widths follow the hand's outline; each one's soft shadow is a blurred
image turned by a ``Rotator`` meter, offset a little down and right. Note that ``LineLength`` is the radius where a line *ends*, not its
length.

Changing the VU meter
---------------------

Both meters' ``.ini`` files and the images in their ``@Resources/Images`` are
generated. Edit ``make_vu_meter.py`` (each meter's floor, labels and port are in
``METERS``, including each one's reference level, ``zero_vu``; the scale range,
lamp and needle are constants near the top), then::

    uv run make_vu_meter.py

and reload the skins. The meters borrow the clock's palette, light and drawing
helpers from ``make_classic_clock.py``, so a change to the brass there carries
over. The scale and its reference legend are drawn into ``Face.png``, so change
``ZeroVU`` and ``TopVU`` in the generator, not the ``.ini``. The measures come from adni18's VU METER skin;
the artwork no longer does.


License
-------

MIT. See ``LICENSE``.
