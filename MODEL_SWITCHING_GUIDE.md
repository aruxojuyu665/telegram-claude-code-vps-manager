# Model Switching Feature - User Guide

## 🎯 Overview

The bot now supports **per-session model switching**, allowing you to use different Claude models for different tasks:

- **Claude Opus 4.5** - Most capable, best for complex reasoning
- **Claude Sonnet 4.5** - Default, balanced performance and cost
- **Claude Haiku 4.5** - Fastest, best for simple tasks

## 📱 Using the /model Command

### View Current Model
```
/model
```
Shows your current model and available options.

### Switch Models
```
/model opus     # Switch to Claude Opus 4.5
/model sonnet   # Switch to Claude Sonnet 4.5 (default)
/model haiku    # Switch to Claude Haiku 4.5
```

### Check Status
```
/status
```
Shows your current model among other system info.

## 🔧 How It Works

1. **Per-Session**: Each session can use a different model
2. **Persistent**: Model choice persists across bot restarts
3. **Independent**: Switching sessions switches models automatically
4. **Default**: New sessions start with Sonnet 4.5

## 📋 Command Availability

If you don't see `/model` in your command list:

1. **Wait a few minutes** - Telegram may need time to sync
2. **Restart Telegram app** - Clear the command cache
3. **Type manually** - Just type `/model` and it will work
4. **Clear cache** - Settings → Data and Storage → Clear Cache

## ✅ Verification

The feature is fully functional on the backend. You can verify by:

1. Sending `/model` (even if not in autocomplete)
2. Checking `/status` for current model
3. Switching models and seeing confirmation

## 🧪 Technical Verification

Run the test script to verify backend functionality:
```bash
cd /opt/jarvis-dev
python test_model_command.py
```

All tests should pass ✅

## 📊 Commands Summary

All 11 bot commands are registered:

| Command | Description |
|---------|-------------|
| /start | Show welcome message |
| /help | Detailed help and examples |
| /status | System and session status |
| /sessions | List and manage sessions |
| /new | Create new session |
| /switch | Switch active session |
| /kill | Delete a session |
| **/model** | **Change Claude model (opus/sonnet/haiku)** ⭐ |
| /wide_context | Batch multiple messages |
| /verbose | Toggle real-time action logs |
| /metrics | View usage statistics |

## 🎨 Example Usage

```
You: /model
Bot: Current model: Sonnet 4.5
     Available models:
     • /model opus - Claude Opus 4.5 (most capable)
     • /model sonnet - Claude Sonnet 4.5 (default, balanced)
     • /model haiku - Claude Haiku 4.5 (fastest)

You: /model opus
Bot: Model changed to: Opus 4.5
     Session: main
     Next message will use the new model.

You: Write me a complex algorithm
Bot: [Uses Opus 4.5 for best quality]

You: /model haiku
Bot: Model changed to: Haiku 4.5

You: What's 2+2?
Bot: [Uses Haiku 4.5 for speed]
```

## 🚀 Next Steps

1. Try the `/model` command in Telegram
2. Switch between models for different tasks
3. Check `/status` to verify your current model
4. Create different sessions for different model preferences

## 📝 Notes

- Model switching is **immediate** - next message uses the new model
- Each session remembers its model choice
- Default for new sessions is Sonnet 4.5
- Model choice survives bot restarts
- Backend is fully functional - client sync may take time

---

**Status**: Feature fully implemented and tested
**Version**: 1.3.0+
