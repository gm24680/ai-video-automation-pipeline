import fcntl
import argparse
import json
import subprocess
from publishing_db import save_upload, connect
import sys
from datetime import datetime, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

ROOT = Path(__file__).resolve().parent
UPLOAD_LOCK = ROOT / "post-captions" / ".youtube_upload.lock"
SECRETS = ROOT / "secrets"
QUEUE = ROOT / "post-captions" / "upload_queue.json"
HISTORY = ROOT / "post-captions" / "youtube_uploads.json"
TOKEN = SECRETS / "youtube_token.json"

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def read_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2))
    temporary.replace(path)


def get_youtube():
    credentials = Credentials.from_authorized_user_file(
        str(TOKEN), SCOPES
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        write_json(TOKEN, json.loads(credentials.to_json()))
        TOKEN.chmod(0o600)

    if not credentials.valid:
        raise RuntimeError("YouTube authorization is invalid")

    return build(
        "youtube", "v3",
        credentials=credentials,
        cache_discovery=False,
    )
def verify_upload_channel(youtube):
    config_path = ROOT / "config" / "youtube_accounts.json"

    config = json.loads(config_path.read_text())
    expected_id = config["accounts"]["gaming"]["channel_id"]

    response = youtube.channels().list(
        part="snippet",
        mine=True,
    ).execute()

    channels = response.get("items", [])

    if len(channels) != 1:
        raise RuntimeError(
            "Expected exactly one authenticated YouTube channel."
        )

    actual_id = channels[0]["id"]
    actual_name = channels[0]["snippet"]["title"]

    if actual_id != expected_id:
        raise RuntimeError(
            f"CHANNEL MISMATCH: expected {expected_id}, "
            f"authenticated as {actual_id}"
        )

    print(
        f"Channel verified: {actual_name} ({actual_id})",
        flush=True,
    )

    return actual_id, actual_name

def check_existing_upload(job_id):
    # Check existing successful YouTube uploads in SQLite.
    with connect() as db:
        existing = db.execute(
            """
            SELECT video_id, status
            FROM publishing_history
            WHERE job_id = ? AND platform = 'youtube'
            """,
            (job_id,),
        ).fetchone()

    if existing and existing["video_id"]:
        raise RuntimeError(
            f"Upload blocked: {job_id} already exists in SQLite "
            f"with video ID {existing['video_id']}"
        )

    # Check attempts that have already started.
    attempts_path = ROOT / "post-captions" / "publishing_attempts.json"
    attempts = read_json(attempts_path, {})

    if job_id in attempts:
        raise RuntimeError(
            f"Upload blocked: {job_id} already has an attempt record. "
            "Manual reconciliation is required before retrying."
        )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--job-id")
    parser.add_argument("--confirm-private-upload", action="store_true")
    args = parser.parse_args()

    queue = read_json(QUEUE, {}).get("jobs", [])

    youtube_jobs = [
        job for job in queue
        if job.get("platform") == "youtube"
        and job.get("status") == "approved_for_upload"
    ]

    history = read_json(HISTORY, [])

    if args.list:
        for job in youtube_jobs:
            uploaded = any(
                record["job_id"] == job["job_id"]
                for record in history
            )
            print(json.dumps({
                "job_id": job["job_id"],
                "title": job["title"],
                "already_uploaded": uploaded,
            }, indent=2))
        return

    if not args.job_id or not args.confirm_private_upload:
        parser.error(
            "Specify --job-id and --confirm-private-upload"
        )

    matches = [
        job for job in youtube_jobs
        if job["job_id"] == args.job_id
    ]

    if len(matches) != 1:
        raise RuntimeError("Approved YouTube job not found")

    job = matches[0]

    if any(r["job_id"] == job["job_id"] for r in history):
        raise RuntimeError("This job already has an upload record")
    check_existing_upload(job["job_id"])

    video = Path(job["video_path"]).resolve()

    if not video.is_file():
        raise FileNotFoundError(video)

    qc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "quality_control.py"),
            str(video),
        ],
        capture_output=True,
        text=True,
    )

    if qc.returncode != 0:
        raise RuntimeError("Video failed QC:\n" + qc.stdout)

    print("QC PASSED", flush=True)
    print("Uploading:", job["title"], flush=True)


    youtube = get_youtube()

    channel_id, channel_name = verify_upload_channel(youtube)

    request = youtube.videos().insert(


        part="snippet,status",
        body={
            "snippet": {
                "title": job["title"],
                "description": job["caption"],
                "categoryId": "22",
            },
            "status": {
                "privacyStatus": "private",
                "selfDeclaredMadeForKids": False,
            },
        },
        media_body=MediaFileUpload(
            str(video),
            mimetype="video/mp4",
            resumable=True,
            chunksize=1024 * 1024,
        ),
    )

    response = None

    while response is None:
        progress, response = request.next_chunk()
        if progress:
            print(
                f"Upload progress: {progress.progress():.0%}",
                flush=True,
            )

    video_id = response["id"]

    record = {
        "job_id": job["job_id"],
        "platform": "youtube",
        "title": job["title"],
        "video": str(video),
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "status": "uploaded_private",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }

    history.append(record)
    write_json(HISTORY, history)
    content_type = (
        "independent"
        if "duke" in record["job_id"].lower()
        else "campaign"
        if "19-day-solo" in record["job_id"].lower()
        else "unknown"
    )

    save_upload(record, content_type)
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    with UPLOAD_LOCK.open("a+") as lock_file:
        try:
            fcntl.flock(
                lock_file.fileno(),
                fcntl.LOCK_EX | fcntl.LOCK_NB
            )
        except BlockingIOError:
            raise SystemExit(
                "Upload blocked: another YouTube uploader is running."
            )

        main()
