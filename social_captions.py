#!/usr/bin/env python3
"""Generate clip-specific social post captions and hand-off metadata for JARVIS.

Standalone commands (from ~/clipping-agent):
  python social_captions.py generate '19-day-solo-video-1-*-upload.mp4' \
      --config campaigns/outdoor-adventure-shorts-posting.json
  python social_captions.py show '19-day-solo-video-1-*-upload.mp4'
  python social_captions.py approve FILE.mp4 --platform tiktok --confirm
  python social_captions.py queue
  python social_captions.py install

This file NEVER uploads or publishes videos. The generated JSON is a hand-off
for a future platform-authorized publishing worker. Captions require review.
"""

import argparse
import datetime as dt
import json
import os
import py_compile
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(
    os.environ.get(
        "CLIP_PIPELINE_ROOT",
        str(Path(__file__).resolve().parent)
    )
).expanduser().resolve()

FINISHED = ROOT / "finished"
SUBTITLES = ROOT / "subtitles"
HEADLINES = ROOT / "headlines"
OUTPUT = ROOT / "post-captions"
DEFAULT_CONFIG = ROOT / "campaigns" / "outdoor-adventure-shorts-posting.json"
MODEL = "qwen3:4b"
PLATFORMS = ("tiktok", "youtube", "instagram")


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise FileNotFoundError(f"Campaign posting config not found: {path}")
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config.get("platforms"), dict) or not config.get("campaign"):
        raise ValueError("Posting config needs a campaign name and a platforms object")
    disclosure = config.get("disclosure_hashtag", "")

    if not isinstance(disclosure, str):
        raise ValueError("Disclosure hashtag must be a string")

    if disclosure and not disclosure.startswith("#"):
        raise ValueError("Disclosure hashtag must begin with #")

    for platform in PLATFORMS:
        if platform not in config["platforms"]:
            raise ValueError(f"Posting config is missing '{platform}'")
    return config


def select_videos(spec: str) -> list[Path]:
    if any(c in spec for c in "*?["):
        if Path(spec).is_absolute():
            raise ValueError("Use a relative glob, such as '19-day-solo-*-upload.mp4'")
        paths = sorted(FINISHED.glob(spec.removeprefix("finished/")))
    else:
        candidate = Path(spec).expanduser()
        if not candidate.is_file():
            candidate = FINISHED / candidate.name
        paths = [candidate] if candidate.is_file() else []
    return [p.resolve() for p in paths if p.name.endswith("-upload.mp4") and p.is_file()]


def base_name(video: Path) -> str:
    return video.name.removesuffix("-upload.mp4")


def excerpt_from_srt(base: str) -> str:
    path = SUBTITLES / f"{base}-vertical.srt"
    if not path.is_file():
        return ""
    parts = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines()]
    return " ".join(p for p in parts if p and not p.isdigit() and "-->" not in p)[:3500]


def clean_body(value: str) -> str:
    body = re.sub(r"\s+", " ", str(value or "")).strip().strip('"\'\u201c\u201d')
    # Model should create the narrative, NOT hashtags, handles, links, or disclosures.
    if "#" in body or "@" in body or "http" in body.lower():
        raise ValueError("Model included a hashtag, mention, or URL")
    if not 24 <= len(body) <= 240:
        raise ValueError("Post text must be 24-240 characters")
    return body


