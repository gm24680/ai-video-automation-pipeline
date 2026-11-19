import re
import shutil
import subprocess
import sys
from pathlib import Path

if len(sys.argv) != 5:
    print("Usage: python make_clip.py VIDEO START_SECONDS END_SECONDS CLIP_NAME")
    raise SystemExit(1)

video = Path(sys.argv[1]).expanduser()

try:
    start = float(sys.argv[2])
    end = float(sys.argv[3])
except ValueError:
    print("Start and end times must be numbers of seconds.")
    raise SystemExit(1)

clip_name = re.sub(r"[^A-Za-z0-9_-]+", "-", sys.argv[4]).strip("-")

if not video.is_file():
    print(f"Video not found: {video}")
    raise SystemExit(1)

if start < 0 or end <= start:
    print("End time must be greater than start time, and start cannot be negative.")
    raise SystemExit(1)

if not clip_name:
    print("Choose a simple clip name, such as moment-01.")
    raise SystemExit(1)

if shutil.which("ffmpeg") is None:
    print("FFmpeg is not installed.")
    raise SystemExit(1)

draft_dir = Path(__file__).resolve().parent / "drafts"
draft_dir.mkdir(parents=True, exist_ok=True)
output = draft_dir / f"{clip_name}.mp4"

if output.exists():
    print(f"That draft already exists: {output}")
    raise SystemExit(0)

duration = end - start

command = [
    "ffmpeg",
    "-hide_banner",
    "-n",
    "-i", str(video),
    "-ss", str(start),
    "-t", str(duration),
    "-map", "0:v:0",
    "-map", "0:a?",
    "-c:v", "libx264",
    "-preset", "veryfast",
    "-crf", "20",
    "-c:a", "aac",
    "-b:a", "160k",
    "-movflags", "+faststart",
    str(output),
]

print("Creating a draft clip...")
result = subprocess.run(command)

if result.returncode == 0:
    print(f"Draft saved to: {output}")
else:
    print("FFmpeg could not create the clip.")
    raise SystemExit(result.returncode)
