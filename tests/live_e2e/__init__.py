"""Live E2E tests using real Telegram via Telethon.

This module provides End-to-End tests that interact with real Telegram
through a real user account (Telethon) - NO MOCKS.

Requirements:
- Telethon installed: pip install telethon
- Telegram API credentials from my.telegram.org
- Bot must be running on VPS

Environment variables:
- LIVE_E2E_API_ID: Telegram API ID
- LIVE_E2E_API_HASH: Telegram API Hash
- LIVE_E2E_PHONE: Phone number for auth (+7XXXXXXXXXX)
- LIVE_E2E_BOT: Bot username (@jarvis_mk1_bot)
"""
