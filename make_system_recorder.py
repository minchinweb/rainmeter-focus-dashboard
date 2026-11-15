# Copyright (c) 2026 MinchinWeb
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow >= 10.1"]
# ///
"""Generate the images, and CPURecorder.ini, for the chart recorder skins.

Writes the frame (Front*.png) and paper (Paper*.png) for both skins into the
dashboard's @Resources/Recorder, which they share (Recorder.lua and CPUStats.lua
are there too), and writes CPURecorder.ini, whose lanes depend on the processor
count. Run it with `uv run make_system_recorder.py` and refresh the skins.
SystemRecorder.ini is written by hand; it must agree with this file on PERIOD and
PEN_INSET (its TickEvery and PenInset).

System Recorder: 360 x 160 px, four pens on one sheet.
CPU Recorder: taller, one lane per logical processor under a lane for the average,
like a multi-channel polygraph, so a pegged or hogging core stands out.

The frame is the VU meters' (make_vu_meter.py draws it): the same bevelled,
beaded brass under the same light, and the same faceplate around a window, with
the same glass sheen. Here the window shows the paper.

Layers, bottom to top:
  Paper.png   the chart paper, wider than its window by one PERIOD. The skin
              shows a PaperW x PaperH crop of it and slides the crop along,
              one pixel per sample, so the paper's rules and grain scroll
  Line meters the traces, one pixel per sample
  Front.png   drop shadow, frame, faceplate with the window cut out, glass
              sheen and the frame's shadow on the paper
  pens        Shape meters, a little in from the window's right edge

The paper repeats every PERIOD pixels (the vertical rules sit that far apart),
so when the crop wraps from one end of the image to the other nothing jumps.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageOps

import make_classic_clock as clock
import make_vu_meter as vu
from make_classic_clock import CREAM, CREAM_SHADE, SCALE, SHADOW, blur, layer

DASHBOARD = Path(__file__).resolve().parent / "skin" / "DesktopDashboard"
# Shared by SystemRecorder and CPURecorder, which read it as #@#Recorder\
IMAGES = DASHBOARD / "@Resources" / "Recorder"

W = 360
PAPER_X, PAPER_Y = 13, 13  # the window's top left
PAPER_W = W - 2 * PAPER_X
BELOW = 39  # px from the window's bottom to the skin's bottom: the legend plate
PERIOD = 30  # px (and seconds, at one pixel per second) between the vertical rules
PEN_INSET = 8  # px from the window's right edge to the pens
LEGEND_DY = 15  # px from the window's bottom to the legend row's centre line
SWATCH_LIFT = 0.75  # px the legend's dots sit above the text's centre line, to look centred
LABEL_X = 22  # the engraved label's left edge, as the VU meters' OUT / MIC
MINOR_EVERY = 6  # px between the faint rules

# CPU recorder lanes (px). Each lane's line is drawn on the rows between two rules.
AVG_LANE = 36  # the average's lane
CORE_LANE = 11  # one core's lane, rule to rule
PEG_AT = 90  # percent: a core at or above this counts as pegged

RULE: tuple[int, int, int] = (168, 96, 60)  # printed ink, a faded red-brown
MAJOR_ALPHA, MINOR_ALPHA = 105, 42
GRAIN = 3.0  # paper fibre, as a standard deviation in levels
FADE = 0.10  # the paper darkens this much towards the bottom
SEED = 7


@dataclass(frozen=True)
class Variant:
    """One skin's frame and paper."""

    suffix: str  # appended to Front / Paper
    paper_h: int
    rules: list[tuple[int, bool]]  # (row, heavy) of the printed horizontal rules
    label: str = ""  # engraved at the left of the legend row, as on the VU meters


def system_variant() -> Variant:
    """The System Recorder's: eight even divisions, the even ones heavy."""
    h = 108
    return Variant("", h, [(round(k * (h - 1) / 8), k % 2 == 0) for k in range(1, 8)])


