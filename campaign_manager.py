#!/usr/bin/env python3
"""Safely preview and remove generated files from the retired Arctic campaign."""
import argparse
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MEDIA_DIRS = (
    "inbox", "working", "drafts", "vertical", "finished",
    "subtitles", "styled-subtitles", "headlines", "post-captions",
)
PREFIXES = ("19-day-solo", "jarvis-integration-test")


def belongs_to_campaign(file: Path) -> bool:
    normalized = re.sub(r"[\s_]+", "-", file.name.lower())
    return normalized.startswith(PREFIXES)


def find_files() -> list[Path]:
    matches = []
    for directory_name in MEDIA_DIRS:
        folder = ROOT / directory_name
        if not folder.is_dir() or folder.is_symlink():
            continue
        for file in folder.rglob("*"):
            if file.is_file() and not file.is_symlink() and belongs_to_campaign(file):
                matches.append(file)
    return sorted(matches)


def processing_is_active() -> bool:
    result = subprocess.run(
        ["ps", "-eo", "args="], capture_output=True, text=True, check=True
    )
    return any(
        ("run_pipeline.py" in line or "batch_runner.py" in line or "job_runner.py" in line)
        and ("python" in line)
        for line in result.stdout.splitlines()
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["cleanup"])
    parser.add_argument("campaign", choices=["19-day-solo"])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--delete", action="store_true")
    args = parser.parse_args()

    files = find_files()
    total_bytes = sum(file.stat().st_size for file in files)
    print(f"Matched {len(files)} files; total {total_bytes / (1024**3):.2f} GiB")
    for file in files:
        print(f"  {file.relative_to(ROOT)}")

    if not args.delete:
        print("\nDRY RUN: Nothing deleted.")
        return

    if not files:
        print("Nothing to delete.")
        return

    if processing_is_active():
        raise SystemExit("Refusing deletion: a clipping or batch process is running.")

    answer = input("\nType DELETE 19-DAY-SOLO to permanently remove these files: ")
    if answer != "DELETE 19-DAY-SOLO":
        raise SystemExit("Cancelled. Nothing deleted.")

    removed = 0
    for file in files:
        file.unlink()
        removed += 1
    print(f"Deleted {removed} files ({total_bytes / (1024**3):.2f} GiB).")
    print("Scripts, campaign briefs, job databases, logs, and publishing records were not changed.")


if __name__ == "__main__":
    main()
