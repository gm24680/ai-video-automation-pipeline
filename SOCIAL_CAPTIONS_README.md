# Social posting captions — agentlab integration

This is **post text** for TikTok, YouTube Shorts, and Instagram, **not** the on-screen subtitles already burned into each MP4. It reads each individual clip's reviewed on-screen headline and Whisper `.srt` transcript, asks `qwen3:4b` for a clip-specific social description, and appends campaign-required tags and disclosures. If Ollama fails, it produces a headline-based fallback clearly marked for review.

## Files

- `social_captions.py` — caption generation, human review/approval, and upload-queue export.
- `campaigns/outdoor-adventure-shorts-posting.json` — campaign/platform-specific tags and disclosure settings.
- Outputs under `post-captions/` — `.txt` captions for each platform, a per-clip `.json` manifest, and eventually `upload_queue.json`.

The config currently enables TikTok and YouTube. Instagram is disabled because the provided screenshot showed no remaining Instagram budget. Recheck budget and campaign availability before changing that setting; screenshot values may have changed.

## Initial use on `agentlab`

```bash
cd ~/vyro-private
source ~/local-ai-agents/.venv/bin/activate
python -m py_compile social_captions.py
python social_captions.py generate '19-day-solo-video-1-*-upload.mp4' \
    --config campaigns/outdoor-adventure-shorts-posting.json
python social_captions.py show '19-day-solo-video-1-*-upload.mp4'
```

The command creates files such as:

```text
post-captions/19-day-solo-video-1-clip-01-94548-96760-tiktok.txt
post-captions/19-day-solo-video-1-clip-01-94548-96760-youtube.txt
post-captions/19-day-solo-video-1-clip-01-94548-96760-instagram.txt
post-captions/19-day-solo-video-1-clip-01-94548-96760.json
```

You can edit `.txt` files with Nano before approving. Use a specific filename or quoted glob. Regeneration normally skips already-created caption sets so manual edits are not lost. `--force` regenerates only sets that have not been approved.

## Add to the main video pipeline

The existing `add_headlines.py` stage must already be integrated. Check or install it first:

```bash
python add_headlines.py install
python social_captions.py install
python -m py_compile run_pipeline.py
```

`social_captions.py install` backs up `run_pipeline.py` before inserting a new stage at the end of its existing clip loop. It is designed to be safe to rerun. The new stage finds a posting config next to the selected campaign brief (example `outdoor-adventure-shorts.md` → `outdoor-adventure-shorts-posting.json`) and generates social post captions for each produced `-upload.mp4`. If the headline render or campaign posting config is missing, it logs a deferral rather than inventing a posting task.

## Approve for eventual uploading

Only approve a caption after reviewing the clip, the post text, the required disclosures, and **current** campaign eligibility and budget.

```bash
python social_captions.py approve \
    '19-day-solo-video-1-clip-01-94548-96760-upload.mp4' \
    --platform tiktok --confirm
python social_captions.py queue
```

`post-captions/upload_queue.json` then holds approved jobs for a future uploader. **No videos are published by this script.** Actual publishing will require authorized platform API integrations, explicit account consent, rate limiting, retry logic, and duplicate-post protection. Do not assume an upload is accepted into the paid campaign merely because the platform accepts the post; campaign review/submission is a distinct process.

## Other campaigns

Copy and adapt `campaigns/outdoor-adventure-shorts-posting.json`, including mentions, hashtags, disclosure and per-platform enabled flags. Give it the same stem as the campaign brief with `-posting.json` appended, so `run_pipeline.py` can find it. Verify each campaign's actual requirements rather than reusing Arctic tags.

## Reminders

- Never store social login credentials or access tokens in the campaign JSON or a public GitHub repository.
- Do not remove `#VyroPartner` from the sample without checking the campaign's disclosure policy.
- TikTok/Instagram need the `@essentialwilderness` mention for this campaign according to the supplied screenshots.
- Instagram is disabled by default in this specific config; change only after confirming a current eligible budget.
- A human review gate remains until a compliant, authorized publishing worker is implemented.