def cpu_variant(cores: int) -> Variant:
    """The CPU Recorder's: a heavy rule under the average's lane, a light one
    between each core's lane, and quarter marks in the average's lane."""
    rules = [(round(2 + 32 * q), False) for q in (0.25, 0.5, 0.75)]
    rules.append((AVG_LANE, True))
    rules += [(AVG_LANE + CORE_LANE * k, False) for k in range(1, cores)]
    return Variant("CPU", AVG_LANE + CORE_LANE * cores, rules, "CPU")


def use_recorder_size(v: Variant) -> None:
    """Point the VU generator's frame code at this skin's size."""
    vu.W, vu.H = W, PAPER_Y + v.paper_h + BELOW
    vu.WINDOW = (PAPER_X, PAPER_Y, W - PAPER_X, PAPER_Y + v.paper_h)
    # the sheen's triangle covers the same share of the window as on the VU meter
    vu.SHEEN_WEDGE = (PAPER_W - 30, v.paper_h + 10)


def front_image(v: Variant) -> Image.Image:
    """Render the frame, faceplate, window and glass over the paper."""
    size = ((vu.W + 4) * SCALE, (vu.H + 10) * SCALE)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    vu.frame(img)
    # The drop shadow is drawn under the whole body, and the VU meters' opaque
    # face hides it. Here the window is open, so clear it out.
    face = vu.window(size)
    img.putalpha(ImageChops.multiply(img.getchannel("A"), ImageOps.invert(face)))
    img.alpha_composite(vu.plate_image(size))
    # the faceplate's shadow falls on the paper, as on the VU meter's face
    shadow = ImageOps.invert(vu.window(size, dy=vu.FRAME_SHADOW_DY))
    shadow = ImageChops.multiply(blur(shadow, vu.FRAME_SHADOW_BLUR), face)
    img.alpha_composite(layer(shadow, SHADOW, vu.FRAME_SHADOW))
    if v.label:
        vu.engrave(img, (LABEL_X, PAPER_Y + v.paper_h + LEGEND_DY), v.label, vu.PLATE_TEXT_PX)
    return clock.save_small_to(img, IMAGES / f"Front{v.suffix}.png")


def paper_image(v: Variant) -> Image.Image:
    """Render the paper: cream, with grain, and printed rules that repeat."""
    width, height = PAPER_W + PERIOD, v.paper_h
    paper = Image.linear_gradient("L").resize((width, height))  # 0 top .. 255 bottom
    cream = Image.new("RGB", (width, height), CREAM)
    shade = Image.new("RGB", (width, height), CREAM_SHADE)
    img = Image.composite(shade, cream, paper.point(lambda x: round(x * FADE)))

    # Grain is one PERIOD wide, tiled, so it repeats where the crop wraps.
    random.seed(SEED)
    tile = Image.effect_noise((PERIOD, height), GRAIN)
    grain = Image.new("L", (width, height))
    for x in range(0, width, PERIOD):
        grain.paste(tile, (x, 0))
    img = ImageChops.add(img, Image.merge("RGB", [grain] * 3), 1, -128)

    # Rules. The newest sample is under the pens, PEN_INSET short of the window's
    # last pixel, so a heavy rule sits there when the crop's offset is 0.
    rules = Image.new("RGBA", img.size, (*RULE, 0))
    draw = ImageDraw.Draw(rules)
    first = (PAPER_W - 1 - PEN_INSET) % PERIOD
    for x in range(first % MINOR_EVERY, width, MINOR_EVERY):
        heavy = (x - first) % PERIOD == 0
        draw.line([(x, 0), (x, height)], fill=(*RULE, MAJOR_ALPHA if heavy else MINOR_ALPHA))
    for y, heavy in v.rules:
        draw.line([(0, y), (width, y)], fill=(*RULE, MAJOR_ALPHA if heavy else MINOR_ALPHA))
    out = img.convert("RGBA")
    out.alpha_composite(rules)
    out.save(IMAGES / f"Paper{v.suffix}.png")
    return out


