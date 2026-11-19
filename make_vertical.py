
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DRAFTS = ROOT / "drafts"
OUTPUT = ROOT / "vertical"

OUTPUT.mkdir(parents=True, exist_ok=True)


if len(sys.argv) == 2:
    files = [Path(sys.argv[1]).expanduser().resolve()]

    if not files[0].is_file():
        sys.exit(f"Video not found: {files[0]}")

elif len(sys.argv) == 1:
    files = sorted(DRAFTS.glob("*.mp4"))

else:
    sys.exit("Usage: python make_vertical.py [DRAFT_MP4]")

if not files:
    sys.exit("No MP4 files found in drafts/")


filter_graph = (
    "[0:v]split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
    "crop=1080:1920,boxblur=20:10[blur];"
    "[fg]scale=1080:-2[front];"
    "[blur][front]overlay=(W-w)/2:(H-h)/2[v]"
)

for index, video in enumerate(files, 1):
    destination = OUTPUT / f"{video.stem}-vertical.mp4"

    if destination.exists():
        print(f"Skipping existing file: {destination.name}")
        continue

    print(f"Converting {index}/{len(files)}: {video.name}", flush=True)

    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostdin", "-n",
            "-i", str(video),
            "-filter_complex", filter_graph,
            "-map", "[v]", "-map", "0:a?",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "aac",
            "-b:a", "160k",
            str(destination),
        ],
        check=True
    )

print("Vertical conversion complete.")
