# Copyright (c) 2026 MinchinWeb
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow >= 10.1"]
# ///
"""Generate the ClassicClock skin: a 210 x 210 px Rainmeter analog clock.

Writes skin/DesktopDashboard/ClassicClock/ClassicClock.ini and the rotated numeral
images in its @Resources folder. Edit this script, not the generated files, then
run it with `uv run make_classic_clock.py` and reload the skin.

Layout (radius from centre, px):
  103     dark outer edge
  97-103  brass rim (6 px stroke centred on 100), beaded ring of 60 dots at 100
  97      dark inner edge line
  92      minute track: 60 dots (larger at the hours)
  88      thin ring between the dots and the numerals
  ~67-86  numeral band: large Roman numerals, bottoms facing the centre
  64      thin inner ring
  0-5     centre cap
Hands: slim dark shafts with a brass edge, spade ornament ~70% of the way out.
Red second hand with a thin tail and a round counterweight.

Rainmeter text cannot be rotated, so each numeral is rendered with Pillow,
rotated, and placed as an Image meter.

Hands are rows of Rainmeter's built-in ROUNDLINE meter driven by a Time measure
(seconds since midnight). NOTE: ROUNDLINE draws from radius LineStart to radius
LineLength (LineLength is the END radius, not a length), so a 1 px slice at s is
LineStart=s, LineLength=s+1.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SKIN = Path(__file__).resolve().parent / "skin" / "DesktopDashboard" / "ClassicClock"
RESOURCES = SKIN / "@Resources"
FONT = "C:/Windows/Fonts/timesbd.ttf"  # Times New Roman Bold

SIZE = 210
C = SIZE / 2

TWELVE = 4.7123889  # 3pi/2: 12 o'clock in ROUNDLINE angles
SIX = 1.5707963  # pi/2: the opposite direction, for the tail and counterweight
FULL = 6.2831853

Colour = tuple[int, int, int]
DARK: Colour = (45, 30, 18)
BRASS: Colour = (200, 158, 68)
CREAM: Colour = (243, 232, 204)
RED: Colour = (190, 30, 30)
HAND: Colour = (28, 20, 14)

# numerals
NUMERALS = {
    12: "XII", 1: "I", 2: "II", 3: "III", 4: "IIII", 5: "V",
    6: "VI", 7: "VII", 8: "VIII", 9: "IX", 10: "X", 11: "XI",
}  # fmt: skip
SCALE = 4  # render numerals at 4x, then reduce, for clean anti-aliasing
NUM_R = 76.5  # centre of the numeral band
NUM_PX = 18  # font size at 1x
CONDENSE = 0.8  # horizontal squeeze, as on vintage dials, so VIII fits its arc

# hands
OVERLAP = 0.3  # overlap of 1 px slices, so anti-aliased seams don't show
EDGE = 1.6  # brass edge: the outline pass is this much wider than the dark fill
SECOND_LENGTH = 89  # short of the hour dots (inner edge ~90.6)
TAIL_LENGTH = 20
COUNTERWEIGHT_R = 5
COUNTERWEIGHT_AT = 20  # centre of the counterweight, behind the pivot


def rgb(colour: Colour, alpha: int = 255) -> str:
    """Format a colour as a Rainmeter `R,G,B,A` string."""
    return f"{colour[0]},{colour[1]},{colour[2]},{alpha}"


def polar(radius: float, degrees: float) -> tuple[float, float]:
    """Return the x, y of a point `radius` from the centre, clockwise from 12."""
    a = math.radians(degrees)
    return C + radius * math.sin(a), C - radius * math.cos(a)


def numerals() -> str:
    """Render the rotated numeral images and return their Image meters."""
    RESOURCES.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(FONT, NUM_PX * SCALE)
    sections = []
    for hour, text in NUMERALS.items():
        theta = (hour % 12) * 30
        left, top, right, bottom = font.getbbox(text)
        pad = 4 * SCALE
        size = (right - left + 2 * pad, bottom - top + 2 * pad)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(canvas).text(
            (pad - left, pad - top), text, font=font, fill=(*DARK, 255)
        )
        canvas = canvas.resize(
            (round(canvas.width * CONDENSE), canvas.height), Image.LANCZOS
        )
        # PIL rotates counter-clockwise; a negative angle turns it clockwise so
        # the numeral's bottom faces the centre. expand=True keeps the ink centred.
        rotated = canvas.rotate(-theta, resample=Image.BICUBIC, expand=True)
        # pad to a multiple of SCALE so the downscale keeps the centre exact
        w4 = -(-rotated.width // SCALE) * SCALE
        h4 = -(-rotated.height // SCALE) * SCALE
        padded = Image.new("RGBA", (w4, h4), (0, 0, 0, 0))
        padded.paste(rotated, ((w4 - rotated.width) // 2, (h4 - rotated.height) // 2))
        img = padded.resize((w4 // SCALE, h4 // SCALE), Image.LANCZOS)
        img.save(RESOURCES / f"Num{hour}.png")
        cx, cy = polar(NUM_R, theta)
        sections.append(
            f"[Num{hour}]\nMeter=Image\n"
            f"ImageName=#CURRENTPATH#@Resources\\Num{hour}.png\n"
            f"X={cx - img.width / 2:.1f}\nY={cy - img.height / 2:.1f}\n"
            f"W={img.width}\nH={img.height}\n"
        )
    return "\n".join(sections)


def face() -> str:
    """Return the Shape lines for the dial, rim, beads, rings and minute dots."""
    clear = "Fill Color 0,0,0,0"
    shapes = [
        (
            f"Ellipse {C},{C},100,100 | Fill Color {rgb(CREAM)}"
            f" | Stroke Color {rgb(BRASS)} | StrokeWidth 6"
        ),
        f"Ellipse {C},{C},103,103 | {clear} | Stroke Color {rgb(DARK)} | StrokeWidth 1",
        f"Ellipse {C},{C},97,97 | {clear} | Stroke Color {rgb(DARK)} | StrokeWidth 1",
        (
            f"Ellipse {C},{C},88,88 | {clear}"
            f" | Stroke Color {rgb(DARK, 170)} | StrokeWidth 0.8"
        ),
        (
            f"Ellipse {C},{C},64,64 | {clear}"
            f" | Stroke Color {rgb(DARK, 170)} | StrokeWidth 0.8"
        ),
    ]
    for k in range(60):  # beaded ring on the brass
        x, y = polar(100, k * 6)
        shapes.append(
            f"Ellipse {x:.2f},{y:.2f},1.4,1.4 | Fill Color {rgb(DARK)} | StrokeWidth 0"
        )
    for k in range(60):  # minute track: dots, larger at the hours
        x, y = polar(92.5, k * 6)
        dot = 1.9 if k % 5 == 0 else 0.9
        shapes.append(
            f"Ellipse {x:.2f},{y:.2f},{dot},{dot}"
            f" | Fill Color {rgb(DARK)} | StrokeWidth 0"
        )
    return "\n".join(f"Shape{i + 1 if i else ''}={s}" for i, s in enumerate(shapes))


def piece(
    name: str,
    angle: float,
    period: int,
    r0: float,
    r1: float,
    width: float | str,
    colour: Colour,
) -> str:
    """Return a ROUNDLINE meter drawn from radius r0 to radius r1.

    Args:
        name: Meter section name.
        angle: StartAngle, in radians (TWELVE or SIX).
        period: Seconds per revolution (ValueReminder).
        r0: Start radius (LineStart).
        r1: End radius (LineLength, which is a radius, not a length).
        width: Line width, in px.
        colour: Line colour.
    """
    if r1 - r0 == 1:  # overlap 1 px slices a little so anti-aliased seams don't show
        r0, r1 = max(0, r0 - OVERLAP), r1 + OVERLAP
    return (
        f"[{name}]\nMeter=ROUNDLINE\nMeasureName=MeasureTime\n"
        f"X=0\nY=0\nW={SIZE}\nH={SIZE}\n"
        f"StartAngle={angle}\nRotationAngle={FULL}\nValueReminder={period}\n"
        f"LineStart={r0}\nLineLength={r1}\nLineWidth={width}\n"
        f"LineColor={rgb(colour)}\nSolid=0\nAntiAlias=1\n"
    )


def spade_profile(
    length: int, at: float, bulge_r: float, shaft_hw: float, base_hw: float
) -> Callable[[float], float]:
    """Return the half-width of a spade hand as a function of radius.

    The hand is a slim shaft (slightly wider at the pivot) with a spade `at` of
    the way out. The spade is round on its inner side and narrows to a point on
    its outer side (over 2.2 x its radius); a fine needle runs on to the tip.

    Args:
        length: Hand length, in px.
        at: Where the spade's centre sits, as a fraction of the length.
        bulge_r: Spade radius, in px.
        shaft_hw: Half-width of the shaft, in px.
        base_hw: Half-width of the shaft at the pivot, in px.
    """
    centre = length * at
    point = centre + 2.2 * bulge_r

    def half_width(r: float) -> float:
        if r <= centre:  # shaft, slightly wider at the pivot
            shaft = base_hw + (shaft_hw - base_hw) * min(1, r / (0.4 * length))
        else:  # needle: shaft width down to a fine point at the tip
            f = (r - centre) / (length - centre)
            shaft = shaft_hw * (1 - f) + 0.3 * f
        d = r - centre
        if -bulge_r < d <= 0:
            spade = math.sqrt(bulge_r * bulge_r - d * d)
        elif 0 < d < point - centre:
            spade = bulge_r * (1 - d / (point - centre))
        else:
            spade = 0
        return max(shaft, spade)

    return half_width


def hand(
    prefix: str,
    period: int,
    length: int,
    half_width: Callable[[float], float],
    fill: Colour,
) -> str:
    """Return a hand as 1 px slices: a brass outline pass under a dark fill pass."""
    widths = [2 * half_width(s + 0.5) for s in range(length)]
    out = [
        piece(f"{prefix}Outline{s}", TWELVE, period, s, s + 1, f"{w + EDGE:.1f}", BRASS)
        for s, w in enumerate(widths)
    ]
    out += [
        piece(f"{prefix}Fill{s}", TWELVE, period, s, s + 1, f"{max(w, 1):.1f}", fill)
        for s, w in enumerate(widths)
    ]
    return "".join(out)


def hands() -> str:
    """Return the hour, minute and second hands."""
    out = hand(
        "Hour",
        43200,
        60,
        spade_profile(60, at=0.68, bulge_r=5.5, shaft_hw=1.0, base_hw=1.8),
        HAND,
    )
    out += hand(
        "Minute",
        3600,
        88,
        spade_profile(88, at=0.70, bulge_r=4.0, shaft_hw=0.8, base_hw=1.6),
        HAND,
    )
    out += piece("SecondHand", TWELVE, 60, 0, SECOND_LENGTH, 1.2, RED)
    out += piece("SecondTail", SIX, 60, 0, TAIL_LENGTH, 1.2, RED)
    # round counterweight, as 1 px slices whose widths are chords of a circle
    r, at = COUNTERWEIGHT_R, COUNTERWEIGHT_AT
    for p in range(at - r, at + r):
        d = p + 0.5 - at
        chord = 2 * math.sqrt(r * r - d * d)
        out += piece(f"CounterWeight{p}", SIX, 60, p, p + 1, f"{chord:.1f}", RED)
    return out


def main() -> None:
    """Write the skin's .ini and numeral images."""
    ini = f"""[Rainmeter]
Update=1000
AccurateText=1
DynamicWindowSize=1
Group=DesktopDashboard

[Metadata]
Name=Desktop Dashboard - Classic Clock
Author=MinchinWeb
Version=1.2.0
License=MIT
Information=Analog clock face with Roman numerals, spade hands, a second hand and a brass rim. Sized to the 210px illustro skins. Generated by make_classic_clock.py; edit the generator, not this file.

[MeasureTime]
Measure=Time

[Face]
Meter=Shape
{face()}

{numerals()}
{hands()}
[CentreCap]
Meter=Shape
Shape=Ellipse {C},{C},5,5 | Fill Color {rgb(DARK)} | StrokeWidth 0
Shape2=Ellipse {C},{C},2,2 | Fill Color {rgb(BRASS)} | StrokeWidth 0
"""
    (SKIN / "ClassicClock.ini").write_text(ini, encoding="utf-8", newline="\n")
    print("wrote", SKIN)


if __name__ == "__main__":
    main()
