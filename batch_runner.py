#!/usr/bin/env python3
"""Sequential, resumable batch runner for clipping-agent.

All input videos must already exist in ROOT/inbox. No automatic publishing occurs.
Requires Python >=3.11. Called from the same venv as run_pipeline.py.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import tomllib
import traceback

ALLOWED_VIDEO_EXTENSIONS = {'.mp4', '.mov', '.mkv', '.webm'}


def slugify(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def safe_filename(value: str, allowed_suffixes: set[str] | None = None) -> str:
    if not isinstance(value, str) or not value or value in {'.', '..'}:
        raise ValueError('File name must be nonempty')
    if Path(value).name != value or '/' in value or '\\' in value or '\x00' in value:
        raise ValueError(f'Only a filename (not a path) is allowed: {value!r}')
    if allowed_suffixes and Path(value).suffix.lower() not in allowed_suffixes:
        raise ValueError(f'Unsupported file type: {value!r}')
    return value


def existing_assets(root: Path, slug: str) -> dict:
    finished = root / 'finished'
    styled = sorted(finished.glob(f'{slug}-clip-*-styled.mp4'))
    upload = sorted(finished.glob(f'{slug}-clip-*-upload.mp4'))
    review_names = {p.name for p in (root / 'headlines' / 'review-needed').glob(f'{slug}-clip-*.txt')}
    styled_bases = {p.name.removesuffix('-styled.mp4') for p in styled}
    upload_bases = {p.name.removesuffix('-upload.mp4') for p in upload}
    missing = sorted(styled_bases - upload_bases)
    return {
        'styled': styled,
        'upload': upload,
        'missing': missing,
        'review_reports': len(review_names),
    }


def run_logged(cmd: list[str], *, cwd: Path, log_path: Path) -> int:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as log:
        log.write(f'Command: {" ".join(cmd)}\n')
        log.flush()
        proc = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                              env={**os.environ, 'PYTHONUNBUFFERED': '1'}, check=False)
        log.write(f'Exit status: {proc.returncode}\n')
    return proc.returncode


def qc_check(python: str, root: Path, video: Path, log_path: Path) -> bool:
    script = root / 'quality_control.py'
    if not script.is_file():
        with log_path.open('a') as log:
            log.write('QUALITY CONTROL SCRIPT MISSING\n')
        return False
    proc = subprocess.run([python, str(script), str(video)], cwd=root,
                          capture_output=True, text=True, check=False)
    with log_path.open('a') as log:
        log.write(f'QC for {video.name}:\n{proc.stdout}\n{proc.stderr}\n')
    if proc.returncode != 0:
        return False
    try:
        payload = json.loads(proc.stdout)
        return payload.get('passed') is True
    except (ValueError, TypeError):
        return False


def caption_check(root: Path, video: Path) -> bool:
    # Social captions use the filename prefix without the -upload suffix.
    prefix = video.name.removesuffix('-upload.mp4')
    return (root / 'post-captions' / f'{prefix}.json').is_file()


def atomic_write(path: Path, data: str) -> None:
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(data, encoding='utf-8')
    os.replace(temp, path)


def write_reports(root: Path, results: list[dict], started: str, finished: str | None = None) -> None:
    reports = root / 'reports'
    reports.mkdir(exist_ok=True)
    payload = {'started_utc': started, 'last_updated_utc': finished or utc_now(), 'jobs': results}
    atomic_write(reports / 'overnight-latest.json', json.dumps(payload, indent=2) + '\n')
    lines = ['# Overnight clipping report', '', f'Started (UTC): {started}',
             f'Last updated (UTC): {payload["last_updated_utc"]}', '',
             '| Video | Status | Upload MP4s | Explanation |', '|---|---|---:|---|']
    for record in results:
        note = record.get('note', '').replace('|', '/').replace('\n', ' ')
        lines.append(f'| {record["video"]} | {record["status"]} | {record.get("upload_count", 0)} | {note} |')
    lines.extend(['', 'All clips require human review before publication.',
                  'This batch runner does not publish or submit videos to campaigns.', ''])
    atomic_write(reports / 'overnight-latest.md', '\n'.join(lines))


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def build_queue(manifest: dict) -> list[dict]:
    campaigns = manifest.get('campaigns')
    if not isinstance(campaigns, list) or not campaigns:
        raise ValueError('Manifest needs one or more [[campaigns]] blocks')
    jobs: list[dict] = []
    seen: set[str] = set()
    for entry in campaigns:
        if not isinstance(entry, dict):
            raise ValueError('Each campaign must be a table')
        name = entry.get('name', 'Unnamed campaign')
        brief = safe_filename(entry.get('brief', ''), {'.md'})
        config = safe_filename(entry.get('posting_config', ''), {'.json'})
        videos = entry.get('videos')
        if not isinstance(videos, list) or not videos:
            raise ValueError(f'Campaign {name}: videos must be a nonempty list')
        for video in videos:
            video = safe_filename(video, ALLOWED_VIDEO_EXTENSIONS)
            if video in seen:
                raise ValueError(f'Duplicate video in batch: {video}')
            seen.add(video)
            jobs.append({'campaign': name, 'video': video, 'brief': brief, 'config': config})
    return jobs


def process_job(root: Path, python: str, spec: dict, *, dry_run: bool, timestamp: str) -> dict:
    name = spec['video']
    slug = slugify(Path(name).stem)
    root_inbox = root / 'inbox'
    video = root_inbox / name
    brief = root / 'campaigns' / spec['brief']
    config = root / 'campaigns' / spec['config']
    log_path = root / 'logs' / f'job-batch-{timestamp}-{slug}.log'
    result = {'video': name, 'campaign': spec['campaign'], 'status': 'pending',
              'upload_count': 0, 'log': str(log_path), 'note': ''}
    if video.is_symlink() or not video.is_file():
        result.update(status='failed', note='Source video missing from inbox')
        return result
    if brief.is_symlink() or not brief.is_file():
        result.update(status='failed', note='Campaign brief missing')
        return result
    if config.is_symlink() or not config.is_file():
        result.update(status='failed', note='Campaign posting configuration missing')
        return result
    assets = existing_assets(root, slug)
    # Avoid expensive duplicate work. Partially processed video needs a targeted recovery.
    if assets['styled'] or assets['upload']:
        result['note'] = 'Existing files detected; did not rerun source video'
        print(f'SKIP existing: {name} ({len(assets["upload"])} upload files)', flush=True)
    elif dry_run:
        result.update(status='would_process', note='Source and configuration validated')
        print(f'DRY RUN would process: {name}', flush=True)
        return result
    else:
        print(f'PROCESSING: {name}', flush=True)
        # job_runner.py manages the existing SQLite jobs database and QC.
        runner = root / 'job_runner.py'
        if not runner.is_file():
            result.update(status='failed', note='job_runner.py is missing')
            return result
        rc = run_logged([python, str(runner), str(video), str(brief)], cwd=root, log_path=log_path)
        result['pipeline_exit_code'] = rc
        assets = existing_assets(root, slug)

    if dry_run:
        result.update(status='existing', upload_count=len(assets['upload']),
                      note='Existing outputs; no changes made')
        return result

    if not assets['upload']:
        result.update(status='needs_attention' if assets['styled'] else 'failed',
                      note='No upload-ready videos; check headline review and job log')
        return result

    # Ensure every available upload file gets the correct campaign's posting config.
    caption_failures: list[str] = []
    qc_failures: list[str] = []
    for clip in assets['upload']:
        if not qc_check(python, root, clip, log_path):
            qc_failures.append(clip.name)
        # Existing caption metadata could have been generated with another config.
        # Never overwrite an already prepared caption; flag for review instead.
        if not caption_check(root, clip):
            rc = run_logged([python, str(root / 'social_captions.py'), 'generate',
                             str(clip), '--config', str(config)], cwd=root, log_path=log_path)
            if rc != 0 or not caption_check(root, clip):
                caption_failures.append(clip.name)
    assets = existing_assets(root, slug)
    result['upload_count'] = len(assets['upload'])
    problems: list[str] = []
    if assets['missing']:
        problems.append(f'{len(assets["missing"])} styled clips lack upload render')
    if qc_failures:
        problems.append(f'{len(qc_failures)} failed quality control')
    if caption_failures:
        problems.append(f'{len(caption_failures)} missing social captions')
    if result.get('pipeline_exit_code', 0) != 0:
        problems.append(f'job_runner exited {result["pipeline_exit_code"]}; inspect job log')
    if spec['config'] != 'outdoor-adventure-shorts-posting.json':
        problems.append('Nondefault campaign caption configuration needs manual verification')
    if problems:
        result.update(status='needs_attention', note='; '.join(problems))
    else:
        result.update(status='ready_for_review',
                      note='Upload videos and caption manifests available; human approval required')
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description='Overnight batch clipping queue; does not publish videos')
    ap.add_argument('--manifest', default='jobs/tonight.toml')
    ap.add_argument('--root', default=str(Path(__file__).resolve().parent))
    ap.add_argument('--python', default=sys.executable,
                    help='Python interpreter with ollama and clipping dependencies installed')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    root = Path(args.root).expanduser().resolve()
    manifest_path = Path(args.manifest).expanduser()
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path
    if not manifest_path.is_file():
        print(f'Manifest missing: {manifest_path}', file=sys.stderr)
        return 2
    with manifest_path.open('rb') as file:
        try:
            queue = build_queue(tomllib.load(file))
        except (ValueError, tomllib.TOMLDecodeError) as e:
            print(f'Invalid manifest: {e}', file=sys.stderr)
            return 2
    python = str(Path(args.python).expanduser().resolve())
    if not Path(python).is_file():
        print(f'Python interpreter not found: {python}', file=sys.stderr)
        return 2
    lock_dir = root / 'logs'
    lock_dir.mkdir(parents=True, exist_ok=True)
    # Also take the lock already used by JARVIS's individual job launcher.
    # The two entry points then cannot launch expensive overlapping jobs.
    with (lock_dir / 'overnight-batch.lock').open('a+') as batch_lock, \
         (lock_dir / 'clipping-job.lock').open('a+') as clipping_lock:
        try:
            fcntl.flock(batch_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(clipping_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('A JARVIS clipping job or overnight batch is already active.', file=sys.stderr)
            return 3
        timestamp = dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d-%H%M%S')
        started = utc_now()
        results: list[dict] = []
        print(f'Queued videos: {len(queue)}', flush=True)
        for i, item in enumerate(queue, 1):
            print(f'[{i}/{len(queue)}] {item["campaign"]}: {item["video"]}', flush=True)
            try:
                result = process_job(root, python, item, dry_run=args.dry_run, timestamp=timestamp)
            except Exception as e:
                result = {'video': item['video'], 'campaign': item['campaign'],
                          'status': 'failed', 'upload_count': 0,
                          'note': f'Runner exception: {type(e).__name__}: {e}'}
                traceback.print_exc()
            results.append(result)
            print(f'  => {result["status"]}: {result["note"]}', flush=True)
            if not args.dry_run:
                write_reports(root, results, started)
        if not args.dry_run:
            write_reports(root, results, started, utc_now())
            print(f'Morning report: {root / "reports" / "overnight-latest.md"}', flush=True)
    return 0 if all(r['status'] in ('ready_for_review', 'existing', 'would_process') for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
