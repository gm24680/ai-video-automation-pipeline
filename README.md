# AI Video Automation Pipeline

A self-hosted, AI-assisted video processing and publishing automation system built with Python and deployed on Ubuntu Linux.

The platform is designed to transform long-form video content into short-form clips through a modular workflow that combines transcription, AI-assisted highlight selection, video editing, caption generation, quality validation, job management, and publishing integrations.

## Overview

This project explores how AI models, media processing tools, databases, and Linux services can work together to automate a multi-stage video production workflow.

The platform supports campaign-oriented content processing as well as more general video clipping workflows.

It also serves as a hands-on engineering project for learning Linux administration, Python development, automation, system architecture, and infrastructure reliability.

## Core Components

| Component | Purpose |
|---|---|
| Video ingestion | Accept video files for processing |
| AI transcription | Convert video audio into text using Whisper |
| Highlight selection | Identify potential clips using AI-assisted analysis |
| Video processing | Extract, crop, and format video using FFmpeg |
| Subtitle generation | Create and style captions for short-form output |
| Campaign management | Organize content processing around configurable requirements |
| Quality control | Validate technical properties of generated videos |
| Job management | Coordinate processing jobs and record their outcomes |
| Publishing integration | Support YouTube uploads and publishing workflows |
| Reporting | Generate processing summaries and operational reports |

## Technology Stack

- **Python:** Pipeline orchestration, scripting, and automation
- **Ubuntu Linux:** Self-hosted execution environment
- **FFmpeg / FFprobe:** Video editing and media inspection
- **Whisper:** Speech-to-text transcription
- **Ollama:** Local AI model execution
- **SQLite:** Job and publishing data persistence
- **systemd:** Linux service and scheduled-job management
- **Git:** Version control

## System Architecture

The processing workflow is organized into stages:

1. A video is supplied to the ingestion workflow.
2. The audio is transcribed.
3. AI-assisted processing identifies candidate highlights.
4. FFmpeg extracts and formats selected segments.
5. Post-processing generates styled subtitles, headlines, and platform-specific captions.
6. Quality checks examine generated media.
7. Job and publishing records track processing outcomes.
8. Publishing components manage supported upload workflows.

The system uses separate Python modules for major processing responsibilities, allowing different stages to be developed, tested, and maintained independently.

## Main Python Modules

| Module | Responsibility |
|---|---|
| `run_pipeline.py` | Main processing workflow |
| `transcribe.py` | Speech transcription |
| `make_clip.py` | Clip extraction |
| `make_vertical.py` | Vertical video formatting |
| `add_captions.py` | Caption processing |
| `style_captions.py` | Subtitle styling |
| `add_headlines.py` | Headline generation |
| `social_captions.py` | Platform-specific publishing text |
| `quality_control.py` | Media validation |
| `job_runner.py` | Individual job execution |
| `batch_runner.py` | Batch job processing |
| `campaign_manager.py` | Campaign configuration handling |
| `publishing_worker.py` | Publishing workflow management |
| `publishing_db.py` | Publishing database operations |
| `youtube_uploader.py` | YouTube integration |
| `morning_report.py` | Operational reporting |

## Development Focus

This project provides a practical environment for studying:

- Linux process and service management
- Python application design
- Local AI model integration
- Persistent data storage
- Background job processing
- Failure recovery and error handling
- API authentication and publishing integration
- System monitoring and automation

## Planned Improvements

- Automated unit and integration tests
- Docker-based deployment
- GitHub Actions CI/CD
- Enhanced application logging and monitoring
- More advanced multimodal video analysis
- Improved processing reliability and job recovery
- Cloud infrastructure experimentation using AWS

## Security and Repository Scope

This public repository is intended to contain application source code, documentation, and sanitized example configurations.

Authentication tokens, OAuth credentials, private campaign data, local databases, downloaded footage, and generated media are excluded from version control.

## Project Status

Active development.

The core video processing workflow has been demonstrated locally. Publishing integrations, reliability improvements, and additional automation features remain areas of ongoing development.

## Author

Computer Science student at the University of Houston–Clear Lake.

GitHub: [gm24680](https://github.com/gm24680)
