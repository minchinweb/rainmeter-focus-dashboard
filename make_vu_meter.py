# Copyright (c) 2026 MinchinWeb
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow >= 10.1"]
# ///
"""Generate the VUMeter skin: a 210px wide Rainmeter analog VU meter.

Scales assets from the original "VU METER by adni18" skin and writes
skin/DesktopDashboard/VUMeter/VUMeter.ini and its scaled images.
Run with `uv run make_vu_meter.py` or `python make_vu_meter.py`.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent
SKIN_DIR = REPO_ROOT / "skin" / "DesktopDashboard" / "VUMeter"
MIC_SKIN_DIR = REPO_ROOT / "skin" / "DesktopDashboard" / "VUMeterMic"

# Default source location in user Documents
SRC_CANDIDATES = [
    Path.home() / "Documents" / "Rainmeter" / "Skins" / "VU METER by adni18" / "@Resources" / "Images",
    Path(r"C:\Users\William\Documents\Rainmeter\Skins\VU METER by adni18\@Resources\Images"),
]

# Target dimensions
TARGET_WIDTH = 210
ORIGINAL_WIDTH = 158
SCALE = TARGET_WIDTH / ORIGINAL_WIDTH  # ~1.3291139

# Scaled sizes (width, height)
# 158x120 -> 210x160 (159.5 rounded to 160)
BG_SIZE = (210, 160)
# 130x130 -> 172x172 (even dimension for exact integer pivot at 86, 86)
NEEDLE_SIZE = (172, 172)
NEEDLE_OFFSET = (86, 86)
# 18x35 -> 24x47
CAP_SIZE = (24, 47)

# Rotator meter positioning on skin canvas
# Original pivot was at (12 + 128/2, 38 + 122/2) = (76, 99)
# Scaled pivot = (76 * SCALE, 99 * SCALE) = (101, 132)
ROTATOR_W = 170
ROTATOR_H = 162
ROTATOR_X = 101 - ROTATOR_W // 2  # 16
ROTATOR_Y = 132 - ROTATOR_H // 2  # 51

# Pivot cap positioning
CAP_X = 101 - CAP_SIZE[0] // 2    # 89
CAP_Y = round(88 * SCALE)         # 117

INI_CONTENT = """\
[Rainmeter]
Update=16
AccurateText=1
DynamicWindowSize=1
Group=DesktopDashboard

[Metadata]
Name=Desktop Dashboard - VU Meter
Author=adni18 (mod by MinchinWeb)
Version=1.4.0
License=Creative Commons BY-NC-SA 3.0
Information=210px wide analog VU meter. Needle reads dBFS corrected for Windows master volume. Scroll to trim the scale; middle-click to reset.

[Variables]
; 1 = compensate for Windows master volume (needle independent of volume slider)
; 0 = raw post-master level (needle drops when you lower volume)
CompensateSystemVolume=1
; Scale trim in dB, adjusted by scrolling. Positive moves the needle up.
Trim=0
; Needle travel: FloorDB at the left stop, 0 dBFS at the right stop.
FloorDB=-40
; Measured Windows master-volume attenuation: dB = -VolumeTaperDB * log10(100 / volume).
VolumeTaperDB=34.6

[MeasureWin7Audio]
Measure=Plugin
Plugin=Win7AudioPlugin

[MeasureAudioOutput]
Measure=Plugin
Plugin=AudioLevel
Port=Output
RMSAttack=100
RMSDecay=300
RMSGain=1
PeakAttack=15
PeakDecay=2500
PeakGain=1.0
DynamicVariables=1

[MeasureAudioRMS]
Measure=Plugin
Plugin=AudioLevel
Parent=MeasureAudioOutput
Channel=Avg
Type=RMS

[MeasureLevelDB]
Measure=Calc
; The AudioLevel Output tap is read AFTER the master volume (measured with a 440 Hz test tone),
; so the level falls as the slider falls. With RMSGain=1 the RMS is already dBFS when the
; master is at 100%. Compensation adds the attenuation back in dB:
;   offset = VolumeTaperDB * log10(100 / volume)   (volume 5..100)
; Muted (Win7 volume < 0) is treated as 100%: the signal is still on the tap, with no offset.
; When CompensateSystemVolume=0 the offset is 0.
; Booleans: (cond) evaluates to 1 or 0 in Rainmeter formulas.
Formula=20 * Log(Max(MeasureAudioRMS, 0.0001)) + #CompensateSystemVolume# * #VolumeTaperDB# * Log(100 / ((MeasureWin7Audio < 0) * 100 + (MeasureWin7Audio >= 0) * Max(MeasureWin7Audio, 5))) + #Trim#
DynamicVariables=1