# ---- CPURecorder.ini ---------------------------------------------------------

CPU_HEAD = """[Rainmeter]
; Update and SampleEvery together: see SystemRecorder.ini.
Update=125
AccurateText=1
DynamicWindowSize=1
Group=DesktopDashboard

[Metadata]
Name=Desktop Dashboard - CPU Recorder
Author=MinchinWeb
Version=2.0.0
License=MIT
Information=Chart recorder for the CPU: a lane for the average of all processors and a lane for each of the @CORES@ logical processors, each with its own pen, so a core that is pegged or hogging stands out. Same paper, frame and clock as the System Recorder. Generated by make_system_recorder.py; edit the generator, not this file.

[Variables]
FontName=B612
PaperX=@PAPER_X@
PaperY=@PAPER_Y@
PaperW=@PAPER_W@
PaperH=@PAPER_H@
; Pixels from the window's right edge to the pens. Must match PEN_INSET in
; make_system_recorder.py.
PenInset=@PEN_INSET@
; Updates per paper sample: 1000 ms / Update. The numbers update this often too.
SampleEvery=8
; Seconds per update, for the pens' spring (1 / Update in Hz).
FrameSeconds=0.125
; The pens are damped springs, as on the VU meters. Keep SpringOmega * FrameSeconds
; under 2 or the integration goes unstable.
SpringOmega=9
SpringDamping=0.8
; Pixels (= samples = seconds) between the heavy vertical rules. Must match
; PERIOD in make_system_recorder.py.
TickEvery=@PERIOD@
Cores=@CORES@
; A core at or above this percent counts as pegged.
PegAt=@PEG_AT@
AvgInk=178,34,34,255
CoreInk=140,45,40,235
; Printed on the paper beside the heavy rules.
TimeColor=130,70,40,210
LaneColor=130,70,40,150
EngraveColor=45,30,18,255
EngraveHighlight=248,208,112,200

; ---- measures ------------------------------------------------------------

; Processor=0 is all processors together: the average.
[MeasureAvg]
Measure=CPU
Processor=0

"""

CPU_SPRING = """[Measure@N@v]
Measure=Calc
Formula=(Measure@N@v + #FrameSeconds# * #SpringOmega# * #SpringOmega# * ((@TARGET@) - Measure@N@x)) / (1 + 2 * #SpringDamping# * #SpringOmega# * #FrameSeconds#)

[Measure@N@x]
Measure=Calc
Formula=Clamp(Measure@N@x + #FrameSeconds# * Measure@N@v, 0, 1)
MinValue=0
MaxValue=1

"""

CPU_MID = """; Pegged cores, the hottest one and its load, once a second, from the pens'
; positions (so a flicker does not count).
[MeasureStats]
Measure=Script
ScriptFile=#@#Recorder\\CPUStats.lua
UpdateDivider=#SampleEvery#

; The paper. Each sample (once a second) the Line meters shift the traces one
; pixel left, and this script shifts the paper's crop the same distance, so the
; paper and the traces move together. It returns how far the newest heavy rule
; is from the pens, 0 to TickEvery - 1; Paper.png repeats every TickEvery pixels,
; so this wraps without a jump. It starts from the wall clock, so the rules fall
; on :00 and :30, and it labels them (see the TimeLabel meters).
[MeasureOffset]
Measure=Script
ScriptFile=#@#Recorder\\Recorder.lua
UpdateDivider=#SampleEvery#
DynamicVariables=1

; ---- paper, lanes and frame ----------------------------------------------

[Paper]
Meter=Image
ImageName=#@#Recorder\\PaperCPU.png
X=#PaperX#
Y=#PaperY#
ImageCrop=[MeasureOffset:0],0,#PaperW#,#PaperH#
DynamicVariables=1

; The clock time of each heavy rule, written up the paper to the left of the
; rule, ending at the top of the paper. There is one more than fits across the
; window, as each slides off the left edge. They are under the frame, which
; trims them at the window's edge.
[TimeLabel]
Meter=String
Y=(#PaperY# + 4)
Angle=-1.5707963
StringAlign=Right
FontFace=#FontName#
FontSize=6.5
FontColor=#TimeColor#
AntiAlias=1
UpdateDivider=#SampleEvery#
DynamicVariables=1

"""

