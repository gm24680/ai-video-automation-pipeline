import subprocess
import sys
from pathlib import Path

from jobs import (
    initialize_jobs_database,
    create_job,
    update_job,
)

ROOT = Path(__file__).resolve().parent

def check_clip_quality(clip: Path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "quality_control.py"),
            str(clip),
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        print(f"QC PASSED: {clip.name}", flush=True)
        return True

    print(
        f"QC FAILED: {clip.name} "
        f"(exit code {result.returncode})",
        flush=True,
    )
    print(result.stdout or result.stderr, flush=True)

    return False

def run_job(video: Path, brief: Path):
    initialize_jobs_database()
    job_id = create_job(video.name)

    print(f"Starting job #{job_id}: {video.name}", flush=True)

    finished = ROOT / "finished"

    before = {
        p.name for p in finished.glob("*-upload.mp4")
        if p.is_file()
    }

    try:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "run_pipeline.py"),
                str(video),
                str(brief),
            ],
            check=True,
        )

        after = {
            p.name for p in finished.glob("*-upload.mp4")
            if p.is_file()
        }

        new_clip_names = sorted(after - before)
        new_clips = len(new_clip_names)

        if new_clips == 0:
            raise RuntimeError(
                "Pipeline finished without creating new upload-ready clips"
            )

        passed_clips = 0
        failed_clips = 0

        for clip_name in new_clip_names:
            clip_path = finished / clip_name

            if check_clip_quality(clip_path):
                passed_clips += 1
            else:
                failed_clips += 1

        print(
            f"QC SUMMARY: {passed_clips} passed, "
            f"{failed_clips} failed",
            flush=True,
        )

        # Refresh the publishing queue after processing.
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "social_captions.py"),
                "queue",
            ],
            cwd=ROOT,
            check=True,
        )

        print("Publishing queue refreshed.", flush=True)

        update_job(
            job_id,
            "completed",
            clips_created=new_clips,
        )

        print(
            f"Job #{job_id} completed: {new_clips} clips created",
            flush=True,
        )

    except Exception as error:
        update_job(
            job_id,
            "failed",
            error_message=str(error),
        )
        raise
if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: python job_runner.py VIDEO BRIEF")

    video = Path(sys.argv[1]).expanduser().resolve()
    brief = Path(sys.argv[2]).expanduser().resolve()

    if not video.is_file() or not brief.is_file():
        sys.exit("Video or campaign brief not found.")

    run_job(video, brief)
