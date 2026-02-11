# DEPLOYMENT Guide - JARVIS MK1 Lite

## VPS Information

| Parameter | Value |
|-----------|-------|
| **IP** | `<YOUR_VPS_IP>` |
| **User** | root |
| **SSH Port** | 22 |
| **OS** | Ubuntu 22.04.5 LTS |
| **CPU** | 16 cores (AMD EPYC 7443P) |
| **RAM** | 64GB |
| **Disk** | 600GB NVMe SSD |

## Prerequisites (Installed)

| Component | Version |
|-----------|---------|
| Python | 3.11.14 |
| Node.js | v20.19.6 |
| NPM | 10.8.2 |
| Claude Code CLI | 2.0.76 |
| Docker | 29.1.3 |
| Git | 2.34.1 |
| GitHub CLI | 2.83.2 |

## SSH Connection

```bash
# From Windows (with ed25519 key)
ssh -i "~/.ssh/id_ed25519" root@<YOUR_VPS_IP>

# Or add to ~/.ssh/config:
Host jarvis-vps
    HostName <YOUR_VPS_IP>
    User root
    IdentityFile ~/.ssh/id_ed25519
```

## Deployment Steps

### 1. Clone Repository

```bash
cd /opt
git clone https://github.com/your-repo/JARVIS-MK1.git jarvis-mk1
cd /opt/jarvis-mk1
```

### 2. Create Virtual Environment

```bash
python3.11 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
# Upgrade pip
pip install --upgrade pip

# Install poetry
pip install poetry

# Install project dependencies with all extras
poetry install --all-extras
```

### 4. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit with your credentials
nano .env
```

Required environment variables:

```env
# Telegram Bot
TELEGRAM_BOT_TOKEN=your_bot_token_from_botfather

# Anthropic API (optional if Claude CLI is authorized)
ANTHROPIC_API_KEY=your_anthropic_api_key

# Security - Allowed user IDs
ALLOWED_USER_IDS=[<YOUR_TELEGRAM_USER_ID>]

# Claude Settings
CLAUDE_MODEL=claude-sonnet-4-5-20250929
CLAUDE_MAX_TOKENS=60000
CLAUDE_TIMEOUT=600

# Paths
WORKSPACE_DIR=/home/projects
SYSTEM_PROMPT_PATH=prompts/system.md

# Logging
LOG_LEVEL=INFO

# Telethon (for voice transcription)
TELETHON_API_ID=your_api_id
TELETHON_API_HASH=your_api_hash
TELETHON_PHONE=+your_phone_number
TELETHON_SESSION_NAME=jarvis_premium
VOICE_TRANSCRIPTION_ENABLED=true
```

### 5. Create Workspace Directory

```bash
mkdir -p /home/projects
```

### 6. Restore Telethon Session (if exists)

```bash
# If session was backed up to /root
cp /root/jarvis_premium.session /opt/jarvis-mk1/
```

### 7. Claude Code Authorization

Claude Code should already be authorized on the VPS. To verify:

```bash
claude --version
```

If not authorized, run interactively:

```bash
claude
# Follow the OAuth flow prompts
```

### 8. Telethon Session Setup

For first-time Telethon setup:

```bash
cd /opt/jarvis-mk1
source .venv/bin/activate
python -c "
from telethon import TelegramClient
import asyncio

async def main():
    client = TelegramClient('jarvis_premium', API_ID, 'API_HASH')
    await client.start(phone='+PHONE_NUMBER')
    print('Session created successfully!')
    await client.disconnect()

asyncio.run(main())
"
# Enter the code sent to your Telegram
```

### 9. Create Systemd Service

```bash
cat > /etc/systemd/system/jarvis.service << 'EOF'
[Unit]
Description=JARVIS MK1 Lite Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/jarvis-mk1
Environment=PATH=/opt/jarvis-mk1/.venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=/opt/jarvis-mk1/.venv/bin/python -m jarvis_mk1_lite
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
```

### 10. Enable and Start Service

```bash
systemctl daemon-reload
systemctl enable jarvis
systemctl start jarvis
```

### 11. Check Service Status

```bash
systemctl status jarvis
journalctl -u jarvis -f
```

## Testing

### Run Unit Tests

```bash
cd /opt/jarvis-mk1
source .venv/bin/activate
pytest tests/ -v
```

### Run Tests with Coverage

```bash
pytest tests/ -v --cov=src/jarvis_mk1_lite --cov-report=term-missing
```

### Run E2E Tests

```bash
pytest tests/test_e2e.py -v
```

## Management Commands

```bash
# View logs
journalctl -u jarvis -f

# Restart service
systemctl restart jarvis

# Stop service
systemctl stop jarvis

# Check status
systemctl status jarvis

# Pull updates and restart
cd /opt/jarvis-mk1
git pull
source .venv/bin/activate
pip install -e .
systemctl restart jarvis
```

## Git Configuration (for pushing fixes)

```bash
# Configure git credentials
git config --global user.email "your@email.com"
git config --global user.name "Your Name"

# Store GitHub token
git config --global credential.helper store
echo "https://YOUR_GITHUB_TOKEN@github.com" > ~/.git-credentials
```

## Troubleshooting

### Bot not responding

1. Check service status: `systemctl status jarvis`
2. Check logs: `journalctl -u jarvis -n 100`
3. Verify bot token is correct in `.env`
4. Verify your Telegram ID is in `ALLOWED_USER_IDS`

### Claude Code errors

1. Check Claude CLI authorization: `claude --version`
2. Re-authorize if needed: `claude` (interactive)
3. Check API key in `.env`

### Telethon errors

1. Check session file exists: `ls -la /opt/jarvis-mk1/jarvis_premium.session`
2. Verify API credentials in `.env`
3. Re-create session if corrupt

### Permission errors

All operations run as root for maximum autonomy.

```bash
chown -R root:root /opt/jarvis-mk1
```

## Quick Deploy Script

```bash
#!/bin/bash
set -e

cd /opt
rm -rf jarvis-mk1

git clone https://github.com/your-repo/JARVIS-MK1.git jarvis-mk1
cd jarvis-mk1

python3.11 -m venv .venv
source .venv/bin/activate

pip install --upgrade pip
pip install poetry
poetry install --all-extras

# Restore session if backed up
[ -f /root/jarvis_premium.session ] && cp /root/jarvis_premium.session ./

# Copy environment
[ -f /root/.env.jarvis ] && cp /root/.env.jarvis .env

systemctl restart jarvis
systemctl status jarvis
```
