# Copyright (c) 2026 MinchinWeb
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow >= 10.1"]
# ///
"""Generate the VUMeter, VUMeterMic and VUMeterDual skins: analog VU meters.

Writes VUMeter/VUMeter.ini, VUMeterMic/VUMeterMic.ini and their images in
@Resources/Images. Edit this script, not the generated files, then run it with
`uv run make_vu_meter.py` and reload the skins.

The look matches the Classic Clock (make_classic_clock.py, whose palette and
drawing helpers this script borrows): a bevelled, beaded brass frame lit by the
same room light from the upper left, with the same drop shadow. As on a
real meter, the scale shows through a window in a brass faceplate, and the
needle's pivot is hidden behind the plate below the window. A lamp behind the
plate backlights the face, so it glows warm at the bottom and dims towards the
top corners.

Layers, bottom to top:
  Face.png       drop shadow, frame, backlit face, scale, legends
  NeedleShadow   Rotator, offset down and right like the clock's hand shadows
  Needle         Rotator
  Front.png      faceplate around the window (hiding the pivot), with the
                 engraved channel name and a screw, and a glass sheen

The needle has momentum: it is a damped spring (NeedleOmega, NeedleDamping in
the ini), tuned to the VU standard of reaching 99% of a step in 0.3 s with
about 1.5% overshoot.

The scale is a true VU scale: the needle moves in proportion to the signal's
voltage (10 ** (dB / 20)), not its level in dB, so the marks crowd together at
the low end and spread out near the top, and 0 to +3 VU (red) fills about the
right third. The right stop is TOP_VU; the left stop is silence, so the scale
is numbered from -20 VU, as real meters are. Each meter has its own reference
level: the dBFS reading that puts the needle on 0 VU (zero_vu in METERS below).
The legend under "VU" states it, so the ini's ZeroVU and TopVU are
written from here; change them here, not there.

Labels are set in B612 (Bold), which must be installed: Pillow draws the static
ones into Face.png, and the trim readout is a Rainmeter String meter.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps

import make_classic_clock as clock
from make_classic_clock import (
    BRASS_DARK,
    BRASS_INNER_LIGHT,
    BRASS_LIGHT,
    CREAM,
    CREAM_SHADE,
    DARK,
    HAND,
    RED,
    SCALE,
    SHADOW,
    Colour,
    blur,
    layer,
)

SKINS = Path(__file__).resolve().parent / "skin" / "DesktopDashboard"
FONT = "C:/Windows/Fonts/B612-Bold.ttf"
FONT_NAME = "B612"  # for Rainmeter's String meters

W, H = 210, 160
CANVAS_W = W + 4  # room for the drop shadow on the right
CANVAS_H = H + 10  # and below

# frame (inset from the outside edge, px)
CORNER = 14  # outer corner radius
FRAME_MID = 4.5  # crown of the frame, where the beads sit
FRAME_IN = 9  # inner edge: the face starts here
BEAD_GAP = 10.5  # as on the clock's rim

# window in the faceplate (px from the skin's top left)
MARGIN = 13  # frame and plate between the skin's edge and the window
WINDOW = (MARGIN, 13, W - MARGIN, 114)  # left, top, right, bottom
WINDOWS: list[tuple[int, int, int, int]] = []  # more than one window: the dual skin
WINDOW_R = 4  # corner radius
LIP = 1.8  # bevel around the window
PANEL_LIGHT: Colour = (230, 190, 100)  # faceplate towards the light
PANEL_DARK: Colour = (170, 128, 48)  # and away from it
SCREW_AT = (W / 2, 133)
PLATE_TEXT_PX = 11  # engraved OUT / MIC and the trim readout
SCREW_R = 3.2

# face lighting
# The face is the clock's cream, lit from behind: full cream by the lamp,
# falling off to the clock's rim-shadow colour away from it.
FACE_DIM: Colour = CREAM_SHADE  # face far from the lamp
LAMP: Colour = CREAM  # face right by the lamp
LAMP_AT = (105, 150)  # at the pivot, behind the plate
LAMPS: list[tuple[float, float]] = []  # one per window, in the dual skin
LAMP_REACH = 170  # px from the lamp to where its light runs out
LAMP_FALLOFF = 1.8  # higher: the glow fades faster with distance
LAMP_GAIN = 1.6  # >1 saturates to full cream near the lamp
FRAME_SHADOW_DY = 4  # the plate's shadow on the face
FRAME_SHADOW_BLUR = 3
FRAME_SHADOW = 0.5
SHEEN = 0.14  # glass reflection
SHEEN_WEDGE = (150, 118)  # the sheen's triangle reaches this far along the top and left

# scale and needle
PIVOT = (105, 150)  # behind the faceplate, well below the window
SWEEP = 80  # degrees, centred on straight up
SCALE_R = 112  # the scale's base line
MINOR_R, MAJOR_R = 117, 121  # outer ends of the ticks
LABEL_R = 129
TOP_VU = 3  # right stop; red above 0 VU
LABELS = [-20, -10, -7, -5, -3, -2, -1, 0, 1, 2, 3]  # VU values to number
MINOR_TICKS = [-15, -6, -4, *[x / 2 for x in range(-5, 6, 2)]]  # half dB near the top
NEEDLE_LENGTH = 120
NEEDLE_BASE, NEEDLE_TIP = 0.9, 0.35  # half-widths, px
NEEDLE_SHADOW_AT = (1, 3)
NEEDLE_SHADOW = 0.3
NEEDLE_SHADOW_BLUR = 1.6
# ballistics: a damped spring. 12 rad/s and 0.74 reach 99% of a step in 0.3 s
# and overshoot by 1.5%, as the VU standard asks.
NEEDLE_OMEGA = 12
NEEDLE_DAMPING = 0.74
FRAME_TIME = 0.016  # s; the skin's Update


@dataclass
class Meter:
    """One VU meter skin."""

    folder: str
    name: str
    info: str
    port: str
    zero_vu: int  # the dBFS reading that puts the needle on 0 VU
    channel: str  # OUT or MIC
    compensate: bool  # undo the Windows master volume


METERS = [
    Meter(
        folder="VUMeter",
        name="Desktop Dashboard - VU Meter",
        info="210px wide analog VU meter. Needle reads VU (0 VU = -10 dBFS), corrected for Windows master volume. Scroll to trim the scale; middle-click to reset.",
        port="Output",
        zero_vu=-10,  # loud music hovers about 0 VU
        channel="OUT",
        compensate=True,
    ),
    Meter(
        folder="VUMeterMic",
        name="Desktop Dashboard - Mic VU Meter",
        info="210px wide analog VU meter for the microphone input (0 VU = -18 dBFS). Scroll to trim the scale; middle-click to reset.",
        port="Input",
        zero_vu=-18,  # the usual broadcast alignment
        channel="MIC",
        compensate=False,
    ),
]


def font(px: float) -> ImageFont.FreeTypeFont:
    """Return B612 Bold at `px` (1x), scaled for drawing at SCALE x."""
    return ImageFont.truetype(FONT, round(px * SCALE))


def rrect(
    size: tuple[int, int], inset: float, radius: float, dy: float = 0
) -> Image.Image:
    """Return an L mask holding the meter's outline, inset by `inset` px."""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (
            inset * SCALE,
            (inset + dy) * SCALE,
            (W - inset) * SCALE,
            (H - inset + dy) * SCALE,
        ),
        radius=radius * SCALE,
        fill=255,
    )
    return mask


