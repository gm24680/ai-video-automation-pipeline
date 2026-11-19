
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from youtube_analytics import get_videos, get_youtube

ROOT = Path(__file__).resolve().parent
POSTS = ROOT / "post-captions"
HISTORY = POSTS / "youtube_uploads.json"
ATTEMPTS = POSTS / "publishing_attempts.json"
REPORTS = ROOT / "reports"

LOCAL_TZ = ZoneInfo("America/Chicago")


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text())


def get_analytics_summary():
    """Collect current YouTube performance statistics."""
    try:
        videos = get_videos()

        if not videos:
            return ["No videos available for analytics."]

        youtube = get_youtube()
        video_ids = [video[0] for video in videos]

        response = youtube.videos().list(
            part="statistics",
            id=",".join(video_ids[:50])
        ).execute()

        stats_by_id = {
            item["id"]: item.get("statistics", {})
            for item in response.get("items", [])
        }

        lines = ["YOUTUBE PERFORMANCE", ""]

        for video_id, title, content_type in videos[:50]:
            stats = stats_by_id.get(video_id)

            lines.append(f"Title: {title}")
            lines.append(f"Type: {content_type}")

            if stats is None:
                lines.append("Statistics unavailable.")
            else:
                lines.append(f"Views: {stats.get('viewCount', 'Unavailable')}")
                lines.append(f"Likes: {stats.get('likeCount', 'Unavailable')}")
                lines.append(f"Comments: {stats.get('commentCount', 'Unavailable')}")

            lines.append("")

        return lines

    except Exception as error:
        return [f"YouTube analytics unavailable: {error}"]


def main():
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=24)

    uploads = load_json(HISTORY, [])
    attempts = load_json(ATTEMPTS, {})

    recent = [
        item for item in uploads
        if datetime.fromisoformat(
            item["uploaded_at"].replace("Z", "+00:00")
        ) >= since
    ]

    recent.sort(key=lambda x: x["uploaded_at"])

    lines = [
        "JARVIS MORNING REPORT",
        f"Generated: {now.astimezone(LOCAL_TZ):%Y-%m-%d %I:%M %p %Z}",
        "Reporting period: Last 24 hours",
        "",
        f"YouTube uploads: {len(recent)}",
        "",
    ]

    if not recent:
        lines.append("No confirmed uploads in this period.")

    for item in recent:
        job_id = item.get("job_id", "")
        attempt = attempts.get(job_id, {})

        if job_id.startswith("duke-dennis"):
            content_type = "independent"
        else:
            content_type = attempt.get(
                "content_type", "campaign/unclassified"
            )

        lines.extend([
            f"Title: {item.get('title', 'Unknown')}",
            f"Type: {content_type}",
            f"Platform: {item.get('platform', 'youtube')}",
            f"Account: {item.get('channel_name') or 'Not recorded'}",
            f"Channel ID: {item.get('channel_id') or 'Not recorded'}",
            f"Status: {item.get('status', 'unknown')}",
            f"URL: {item.get('url', 'Unavailable')}",
            "",
        ])

    unresolved = [
        job_id for job_id, item in attempts.items()
        if item.get("status") == "needs_reconciliation"
    ]

    lines.append(f"Uploads needing verification: {len(unresolved)}")
    for job_id in unresolved:
        lines.append(f"- {job_id}")

    lines.append("")
    lines.extend(get_analytics_summary())

    report = "\n".join(lines) + "\n"

    REPORTS.mkdir(exist_ok=True)
    output = REPORTS / "morning-latest.txt"
    output.write_text(report)

    print(report)
    print(f"Report saved: {output}")


if __name__ == "__main__":
    main()