def generate_body(headline: str, transcript: str, campaign: str) -> tuple[str, str, str]:
    """Return post body, generator label, and any warning. Never invent specifics in fallback."""
    if transcript.strip():
        try:
            from ollama import chat
            for attempt in range(2):
                try:
                    prompt = (
                        "You write engaging captions for YouTube Shorts and TikTok. "
                        "Create ONE short, natural caption about the specific moment in this clip. "
                        "Start with the most interesting moment supported by the transcript. "
                        "Write like a creator describing this specific short video. "
                        "Use an engaging statement or question when appropriate. "
                        "Do not use documentary narration or phrases like "
                        "'the footage shows', 'the explorer notes', 'the adventurer', "
                        "or 'the expedition footage'. "
                        "Do not claim to be the person in the video. "
                        "Use only facts supported by the transcript. Treat the headline as a suggestion, not verified evidence. "
                        "Never invent danger, dialogue, outcomes, or emotions. "
                        "Write 1-2 short sentences, maximum 170 characters. "
                        "Do not include hashtags, mentions, URLs, emojis, or markdown. "
                        'Return ONLY JSON: {"caption":"YOUR CAPTION"}. '
                        + (
                            "Your previous caption was invalid. Follow every requirement. "
                            if attempt else ""
                        )
                    )
                    response = chat(
                        model=MODEL,
                        think=False,
                        format="json",
                        options={"num_predict": 180, "temperature": 0.4, "repeat_penalty": 1.2},
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": (
                                f"Content collection: {campaign}\n"
                                f"Reviewed headline: {headline}\n"
                                f"Individual clip transcript: {transcript[:2800]}"
                            )},
                        ],
                    )
                    body = clean_body(json.loads(response.message.content).get("caption", ""))
                    return body, "ollama", ""
                except (ValueError, TypeError, AttributeError, json.JSONDecodeError) as exc:
                    print(f"  Caption attempt {attempt + 1}/2 invalid: {exc}", flush=True)
        except Exception as exc:
            print(f"  Ollama unavailable: {exc}", flush=True)

    # The headline has already been reviewed by the user; never fabricate details.
    fallback = f"Highlight: {headline.strip()}"
    return fallback, "reviewed_headline_fallback", "AI caption not usable; fallback needs human review"


def hashtags_for(platform: str, config: dict) -> list[str]:
    hashtags = []

    if config.get("disclosure_hashtag"):
        hashtags.append(config["disclosure_hashtag"])
    hashtags += config.get("extra_hashtags", [])
    hashtags += config["platforms"][platform].get("hashtags", [])
    return list(dict.fromkeys(x for x in hashtags if x.startswith("#")))


def make_platform_caption(body: str, platform: str, config: dict) -> str:
    platform_cfg = config["platforms"][platform]
    parts = [body]
    if platform_cfg.get("mention"):
        parts.append(platform_cfg["mention"])
    parts.append(" ".join(hashtags_for(platform, config)))
    return "\n\n".join(parts)


