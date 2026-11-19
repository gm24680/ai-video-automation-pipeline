
import argparse
import fcntl
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "post-captions"
QUEUE = POSTS / "upload_queue.json"
HISTORY = POSTS / "youtube_uploads.json"
ATTEMPTS = POSTS / "publishing_attempts.json"
LOCK = POSTS / ".publishing_worker.lock"

CONTENT_TYPES = {
    "duke-dennis-cruise-posting.json": "independent",
    "outdoor-adventure-shorts-posting.json": "campaign",
}


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def save_json(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)


def content_type(job):
    manifest = load_json(Path(job["manifest"]), {})
    config = Path(manifest.get("campaign_config", "")).name
    return CONTENT_TYPES.get(config, "unclassified")

def campaign_is_eligible(job):
    config_path = ROOT / "config" / "campaign_eligibility.json"
    config = load_json(config_path, {})

    campaign_name = job.get("campaign")
    campaign = config.get("campaigns", {}).get(campaign_name)

    if not isinstance(campaign, dict):
        return False

    if campaign.get("youtube_enabled") is not True:
        return False

    verified_until = campaign.get("verified_until")

    if not verified_until:
        return False

    try:
        deadline = datetime.fromisoformat(
            verified_until.replace("Z", "+00:00")
        )
    except (ValueError, AttributeError):
        return False

    if deadline.tzinfo is None:
        return False

    return datetime.now(timezone.utc) < deadline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--type",
        choices=("campaign", "independent"),
        required=True,
    )
    parser.add_argument(
        "--execute-private",
        action="store_true",
        help="Upload one eligible clip privately",
    )
    args = parser.parse_args()

    with LOCK.open("a+") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)

        queue = load_json(QUEUE, {}).get("jobs", [])
        history = load_json(HISTORY, [])
        attempts = load_json(ATTEMPTS, {})

        uploaded = {
            item["job_id"]
            for item in history
            if item.get("video_id")
        }

        eligible = []

        for job in queue:
            if job.get("platform") != "youtube":
                continue

            if job.get("status") != "approved_for_upload":
                continue

            if content_type(job) != args.type:
                continue

            if args.type == "campaign":
                if not campaign_is_eligible(job):
                    continue

            job_id = job["job_id"]

            if job_id in uploaded or job_id in attempts:
                continue

            manifest = load_json(Path(job["manifest"]), {})
            youtube = manifest.get("platforms", {}).get("youtube", {})
            caption_file = Path(youtube.get("caption_file", ""))

            if youtube.get("status") != "approved_for_upload":
                continue

            if not caption_file.is_file():
                continue

            if caption_file.read_text().strip() != job["caption"]:
                continue

            if not Path(job["video_path"]).is_file():
                continue

            eligible.append(job)

        if not eligible:
            print(f"No eligible {args.type} YouTube clips.")
            return

        job = eligible[0]
        job_id = job["job_id"]

        print("Selected:", job["title"])
        print("Content type:", args.type)
        print("Job ID:", job_id)

        if not args.execute_private:
            print("DRY RUN: Nothing uploaded.")
            return

        # Record the attempt before calling YouTube.
        # Never automatically retry an uncertain upload.
        attempts[job_id] = {
            "status": "started",
            "content_type": args.type,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        save_json(ATTEMPTS, attempts)

        result = subprocess.run(
            [
                sys.executable,
                str(ROOT / "youtube_uploader.py"),
                "--job-id", job_id,
                "--confirm-private-upload",
            ],
            capture_output=True,
            text=True,
        )

        print(result.stdout, flush=True)
        if result.stderr:
            print(result.stderr, file=sys.stderr, flush=True)

        updated_history = load_json(HISTORY, [])
        record = next(
            (
                item for item in updated_history
                if item.get("job_id") == job_id
                and item.get("video_id")
            ),
            None,
        )

        if record:
            attempts[job_id]["status"] = "uploaded_private"
            attempts[job_id]["video_id"] = record["video_id"]
            attempts[job_id]["url"] = record["url"]
        else:
            attempts[job_id]["status"] = "needs_reconciliation"
            attempts[job_id]["error"] = (
                "Upload result uncertain; verify in YouTube Studio"
                if result.returncode
                else "No upload record found; manual verification required"
            )

        attempts[job_id]["finished_at"] = (
            datetime.now(timezone.utc).isoformat()
        )
        save_json(ATTEMPTS, attempts)

        if attempts[job_id]["status"] != "uploaded_private":
            sys.exit(1)


if __name__ == "__main__":
    main()
