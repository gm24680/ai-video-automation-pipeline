
import sqlite3
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "publishing.db"
TOKEN = ROOT / "secrets" / "youtube_token.json"


def get_videos():
    """Retrieve uploaded YouTube video IDs from SQLite."""
    with sqlite3.connect(
        f"file:{DATABASE}?mode=ro", uri=True
    ) as db:
        return db.execute("""
            SELECT video_id, title, content_type
            FROM publishing_history
            WHERE platform = 'youtube'
              AND video_id IS NOT NULL
              AND status = 'uploaded_private'
        """).fetchall()


def get_youtube():
    """Authenticate with the existing YouTube token."""
    credentials = Credentials.from_authorized_user_file(
        str(TOKEN)
    )

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())

    if not credentials.valid:
        raise RuntimeError("YouTube authorization is invalid")

    return build(
        "youtube", "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def main():
    videos = get_videos()

    if not videos:
        print("No uploaded YouTube videos found.")
        return

    youtube = get_youtube()
    ids = [row[0] for row in videos]

    response = youtube.videos().list(
        part="snippet,statistics,status",
        id=",".join(ids),
    ).execute()

    results = {
        item["id"]: item
        for item in response.get("items", [])
    }

    print("\nJARVIS YOUTUBE PERFORMANCE REPORT\n")

    for video_id, title, content_type in videos:
        item = results.get(video_id)

        print(f"Title: {title}")
        print(f"Type: {content_type}")

        if item is None:
            print("Video unavailable to authenticated account.\n")
            continue

        stats = item.get("statistics", {})
        snippet = item.get("snippet", {})
        status = item.get("status", {})

        print(f"Views: {stats.get('viewCount', 'Unavailable')}")
        print(f"Likes: {stats.get('likeCount', 'Unavailable')}")
        print(f"Comments: {stats.get('commentCount', 'Unavailable')}")
        print(f"Channel: {snippet.get('channelTitle', 'Unknown')}")
        print(f"Privacy: {status.get('privacyStatus', 'Unknown')}")
        print(f"URL: https://www.youtube.com/watch?v={video_id}")
        print()


if __name__ == "__main__":
    main()
