
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "vertical"
SUBTITLES = ROOT / "subtitles"
OUTPUT = ROOT / "finished"
STYLED = ROOT / "styled-subtitles"

OUTPUT.mkdir(parents=True, exist_ok=True)
STYLED.mkdir(parents=True, exist_ok=True)

# Caption appearance
FONT = "Lato"
FONT_SIZE = 76
OUTLINE = 5
SHADOW = 2

# ASS subtitle colors (BGR format)
WHITE = "&H00FFFFFF"
YELLOW = "&H0000FFFF"
BLACK = "&H00000000"


def parse_time(value):
    hours, minutes, seconds = value.split(":")
    return (
        int(hours) * 3600
        + int(minutes) * 60
        + float(seconds.replace(",", "."))
    )


def ass_time(seconds):
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)

    return f"{hours}:{minutes:02}:{secs:02}.{cs:02}"


def escape_ass(text):
    return (
        text.replace("\\", r"\\")
        .replace("{", r"\{")
        .replace("}", r"\}")
    )


def make_ass(srt_path, ass_path):
    content = srt_path.read_text(encoding="utf-8-sig")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},{FONT_SIZE},{WHITE},{YELLOW},{BLACK},{BLACK},-1,0,0,0,100,100,0,0,1,{OUTLINE},{SHADOW},2,65,65,750,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []

    for block in re.split(r"\n\s*\n", content.strip()):
        lines = block.strip().splitlines()

        if len(lines) < 3:
            continue

        timing = lines[1]

        if "-->" not in timing:
            continue

        start_text, end_text = timing.split("-->")
        start = parse_time(start_text.strip())
        end = parse_time(end_text.strip())

        if end <= start:
            continue

        words = " ".join(lines[2:]).split()

        if not words:
            continue

        # Divide captions into groups of four words.
        groups = [
            words[i:i + 4]
            for i in range(0, len(words), 4)
        ]

        duration = (end - start) / len(groups)

        for i, group in enumerate(groups):
            group_start = start + i * duration
            group_end = min(end, group_start + duration)

            highlighted = []

            # Highlight the last word in yellow.
            for j, word in enumerate(group):
                word = escape_ass(word)

                if j == len(group) - 1:
                    highlighted.append(
                        r"{\c" + YELLOW + "}"
                        + word
                        + r"{\c" + WHITE + "}"
                    )
                else:
                    highlighted.append(word)

            caption = " ".join(highlighted)

            events.append(
                f"Dialogue: 0,{ass_time(group_start)},"
                f"{ass_time(group_end)},Default,,0,0,0,,"
                f"{caption}"
            )

    ass_path.write_text(
        header + "\n".join(events) + "\n",
        encoding="utf-8"
    )


# Select one video or all available videos.
if len(sys.argv) == 2:
    video = Path(sys.argv[1]).expanduser().resolve()

    if not video.is_file():
        sys.exit(f"Video not found: {video}")

    videos = [video]

elif len(sys.argv) == 1:
    videos = sorted(INPUT.glob("*-vertical.mp4"))

else:
    sys.exit("Usage: python style_captions.py [VIDEO]")


if not videos:
    sys.exit("No vertical videos found.")


# Process the selected videos.
for video in videos:

    # Ignore the old test video.
    if video.name == "clip-01-vertical.mp4":
        continue

    srt = SUBTITLES / f"{video.stem}.srt"

    if not srt.exists():
        print(f"Missing subtitles: {video.name}")
        continue

    destination = OUTPUT / video.name.replace(
        "-vertical.mp4", "-styled.mp4"
    )

    # Skip videos that have already been rendered.
    if destination.exists():
        print(f"Skipping existing: {destination.name}")
        continue

    # Generate styled ASS subtitles.
    ass = STYLED / f"{video.stem}.ass"
    make_ass(srt, ass)

    print(f"Rendering: {video.name}", flush=True)

    # Burn subtitles into the video.
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-n",
            "-i", str(video),
            "-vf", f"ass={ass}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "21",
            "-c:a", "copy",
            str(destination),
        ],
        check=True
    )

    print(f"Saved: {destination.name}", flush=True)


print("All styled videos completed.")