[MeasureNormalizedRMS]
Measure=Calc
; Maps the dB level onto the needle: FloorDB -> 0, 0 dBFS -> 1.
Formula=Min(Max((MeasureLevelDB - #FloorDB#) / (0 - #FloorDB#), 0), 1)
DynamicVariables=1

[MeterBackground]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Images\\VU Meter.png
X=0
Y=0
W=""" + str(BG_SIZE[0]) + """
H=""" + str(BG_SIZE[1]) + """
MouseScrollUpAction=[!SetVariable Trim (Min(#Trim#+1,20))][!Redraw]
MouseScrollDownAction=[!SetVariable Trim (Max(#Trim#-1,-20))][!Redraw]
MiddleMouseDownAction=[!SetVariable Trim 0][!Redraw]
ToolTipText="VU Meter  |  Trim: #Trim# dB#CRLF#Scroll to adjust  |  Middle-click to reset"
DynamicVariables=1

; Each sign has its own measure so zero can hide both meters.
[MeasureTrimPos]
Measure=Calc
Formula=#Trim#
IfCondition=(MeasureTrimPos > 0)
IfTrueAction=[!ShowMeter MeterTrimPos][!Redraw]
IfFalseAction=[!HideMeter MeterTrimPos][!Redraw]
DynamicVariables=1

[MeasureTrimNeg]
Measure=Calc
Formula=#Trim#
IfCondition=(MeasureTrimNeg < 0)
IfTrueAction=[!ShowMeter MeterTrimNeg][!Redraw]
IfFalseAction=[!HideMeter MeterTrimNeg][!Redraw]
DynamicVariables=1

[MeterTrimPos]
Meter=String
Text=+#Trim# dB
X=182
Y=116
StringAlign=Right
FontFace=Segoe UI
FontSize=10
FontColor=70,70,70,255
AntiAlias=1
Hidden=1
DynamicVariables=1

[MeterTrimNeg]
Meter=String
Text=#Trim# dB
X=182
Y=116
StringAlign=Right
FontFace=Segoe UI
FontSize=10
FontColor=70,70,70,255
AntiAlias=1
Hidden=1
DynamicVariables=1

[MeterLabel]
Meter=String
Text=OUT
X=20
Y=118
StringAlign=Left
FontFace=Segoe UI
FontSize=9
StringStyle=Bold
FontColor=70,70,70,255
AntiAlias=1

[MeterAudioRMS]
Meter=Rotator
MeasureName=MeasureNormalizedRMS
X=""" + str(ROTATOR_X) + """
Y=""" + str(ROTATOR_Y) + """
W=""" + str(ROTATOR_W) + """
H=""" + str(ROTATOR_H) + """
ImageName=#CURRENTPATH#@Resources\\Images\\needle.png
AntiAlias=1
OffsetX=""" + str(NEEDLE_OFFSET[0]) + """
OffsetY=""" + str(NEEDLE_OFFSET[1]) + """
StartAngle=5.51
RotationAngle=1.55

[MeterCap]
Meter=Image
ImageName=#CURRENTPATH#@Resources\\Images\\vu-cap.png
X=""" + str(CAP_X) + """
Y=""" + str(CAP_Y) + """
AntiAlias=1
"""


def mic_ini_content() -> str:
    """Same skin, but reading the microphone (capture) input with no master-volume compensation."""
    text = INI_CONTENT
    pairs = [
        ("Name=Desktop Dashboard - VU Meter", "Name=Desktop Dashboard - Mic VU Meter"),
        (
            "Information=210px wide analog VU meter. Needle reads dBFS corrected for Windows master volume. Scroll to trim the scale; middle-click to reset.",
            "Information=210px wide analog VU meter for the microphone input (dBFS). Scroll to trim the scale; middle-click to reset.",
        ),
        ("Port=Output\n", "Port=Input\n"),
        (
            "; 1 = compensate for Windows master volume (needle independent of volume slider)\n"
            "; 0 = raw post-master level (needle drops when you lower volume)\n"
            "CompensateSystemVolume=1\n",
            "; Mic meter: no master-volume compensation. The mic is not on the playback path.\n"
            "CompensateSystemVolume=0\n",
        ),
        ("FloorDB=-40\n", "FloorDB=-60\n"),
        ("Text=OUT\n", "Text=MIC\n"),
    ]
    for old, new in pairs:
        assert text.count(old) == 1, old[:60]
        text = text.replace(old, new)
    return text


def find_source_dir() -> Path:
    for candidate in SRC_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Could not find VU METER by adni18 source images in: {SRC_CANDIDATES}")


def scale_images(src_dir: Path, skin_dir: Path) -> None:
    img_out = skin_dir / "@Resources" / "Images"
    img_out.mkdir(parents=True, exist_ok=True)
    targets = [
        ("VU Meter.png", BG_SIZE),
        ("needle.png", NEEDLE_SIZE),
        ("vu-cap.png", CAP_SIZE),
    ]
    for filename, size in targets:
        src_path = src_dir / filename
        if not src_path.exists():
            raise FileNotFoundError(f"Missing required source image: {src_path}")
        with Image.open(src_path) as img:
            scaled = img.resize(size, resample=Image.Resampling.LANCZOS)
            dest_path = img_out / filename
            scaled.save(dest_path, "PNG")
            print(f"Generated {dest_path} ({size[0]}x{size[1]})")


def write_skin_ini(skin_dir: Path, filename: str, content: str) -> None:
    skin_dir.mkdir(parents=True, exist_ok=True)
    ini_path = skin_dir / filename
    # Write LF endings to match the rest of the repo, even on Windows.
    ini_path.write_bytes(content.encode("utf-8"))
    print(f"Generated {ini_path}")


def main() -> None:
    src_dir = find_source_dir()
    print(f"Source images: {src_dir}")
    for skin_dir in (SKIN_DIR, MIC_SKIN_DIR):
        scale_images(src_dir, skin_dir)
    write_skin_ini(SKIN_DIR, "VUMeter.ini", INI_CONTENT)
    write_skin_ini(MIC_SKIN_DIR, "VUMeterMic.ini", mic_ini_content())
    print("Done! VU Meter and Mic VU Meter skins generated successfully.")


if __name__ == "__main__":
    main()