def window(size: tuple[int, int], grow: float = 0, dy: float = 0) -> Image.Image:
    """Return an L mask holding the window, grown by `grow` px, moved down `dy`."""
    mask = Image.new("L", size, 0)
    for left, top, right, bottom in WINDOWS or [WINDOW]:
        ImageDraw.Draw(mask).rounded_rectangle(
            (
                (left - grow) * SCALE,
                (top - grow + dy) * SCALE,
                (right + grow) * SCALE,
                (bottom + grow + dy) * SCALE,
            ),
            radius=(WINDOW_R + grow) * SCALE,
            fill=255,
        )
    return mask


def light_gradient(size: tuple[int, int]) -> Image.Image:
    """Return an L mask over the meter: 0 towards the room light, 255 away from it."""
    span = round(math.hypot(W, H) * SCALE)
    g = Image.linear_gradient("L").resize((span, span), Image.BICUBIC)
    g = g.rotate(clock.LIGHT_ANGLE, resample=Image.BICUBIC, expand=True)
    left, top = (g.width - span) // 2, (g.height - span) // 2
    g = g.crop((left, top, left + span, top + span))
    out = Image.new("L", size, 128)
    out.paste(g, (round((W / 2) * SCALE - span / 2), round((H / 2) * SCALE - span / 2)))
    return out


def perimeter_points(
    inset: float, radius: float, gap: float
) -> list[tuple[float, float]]:
    """Return evenly spaced points around a rounded rectangle inset by `inset` px."""
    x0, y0, x1, y1 = inset, inset, W - inset, H - inset
    straight_w, straight_h = x1 - x0 - 2 * radius, y1 - y0 - 2 * radius
    arc = math.pi * radius / 2
    # (length, function of distance along the segment -> point), clockwise from top left
    corners = [
        (x1 - radius, y0 + radius, -90),
        (x1 - radius, y1 - radius, 0),
        (x0 + radius, y1 - radius, 90),
        (x0 + radius, y0 + radius, 180),
    ]
    starts = [(x0 + radius, y0, 1, 0), (x1, y0 + radius, 0, 1),
              (x1 - radius, y1, -1, 0), (x0, y1 - radius, 0, -1)]  # fmt: skip
    lengths = [straight_w, straight_h, straight_w, straight_h]
    segments = []
    for (sx, sy, dx, dy), length, (cx, cy, a0) in zip(starts, lengths, corners):
        segments.append(
            (length, lambda d, sx=sx, sy=sy, dx=dx, dy=dy: (sx + dx * d, sy + dy * d))
        )
        segments.append((arc, lambda d, cx=cx, cy=cy, a0=a0: (
            cx + radius * math.cos(math.radians(a0 + 90 * d / arc)),
            cy + radius * math.sin(math.radians(a0 + 90 * d / arc)),
        )))  # fmt: skip
    total = sum(length for length, _ in segments)
    count = round(total / gap)
    points = []
    for k in range(count):
        d = k * total / count
        for length, at in segments:
            if d <= length:
                points.append(at(d))
                break
            d -= length
    return points


