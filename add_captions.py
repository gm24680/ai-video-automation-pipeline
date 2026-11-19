
import re
import subprocess
import sys
from pathlib import Path

from faster_whisper import WhisperModel

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "vertical"
OUTPUT = ROOT / "finished"
SUBTITLES = ROOT / "subtitles"

OUTPUT.mkdir(exist_ok=True)
SUBTITLES.mkdir(exist_ok=True)


if len(sys.argv) == 2:
    video = Path(sys.argv[1]).expanduser().resolve()

    if not video.is_file():
        sys.exit(f"Video not found: {video}")

    videos = [video]

elif len(sys.argv) == 1:
    videos = sorted(INPUT.glob("*.mp4"))
    videos = [v for v in videos if v.name != "clip-01-vertical.mp4"]

else:
    sys.exit("Usage: python add_captions.py [VIDEO]")


if not videos:
    sys.exit("No vertical videos found.")

print("Loading Whisper...", flush=True)
model = WhisperModel("small", device="cpu", compute_type="int8")


def srt_time(seconds):
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3600000)
    minutes, remainder = divmod(remainder, 60000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


for index, video in enumerate(videos, 1):
    finished = OUTPUT / video.name.replace("-vertical.mp4", "-finished.mp4")
    srt_file = SUBTITLES / f"{video.stem}.srt"

    if finished.exists():
        print(f"Skipping {finished.name}")
        continue

    print(f"Processing {index}/{len(videos)}: {video.name}", flush=True)

    if not srt_file.exists():
        segments, info = model.transcribe(
            str(video),
            beam_size=5,
            language="en",
            vad_filter=True,
        )

        count = 0

        with srt_file.open("w", encoding="utf-8") as f:
            for segment in segments:
                words = segment.text.strip().split()

                # Keep captions short and readable.
                for offset in range(0, len(words), 5):
                    group = words[offset:offset + 5]
                    if not group:
                        continue

                    fraction_start = offset / len(words)
                    fraction_end = min(offset + 5, len(words)) / len(words)

                    start = segment.start + (
                        segment.end - segment.start
                    ) * fraction_start

                    end = segment.start + (
                        segment.end - segment.start
                    ) * fraction_end

                    if end <= start:
                        continue

                    count += 1
                    f.write(
                        f"{count}\n"
                        f"{srt_time(start)} --> {srt_time(end)}\n"
                        f"{' '.join(group)}\n\n"
                    )

        if count == 0:
            print(f"No speech detected in {video.name}; skipping.")
            srt_file.unlink(missing_ok=True)
            continue

    # Escape characters for FFmpeg's filter parser.
    escaped_path = re.sub(r"([\\':,\[\]])", r"\\\1", str(srt_file))

    subtitle_filter = (
        f"subtitles='{escaped_path}':"
        "force_style='FontName=Lato,"
        "FontSize=14,"
        "Bold=1,"
        "PrimaryColour=&H00FFFFFF,"
        "OutlineColour=&H00000000,"
        "BorderStyle=1,"
        "Outline=2,"
        "Shadow=1,"
        "Alignment=2,"
        "MarginV=320'"
    )

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-n",
            "-i", str(video),
            "-vf", subtitle_filter,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "copy",
            str(finished),
        ],
        check=True,
    )

    print(f"Saved: {finished.name}", flush=True)

print("Caption processing complete.")