CPU_TIME_LABEL = """[TimeLabel@K@]
Meter=String
MeterStyle=TimeLabel
X=(#PaperX# + #PaperW# - #PenInset# - 11 - [MeasureOffset:0] - @K@ * #TickEvery#)
Text=[&MeasureOffset:Label(@K@)]

"""

CPU_LANE_AVG = """; The average's lane, then one lane per processor, top to bottom.
[LaneAvg]
Meter=Line
MeasureName=MeasureAvgx
X=#PaperX#
Y=(#PaperY# + 2)
W=(#PaperW# - #PenInset#)
H=32
UpdateDivider=#SampleEvery#
LineColor=#AvgInk#
LineWidth=1.8
AntiAlias=1
AutoScale=0

"""

CPU_LANE = """[LaneCore@I@]
Meter=Line
MeasureName=MeasureCore@I@x
X=#PaperX#
Y=(#PaperY# + @TOP@)
W=(#PaperW# - #PenInset#)
H=@LANE_H@
UpdateDivider=#SampleEvery#
LineColor=#CoreInk#
LineWidth=1
AntiAlias=1
AutoScale=0

"""

CPU_NAMES = """; Lane names, small, at the paper's left edge.
[LaneName]
Meter=String
X=(#PaperX# + 3)
FontFace=#FontName#
FontSize=5.5
StringStyle=Bold
FontColor=#LaneColor#
AntiAlias=1

[LaneNameAvg]
Meter=String
MeterStyle=LaneName
Y=(#PaperY# + 3)
Text=AVG

"""

CPU_NAME = """[LaneName@I@]
Meter=String
MeterStyle=LaneName
Y=(#PaperY# + @TOP@)
Text=@I@

"""

CPU_FRONT = """; Frame, faceplate with the window cut out, and glass: over the lanes, so the
; window's edge trims them.
[Front]
Meter=Image
ImageName=#@#Recorder\\FrontCPU.png
X=0
Y=0

; ---- pens ----------------------------------------------------------------
; An ink dot at each lane's current height, on an arm reaching in from the
; window's right edge.

[PenAvg]
Meter=Shape
X=(#PaperX# + #PaperW# - 1 - #PenInset#)
Y=(#PaperY# + 2 + 31 * (1 - [MeasureAvgx]))
Shape=Rectangle 0,-1,(#PenInset# - 1),2 | Fill Color 60,45,25,230 | StrokeWidth 0
Shape2=Ellipse 0,0,3 | Fill Color #AvgInk# | Stroke Color 255,255,255,120
DynamicVariables=1

"""

CPU_PEN = """[PenCore@I@]
Meter=Shape
X=(#PaperX# + #PaperW# - 1 - #PenInset#)
Y=(#PaperY# + @TOP@ + @SPAN@ * (1 - [MeasureCore@I@x]))
Shape=Rectangle 0,-0.5,(#PenInset# - 1),1 | Fill Color 60,45,25,200 | StrokeWidth 0
Shape2=Ellipse 0,0,1.9 | Fill Color #CoreInk# | Stroke Color 255,255,255,100
DynamicVariables=1

"""