def angle_for(vu: float) -> float:
    """Return the needle angle (degrees clockwise from straight up) for a VU level.

    The needle's travel is proportional to voltage: 0 at the left stop
    (silence) and 1 at TOP_VU.
    """
    return -SWEEP / 2 + SWEEP * 10 ** ((vu - TOP_VU) / 20)


def at_angle(radius: float, degrees: float) -> tuple[float, float]:
    """Return the 1x point `radius` from the pivot, `degrees` clockwise from up."""
    a = math.radians(degrees)
    return PIVOT[0] + radius * math.sin(a), PIVOT[1] - radius * math.cos(a)


def big(point: tuple[float, float]) -> tuple[float, float]:
    """Scale a 1x point to SCALE x."""
    return point[0] * SCALE, point[1] * SCALE


def text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], s: str, px: float,
         colour: Colour, anchor: str = "mm") -> None:  # fmt: skip
    """Draw `s` in B612 at a 1x position."""
    draw.text(big(xy), s, font=font(px), fill=(*colour, 255), anchor=anchor)


def frame(img: Image.Image) -> None:
    """Draw the drop shadow and the bevelled, beaded brass frame."""
    size = img.size
    for dy, radius, strength in clock.DROP_SHADOWS:
        img.alpha_composite(
            layer(blur(rrect(size, 0, CORNER, dy), radius), SHADOW, strength)
        )
    light = light_gradient(size)
    dark_brass = Image.new("RGBA", size, (*BRASS_DARK, 255))
    lit = Image.composite(
        dark_brass, Image.new("RGBA", size, (*BRASS_LIGHT, 255)), light
    )
    unlit = Image.composite(
        dark_brass,
        Image.new("RGBA", size, (*BRASS_INNER_LIGHT, 255)),
        ImageOps.invert(light),
    )
    mid_r, in_r = CORNER - FRAME_MID, CORNER - FRAME_IN
    outer = ImageChops.subtract(rrect(size, 0, CORNER), rrect(size, FRAME_MID, mid_r))
    inner = ImageChops.subtract(
        rrect(size, FRAME_MID, mid_r), rrect(size, FRAME_IN, in_r)
    )
    img.paste(lit, (0, 0), blur(outer, 0.3))
    img.paste(unlit, (0, 0), blur(inner, 0.3))
    crown = ImageChops.subtract(
        rrect(size, FRAME_MID - 0.7, mid_r + 0.7),
        rrect(size, FRAME_MID + 0.7, mid_r - 0.7),
    )
    img.alpha_composite(layer(blur(crown, 0.5), BRASS_LIGHT, clock.CROWN))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((0, 0, W * SCALE, H * SCALE), radius=CORNER * SCALE,
                           outline=(*DARK, 255), width=SCALE)  # fmt: skip
    for x, y in perimeter_points(FRAME_MID, mid_r, BEAD_GAP):
        draw.ellipse(clock.box(x, y, 1.4), fill=(*DARK, 255))


def backlit_face(img: Image.Image) -> Image.Image:
    """Fill the window's face, lit by a lamp below the pivot. Returns its mask."""
    size = img.size
    face = window(size)
    img.paste((*FACE_DIM, 255), (0, 0), face)
    span = round(2 * LAMP_REACH * SCALE)
    radial = Image.radial_gradient("L").resize((span, span), Image.BICUBIC)
    radial = radial.point(
        lambda v: round(255 * min(1, LAMP_GAIN * max(0, 1 - v / 255) ** LAMP_FALLOFF))
    )
    glow = Image.new("L", size, 0)
    for lamp in LAMPS or [LAMP_AT]:
        one = Image.new("L", size, 0)
        one.paste(radial, (round((lamp[0] - LAMP_REACH) * SCALE),
                           round((lamp[1] - LAMP_REACH) * SCALE)))  # fmt: skip
        glow = ImageChops.lighter(glow, one)
    img.alpha_composite(layer(ImageChops.multiply(glow, face), LAMP))
    return face


