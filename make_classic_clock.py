# Copyright (c) 2026 MinchinWeb
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow >= 10.1"]
# ///
"""Generate the ClassicClock skin: a 210 x 210 px Rainmeter analog clock.

Writes skin/DesktopDashboard/ClassicClock/ClassicClock.ini and its images in
@Resources. Edit this script, not the generated files, then
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

Depth: light comes from the upper left. Everything that doesn't move (drop
shadow, bevelled rim, vignetted face, the rim's shadow on it, track and
numerals) is rendered by Pillow at 4x into Dial.png; Rainmeter text cannot be
rotated anyway. Each hand sits above a blurred shadow image that a Rotator
meter turns with it, offset down and right (more for higher hands). Cap.png is
a domed centre cap and Glare.png a faint glass reflection over everything.

Hands are rows of Rainmeter's built-in ROUNDLINE meter driven by a Time measure
(seconds since midnight). NOTE: ROUNDLINE draws from radius LineStart to radius
LineLength (LineLength is the END radius, not a length), so a 1 px slice at s is
LineStart=s, LineLength=s+1.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps

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
BRASS_LIGHT: Colour = (248, 208, 112)  # brass facing the light
# the inner slope's highlight sits against the cream face, so keep it deeper
BRASS_INNER_LIGHT: Colour = (222, 172, 72)
BRASS_DARK: Colour = (98, 68, 22)  # brass facing away from it
CREAM_SHADE: Colour = (190, 168, 125)  # vignette at the edge of the face
SHADOW: Colour = (12, 8, 4)

# rim (radius, px)
RIM_OUT = 103
RIM_MID = 100
RIM_IN = 97

# depth: light from the upper left
LIGHT_ANGLE = 35  # degrees the light sits left of straight up
DIAL_W = SIZE + 4  # room for the drop shadow on the right
DIAL_H = SIZE + 10  # and below
DROP_SHADOWS = [(4, 4.0, 0.7), (1.5, 1.2, 0.5)]  # (drop, blur, strength)
CROWN = 0.6  # highlight along the top of the rim
VIGNETTE = 0.45
RIM_SHADOW_DY = 4  # the rim's shadow on the face
RIM_SHADOW_BLUR = 3
RIM_SHADOW = 0.55
GLARE = 0.24  # glass reflection
HAND_SHADOW = 0.45
CAP_HALF = 10  # Cap.png is 2 x CAP_HALF square

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


def box(cx: float, cy: float, r: float) -> tuple[float, float, float, float]:
    """Return the SCALE x bounding box of a circle given in 1x px."""
    return ((cx - r) * SCALE, (cy - r) * SCALE, (cx + r) * SCALE, (cy + r) * SCALE)


def disc(size: tuple[int, int], cx: float, cy: float, r: float) -> Image.Image:
    """Return an L mask (SCALE x `size`) holding a filled circle given in 1x px."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).ellipse(box(cx, cy, r), fill=255)
    return mask


def layer(mask: Image.Image, colour: Colour, strength: float = 1.0) -> Image.Image:
    """Return a solid `colour` layer whose alpha is `mask` times `strength`."""
    out = Image.new("RGBA", mask.size, (*colour, 0))
    out.putalpha(mask.point(lambda v: round(v * strength)))
    return out


def blur(mask: Image.Image, radius: float) -> Image.Image:
    """Gaussian-blur a SCALE x mask by `radius` 1x px."""
    return mask.filter(ImageFilter.GaussianBlur(radius * SCALE))


def light_gradient(size: tuple[int, int]) -> Image.Image:
    """Return an L mask across the dial: 0 towards the light, 255 away from it."""
    span = round(2 * RIM_OUT * SCALE)
    g = Image.linear_gradient("L").resize((span, span), Image.BICUBIC)
    g = g.rotate(LIGHT_ANGLE, resample=Image.BICUBIC, expand=True)
    left, top = (g.width - span) // 2, (g.height - span) // 2
    g = g.crop((left, top, left + span, top + span))
    out = Image.new("L", size, 128)
    out.paste(g, (round((C - RIM_OUT) * SCALE),) * 2)
    return out


