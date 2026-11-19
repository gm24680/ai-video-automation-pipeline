import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

ROOT = Path(__file__).resolve().parent
TOKEN = ROOT / "secrets" / "youtube_token.json"
CONFIG = ROOT / "config" / "youtube_accounts.json"
HISTORY = ROOT / "post-captions" / "youtube_uploads.json"


def main():
    config = json.loads(CONFIG.read_text())
    expected_id = config["accounts"]["gaming"]["channel_id"]

    uploads = json.loads(HISTORY.read_text())

    if not uploads:
        raise SystemExit("No uploads available for verification.")

    video_id = uploads[-1]["video_id"]

    credentials = Credentials.from_authorized_user_file(str(TOKEN))

    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        TOKEN.write_text(credentials.to_json())
        TOKEN.chmod(0o600)

    youtube = build(
        "youtube",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )

    response = youtube.videos().list(
        part="snippet",
        id=video_id,
    ).execute()

    if not response.get("items"):
        raise SystemExit(
            "Could not retrieve video ownership. "
            "Additional OAuth read permission may be required."
        )

    snippet = response["items"][0]["snippet"]

    actual_id = snippet["channelId"]
    actual_name = snippet["channelTitle"]

    print("Configured Channel ID:", expected_id)
    print("Actual Channel ID:", actual_id)
    print("Channel Name:", actual_name)

    if actual_id != expected_id:
        raise SystemExit("CHANNEL MISMATCH — verification failed.")

    print("CHANNEL VERIFIED — IDs match.")


if __name__ == "__main__":
    main()