def scale_marks(img: Image.Image, meter: Meter) -> None:
    """Draw the VU scale, its red zone and the legends."""
    draw = ImageDraw.Draw(img)
    # base line, then a heavier red arc over the red zone
    r = SCALE_R * SCALE
    pivot = big(PIVOT)
    arc_box = (pivot[0] - r, pivot[1] - r, pivot[0] + r, pivot[1] + r)

    def to_pil(deg: float) -> float:
        return deg - 90  # PIL arcs: 0 = 3 o'clock, clockwise

    draw.arc(arc_box, to_pil(-SWEEP / 2), to_pil(SWEEP / 2),
             fill=(*DARK, 255), width=round(0.8 * SCALE))  # fmt: skip
    grow = 1.2 * SCALE
    red_box = (
        arc_box[0] - grow,
        arc_box[1] - grow,
        arc_box[2] + grow,
        arc_box[3] + grow,
    )
    draw.arc(red_box, to_pil(angle_for(0)), to_pil(SWEEP / 2),
             fill=(*RED, 255), width=round(2.6 * SCALE))  # fmt: skip
    ticks = sorted({*MINOR_TICKS, *LABELS})
    for vu in ticks:
        deg = angle_for(vu)
        major = vu in LABELS
        colour = RED if vu > 0 else DARK
        draw.line([big(at_angle(SCALE_R, deg)), big(at_angle(MAJOR_R if major else MINOR_R, deg))],
                  fill=(*colour, 255), width=round((1.2 if major else 0.8) * SCALE))  # fmt: skip
    for vu in LABELS:
        colour = RED if vu > 0 else DARK
        text(draw, at_angle(LABEL_R, angle_for(vu)), str(abs(vu)), 8.5, colour)
    ends = SWEEP / 2 - 1  # minus and plus above each end of the scale
    text(draw, at_angle(LABEL_R + 10, -ends), "−", 11, DARK)
    text(draw, at_angle(LABEL_R + 10, ends), "+", 11, RED)
    text(draw, (PIVOT[0], 84), "VU", 17, DARK)
    zero = f"0 VU = {meter.zero_vu} dBFS".replace("-", "−")
    text(draw, (PIVOT[0], 101), zero, 6, DARK)


def face_image(meter: Meter, out: Path) -> Image.Image:
    """Render the static meter: shadow, frame, backlit face, scale and legends."""
    img = Image.new("RGBA", (CANVAS_W * SCALE, CANVAS_H * SCALE), (0, 0, 0, 0))
    frame(img)
    face = backlit_face(img)
    scale_marks(img, meter)
    shadow = ImageOps.invert(window(img.size, dy=FRAME_SHADOW_DY))
    shadow = ImageChops.multiply(blur(shadow, FRAME_SHADOW_BLUR), face)
    img.alpha_composite(layer(shadow, SHADOW, FRAME_SHADOW))
    return clock.save_small_to(img, out / "Face.png")


def engrave(img: Image.Image, xy: tuple[float, float], s: str, px: float,
            anchor: str = "lm") -> None:  # fmt: skip
    """Engrave `s` into the brass: dark letters with a lit lower edge."""
    draw = ImageDraw.Draw(img)
    text(draw, (xy[0], xy[1] + 0.7), s, px, BRASS_LIGHT, anchor)
    text(draw, xy, s, px, DARK, anchor)


def screw(img: Image.Image) -> None:
    """Draw a slotted screw head in the faceplate."""
    size = img.size
    x, y = SCREW_AT
    img.alpha_composite(
        layer(blur(clock.disc(size, x + 0.5, y + 0.8, SCREW_R), 0.6), SHADOW, 0.4)
    )
    head = clock.disc(size, x, y, SCREW_R)
    lit = Image.composite(
        Image.new("RGBA", size, (*BRASS_DARK, 255)),
        Image.new("RGBA", size, (*BRASS_LIGHT, 255)),
        light_gradient(size),
    )
    img.paste(lit, (0, 0), head)
    draw = ImageDraw.Draw(img)
    draw.ellipse(
        clock.box(x, y, SCREW_R), outline=(*BRASS_DARK, 255), width=round(0.6 * SCALE)
    )
    a = math.radians(30)
    dx, dy = (SCREW_R - 0.6) * math.cos(a), (SCREW_R - 0.6) * math.sin(a)
    draw.line(
        [big((x - dx, y - dy)), big((x + dx, y + dy))],
        fill=(*DARK, 255),
        width=round(0.9 * SCALE),
    )