def save_small(big: Image.Image, name: str) -> Image.Image:
    """Reduce a SCALE x image to 1x and save it in @Resources."""
    img = big.resize((big.width // SCALE, big.height // SCALE), Image.LANCZOS)
    img.save(RESOURCES / name)
    return img


def numeral_images() -> list[tuple[Image.Image, float, float]]:
    """Return each numeral, rotated at SCALE x, with its 1x centre."""
    font = ImageFont.truetype(FONT, NUM_PX * SCALE)
    out = []
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
        out.append((rotated, *polar(NUM_R, theta)))
    return out


def dial() -> Image.Image:
    """Render the static dial: shadow, bevelled rim, face, track and numerals.

    Light comes from the upper left. The rim is a rounded brass ring: its outer
    slope is lit at the upper left, its inner slope at the lower right. The rim
    casts a soft shadow onto the top of the face, and the whole clock casts a
    drop shadow down onto the desktop.
    """
    size = (DIAL_W * SCALE, DIAL_H * SCALE)
    img = Image.new("RGBA", size, (0, 0, 0, 0))

    for dy, radius, strength in DROP_SHADOWS:  # a wide soft one, a tight one
        mask = blur(disc(size, C, C + dy, RIM_OUT), radius)
        img.alpha_composite(layer(mask, SHADOW, strength))

    # bevelled brass rim
    light = light_gradient(size)
    dark_brass = Image.new("RGBA", size, (*BRASS_DARK, 255))
    light_brass = Image.new("RGBA", size, (*BRASS_LIGHT, 255))
    lit = Image.composite(dark_brass, light_brass, light)
    inner_light = Image.new("RGBA", size, (*BRASS_INNER_LIGHT, 255))
    unlit = Image.composite(dark_brass, inner_light, ImageOps.invert(light))
    outer = ImageChops.subtract(disc(size, C, C, RIM_OUT), disc(size, C, C, RIM_MID))
    inner = ImageChops.subtract(disc(size, C, C, RIM_MID), disc(size, C, C, RIM_IN))
    img.paste(lit, (0, 0), blur(outer, 0.3))
    img.paste(unlit, (0, 0), blur(inner, 0.3))
    crown = ImageChops.subtract(
        disc(size, C, C, RIM_MID + 0.7), disc(size, C, C, RIM_MID - 0.7)
    )
    img.alpha_composite(layer(blur(crown, 0.5), BRASS_LIGHT, CROWN))

    draw = ImageDraw.Draw(img)
    line = SCALE  # 1 px
    draw.ellipse(box(C, C, RIM_OUT), outline=(*DARK, 255), width=line)
    for k in range(60):  # beaded ring on the brass
        x, y = polar(RIM_MID, k * 6)
        draw.ellipse(box(x, y, 1.4), fill=(*DARK, 255))

    # face, with a slight vignette towards the rim
    face_mask = disc(size, C, C, RIM_IN)
    img.paste((*CREAM, 255), (0, 0), face_mask)
    span = round(2 * RIM_IN * SCALE)
    radial = Image.radial_gradient("L").resize((span, span), Image.BICUBIC)
    radial = radial.point(lambda v: round(max(0, v - 120) / 135 * 255))
    vignette = Image.new("L", size, 0)
    vignette.paste(radial, (round((C - RIM_IN) * SCALE),) * 2)
    vignette = ImageChops.multiply(vignette, face_mask)
    img.alpha_composite(layer(vignette, CREAM_SHADE, VIGNETTE))

    # rings, minute track and numerals
    for r in (88, 64):
        draw.ellipse(box(C, C, r), outline=(*DARK, 170), width=round(0.8 * SCALE))
    for k in range(60):  # minute track: dots, larger at the hours
        x, y = polar(92.5, k * 6)
        draw.ellipse(box(x, y, 1.9 if k % 5 == 0 else 0.9), fill=(*DARK, 255))
    for numeral, x, y in numeral_images():
        at = (round(x * SCALE - numeral.width / 2), round(y * SCALE - numeral.height / 2))
        img.alpha_composite(numeral, at)

    # the rim's shadow on the face, falling down from the top edge
    rim_shadow = ImageOps.invert(disc(size, C, C + RIM_SHADOW_DY, RIM_IN))
    rim_shadow = ImageChops.multiply(blur(rim_shadow, RIM_SHADOW_BLUR), face_mask)
    img.alpha_composite(layer(rim_shadow, SHADOW, RIM_SHADOW))

    # dark line where the face meets the rim, over the rim shadow
    ImageDraw.Draw(img).ellipse(box(C, C, RIM_IN), outline=(*DARK, 255), width=line)
    return save_small(img, "Dial.png")


def glare() -> Image.Image:
    """Render a faint crescent of reflected light over the upper left of the face."""
    size = (DIAL_W * SCALE, DIAL_H * SCALE)
    glow = Image.new("L", size, 0)
    ImageDraw.Draw(glow).ellipse(box(C - 22, C - 52, 70), fill=255)
    bite = Image.new("L", size, 0)  # take a bite out of the bottom: a crescent
    ImageDraw.Draw(bite).ellipse(box(C + 8, C - 2, 92), fill=255)
    glow = ImageChops.subtract(glow, bite)
    glow = ImageChops.multiply(blur(glow, 7), disc(size, C, C, RIM_IN - 1))
    return save_small(layer(glow, (255, 255, 255), GLARE), "Glare.png")


def centre_cap() -> Image.Image:
    """Render the domed centre cap, with its own small shadow."""
    half = CAP_HALF
    size = (2 * half * SCALE,) * 2
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    shadow = blur(disc(size, half + 1, half + 2, 5), 1.2)
    img.alpha_composite(layer(shadow, SHADOW, 0.5))
    img.paste((*DARK, 255), (0, 0), disc(size, half, half, 5))
    img.paste((*BRASS, 255), (0, 0), disc(size, half, half, 2.2))
    shine = blur(disc(size, half - 1.5, half - 1.5, 1.6), 0.8)
    shine = ImageChops.multiply(shine, disc(size, half, half, 5))
    img.alpha_composite(layer(shine, (255, 240, 200), 0.75))
    return save_small(img, "Cap.png")


Drawer = Callable[[ImageDraw.ImageDraw, float], None]


def shadow_image(name: str, reach: float, shapes: Drawer, soft: float) -> int:
    """Render a hand's shadow, pointing to 12, with the pivot at the centre.

    Args:
        name: File name (without .png) in @Resources.
        reach: Furthest the hand reaches from the pivot, in px.
        shapes: Draws the hand silhouette at SCALE x, given the pivot position.
        soft: Blur radius, in px.

    Returns:
        Half the image's side, which is also the pivot's x and y.
    """
    half = math.ceil(reach + 2 + 3 * soft)
    side = 2 * half * SCALE
    mask = Image.new("L", (side, side), 0)
    shapes(ImageDraw.Draw(mask), half * SCALE)
    save_small(layer(blur(mask, soft), SHADOW, HAND_SHADOW), f"{name}.png")
    return half


def spade_shapes(length: int, half_width: Callable[[float], float]) -> Drawer:
    """Return a drawer for a spade hand's silhouette, brass edge included."""

    def draw(d: ImageDraw.ImageDraw, p: float) -> None:
        radii = [i / 4 for i in range(4 * length + 1)]
        right = [(p + (half_width(r) + EDGE / 2) * SCALE, p - r * SCALE) for r in radii]
        left = [(p - (half_width(r) + EDGE / 2) * SCALE, p - r * SCALE) for r in radii]
        d.polygon(right + left[::-1], fill=255)

    return draw


def second_shapes(d: ImageDraw.ImageDraw, p: float) -> None:
    """Draw the second hand's silhouette: needle, tail and counterweight."""
    hw = 0.6 * SCALE
    top, bottom = p - SECOND_LENGTH * SCALE, p + TAIL_LENGTH * SCALE
    d.rectangle((p - hw, top, p + hw, bottom), fill=255)
    r, at = COUNTERWEIGHT_R * SCALE, COUNTERWEIGHT_AT * SCALE
    d.ellipse((p - r, p + at - r, p + r, p + at + r), fill=255)


def shadow_meter(name: str, measure: str, half: int, offset: tuple[int, int]) -> str:
    """Return a Rotator meter that turns a hand's shadow with the hand.

    A Rotator puts the image's pivot (OffsetX, OffsetY) at the centre of the
    meter, so nudging the skin-sized meter by `offset` turns the shadow about a
    point just below and right of the hand's pivot. Angle 0 leaves the image as
    drawn (pointing to 12); positive angles turn clockwise.
    """
    dx, dy = offset
    return (
        f"[{name}]\nMeter=Rotator\nMeasureName={measure}\n"
        f"ImageName=#CURRENTPATH#@Resources\\{name}.png\n"
        f"X={dx}\nY={dy}\nW={SIZE}\nH={SIZE}\n"
        f"OffsetX={half}\nOffsetY={half}\n"
        f"StartAngle=0\nRotationAngle={FULL}\nAntiAlias=1\n"
    )


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
    """Return the hands, each above its own shadow.

    Each hand rides a little higher off the face than the one below it, so its
    shadow falls a little further away.
    """
    hour = spade_profile(60, at=0.68, bulge_r=5.5, shaft_hw=1.0, base_hw=1.8)
    minute = spade_profile(88, at=0.70, bulge_r=4.0, shaft_hw=0.8, base_hw=1.6)

    half = shadow_image("HourShadow", 60, spade_shapes(60, hour), soft=1.0)
    out = shadow_meter("HourShadow", "MeasureHour", half, (1, 2))
    out += hand("Hour", 43200, 60, hour, HAND)

    half = shadow_image("MinuteShadow", 88, spade_shapes(88, minute), soft=1.2)
    out += shadow_meter("MinuteShadow", "MeasureMinute", half, (1, 3))
    out += hand("Minute", 3600, 88, minute, HAND)

    half = shadow_image("SecondShadow", SECOND_LENGTH, second_shapes, soft=1.4)
    out += shadow_meter("SecondShadow", "MeasureSecond", half, (2, 4))
    out += piece("SecondHand", TWELVE, 60, 0, SECOND_LENGTH, 1.2, RED)
    out += piece("SecondTail", SIX, 60, 0, TAIL_LENGTH, 1.2, RED)
    # round counterweight, as 1 px slices whose widths are chords of a circle
    r, at = COUNTERWEIGHT_R, COUNTERWEIGHT_AT
    for p in range(at - r, at + r):
        d = p + 0.5 - at
        chord = 2 * math.sqrt(r * r - d * d)
        out += piece(f"CounterWeight{p}", SIX, 60, p, p + 1, f"{chord:.1f}", RED)
    return out


def fraction(name: str, period: int) -> str:
    """Return a Calc measure: how far through `period` seconds the time is, 0-1.

    The shadow Rotators read these; the ROUNDLINE hands use ValueReminder on
    the Time measure directly, which works out the same.
    """
    return (
        f"[{name}]\nMeasure=Calc\nFormula=(MeasureTime % {period}) / {period}\n"
        f"MinValue=0\nMaxValue=1\n"
    )


def main() -> None:
    """Write the skin's .ini and images."""
    RESOURCES.mkdir(parents=True, exist_ok=True)
    for old in RESOURCES.glob("Num*.png"):  # numerals are now part of Dial.png
        old.unlink()
    dial_img = dial()
    glare()
    centre_cap()
    ini = f"""[Rainmeter]
Update=1000
AccurateText=1
DynamicWindowSize=1
Group=DesktopDashboard

[Metadata]
Name=Desktop Dashboard - Classic Clock
Author=MinchinWeb
Version=1.3.0
License=MIT
Information=Analog clock face with Roman numerals, spade hands, a second hand and a bevelled brass rim, lit from the upper left with soft shadows. Sized to the 210px illustro skins. Generated by make_classic_clock.py; edit the generator, not this file.

[MeasureTime]
Measure=Time

{fraction("MeasureHour", 43200)}
{fraction("MeasureMinute", 3600)}
{fraction("MeasureSecond", 60)}
[Dial]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Dial.png
X=0
Y=0
W={dial_img.width}
H={dial_img.height}

{hands()}
[CentreCap]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Cap.png
X={C - CAP_HALF:g}
Y={C - CAP_HALF:g}

[Glare]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Glare.png
X=0
Y=0
"""
    (SKIN / "ClassicClock.ini").write_text(ini, encoding="utf-8", newline="\n")
    print("wrote", SKIN)


if __name__ == "__main__":
    main()
