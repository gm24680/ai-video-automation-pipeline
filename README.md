# Scrubs Discovery Mode — configuration pack

This package provides three briefs, three posting configs, a **template** batch manifest, and a review CSV for the existing `~/clipping-agent` project on `agents`. No script modifications are included.

## Why one discovery pass?
The Scrubs humorous and emotional Vyro campaigns use the same approved footage. The overnight worker should discover a broad pool of candidates ONCE, then you watch each and classify it as `funny`, `emotional`, or `reject` before preparing each campaign's publication caption. The runner does not classify, publish, or submit to Vyro.

## Install
From the root of `~/clipping-agent`:
```
python3 -m zipfile -e scrubs_discovery_pack.zip .
```
This adds `campaigns/scrubs-discovery.md`, `campaigns/scrubs-discovery-posting.json`, `campaigns/scrubs-humor.md`, `campaigns/scrubs-humor-posting.json`, `campaigns/scrubs-emotional.md`, `campaigns/scrubs-emotional-posting.json`, `jobs/scrubs-discovery.example.toml`, `review/scrubs-decisions.csv` and this README. It does NOT overwrite `jobs/tonight.toml`.

Make a backup and copy the example before editing:
```
cp jobs/tonight.toml jobs/tonight.before-scrubs.toml
cp jobs/scrubs-discovery.example.toml jobs/tonight.toml
nano jobs/tonight.toml
```
List exact approved source video filenames present in `inbox/`, replacing both example names. Then:
```
source ~/local-ai-agents/.venv/bin/activate
python batch_runner.py --dry-run
systemctl --user start --no-block overnight-clips.service
cat reports/overnight-latest.md
```

## Important caveats of the current code
1. `run_pipeline.py` currently targets about one clip per five minutes, capped at 20 per video. This pack does NOT increase the count. That change requires modifying the pipeline's selection logic, and the model still may find fewer usable candidates.
2. `batch_runner.py` regards non-Outdoor-Adventure configurations as needing manual verification. Expect `needs_attention` even if render/QC succeeded. **That is appropriate for discovery candidates.**
3. The pipeline may generate provisional social captions even in discovery mode; all discovery platform configs are marked `enabled=false`. Do not approve, queue, or upload from this config.
4. The `required_promotional_text_options` field is for humans and a future enforcement hook: the current `social_captions.py` does NOT automatically enforce or append it. For any finally selected candidate, manually include exactly one required sentence plus `#ScrubsPartner` and **no other hashtag** before uploading. Use the appropriate humorous or emotional campaign rules.
5. Each source is processed only ONCE. Existing styled/upload-ready outputs cause the runner to skip reprocessing. Do NOT list the same source under two campaigns in the same TOML manifest; the runner rejects duplicates.
6. Approved footage must come exclusively from the Disney-authorized folder; AI tools must not train on or improve themselves using input footage. Local inference is preferred; check the actual privacy and training behavior of every installed tool. Keep final footage <=120s, with Instagram Reels >=15s. Original/native show audio is safest.
7. The completed file, headline and captions still require visual verification: comedy and emotional moments often depend on actions not available in speech transcripts.
8. No automated YouTube/TikTok/Instagram publishing or Vyro submission exists in this pack.