def plate_image(size: tuple[int, int]) -> Image.Image:
    """Render the faceplate around the window and the glass sheen over it.

    This is everything in Front.png but the engraving and the screw. The
    System Recorder reuses it at its own size by changing W, H, WINDOW and
    SHEEN_WEDGE.
    """
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    face = window(size)

    # glass sheen: a pale wedge over the upper left of the window, fading downwards
    sheen = Image.new("L", size, 0)
    for left, *_ in WINDOWS or [WINDOW]:
        x = left - MARGIN  # the wedge starts at the window's own left edge
        ImageDraw.Draw(sheen).polygon(
            [big((x, 0)), big((x + SHEEN_WEDGE[0], 0)), big((x, SHEEN_WEDGE[1]))], fill=255
        )
    fade = Image.linear_gradient("L").resize(size).point(lambda v: 255 - v)
    sheen = ImageChops.multiply(ImageChops.multiply(blur(sheen, 2.5), fade), face)
    img.alpha_composite(layer(sheen, (255, 255, 255), SHEEN))

    # faceplate: everything inside the frame but outside the window, gently lit
    light = light_gradient(size)
    plate = ImageChops.subtract(rrect(size, FRAME_IN, CORNER - FRAME_IN), face)
    plate_fill = Image.composite(
        Image.new("RGBA", size, (*PANEL_DARK, 255)),
        Image.new("RGBA", size, (*PANEL_LIGHT, 255)),
        light,
    )
    img.paste(plate_fill, (0, 0), plate)
    # the window is cut into the plate: its far (lower right) edges catch the light
    lip = ImageChops.subtract(window(size, grow=LIP), face)
    lip_fill = Image.composite(
        Image.new("RGBA", size, (*BRASS_DARK, 255)),
        Image.new("RGBA", size, (*BRASS_INNER_LIGHT, 255)),
        ImageOps.invert(light),
    )
    img.paste(lip_fill, (0, 0), blur(lip, 0.25))
    draw = ImageDraw.Draw(img)
    for left, top, right, bottom in WINDOWS or [WINDOW]:
        draw.rounded_rectangle((left * SCALE, top * SCALE, right * SCALE, bottom * SCALE),
                               radius=WINDOW_R * SCALE, outline=(*DARK, 255), width=SCALE)  # fmt: skip
    # the frame's shadow on the plate, and the line where they meet
    rim = ImageOps.invert(rrect(size, FRAME_IN, CORNER - FRAME_IN, 2))
    rim = ImageChops.multiply(blur(rim, 1.5), plate)
    img.alpha_composite(layer(rim, SHADOW, 0.4))
    draw.rounded_rectangle(
        (FRAME_IN * SCALE, FRAME_IN * SCALE, (W - FRAME_IN) * SCALE, (H - FRAME_IN) * SCALE),
        radius=(CORNER - FRAME_IN) * SCALE, outline=(*DARK, 255), width=SCALE,
    )  # fmt: skip

    return img


def front_image(meter: Meter, out: Path) -> Image.Image:
    """Render what sits over the needle: the faceplate around the window, which
    hides the pivot, with its engraving and screw, and the glass sheen."""
    img = plate_image((CANVAS_W * SCALE, CANVAS_H * SCALE))
    engrave(img, (22, SCREW_AT[1]), meter.channel, PLATE_TEXT_PX)
    screw(img)
    return clock.save_small_to(img, out / "Front.png")


def needle_images(out: Path) -> tuple[int, int]:
    """Render the needle and its shadow, pointing up, cropped close to the needle.

    Returns:
        The pivot's x and y in the images.
    """
    margin = math.ceil(2 + 3 * NEEDLE_SHADOW_BLUR)  # room for the shadow's blur
    px, py = margin, NEEDLE_LENGTH + margin
    mask = Image.new("L", (2 * margin * SCALE, (py + margin) * SCALE), 0)
    p, q = px * SCALE, py * SCALE
    tip = NEEDLE_LENGTH * SCALE
    base, end = NEEDLE_BASE * SCALE, NEEDLE_TIP * SCALE
    ImageDraw.Draw(mask).polygon(
        [(p - base, q), (p - end, q - tip), (p + end, q - tip), (p + base, q)], fill=255
    )
    clock.save_small_to(layer(mask, HAND), out / "Needle.png")
    shadow = layer(blur(mask, NEEDLE_SHADOW_BLUR), SHADOW, NEEDLE_SHADOW)
    clock.save_small_to(shadow, out / "NeedleShadow.png")
    return px, py


def rotator(name: str, pivot: tuple[int, int], offset: tuple[int, int] = (0, 0),
            tag: str = "", dx: int = 0) -> str:  # fmt: skip
    """Return a Rotator meter turning a needle image about the pivot.

    A Rotator draws the image's (OffsetX, OffsetY) at the centre of the meter, and
    the image may spill outside the meter. So the meter is a 2 px box centred on
    the pivot: a meter box from the image's size would start at negative X and Y,
    which shifts the whole skin.

    `tag` is added to the meter's names and `dx` to its X: the dual skin has two
    meters in one file.
    """
    return f"""[{name}{tag}]
Meter=Rotator
MeasureName=MeasureNeedle{tag}
ImageName=#CURRENTPATH#@Resources\\Images\\{name}.png
X={PIVOT[0] - 1 + offset[0] + dx}
Y={PIVOT[1] - 1 + offset[1]}
W=2
H=2
OffsetX={pivot[0]}
OffsetY={pivot[1]}
StartAngle={math.radians(-SWEEP / 2):.7f}
RotationAngle={math.radians(SWEEP):.7f}
AntiAlias=1
"""


