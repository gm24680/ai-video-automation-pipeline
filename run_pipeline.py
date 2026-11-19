
import math
import re
import json
import subprocess
import sys
from pathlib import Path

from ollama import chat

ROOT = Path(__file__).resolve().parent
MODEL = "qwen3:4b"

if len(sys.argv) not in (3, 5):
    sys.exit(
        "Usage: python run_pipeline.py VIDEO BRIEF "
        "[--selections FILE]"
    )

if len(sys.argv) == 5 and sys.argv[3] != "--selections":
    sys.exit("Expected --selections FILE")

video = Path(sys.argv[1]).expanduser().resolve()
brief = Path(sys.argv[2]).expanduser().resolve()

selections_file = None

if len(sys.argv) == 5:
    selections_file = Path(sys.argv[4]).expanduser().resolve()
    if not selections_file.is_file():
        sys.exit(f"Selections file not found: {selections_file}")
if not video.is_file() or not brief.is_file():
    sys.exit("Video or campaign brief not found.")


# Get the source video's duration.
duration = float(subprocess.check_output(
    [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video),
    ],
    text=True
).strip())

# Target one clip per five minutes.
target_clips = max(3, min(30, math.ceil(duration / 120)))

print(f"Target clips: {target_clips}", flush=True)

transcript = ROOT / "working" / f"{video.stem}_transcript.txt"
drafts = ROOT / "drafts"
drafts.mkdir(exist_ok=True)

if not transcript.exists():
    subprocess.run(
        [sys.executable, str(ROOT / "transcribe.py"), str(video)],
        check=True
    )

if selections_file is not None:
    valid = json.loads(selections_file.read_text(encoding="utf-8"))

    if not isinstance(valid, list):
        sys.exit("Selections file must contain a list.")

    for clip in valid:
        start = float(clip["start"])
        end = float(clip["end"])

        if not (0 <= start < end <= duration and 15 <= end - start <= 60):
            sys.exit(f"Invalid saved selection: {clip}")

    print(f"Loaded {len(valid)} saved highlights.", flush=True)
else:
    lines = transcript.read_text(encoding="utf-8").splitlines()
    brief_text = brief.read_text(encoding="utf-8")

    # Split long transcripts into manageable chunks.
    chunks = []
    current = []
    length = 0

    for line in lines:
        if length + len(line) > 6500 and current:
            chunks.append("\n".join(current))
            current = []
            length = 0
        current.append(line)
        length += len(line) + 1

    if current:
        chunks.append("\n".join(current))

    candidates = []

    for index, chunk in enumerate(chunks, 1):
        print(f"Analyzing transcript section {index}/{len(chunks)}...", flush=True)

        response = chat(
            model=MODEL,
            think=False,
            format="json",
            options={
                "num_predict": 1000,
                "temperature": 0.5,
                "repeat_penalty": 1.2,
             },
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Identify up to 8 distinct entertaining moments from "
                        "this timestamped video transcript. "
                        "Prioritize funny interactions, surprising statements, "
                        "reactions, stories, and conversations. "
                        "Each clip must be between 15 and 60 seconds long. "
                        "Include enough real dialogue before and after the key "
                        "moment to make the clip understandable by itself. "
                        "Use exact timestamps from the supplied transcript. "
                        "Do not invent dialogue, events, or timestamps. "
                        "Avoid music-only sections, filler, and repeated moments. "
                        "Return ONLY JSON with a clips array. "
                        "Each clip requires start and end as JSON NUMBERS "
                        "representing seconds, without letters or units, "
                        "and a short reason. "
                        "Example: "
                        '{"clips":[{"start":203.12,"end":220.64,'
                        '"reason":"Funny conversation"}]}. '
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"BRIEF:\n{brief_text}\n\n"
                        f"TRANSCRIPT:\n{chunk}\n\n"
                        'Example: {"clips":[{"start":10.0,'
                        '"end":35.0,"reason":"Strong opening"}]}'
                    )
                }
            ]
        )

        try:
            data = json.loads(response.message.content)
            candidates.extend(data.get("clips", []))
        except (ValueError, TypeError, AttributeError):
            print(f"Could not parse section {index}; skipping.")

    valid = []

    for clip in candidates:
        try:
            start = float(clip["start"])
            end = float(clip["end"])
            # Expand promising short moments into candidate clips.
            clip_length = end - start

            if 5 <= clip_length < 15:
                padding = 20 - clip_length

                start = max(0, start - padding / 2)
                end = min(duration, end + padding / 2)
            if start < 0 or not 15 <= end - start <= 60:
                print(
                    f"REJECTED duration: {start:.1f}s–{end:.1f}s "
                    f"({end - start:.1f}s)",
                    flush=True,
                )
            if start >= 0 and 15 <= end - start <= 60:
                if not any(abs(start - x["start"]) < 5 for x in valid):
                    valid.append({
                        "start": start,
                        "end": end,
                        "reason": str(clip.get("reason", ""))
                    })

        except (KeyError, TypeError, ValueError) as exc:
            print(
                f"REJECTED candidate: {clip!r} | Reason: {exc}",
                flush=True,
            )
            continue
    valid = valid[:target_clips]

    (drafts / f"{video.stem}_selections.json").write_text(
        json.dumps(valid, indent=2), encoding="utf-8"
    )

def process_clip(index, clip):
    base = re.sub(r"[^A-Za-z0-9]+", "-", video.stem[:30]).strip("-")
    name = f"{base}-clip-{index:02d}-{int(clip['start']*100)}-{int(clip['end']*100)}"
    print(f"Creating {name}...", flush=True)
    subprocess.run(
        [
             sys.executable,
             str(ROOT / "make_clip.py"),
             str(video),
             str(clip["start"]),
             str
(clip["end"]),
             name
        ],
        check=True
     )
    draft_file = drafts / f"{name}.mp4"
    vertical_file = ROOT / "vertical" / f"{name}-vertical.mp4"

    for script, input_file in [
        ("make_vertical.py", draft_file),
        ("add_captions.py", vertical_file),
        ("style_captions.py", vertical_file),
    ]:
        print(f"Running {script}...", flush=True)

        subprocess.run(
            [
                sys.executable,
                str(ROOT / script),
                str(input_file),
            ],
            check=True,
        )

    # Check that subtitle styling produced a usable video.
    styled_file = ROOT / "finished" / f"{name}-styled.mp4"

    if not styled_file.is_file():
        print(
            f"SKIPPING {name}: no styled video was created.",
            flush=True,
        )
        return False

    # Generate the headline and upload-ready video.
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "add_headlines.py"),
            "process",
            str(styled_file),
        ],
        check=True,
    )
    # BEGIN SOCIAL_CAPTIONS_AUTO
    posting_config = brief.with_name(f"{brief.stem}-posting.json")
    upload_copy = ROOT / "finished" / f"{name}-upload.mp4"
    if posting_config.is_file() and upload_copy.is_file():
        subprocess.run(
            [sys.executable, str(ROOT / "social_captions.py"), "generate",
             str(upload_copy), "--config", str(posting_config)],
            check=True,
        )
    else:
        print(f"Posting captions deferred: config or upload video missing for {name}")
    # END SOCIAL_CAPTIONS_AUTO

    return upload_copy.is_file()


completed = 0
failed = 0
skipped = 0

for index, clip in enumerate(valid, 1):
    try:
        if process_clip(index, clip):
            completed += 1
        else:
            skipped += 1
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        failed += 1
        print(f"FAILED clip {index:02d}: {exc}", flush=True)

print(
    f"Processing finished: {completed} completed, "
    f"{skipped} skipped, {failed} failed."
)
