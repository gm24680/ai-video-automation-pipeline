
import json
import subprocess
import sys
from pathlib import Path


def inspect_video(video_path):
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries",
        "format=duration:stream=codec_type,width,height",
        "-of", "json",
        str(video_path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout)


def validate_video(metadata):
    streams = metadata.get("streams", [])

    video_streams = [
        stream for stream in streams
        if stream.get("codec_type") == "video"
    ]

    audio_streams = [
        stream for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    duration = float(
        metadata.get("format", {}).get("duration", 0)
    )

    checks = {
        "resolution": (
            len(video_streams) > 0
            and video_streams[0].get("width") == 1080
            and video_streams[0].get("height") == 1920
        ),
        "audio": len(audio_streams) > 0,
        "duration": duration >= 15,
    }

    return {
        "passed": all(checks.values()),
        "checks": checks,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Usage: python quality_control.py VIDEO")

    video = Path(sys.argv[1]).expanduser().resolve()

    if not video.is_file():
        sys.exit(f"Video not found: {video}")

    try:
        metadata = inspect_video(video)

    except (subprocess.CalledProcessError, OSError) as error:
        print(json.dumps({
            "passed": False,
            "error": str(error),
        }, indent=2))
        sys.exit(2)

    report = validate_video(metadata)

    print(json.dumps(report, indent=2))

    if report["passed"]:
        sys.exit(0)
    else:
        sys.exit(1)
    print(json.dumps(report, indent=2))

    if report["passed"]:
        sys.exit(0)
    else:
        sys.exit(1)