def trim_actions(tag: str = "", title: str = "VU Meter") -> str:
    """Return the mouse actions: scroll to trim, middle-click to reset.

    On a single meter these go on both the face and the faceplate over it, so they
    work wherever the mouse is: a meter only gets the mouse over its own visible
    pixels. They need DynamicVariables=1 so #Trim# is read when the action runs,
    not when the skin loads; that's also why they can't go in the [Rainmeter]
    section, which can't be dynamic.
    """
    return f"""\
MouseScrollUpAction=[!SetVariable Trim{tag} (Min(#Trim{tag}#+1,20))][!UpdateMeasureGroup Trim{tag}][!Redraw]
MouseScrollDownAction=[!SetVariable Trim{tag} (Max(#Trim{tag}#-1,-20))][!UpdateMeasureGroup Trim{tag}][!Redraw]
MiddleMouseDownAction=[!SetVariable Trim{tag} 0][!UpdateMeasureGroup Trim{tag}][!Redraw]
ToolTipText="{title}  |  Trim: #Trim{tag}# dB#CRLF#Scroll to adjust  |  Middle-click to reset"
DynamicVariables=1
"""


def variables(meter: Meter, tag: str = "") -> str:
    """Return the variables that belong to one meter."""
    if meter.compensate:
        compensate = (
            "; 1 = compensate for Windows master volume (needle independent of volume slider)\n"
            "; 0 = raw post-master level (needle drops when you lower volume)\n"
            f"CompensateSystemVolume{tag}=1\n"
        )
    else:
        compensate = (
            "; Mic meter: no master-volume compensation. The mic is not on the playback path.\n"
            f"CompensateSystemVolume{tag}=0\n"
        )
    return f"""{compensate}; Scale trim in dB, adjusted by scrolling. Positive moves the needle up.
Trim{tag}=0
; Reference level: the dBFS reading that puts the needle on 0 VU.
ZeroVU{tag}={meter.zero_vu}
"""


def shared_variables() -> str:
    """Return the variables that are the same for every meter."""
    return f"""; Right stop, in VU. The needle moves in proportion to voltage, from silence at
; the left stop to TopVU at the right. The scale in Face.png is drawn for ZeroVU
; and TopVU; change them in make_vu_meter.py, not here.
TopVU={TOP_VU}
; Measured Windows master-volume attenuation: dB = -VolumeTaperDB * log10(100 / volume).
VolumeTaperDB=34.6
; Needle ballistics: a damped spring. NeedleOmega (rad/s) sets how fast it moves,
; NeedleDamping how much it overshoots (1 = none). 12 and 0.74 reach 99% of a step
; in 0.3 s with 1.5% overshoot, as the VU standard asks.
NeedleOmega={NEEDLE_OMEGA}
NeedleDamping={NEEDLE_DAMPING}
"""


def header(name: str, info: str, body: str) -> str:
    """Return the [Rainmeter] and [Metadata] sections, then `body`."""
    return f"""[Rainmeter]
Update={round(FRAME_TIME * 1000)}
AccurateText=1
DynamicWindowSize=1
Group=DesktopDashboard

[Metadata]
Name={name}
Author=MinchinWeb (after VU METER by adni18)
Version=2.0.0
License=Creative Commons BY-NC-SA 3.0
Information={info} Generated by make_vu_meter.py; edit the generator, not this file.

{body}"""


WIN7_AUDIO = """[MeasureWin7Audio]
Measure=Plugin
Plugin=Win7AudioPlugin

"""


