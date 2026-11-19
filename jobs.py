import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "jobs.db"

def initialize_jobs_database():
    with sqlite3.connect(DATABASE) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                clips_created INTEGER DEFAULT 0,
                error_message TEXT
            )
        """)

        connection.execute("""
            CREATE TABLE IF NOT EXISTS clip_quality (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                clip_name TEXT NOT NULL,
                passed INTEGER NOT NULL,
                failure_reason TEXT,
                checked_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (job_id) REFERENCES jobs(id),
                UNIQUE(job_id, clip_name)
            )
        """)


def create_job(video_name: str) -> int:
    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.execute(
            """
            INSERT INTO jobs (video_name, status, started_at)
            VALUES (?, 'running', datetime('now'))
            """,
            (video_name,)
        )

        return cursor.lastrowid
def update_job(
    job_id: int,
    status: str,
    clips_created: int = 0,
    error_message: str | None = None
) -> None:

    if status not in {"completed", "failed"}:
        raise ValueError("Status must be completed or failed")

    with sqlite3.connect(DATABASE) as connection:
        cursor = connection.execute(
            """
            UPDATE jobs
            SET status = ?,
                finished_at = datetime('now'),
                clips_created = ?,
                error_message = ?
            WHERE id = ?
            """,
            (status, clips_created, error_message, job_id)
        )

        if cursor.rowcount == 0:
            raise ValueError(f"Job {job_id} does not exist")
def get_recent_jobs(limit: int = 5) -> list:
    with sqlite3.connect(DATABASE) as connection:
        connection.row_factory = sqlite3.Row

        rows = connection.execute(
            """
            SELECT id, video_name, status,
                   started_at, finished_at,
                   clips_created, error_message
            FROM jobs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,)
        ).fetchall()

        return [dict(row) for row in rows]
if __name__ == "__main__":
    import json

    initialize_jobs_database()
    print(json.dumps(get_recent_jobs(5), indent=2))
