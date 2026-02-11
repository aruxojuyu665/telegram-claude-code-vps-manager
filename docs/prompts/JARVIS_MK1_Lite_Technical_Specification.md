# JARVIS MK1 Lite: Technical Specification

> **Version:** 1.0 | **Architecture:** Minimalist monolith | **Python:** 3.11+

---

## Critical Principles
- **First Principles** — make decisions based on Elon Musk's First Principles thinking
- **SOLID Principles** — Single Responsibility, Open/Closed, Liskov Substitution, Interface Segregation, Dependency Inversion
- **KISS (Keep It Simple, Stupid)** — maximum simplicity
- **DRY (Don't Repeat Yourself)** — avoid duplication

---

## 1. PROJECT PHILOSOPHY

### First Principles

> "The best part is no part. The best process is no process." — Elon Musk

**JARVIS MK1 Lite** is a minimalist Telegram interface for Claude Code SDK on Ubuntu VPS. We don't duplicate Claude Code functionality — we only provide a communication channel.

### What Claude Code SDK does (we don't duplicate):
- Bash command execution
- File operations (Read, Write, Edit)
- Git operations
- Session and context management
- Retries and error handling
- Response formatting

### What we do (unique value):
- Telegram as an interface to Claude Code
- Whitelist user authorization
- Socratic Gate for dangerous operations
- System prompt with VPS context

---

## 2. ARCHITECTURE

```
+--------------------------------------------------------------+
|                      JARVIS MK1 LITE                         |
|                                                              |
|   Telegram        Socratic         Claude Code               |
|   User            Gate             SDK (Subscription)        |
|     |               |                    |                   |
|     v               v                    v                   |
|  +------+      +---------+      +--------------+            |
|  | Bot  | ---> | Safety  | ---> |   Bridge     |            |
|  |      | <--- | Check   | <--- | (Bypass Mode)|            |
|  +------+      +---------+      +--------------+            |
|      |                                  |                    |
|      v                                  v                    |
|  +----------------------------------------------+           |
|  |              Ubuntu VPS (Root)                |           |
|  |  /home/projects/  |  /var/log/  |  /etc/     |           |
|  +----------------------------------------------+           |
+--------------------------------------------------------------+
```

### Data Flow

```
1. User Message (Telegram)
        |
        v
2. Whitelist Check ---- [REJECT] --> Ignore
        |
        v [PASS]
3. Socratic Gate ------ [DANGEROUS] --> Confirmation Request
        |                                      |
        v [SAFE]                               v
4. Claude Code SDK <------------------ [CONFIRMED]
   (Bypass Mode)
        |
        v
5. Response --> Telegram
```

---

## 3. PROJECT STRUCTURE

```
jarvis-mk1/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point + graceful shutdown
│   ├── config.py               # Pydantic Settings
│   ├── bot.py                  # Aiogram bot + handlers
│   ├── bridge.py               # Claude Code SDK wrapper
│   └── safety.py               # Socratic Gate implementation
│
├── prompts/
│   └── system.md               # System prompt for VPS
│
├── tests/
│   ├── __init__.py
│   ├── test_safety.py          # Socratic Gate tests
│   └── test_bridge.py          # Claude Bridge tests
│
├── .env.example
├── pyproject.toml
└── README.md
```

**Total: 8 code files** (including tests)

---

## 4. COMPONENTS

### 4.1 Config (`src/config.py`)

Pydantic Settings for environment-based configuration with validation.

### 4.2 Socratic Gate (`src/safety.py`)

**Concept:** Instead of blocking dangerous commands — ask clarifying questions (Socratic method).

Four risk levels:
- **SAFE** — execute immediately
- **MODERATE** — show warning, execute
- **DANGEROUS** — requires YES/NO confirmation
- **CRITICAL** — requires exact confirmation phrase

### 4.3 Claude Bridge (`src/bridge.py`)

Bridge to Claude Code SDK via CLI subscription. Uses `claude` CLI in Bypass Mode for command execution. Sessions are bound to Telegram user_id for context preservation.

### 4.4 Telegram Bot (`src/bot.py`)

Aiogram 3.x bot with handlers for commands and messages. Includes whitelist middleware, confirmation flow, and chunked message sending.

### 4.5 Main (`src/main.py`)

Entry point with structlog configuration and graceful shutdown via signal handlers.

---

## 5. SEQUENCE DIAGRAM

```
+-----+          +-----+          +----------+          +-----------+
|User |          | Bot |          | Socratic |          |  Claude   |
|(TG) |          |     |          |   Gate   |          |   Code    |
+--+--+          +--+--+          +----+-----+          +-----+-----+
   |                |                  |                      |
   |  Message       |                  |                      |
   |--------------->|                  |                      |
   |                |                  |                      |
   |                |  check(msg)      |                      |
   |                |----------------->|                      |
   |                |                  |                      |
   |                |  SafetyCheck     |                      |
   |                |<-----------------|                      |
   |                |                  |                      |
   |                |------------------------------------------
   |                |         [If SAFE or CONFIRMED]          |
   |                |------------------------------------------
   |                |                                         |
   |                |  send(user_id, msg)                     |
   |                |---------------------------------------->|
   |                |                                         |
   |                |                        ClaudeResponse   |
   |                |<----------------------------------------|
   |                |                                         |
   |  Response      |                                         |
   |<---------------|                                         |
   |                |                                         |
```

---

## 6. CODE PRINCIPLES

```python
# Correct: simplicity
async def handle_message(message):
    response = await claude_bridge.send(message.from_user.id, message.text)
    await message.answer(response.content)

# Wrong: over-engineering
async def handle_message(message):
    context = await context_manager.get_or_create(message.from_user.id)
    preprocessed = await preprocessor.process(message.text)
    validated = await validator.validate(preprocessed)
    result = await executor.execute(validated, context)
    formatted = await formatter.format(result)
    await response_sender.send(message, formatted)
```

**Mantra:** "If Claude Code already does it — don't duplicate."