def measures(meter: Meter, tag: str = "") -> str:
    """Return the audio measures and the needle's spring for one meter."""
    return f"""[MeasureAudioOutput{tag}]
Measure=Plugin
Plugin=AudioLevel
Port={meter.port}
; Short RMS window: the needle's own ballistics (below) do the VU averaging.
RMSAttack=30
RMSDecay=30
RMSGain=1
PeakAttack=15
PeakDecay=2500
PeakGain=1.0
DynamicVariables=1

[MeasureAudioRMS{tag}]
Measure=Plugin
Plugin=AudioLevel
Parent=MeasureAudioOutput{tag}
Channel=Avg
Type=RMS

[MeasureLevelDB{tag}]
Measure=Calc
; The AudioLevel Output tap is read AFTER the master volume (measured with a 440 Hz test tone),
; so the level falls as the slider falls. With RMSGain=1 the RMS is already dBFS when the
; master is at 100%. Compensation adds the attenuation back in dB:
;   offset = VolumeTaperDB * log10(100 / volume)   (volume 5..100)
; Muted (Win7 volume < 0) is treated as 100%: the signal is still on the tap, with no offset.
; When CompensateSystemVolume=0 the offset is 0.
; Booleans: (cond) evaluates to 1 or 0 in Rainmeter formulas.
Formula=20 * Log(Max(MeasureAudioRMS{tag}, 0.0001)) + #CompensateSystemVolume{tag}# * #VolumeTaperDB# * Log(100 / ((MeasureWin7Audio < 0) * 100 + (MeasureWin7Audio >= 0) * Max(MeasureWin7Audio, 5))) + #Trim{tag}#
DynamicVariables=1

[MeasureNormalizedRMS{tag}]
Measure=Calc
; VU law: travel is proportional to voltage, 10 ^ ((VU - TopVU) / 20), where
; VU = dBFS - ZeroVU. Exp(x * Ln(10) / 20) is 10 ^ (x / 20). Silence -> 0, TopVU -> 1.
Formula=Min(Exp((MeasureLevelDB{tag} - #ZeroVU{tag}# - #TopVU#) * 0.1151292546), 1)
DynamicVariables=1

; The needle chases MeasureNormalizedRMS as a damped spring, one step per update
; ({FRAME_TIME} s). Velocity uses last update's position; position then uses the
; new velocity (semi-implicit Euler, stable at these rates). The stops are 0 and 1.
[MeasureNeedleVelocity{tag}]
Measure=Calc
Formula=MeasureNeedleVelocity{tag} + {FRAME_TIME} * (#NeedleOmega# * #NeedleOmega# * (MeasureNormalizedRMS{tag} - MeasureNeedle{tag}) - 2 * #NeedleDamping# * #NeedleOmega# * MeasureNeedleVelocity{tag})
DynamicVariables=1

[MeasureNeedle{tag}]
Measure=Calc
Formula=Clamp(MeasureNeedle{tag} + {FRAME_TIME} * MeasureNeedleVelocity{tag}, 0, 1)
MinValue=0
MaxValue=1

; Each sign has its own measure so zero can hide both meters.
[MeasureTrimPos{tag}]
Measure=Calc
Group=Trim{tag}
Formula=#Trim{tag}#
IfCondition=(MeasureTrimPos{tag} > 0)
IfTrueAction=[!ShowMeter MeterTrimPos{tag}][!Redraw]
IfFalseAction=[!HideMeter MeterTrimPos{tag}][!Redraw]
DynamicVariables=1

[MeasureTrimNeg{tag}]
Measure=Calc
Group=Trim{tag}
Formula=#Trim{tag}#
IfCondition=(MeasureTrimNeg{tag} < 0)
IfTrueAction=[!ShowMeter MeterTrimNeg{tag}][!Redraw]
IfFalseAction=[!HideMeter MeterTrimNeg{tag}][!Redraw]
DynamicVariables=1

"""


def trim_readouts(tag: str = "", dx: int = 0) -> str:
    """Return the two trim readouts, + and -, on the faceplate."""
    # FontSize is in points (96 dpi: 0.75 pt per px). The shadow, in the plate's
    # light brass, sits below and right like the engraved label's lit edge.
    return "\n".join(
        f"""[MeterTrim{sign}{tag}]
Meter=String
Text={prefix}#Trim{tag}# dB
X={W - 22 + dx}
Y={SCREW_AT[1]:g}
StringAlign=RightCenter
FontFace={FONT_NAME}
FontSize={PLATE_TEXT_PX * 0.75:g}
StringStyle=Bold
FontColor={clock.rgb(DARK)}
StringEffect=Shadow
FontEffectColor={clock.rgb(BRASS_LIGHT, 200)}
AntiAlias=1
Hidden=1
DynamicVariables=1
"""
        for sign, prefix in (("Pos", "+"), ("Neg", ""))
    )


def ini(meter: Meter, pivot: tuple[int, int]) -> str:
    """Return the skin's .ini."""
    actions = trim_actions()
    body = f"""[Variables]
{variables(meter)}{shared_variables()}
{WIN7_AUDIO}{measures(meter)}[MeterFace]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Images\\Face.png
X=0
Y=0
{actions}
{rotator("NeedleShadow", pivot, NEEDLE_SHADOW_AT)}
{rotator("Needle", pivot)}
[MeterFront]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Images\\Front.png
X=0
Y=0
{actions}
; The trim readout sits on the faceplate, so it is drawn after it.
{trim_readouts()}"""
    return header(meter.name, meter.info, body)


# ---- the dual skin ---------------------------------------------------------
# Two meters, OUT then MIC, on one shared plate. Each keeps its own 184 px window,
# so the dials are the single meters' size; one mid-frame, MARGIN px wide, divides
# them. Everything is drawn by the functions above with the module's geometry
# swapped (W, WINDOWS, LAMPS, PIVOT, SCREW_AT), as the System Recorder does.

DUAL_FOLDER = "VUMeterDual"
GAP = 14  # the shared mid-frame, a pixel wider than MARGIN so the skin's width is even
PITCH = (WINDOW[2] - WINDOW[0]) + GAP  # from one meter's window to the next
DUAL_W = W + PITCH


@contextmanager
def dual_geometry() -> Iterator[None]:
    """Make the module's geometry the dual skin's, then restore it."""
    global W, WINDOWS, LAMPS
    saved = W, WINDOWS, LAMPS
    W = DUAL_W
    WINDOWS = [(left + k * PITCH, top, right + k * PITCH, bottom)
               for k in range(2) for left, top, right, bottom in [WINDOW]]  # fmt: skip
    LAMPS = [(LAMP_AT[0] + k * PITCH, LAMP_AT[1]) for k in range(2)]
    try:
        yield
    finally:
        W, WINDOWS, LAMPS = saved


