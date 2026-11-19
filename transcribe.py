import sys
from pathlib import Path

from faster_whisper import WhisperModel

if len(sys.argv) != 2:
    print("Usage: python transcribe.py /path/to/video")
    raise SystemExit(1)

video_path = Path(sys.argv[1]).expanduser()

if not video_path.is_file():
    print(f"Video not found: {video_path}")
    raise SystemExit(1)

output_dir = Path(__file__).resolve().parent / "working"
output_dir.mkdir(parents=True, exist_ok=True)
transcript_path = output_dir / f"{video_path.stem}_transcript.txt"

print("Loading the small transcription model...")
model = WhisperModel("small", device="cpu", compute_type="int8")

print(f"Transcribing: {video_path.name}")
segments, info = model.transcribe(str(video_path), beam_size=5)

with transcript_path.open("w", encoding="utf-8") as transcript:
    transcript.write(f"Detected language: {info.language}\n\n")

    for segment in segments:
        transcript.write(
            f"[{segment.start:07.2f}s - {segment.end:07.2f}s] "
            f"{segment.text.strip()}\n"
        )

print(f"Transcript saved to: {transcript_path}")