CPU_LEGEND = """; ---- engraved legend -----------------------------------------------------
; The numbers update once a second (every SampleEvery updates). Only what has
; its colour on the graph gets a dot.

[LabelBase]
Meter=String
Y=@LEGEND_Y@
FontFace=#FontName#
FontSize=8.25
StringStyle=Bold
StringAlign=LeftCenter
FontColor=#EngraveColor#
StringEffect=Shadow
FontEffectColor=#EngraveHighlight#
AntiAlias=1
UpdateDivider=#SampleEvery#
DynamicVariables=1

[SwatchAvg]
Meter=Shape
X=58
Y=@SWATCH_Y@
Shape=Ellipse 0,0,3.5 | Fill Color #AvgInk# | Stroke Color 255,255,255,120
[LabelAvg]
Meter=String
MeterStyle=LabelBase
X=67
Text=AVG [MeasureAvg:0]%

[LabelPegged]
Meter=String
MeterStyle=LabelBase
X=140
Text=PEGGED [&MeasureStats:Pegged()]/#Cores#

[LabelHottest]
Meter=String
MeterStyle=LabelBase
X=246
Text=TOP [&MeasureStats:Hottest()]: [&MeasureStats:HottestPct()]%
"""


def fill(template: str, **values: object) -> str:
    """Replace each @NAME@ in `template` with its value."""
    for name, value in values.items():
        template = template.replace(f"@{name}@", str(value))
    return template


def cpu_ini(cores: int) -> str:
    """Return CPURecorder.ini: lanes for the average and for each processor."""
    paper_h = AVG_LANE + CORE_LANE * cores
    top = [AVG_LANE + CORE_LANE * k + 1 for k in range(cores)]  # each lane's first row
    lane_h = CORE_LANE - 2  # rows drawn: the rules and a spare row bound them
    out = fill(
        CPU_HEAD, CORES=cores, PAPER_X=PAPER_X, PAPER_Y=PAPER_Y, PAPER_W=PAPER_W,
        PAPER_H=paper_h, PEN_INSET=PEN_INSET, PERIOD=PERIOD, PEG_AT=PEG_AT,
    )  # fmt: skip
    for i in range(1, cores + 1):
        out += f"[MeasureCore{i}]\nMeasure=CPU\nProcessor={i}\n\n"
    out += (
        "; Each pen is a damped spring chasing its load (0..1): velocity first, then\n"
        "; position. The traces are drawn from the pen's position, so a dot always sits\n"
        "; on the end of its line. The damping is applied implicitly (the divisor), which\n"
        "; stays stable at this frame rate; the VU meters' explicit form needs 16 ms steps.\n"
    )
    out += fill(CPU_SPRING, N="Avg", TARGET="MeasureAvg / 100")
    for i in range(1, cores + 1):
        out += fill(CPU_SPRING, N=f"Core{i}", TARGET=f"MeasureCore{i} / 100")
    out += CPU_MID
    for k in range(-(-PAPER_W // PERIOD) + 1):  # one more than fits: each slides off
        out += fill(CPU_TIME_LABEL, K=k)
    out += CPU_LANE_AVG
    for i in range(1, cores + 1):
        out += fill(CPU_LANE, I=i, TOP=top[i - 1], LANE_H=lane_h)
    out += CPU_NAMES
    for i in range(1, cores + 1):
        out += fill(CPU_NAME, I=i, TOP=top[i - 1] - 1)
    out += CPU_FRONT
    for i in range(1, cores + 1):
        out += fill(CPU_PEN, I=i, TOP=top[i - 1], SPAN=lane_h - 1)
    legend_y = PAPER_Y + paper_h + LEGEND_DY
    out += fill(CPU_LEGEND, LEGEND_Y=legend_y, SWATCH_Y=legend_y - SWATCH_LIFT)
    return out


def main() -> None:
    """Write both skins' images and CPURecorder.ini."""
    IMAGES.mkdir(parents=True, exist_ok=True)
    cores = os.cpu_count() or 1
    for variant in (system_variant(), cpu_variant(cores)):
        use_recorder_size(variant)
        front_image(variant)
        paper_image(variant)
    skin = DASHBOARD / "CPURecorder"
    skin.mkdir(exist_ok=True)
    (skin / "CPURecorder.ini").write_text(cpu_ini(cores), encoding="utf-8", newline="\n")
    print("wrote", IMAGES, "and", skin)


if __name__ == "__main__":
    main()
