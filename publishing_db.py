import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

DATABASE = ROOT / "publishing.db"
UPLOAD_HISTORY = ROOT / "post-captions" / "youtube_uploads.json"


def connect():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    with connect() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS publishing_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                content_type TEXT,
                channel_id TEXT,
                channel_name TEXT,
                title TEXT,
                video_id TEXT,
                video_path TEXT,
                url TEXT,
                status TEXT NOT NULL,
                uploaded_at TEXT,
                UNIQUE(job_id, platform)
            )
        """)


def import_upload_history():
    initialize()

    if not UPLOAD_HISTORY.exists():
        print("No existing upload history.")
        return

    records = json.loads(UPLOAD_HISTORY.read_text())

    with connect() as db:
        for item in records:
            job_id = item.get("job_id", "")

            content_type = (
                "independent"
                if "duke" in job_id.lower()
                else "campaign"
                if "19-day-solo" in job_id.lower()
                else "unknown"
            )

            db.execute("""
                INSERT INTO publishing_history (
                    job_id,
                    platform,
                    content_type,
                    channel_id,
                    channel_name,
                    title,
                    video_id,
                    video_path,
                    url,
                    status,
                    uploaded_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id, platform) DO NOTHING
            """, (
                job_id,
                item.get("platform", "youtube"),
                content_type,
                item.get("channel_id"),
                item.get("channel_name"),
                item.get("title"),
                item.get("video_id"),
                item.get("video"),
                item.get("url"),
                item.get("status", "unknown"),
                item.get("uploaded_at"),
            ))

    print("Upload history imported successfully.")


def show_history():
    initialize()

    with connect() as db:
        rows = db.execute("""
            SELECT
                title,
                content_type,
                platform,
                channel_name,
                status,
                video_id
            FROM publishing_history
            ORDER BY uploaded_at DESC
        """).fetchall()

    print(f"Total publishing records: {len(rows)}")

    for row in rows:
        print()
        print("Title:", row["title"])
        print("Type:", row["content_type"])
        print("Platform:", row["platform"])
        print("Channel:", row["channel_name"] or "Not recorded")
        print("Status:", row["status"])
        print("Video ID:", row["video_id"])
def save_upload(record, content_type="unknown"):
    initialize()

    with connect() as db:
        db.execute("""
            INSERT INTO publishing_history (
                job_id,
                platform,
                content_type,
                channel_id,
                channel_name,
                title,
                video_id,
                video_path,
                url,
                status,
                uploaded_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(job_id, platform)
            DO UPDATE SET
                content_type = excluded.content_type,
                channel_id = COALESCE(
                    excluded.channel_id,
                    publishing_history.channel_id
                ),
                channel_name = COALESCE(
                    excluded.channel_name,
                    publishing_history.channel_name
                ),
                video_id = excluded.video_id,
                url = excluded.url,
                status = excluded.status,
                uploaded_at = excluded.uploaded_at
        """, (
            record["job_id"],
            record.get("platform", "youtube"),
            content_type,
            record.get("channel_id"),
            record.get("channel_name"),
            record.get("title"),
            record.get("video_id"),
            record.get("video"),
            record.get("url"),
            record.get("status", "unknown"),
            record.get("uploaded_at"),
        ))

if __name__ == "__main__":
    import_upload_history()
    show_history()
