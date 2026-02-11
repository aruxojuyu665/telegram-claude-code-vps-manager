# Scripts

This directory contains utility scripts for testing and development.

## test_voice.py

E2E test script for voice transcription functionality.

### Features

- **Uses existing bot session** - no separate authorization needed
- **Forward from Saved Messages** - find voice message in your saved messages (default)
- **Send from file** - alternative mode if you have a voice file
- **Auto-discovery** - finds session file in project root, cwd, or `/opt/jarvis-mk1`

### Prerequisites

1. **Bot must have created a Telethon session:**
   ```bash
   # The bot creates jarvis_premium.session on first run
   python -m jarvis_mk1_lite
   ```

2. **For --use-saved mode (default):**
   - Save at least one voice message to "Saved Messages" in Telegram
   - The script will find and forward it to the bot

3. **For --voice-file mode:**
   - Have an OGG/Opus audio file ready

### Usage

```bash
# Default: Forward first voice from Saved Messages
python scripts/test_voice.py

# Explicitly use saved messages mode
python scripts/test_voice.py --use-saved

# Send from file instead
python scripts/test_voice.py --voice-file path/to/voice.ogg

# Custom session path (without .session extension)
python scripts/test_voice.py --session /opt/jarvis-mk1/jarvis_premium

# Custom timeout
python scripts/test_voice.py --timeout 120
```

### Expected Output

```
[INFO] Loaded configuration from .env
[INFO] Found session file: /opt/jarvis-mk1/jarvis_premium.session
==================================================
[INFO] Voice Transcription E2E Test
==================================================
[INFO] Mode: Forward from Saved Messages
[INFO] Bot ID: <YOUR_BOT_ID>
[INFO] Session: /opt/jarvis-mk1/jarvis_premium
[INFO] Timeout: 60.0s
==================================================
[INFO] Connected to Telegram as: @username (id=123456)
[INFO] Found bot: @jarvis_bot
[INFO] Searching for voice message in Saved Messages (limit=100)...
[INFO] Found voice message: id=12345, date=2025-12-30 12:00:00
[INFO] Forwarding voice message to bot...
[INFO] Voice message forwarded, msg_id=67890
[INFO] Waiting for bot response (timeout: 60.0s)...
[INFO] Bot response received:
--------------------------------------------------
Transcribed: Hello JARVIS...
--------------------------------------------------
[SUCCESS] Voice transcription E2E test passed!
```

### Troubleshooting

| Error | Solution |
|-------|----------|
| `Session not authorized` | Run the bot first to create and authorize the session |
| `No voice message found in Saved Messages` | Save a voice message to "Saved Messages" in Telegram |
| `Bot did not respond` | Check that the bot is running |
| `Voice file not found` | Provide valid path with `--voice-file` |
| `Telegram Premium required` | The Telethon account needs Telegram Premium for transcription |

### Environment Variables

Required in `.env`:
```
TELETHON_API_ID=your_api_id
TELETHON_API_HASH=your_api_hash
BOT_ID=<YOUR_BOT_ID>
TELETHON_SESSION_NAME=jarvis_premium  # optional, default
```