def load_record(video: Path) -> dict:
    path = OUTPUT / f"{base_name(video)}.json"
    if not path.is_file():
        raise FileNotFoundError(f"Generate captions first: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def generate_one(video: Path, config: dict, config_path: Path, force: bool) -> bool:
    base = base_name(video)
    record_file = OUTPUT / f"{base}.json"
    if record_file.is_file():
        if not force:
            print(f"Skipping existing caption set: {record_file.name}")
            return False
        existing = json.loads(record_file.read_text(encoding="utf-8"))
        approved = [p for p, v in existing.get("platforms", {}).items()
                    if v.get("status") == "approved_for_upload"]
        if approved:
            raise ValueError(
                f"Cannot --force overwrite an approved caption set ({', '.join(approved)}). "
                "Review/revoke approval in its JSON manifest first."
            )
    headline_file = HEADLINES / f"{base}.txt"
    if not headline_file.is_file():
        print(f"REVIEW NEEDED: no reviewed headline file for {video.name}: {headline_file}")
        return False
    headline = headline_file.read_text(encoding="utf-8").strip()
    if len(headline) < 8:
        print(f"REVIEW NEEDED: headline empty/too short: {headline_file}")
        return False

    transcript = excerpt_from_srt(base)
    body, generator, warning = generate_body(headline, transcript, config["campaign"])
    platforms = {}
    for platform in PLATFORMS:
        info = config["platforms"][platform]
        caption = make_platform_caption(body, platform, config)
        txt = OUTPUT / f"{base}-{platform}.txt"
        txt.parent.mkdir(parents=True, exist_ok=True)
        txt.write_text(caption + "\n", encoding="utf-8")
        platforms[platform] = {
            "enabled": bool(info.get("enabled", False)),
            "status": "needs_review" if info.get("enabled", False) else "disabled",
            "title": headline[:90].title() + (" #Shorts" if platform == "youtube" else ""),
            "caption_file": str(txt),
            "caption": caption,
            "approved_at": None,
            "post_url": None,
        }
    payload = {
        "schema_version": 1,
        "campaign": config["campaign"],
        "campaign_config": str(config_path.resolve()),
        "video_path": str(video.resolve()),
        "headline": headline,
        "transcript_available": bool(transcript),
        "generator": generator,
        "generation_warning": warning,
        "review_note": "Review clip, caption, disclosures, rights, campaign status and platform budget before publishing.",
        "platforms": platforms,
    }
    save_json(record_file, payload)
    print(f"\nCLIP: {video.name}\nHEADLINE: {headline}\nGENERATOR: {generator}")
    if warning:
        print(f"WARNING: {warning}")
    for platform, data in platforms.items():
        print(f"{platform.upper()} [{'enabled' if data['enabled'] else 'disabled'}]:\n{data['caption']}\n")
    print(f"Saved caption files and manifest: {record_file}")
    return True


def approve_one(video: Path, platform: str, confirm: bool) -> None:
    if not confirm:
        raise ValueError("Review the clip and caption first, then pass --confirm")
    record = load_record(video)
    info = record["platforms"][platform]
    if not info["enabled"]:
        raise ValueError(f"{platform} is disabled in the campaign config")
    path = Path(info["caption_file"])
    caption = path.read_text(encoding="utf-8").strip()
    cfg = load_config(Path(record["campaign_config"]))
    required_hashtag = cfg["disclosure_hashtag"]
    required_mention = cfg["platforms"][platform].get("mention", "")
    if (required_hashtag and required_hashtag not in caption) or (required_mention and required_mention not in caption):
        raise ValueError(f"Missing required disclosure or creator tag in {path}")
    if not caption or len(caption) > 2200:
        raise ValueError("Empty or overly long caption")
    info["caption"] = caption
    info["status"] = "approved_for_upload"
    info["approved_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
    save_json(OUTPUT / f"{base_name(video)}.json", record)
    print(f"Approved {platform} caption for {video.name}; NOT uploaded.")


def export_queue() -> None:
    queue = []
    for manifest in sorted(OUTPUT.glob("*.json")):
        if manifest.name == "upload_queue.json":
            continue
        record = json.loads(manifest.read_text(encoding="utf-8"))

        # Ignore JSON files that are not clip manifests.
        if not isinstance(record, dict):
            continue

        if not all(
            key in record
            for key in ("video_path", "platforms", "campaign")
        ):
            continue

        media = Path(record["video_path"])
        if not media.is_file():
            continue
        for platform, info in record["platforms"].items():
            if info["enabled"] and info["status"] == "approved_for_upload":
                saved_file = Path(info["caption_file"])
                if not saved_file.is_file() or saved_file.read_text(encoding="utf-8").strip() != info["caption"]:
                    print(f"SKIPPING CHANGED CAPTION: {saved_file} (review/approve again)")
                    continue
                queue.append({
                    "job_id": f"{media.stem}:{platform}",
                    "status": "approved_for_upload",
                    "campaign": record["campaign"],
                    "platform": platform,
                    "video_path": str(media),
                    "title": info["title"],
                    "caption": info["caption"],
                    "manifest": str(manifest),
                    "posting_requirements": "Uploader must check current campaign eligibility, platform settings, disclosures and account authorization.",
                })
    path = OUTPUT / "upload_queue.json"
    save_json(path, {"schema_version": 1, "publishes_automatically": False, "jobs": queue})
    print(f"Exported {len(queue)} approved upload jobs to {path}. Nothing was posted.")


def install() -> None:
    pipeline = ROOT / "run_pipeline.py"
    if not pipeline.is_file():
        raise FileNotFoundError(f"Can't locate pipeline: {pipeline}")
    source = pipeline.read_text(encoding="utf-8")
    if "# BEGIN SOCIAL_CAPTIONS_AUTO" in source:
        print("Social caption generation already integrated. No changes made.")
        return
    if 'str(ROOT / "add_headlines.py")' not in source:
        raise ValueError("Headline stage not installed yet. Run: python add_headlines.py install")
    lines = source.splitlines(keepends=True)
    matches = [i for i, item in enumerate(lines) if item.startswith('print(f"Finished. Created ')]
    if len(matches) != 1:
        raise ValueError("Couldn't safely find the end of the clip loop. Pipeline unchanged.")
    insertion = (
        '    # BEGIN SOCIAL_CAPTIONS_AUTO\n'
        '    posting_config = brief.with_name(f"{brief.stem}-posting.json")\n'
        '    upload_copy = ROOT / "finished" / f"{name}-upload.mp4"\n'
        '    if posting_config.is_file() and upload_copy.is_file():\n'
        '        subprocess.run(\n'
        '            [sys.executable, str(ROOT / "social_captions.py"), "generate",\n'
        '             str(upload_copy), "--config", str(posting_config)],\n'
        '            check=True,\n'
        '        )\n'
        '    else:\n'
        '        print(f"Posting captions deferred: config or upload video missing for {name}")\n'
        '    # END SOCIAL_CAPTIONS_AUTO\n\n'
    )
    updated = "".join(lines[:matches[0]]) + insertion + "".join(lines[matches[0]:])
    backup = pipeline.with_name("run_pipeline.py.before-social-captions")
    if not backup.exists():
        shutil.copy2(pipeline, backup)
    pipeline.write_text(updated, encoding="utf-8")
    try:
        py_compile.compile(str(pipeline), doraise=True)
    except Exception:
        pipeline.write_text(source, encoding="utf-8")
        raise
    print(f"Installed automatic post captions. Pipeline backed up at {backup}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate platform-specific post captions from completed short videos.")
    parser.add_argument("command", choices=("generate", "show", "approve", "queue", "install"))
    parser.add_argument("videos", nargs="?", help="An -upload.mp4 filename/path or quoted glob in finished/")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Campaign posting config JSON")
    parser.add_argument("--force", action="store_true", help="Regenerate and overwrite unapproved captions (review edits lost)")
    parser.add_argument("--platform", choices=PLATFORMS, help="Platform to approve")
    parser.add_argument("--confirm", action="store_true", help="Confirms you've personally reviewed caption, clip and posting rules")
    args = parser.parse_args()

    if args.command == "install":
        install()
        return
    if args.command == "queue":
        export_queue()
        return
    if not args.videos:
        parser.error("Specify an -upload.mp4 filename or quoted glob")
    videos = select_videos(args.videos)
    if not videos:
        parser.error(f"No matching upload-ready videos: {args.videos}")
    if args.command == "generate":
        config_path = Path(args.config).expanduser().resolve()
        config = load_config(config_path)
        for video in videos:
            generate_one(video, config, config_path, args.force)
    elif args.command == "show":
        for video in videos:
            record = load_record(video)
            print(f"\n{video.name}: {record['headline']}")
            for platform, info in record["platforms"].items():
                print(f"\n{platform.upper()} [{info['status']}]\n{info['caption']}\n")
    elif args.command == "approve":
        if not args.platform:
            parser.error("approve requires --platform tiktok|youtube|instagram")
        for video in videos:
            approve_one(video, args.platform, args.confirm)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"ERROR: {exc}")
