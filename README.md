# JARVIS MK1 Lite

> Minimalist Telegram interface for Claude Code on Ubuntu VPS

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

JARVIS MK1 Lite is a minimalist Telegram bot that provides a secure interface to Claude Code SDK on Ubuntu VPS. Following First Principles, it delegates all heavy lifting to Claude Code, focusing on:

- **Telegram Interface**: Simple message handling via aiogram
- **Socratic Gate**: Security layer for confirming dangerous commands
- **Claude Bridge**: Direct passthrough to Claude Code SDK
- **Structured Logging**: Production-ready logging with structlog

## Philosophy

> "The best part is no part. The best process is no process." — Elon Musk

This project follows KISS (Keep It Simple, Stupid) and DRY (Don't Repeat Yourself) principles:
- We don't duplicate what Claude Code SDK already does
- Minimal code, maximum functionality
- Security through simplicity (whitelist + Socratic confirmation)

## Architecture

```
[Telegram] --> [Bot] --> [Rate Limiter] --> [Socratic Gate] --> [Claude Bridge] --> [Claude Code SDK]
                  |                                                      |
                  v                                                      v
             [Metrics] <------------------------------------------------+
```

### Components

| Component | Responsibility |
|-----------|---------------|
| `bot.py` | Telegram handlers (aiogram) |
| `safety.py` | Socratic Gate — multi-level risk assessment (SAFE/MODERATE/DANGEROUS/CRITICAL) |
| `bridge.py` | Claude Code SDK integration |
| `config.py` | Pydantic Settings configuration |
| `metrics.py` | Application metrics, health checks and rate limiting |
| `chunker.py` | Smart message splitting for Telegram limits |
| `file_processor.py` | PDF/text file handling |
| `file_sender.py` | File download/upload management |
| `transcription.py` | Telethon voice transcription |
| `__main__.py` | Entry point with structlog and signal handlers |

## Requirements

- Python 3.11+
- Ubuntu VPS with Claude Code SDK installed
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Anthropic API Key (optional if Claude CLI is authorized via OAuth)

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/JARVIS-MK1.git
cd JARVIS-MK1

# Install dependencies via Poetry
poetry install

# Configure environment
cp .env.example .env
# Edit .env with your credentials
```

## Configuration

Create a `.env` file with the following variables:

```env
# Required
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
ANTHROPIC_API_KEY=your_anthropic_api_key

# Security — whitelist of allowed user IDs (JSON array)
ALLOWED_USER_IDS=[123456789, 987654321]

# Claude Code settings (optional)
CLAUDE_MODEL=claude-sonnet-4-5-20250929
CLAUDE_MAX_TOKENS=16384
CLAUDE_TIMEOUT=300

# Paths (optional)
WORKSPACE_DIR=/home/projects
SYSTEM_PROMPT_PATH=prompts/system.md

# Logging (optional)
LOG_LEVEL=INFO
```

### Configuration Options

| Variable | Description | Default |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | Bot token from @BotFather | Required |
| `ANTHROPIC_API_KEY` | Anthropic API key | Required |
| `ALLOWED_USER_IDS` | JSON array of allowed Telegram user IDs | `[]` |
| `CLAUDE_MODEL` | Claude model identifier | `claude-sonnet-4-5-20250929` |
| `CLAUDE_MAX_TOKENS` | Maximum tokens for responses | `16384` |
| `CLAUDE_TIMEOUT` | Timeout in seconds | `300` |
| `WORKSPACE_DIR` | Working directory for Claude | `/home/projects` |
| `SYSTEM_PROMPT_PATH` | Path to system prompt file | `prompts/system.md` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `RATE_LIMIT_MAX_TOKENS` | Max tokens per user for rate limiting | `10` |
| `RATE_LIMIT_REFILL_RATE` | Token refill rate per second | `0.5` |
| `RATE_LIMIT_ENABLED` | Enable rate limiting | `true` |
| `SESSION_EXPIRY_SECONDS` | Time in seconds before session expires | `3600` |
| `MAX_SESSIONS` | Maximum sessions (LRU eviction) | `1000` |
| `TELETHON_API_ID` | Telegram API ID (for voice transcription) | - |
| `TELETHON_API_HASH` | Telegram API Hash | - |
| `TELETHON_PHONE` | Phone number for Telethon | - |
| `TELETHON_SESSION_NAME` | Telethon session filename | `jarvis_premium` |
| `VOICE_TRANSCRIPTION_ENABLED` | Enable voice transcription | `false` |

## Voice Transcription

JARVIS MK1 Lite supports voice message and video note transcription via Telegram Premium API.

### Requirements

- Telegram Premium account (for transcription)
- Telethon library: `pip install jarvis-mk1-lite[voice]`
- API credentials from [my.telegram.org](https://my.telegram.org)

### Setup

1. **Get API credentials:**
   - Go to https://my.telegram.org
   - Create an application
   - Get `api_id` and `api_hash`

2. **Configure `.env`:**
   ```env
   TELETHON_API_ID=12345
   TELETHON_API_HASH=abc123...
   TELETHON_PHONE=+1234567890
   VOICE_TRANSCRIPTION_ENABLED=true
   ```

3. **First-time authorization:**
   On first launch, Telethon will ask for a verification code from Telegram.
   The session is saved to `jarvis_premium.session`.

### How It Works

```
Voice message → Aiogram Bot → Telethon (Premium) → TranscribeAudio API → Text → Claude
```

- Voice messages are automatically transcribed
- Transcribed text is sent to Claude
- Video notes (round videos) are supported
- An error message is shown if Premium is unavailable

## Session Management

JARVIS MK1 Lite manages Claude dialogue sessions with automatic expiry and LRU eviction.

### Session Expiry

Sessions automatically expire after `SESSION_EXPIRY_SECONDS` of inactivity (default: 1 hour).
- Cleanup occurs on each message to Claude
- Expired sessions are logged for monitoring
- Users start a new dialogue after expiry

### LRU Eviction

When the `MAX_SESSIONS` limit is reached, least recently used sessions are evicted.
- Protects against memory leaks in long-running deployments
- Active users retain their sessions
- Evicted sessions are logged with reason

### Session Statistics

View session statistics via the `/metrics` command:
- Number of active sessions
- Number of expired sessions
- Number of evicted sessions
- Age of the oldest session

### Configuration Recommendations

| Scenario | `SESSION_EXPIRY_SECONDS` | `MAX_SESSIONS` |
|----------|--------------------------|----------------|
| Default | `3600` (1 hour) | `1000` |
| High load | `1800` (30 min) | `5000-10000` |
| Long dialogues | `7200-86400` (2-24 hours) | `1000` |
| Low-memory VPS | `1800` (30 min) | `100-500` |

## Usage

```bash
# Run the bot
poetry run python -m jarvis_mk1_lite

# Or directly via Python
python -m jarvis_mk1_lite
```

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Welcome message and bot info |
| `/help` | Detailed help with examples |
| `/status` | System status and session info |
| `/metrics` | Application metrics (uptime, requests, errors) |
| `/new` | Start a new dialogue session |

## Security Features

### Whitelist Access Control
Only users listed in `ALLOWED_USER_IDS` can interact with the bot. Unauthorized access attempts are silently ignored.

### Socratic Gate — Multi-Level Risk System

The Socratic Gate implements a four-level security system:

| Risk Level | Action | Example Commands |
|------------|--------|-----------------|
| **SAFE** | Execute immediately | `ls`, `pwd`, `echo` |
| **MODERATE** | Show warning, execute | `apt remove`, `pip uninstall`, `git push --force` |
| **DANGEROUS** | Requires YES/NO confirmation | `rm -rf ./dir`, `shutdown`, `iptables -F` |
| **CRITICAL** | Requires exact confirmation phrase | `rm -rf /`, `mkfs.ext4`, `DROP DATABASE` |

Critical operations require typing: `CONFIRM CRITICAL OPERATION`

## Development

```bash
# Install dev dependencies
poetry install --with dev

# Run tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov=src/jarvis_mk1_lite --cov-report=term-missing

# Type checking
poetry run mypy src/ tests/

# Linting
poetry run ruff check src/ tests/

# Formatting
poetry run black src/ tests/
```

## Project Status

- **Current version**: 1.3.2
- **Status**: Production Ready
- **Tests**: 1008+ unit/integration + 20+ live E2E
- **Coverage**: 71%

## Documentation

- [Technical Specification](docs/prompts/JARVIS_MK1_Lite_Technical_Specification.md)
- [Deployment Guide](DEPLOYMENT.md)
- [Changelog](CHANGELOG.md)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Production Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the full deployment guide.

### Quick Start

1. **Clone the repository:**
   ```bash
   git clone https://github.com/yourusername/JARVIS-MK1.git
   cd JARVIS-MK1
   ```

2. **Configure environment:**
   ```bash
   cp .env.production.example .env
   # Edit .env with production values
   nano .env
   ```

3. **Run the install script:**
   ```bash
   sudo bash deploy/install.sh
   ```

### Service Management

```bash
# Start the service
sudo systemctl start jarvis

# Stop the service
sudo systemctl stop jarvis

# Restart the service
sudo systemctl restart jarvis

# Check status
sudo systemctl status jarvis

# View logs
sudo journalctl -u jarvis -f

# Enable autostart
sudo systemctl enable jarvis
```

## Security

- **NEVER** commit secrets to git
- Use `.env` files (listed in `.gitignore`)
- Report security issues privately
- Always use whitelist for access control
- Regularly review Socratic Gate patterns

## License

MIT License — see [LICENSE](LICENSE) file for details.

---

<p align="center">
<sub>JARVIS MK1 Lite — Built on First Principles</sub>
</p>
