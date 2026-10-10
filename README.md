# Video Translate Agent

## Overview

This Skill translates a local video, cleans visible source subtitles or text overlays, creates a new dub, aligns audio and video, and renders a subtitled MP4. It is intended for creators localizing videos they may use. The Agent Skills root is this repository's `video-translate-agent/` folder, where `SKILL.md` lives; keep its scripts, Python package, configuration and documentation together.

## Key Features

- Local Faster Whisper transcription and RapidOCR overlay detection.
- Server-owned cleanup and alignment decisions through the bundled LuluLab Node.js client. Local STTN or OpenCV cleanup and FFmpeg rendering.
- Agent-local translation and review, ElevenLabs dubbing, and positioned ASS hard subtitles. MiniMax voice use is available when explicitly selected.
- Saved jobs and task IDs for recovery. Source and target media languages remain separate from the agent's interaction language.

The Skill does not clone a voice or preserve the source audio in the final dub. See [SKILL.md](SKILL.md) for the workflow and authorization rules.

## Requirements

- A file-capable Agent Skills host such as Codex or Claude Code. Confirm that agent's current user Skill directory; other agents need an equivalent file-based mechanism.
- Python 3.10+, Node.js 18+, and FFmpeg/FFprobe with libass/subtitles, atempo, libx264 and AAC. macOS and Windows are supported; a GPU is optional. The installer prepares a platform-specific `.venv` and Python dependencies.
- Network access for LuluLab policy requests, model/dependency downloads and the selected voice service. A LuluLab API Key is required at the first policy stage, not at installation. The bundled Node client is `scripts/lululab_cli.mjs`; no npm or `npx` install is needed.

## Installation

Ask your agent:

> Please install this LuluLab Skill into my current AI agent environment: https://github.com/LuluLab-AI/video-translate-agent . Follow the project's official installation instructions.

After reviewing the repository, copy the **whole** `video-translate-agent/` folder to the current agent's user Skill directory under the same name. If a version is already installed, compare versions and ask before replacement; leave unrelated Skills alone. Do not copy `.venv`, jobs, output videos, model weights or local credentials from another computer. In the final location, review and run `sh ./install.sh` on macOS or `./install.ps1` in Windows PowerShell. Then run the installed Python's `scripts/video_translate.py preflight --json`, reload the agent's Skill list, and verify discovery. The installer may open the existing ElevenLabs credential wizard.

## Quick Start

- “Use $video-translate-agent to translate this Chinese video into English, remove its original captions, dub it, and render English hard subtitles.”
- “Localize my English tutorial into Japanese with Japanese dubbing and positioned subtitles; reply to me in English.”

The agent should review source rights, target language, cleanup and voice choices under [SKILL.md](SKILL.md) before paid or remote steps.

## Configuration

Check the bundled client offline with `node --check scripts/lululab_cli.mjs`. At the policy stage, set `LULULAB_API_KEY` locally or use the existing `credential-set --provider lululab --stdin --json` flow through the Skill's Python CLI. The Key must pass through standard input and must never be put in command arguments, logs or GitHub. Legacy environment names are supported for migration. `LULULAB_NODE` may point to Node.js when `node` is absent from `PATH`. See [LuluLab API](docs/LULULAB_API.md) and [the Chinese setup guide](README.zh-CN.md).

## Supported Languages

The agent can interact in English, Chinese and other BCP-47 languages under [the existing interaction-language rules](docs/INTERACTION_LANGUAGE.md). Source and target video languages are independent. Translation and dubbing availability also depends on the selected voice provider.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Skill is not recognized | Verify the folder name and root `SKILL.md`, then reload the agent's Skill list. |
| CLI is missing | Confirm Node.js 18+ and `scripts/lululab_cli.mjs`; run `--help`. |
| API Key is missing | Configure the Key locally at the policy stage using the supported credential flow. |
| Network request fails | Check service access and recover a saved task ID before resubmitting. |
| Model or policy call fails | Inspect the saved job and task status; do not bypass the policy step or repeat a paid task blindly. |
| Dependency is missing | Run `preflight --json`; confirm Python packages and FFmpeg's libass/subtitles, libx264 and AAC support. |

## Support

Website: https://lululab.ai  
Email: contact@lululab.ai
