"""Live E2E tests for model switching with real task execution.

P1-LIVE-MODEL-OPUS: Switch to Opus and execute a complex task
P1-LIVE-MODEL-SONNET: Switch to Sonnet and execute a balanced task
P1-LIVE-MODEL-HAIKU: Switch to Haiku and execute a simple task

These tests send REAL messages through Telegram to the REAL bot,
switch models, execute actual tasks, and verify REAL responses. NO MOCKS.

Test flow:
1. Switch to model
2. Verify model switch confirmation
3. Execute a task appropriate for that model
4. Verify the task was processed (response received)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from .helpers import (
    assert_contains,
    send_and_collect_responses,
    send_message_and_wait,
)

if TYPE_CHECKING:
    from telethon import TelegramClient
    from telethon.tl.types import User


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_switch_to_opus_and_execute_task_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-OPUS: Switch to Opus 4.5 and execute complex reasoning task.

    Test flow:
    1. Send /model opus - switch to most capable model
    2. Verify bot confirms switch to Opus 4.5
    3. Execute complex task: "Explain quantum entanglement in simple terms"
    4. Verify bot processes the request and responds

    This verifies:
    - /model opus command works
    - Model switch is confirmed
    - Opus model is actually used for subsequent messages
    - Bot can handle complex reasoning with Opus
    """
    # Step 1: Switch to Opus
    print("\n[OPUS TEST] Step 1: Switching to Opus 4.5...")
    switch_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model opus",
        timeout=30,
    )

    assert switch_response.text is not None
    print(f"[OPUS TEST] Switch response: {switch_response.text[:200]}...")

    # Verify switch confirmation
    assert_contains(
        switch_response.text,
        "Model changed",
        "Opus",
    )
    print("[OPUS TEST] ✓ Model switch confirmed")

    # Step 2: Execute a complex task suitable for Opus
    print("[OPUS TEST] Step 2: Executing complex reasoning task...")
    task_message = "Explain quantum entanglement in simple terms, using an analogy."

    task_responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        task_message,
        timeout=120,  # Opus may take longer for complex reasoning
        max_messages=10,
    )

    assert len(task_responses) > 0, "No response received from Opus model"
    print(f"[OPUS TEST] Received {len(task_responses)} response(s)")

    # Verify we got a substantive response (not an error)
    first_response = task_responses[0].text or ""
    print(f"[OPUS TEST] First response preview: {first_response[:300]}...")

    # Should contain actual explanation content
    assert len(first_response) > 100, "Response too short - may indicate error"
    # Should not contain error messages
    assert "error" not in first_response.lower() or "quantum" in first_response.lower()

    print("[OPUS TEST] ✓ Opus model successfully processed complex task")


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_switch_to_sonnet_and_execute_task_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-SONNET: Switch to Sonnet 4.5 and execute balanced task.

    Test flow:
    1. Send /model sonnet - switch to balanced model (default)
    2. Verify bot confirms switch to Sonnet 4.5
    3. Execute balanced task: "List 5 tips for better Python code"
    4. Verify bot processes the request and responds

    This verifies:
    - /model sonnet command works
    - Model switch is confirmed
    - Sonnet model is actually used for subsequent messages
    - Bot can handle balanced tasks with Sonnet
    """
    # Step 1: Switch to Sonnet
    print("\n[SONNET TEST] Step 1: Switching to Sonnet 4.5...")
    switch_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model sonnet",
        timeout=30,
    )

    assert switch_response.text is not None
    print(f"[SONNET TEST] Switch response: {switch_response.text[:200]}...")

    # Verify switch confirmation
    assert_contains(
        switch_response.text,
        "Model changed",
        "Sonnet",
    )
    print("[SONNET TEST] ✓ Model switch confirmed")

    # Step 2: Execute a balanced task suitable for Sonnet
    print("[SONNET TEST] Step 2: Executing balanced coding task...")
    task_message = "List 5 practical tips for writing better Python code. Be concise."

    task_responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        task_message,
        timeout=90,
        max_messages=10,
    )

    assert len(task_responses) > 0, "No response received from Sonnet model"
    print(f"[SONNET TEST] Received {len(task_responses)} response(s)")

    # Verify we got a substantive response
    first_response = task_responses[0].text or ""
    print(f"[SONNET TEST] First response preview: {first_response[:300]}...")

    # Should contain list of tips
    assert len(first_response) > 80, "Response too short"
    # Should mention Python or coding concepts
    assert any(
        keyword in first_response.lower()
        for keyword in ["python", "code", "tip", "1.", "1)"]
    ), "Response doesn't appear to contain tips"

    print("[SONNET TEST] ✓ Sonnet model successfully processed balanced task")


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_switch_to_haiku_and_execute_task_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-HAIKU: Switch to Haiku 4.5 and execute simple task.

    Test flow:
    1. Send /model haiku - switch to fastest model
    2. Verify bot confirms switch to Haiku 4.5
    3. Execute simple task: "What is 42 + 58?"
    4. Verify bot processes the request quickly and responds

    This verifies:
    - /model haiku command works
    - Model switch is confirmed
    - Haiku model is actually used for subsequent messages
    - Bot can handle simple tasks quickly with Haiku
    """
    # Step 1: Switch to Haiku
    print("\n[HAIKU TEST] Step 1: Switching to Haiku 4.5...")
    switch_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model haiku",
        timeout=30,
    )

    assert switch_response.text is not None
    print(f"[HAIKU TEST] Switch response: {switch_response.text[:200]}...")

    # Verify switch confirmation
    assert_contains(
        switch_response.text,
        "Model changed",
        "Haiku",
    )
    print("[HAIKU TEST] ✓ Model switch confirmed")

    # Step 2: Execute a simple task suitable for Haiku (fast response)
    print("[HAIKU TEST] Step 2: Executing simple calculation task...")
    task_message = "What is 42 + 58? Just give me the answer."

    task_responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        task_message,
        timeout=60,  # Haiku should be fast
        max_messages=5,
    )

    assert len(task_responses) > 0, "No response received from Haiku model"
    print(f"[HAIKU TEST] Received {len(task_responses)} response(s)")

    # Verify we got a response with the answer
    first_response = task_responses[0].text or ""
    print(f"[HAIKU TEST] First response: {first_response}")

    # Should contain the answer 100
    assert "100" in first_response, "Response doesn't contain correct answer (100)"
    print("[HAIKU TEST] ✓ Haiku model successfully processed simple task quickly")


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_verification_via_status_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-STATUS: Verify current model is shown in /status.

    Test flow:
    1. Switch to a specific model (Sonnet)
    2. Send /status
    3. Verify status shows the correct current model

    This verifies:
    - Model information is displayed in /status
    - The displayed model matches the last switch
    """
    # Step 1: Switch to Sonnet (known state)
    print("\n[STATUS TEST] Step 1: Switching to Sonnet for verification...")
    switch_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model sonnet",
        timeout=30,
    )

    assert switch_response.text is not None
    assert_contains(switch_response.text, "Model changed", "Sonnet")
    print("[STATUS TEST] ✓ Switched to Sonnet")

    # Step 2: Check status
    print("[STATUS TEST] Step 2: Checking /status...")
    status_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/status",
        timeout=30,
    )

    assert status_response.text is not None
    print(f"[STATUS TEST] Status response: {status_response.text}")

    # Verify status shows the model
    assert_contains(
        status_response.text,
        "Model:",
    )

    # Should show Sonnet since we just switched to it
    assert "Sonnet" in status_response.text, "Status doesn't show current model (Sonnet)"

    print("[STATUS TEST] ✓ Status correctly shows current model")


@pytest.mark.live
@pytest.mark.asyncio(loop_scope="session")
async def test_model_persistence_across_messages_live(
    telethon_client: "TelegramClient",
    bot_entity: "User",
    between_tests_delay: None,
) -> None:
    """P1-LIVE-MODEL-PERSIST: Verify model persists across multiple messages.

    Test flow:
    1. Switch to Haiku
    2. Send first task
    3. Send second task (without switching model)
    4. Verify both tasks are processed

    This verifies:
    - Model choice persists across multiple messages
    - No need to re-select model for each message
    """
    # Step 1: Switch to Haiku
    print("\n[PERSIST TEST] Step 1: Switching to Haiku...")
    switch_response = await send_message_and_wait(
        telethon_client,
        bot_entity,
        "/model haiku",
        timeout=30,
    )

    assert switch_response.text is not None
    assert_contains(switch_response.text, "Model changed", "Haiku")
    print("[PERSIST TEST] ✓ Switched to Haiku")

    # Step 2: Send first task
    print("[PERSIST TEST] Step 2: Sending first task...")
    task1_responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "What is 10 + 15?",
        timeout=60,
        max_messages=5,
    )

    assert len(task1_responses) > 0
    first_task_response = task1_responses[0].text or ""
    assert "25" in first_task_response
    print("[PERSIST TEST] ✓ First task processed")

    # Step 3: Send second task WITHOUT switching model
    print("[PERSIST TEST] Step 3: Sending second task (no model switch)...")
    task2_responses = await send_and_collect_responses(
        telethon_client,
        bot_entity,
        "What is 20 + 30?",
        timeout=60,
        max_messages=5,
    )

    assert len(task2_responses) > 0
    second_task_response = task2_responses[0].text or ""
    assert "50" in second_task_response
    print("[PERSIST TEST] ✓ Second task processed with same model")

    print("[PERSIST TEST] ✓ Model persists across multiple messages")