@contextmanager
def meter_at(k: int) -> Iterator[None]:
    """Move the pivot and screw to the k-th meter (inside dual_geometry)."""
    global PIVOT, SCREW_AT
    saved = PIVOT, SCREW_AT
    PIVOT = (saved[0][0] + k * PITCH, saved[0][1])
    SCREW_AT = (saved[1][0] + k * PITCH, saved[1][1])
    try:
        yield
    finally:
        PIVOT, SCREW_AT = saved


def dual_face_image(meters: list[Meter], out: Path) -> Image.Image:
    """Render the static dual meter, as face_image() does one."""
    with dual_geometry():
        img = Image.new("RGBA", ((W + 4) * SCALE, CANVAS_H * SCALE), (0, 0, 0, 0))
        frame(img)
        face = backlit_face(img)
        for k, meter in enumerate(meters):
            with meter_at(k):
                scale_marks(img, meter)
        shadow = ImageOps.invert(window(img.size, dy=FRAME_SHADOW_DY))
        shadow = ImageChops.multiply(blur(shadow, FRAME_SHADOW_BLUR), face)
        img.alpha_composite(layer(shadow, SHADOW, FRAME_SHADOW))
        return clock.save_small_to(img, out / "Face.png")


def dual_front_image(meters: list[Meter], out: Path) -> Image.Image:
    """Render the dual faceplate with each meter's name and screw."""
    with dual_geometry():
        img = plate_image(((W + 4) * SCALE, CANVAS_H * SCALE))
        for k, meter in enumerate(meters):
            with meter_at(k):
                engrave(img, (22 + k * PITCH, SCREW_AT[1]), meter.channel, PLATE_TEXT_PX)
                screw(img)
        return clock.save_small_to(img, out / "Front.png")


def dual_ini(meters: list[Meter], pivot: tuple[int, int]) -> str:
    """Return the dual skin's .ini: each meter's names get a tag (Out, Mic)."""
    tags = [m.channel.title() for m in meters]
    variables_ = "".join(variables(m, t) for m, t in zip(meters, tags))
    measures_ = "".join(measures(m, t) for m, t in zip(meters, tags))
    # A faceplate and a face cover both meters, so each meter's scroll and
    # middle-click go on a clear shape over its half (alpha 1 still takes the mouse).
    parts = [f"""[MeterFace]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Images\\Face.png
X=0
Y=0
"""]
    for k, t in enumerate(tags):
        parts.append(rotator("NeedleShadow", pivot, NEEDLE_SHADOW_AT, t, k * PITCH))
        parts.append(rotator("Needle", pivot, (0, 0), t, k * PITCH))
    parts.append("""[MeterFront]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Images\\Front.png
X=0
Y=0

; The trim readouts sit on the faceplate, so they are drawn after it.
""")
    for k, t in enumerate(tags):
        parts.append(trim_readouts(t, k * PITCH))
    half = DUAL_W / 2
    for k, (m, t) in enumerate(zip(meters, tags)):
        left, right = (0, half) if k == 0 else (half, DUAL_W)
        parts.append(f"""[Mouse{t}]
Meter=Shape
X=0
Y=0
Shape=Rectangle {left:g},0,{right - left:g},{H} | Fill Color 0,0,0,1 | StrokeWidth 0
{trim_actions(t, f"{m.channel} VU Meter")}""")
    body = (f"[Variables]\n{variables_}{shared_variables()}\n"
            f"{WIN7_AUDIO}{measures_}" + "\n".join(parts))
    info = ("Two analog VU meters on one plate: the output (0 VU = -10 dBFS, corrected "
            "for Windows master volume) and the microphone (0 VU = -18 dBFS). Scroll "
            "over a meter to trim its scale; middle-click to reset.")
    return header("Desktop Dashboard - Dual VU Meter", info, body)


def main() -> None:
    """Write both skins' .ini files and images."""
    for meter in METERS:
        skin = SKINS / meter.folder
        images = skin / "@Resources" / "Images"
        images.mkdir(parents=True, exist_ok=True)
        for old in ("VU Meter.png", "needle.png", "vu-cap.png"):  # the adni18 art
            (images / old).unlink(missing_ok=True)
        face_image(meter, images)
        front_image(meter, images)
        pivot = needle_images(images)
        (skin / f"{meter.folder}.ini").write_text(
            ini(meter, pivot), encoding="utf-8", newline="\n"
        )
        print("wrote", skin)
    skin = SKINS / DUAL_FOLDER
    images = skin / "@Resources" / "Images"
    images.mkdir(parents=True, exist_ok=True)
    dual_face_image(METERS, images)
    dual_front_image(METERS, images)
    pivot = needle_images(images)
    (skin / f"{DUAL_FOLDER}.ini").write_text(
        dual_ini(METERS, pivot), encoding="utf-8", newline="\n"
    )
    print("wrote", skin)


if __name__ == "__main__":
    main()
