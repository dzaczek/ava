"""
AVA – Owner Channel (Signal only)
==================================
All communication with the owner goes through Signal via signal-cli-rest-api
(self-hosted, no external API keys required).

Outbound: AVA sends notifications to the owner's Signal number.
Inbound:  A background poller checks for new Signal messages every few seconds
          and forwards them to AVA as live call instructions.

signal-cli-rest-api docs: https://github.com/bbernhard/signal-cli-rest-api
"""

import asyncio
import logging
import os
from collections import deque
from typing import Awaitable, Callable, Optional

import httpx

# Slash command handler: receives args string, returns reply text
SlashHandler = Callable[[str], Awaitable[str]]

logger = logging.getLogger(__name__)


class OwnerChannel:

    def __init__(self):
        self.signal_url    = os.getenv("SIGNAL_CLI_URL", "http://signal-cli:8080")
        self.signal_sender = os.getenv("SIGNAL_SENDER_NUMBER")  # bot number in signal-cli
        self.signal_owner  = os.getenv("SIGNAL_RECIPIENT")      # your personal Signal number

        # Pending instructions per call_sid  { sid: ["instr1", ...] }
        self._instructions: dict[str, list[str]] = {}
        self._active_call:  Optional[str] = None

        # Tracks message timestamps already processed (avoids duplicates)
        self._seen_timestamps: deque[int] = deque(maxlen=500)

        # Persistent HTTP client for Signal API
        self._client = httpx.AsyncClient(timeout=10)

        # Slash command registry (populated via register_slash)
        self._slash_commands: dict[str, SlashHandler] = {}

    # ── Slash commands ────────────────────────────────────────────────────────

    def register_slash(self, name: str, handler: SlashHandler):
        """Register a slash command handler. Name should include the '/' prefix."""
        self._slash_commands[name.lower()] = handler
        logger.info(f"Registered slash command: {name}")

    async def _handle_slash(self, text: str) -> str:
        """Route a /command to its registered handler."""
        parts = text.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handler = self._slash_commands.get(cmd)
        if handler:
            try:
                return await handler(args)
            except Exception as exc:
                logger.exception(f"Slash command {cmd} failed")
                return f"Error in {cmd}: {exc}"

        return f"Unknown command: {cmd}\nType /help for available commands."

    # ── Outbound ──────────────────────────────────────────────────────────────

    async def notify(self, message: str, call_sid: Optional[str] = None) -> bool:
        """Send a Signal message to the owner."""
        if call_sid:
            self._active_call = call_sid

        if not self.signal_sender or not self.signal_owner:
            logger.warning("Signal not configured – check SIGNAL_SENDER_NUMBER and SIGNAL_RECIPIENT")
            return False

        try:
            resp = await self._client.post(
                f"{self.signal_url}/v2/send",
                json={
                    "message":    message,
                    "number":     self.signal_sender,
                    "recipients": [self.signal_owner],
                },
            )
            if resp.status_code == 201:
                return True
            logger.error(f"Signal send {resp.status_code}: {resp.text[:200]}")
            return False
        except Exception as exc:
            logger.error(f"Signal send failed: {exc}")
            return False

    # ── Inbound polling ───────────────────────────────────────────────────────

    async def start_polling(self, interval: float = 3.0):
        """
        Background task – polls signal-cli for new messages every `interval` seconds.
        Start once at application startup:
            asyncio.create_task(owner_channel.start_polling())
        """
        logger.info(f"Signal inbound polling started (interval={interval}s)")
        while True:
            try:
                await self._poll_once()
            except Exception as exc:
                logger.error(f"Signal poll error: {exc}")
            await asyncio.sleep(interval)

    async def _poll_once(self):
        """Fetch and process any new incoming Signal messages."""
        if not self.signal_sender:
            return

        resp = await self._client.get(
            f"{self.signal_url}/v1/receive/{self.signal_sender}"
        )

        if resp.status_code != 200:
            return

        messages = resp.json()
        if not isinstance(messages, list):
            return

        for msg in messages:
            envelope = msg.get("envelope", {})

            # Only care about actual text messages
            data = envelope.get("dataMessage")
            if not data:
                continue

            # Deduplicate by Signal timestamp (milliseconds epoch)
            ts = envelope.get("timestamp", 0)
            if ts in self._seen_timestamps:
                continue
            self._seen_timestamps.append(ts)

            # Only accept messages from the configured owner number
            source = envelope.get("source") or envelope.get("sourceNumber", "")
            if self.signal_owner and source not in (
                self.signal_owner,
                self.signal_owner.lstrip("+"),
            ):
                logger.warning("Ignoring Signal message from unknown source")
                continue

            text = data.get("message", "").strip()
            if not text:
                continue

            logger.info(f"Signal inbound from owner ({len(text)} chars)")
            if text.startswith("/"):
                reply = await self._handle_slash(text)
            else:
                reply = self.receive_instruction(text)
            await self.notify(reply)

    # ── Instruction parsing ───────────────────────────────────────────────────

    def receive_instruction(self, text: str, call_sid: Optional[str] = None) -> str:
        """
        Parse an owner Signal message and queue it for the active call.
        Returns a confirmation string that gets sent back to the owner.

        Commands
        ────────
        status / ?                  show whether a call is active
        end / hang up / stop        ask AVA to end the call
        tell him/her <msg>          AVA relays the message to the caller
        ask him/her <question>      AVA asks the caller the question
        <anything else>             forwarded as a generic instruction
        """
        target = call_sid or self._active_call
        cmd    = text.lower().strip()

        if cmd in ("status", "?"):
            if not target:
                return "No active call at the moment."
            return f"✅ Active call in progress.\nInstructions will be applied."

        if cmd in ("end", "hang up", "stop", "finish", "zakończ", "koniec"):
            if target:
                self._queue(target, "__END_CALL__")
                return "⏹ AVA will end the call at the next opportunity."
            return "No active call."

        if cmd.startswith(("tell ", "tell him ", "tell her ", "powiedz ")):
            payload = text.split(" ", 2)[-1].strip()
            if target:
                self._queue(target, f"RELAY_TO_CALLER: {payload}")
                return f"✅ AVA will tell the caller:\n_{payload}_"
            return "No active call."

        if cmd.startswith(("ask ", "ask him ", "ask her ", "zapytaj ")):
            payload = text.split(" ", 2)[-1].strip()
            if target:
                self._queue(target, f"ASK_CALLER: {payload}")
                return f"✅ AVA will ask:\n_{payload}_"
            return "No active call."

        # Generic instruction
        if target:
            self._queue(target, text.strip())
            return "✅ Instruction forwarded to AVA."

        return "❌ No active call. Instructions will be applied once a call is in progress."

    def _queue(self, call_sid: str, instruction: str):
        self._instructions.setdefault(call_sid, []).append(instruction)
        logger.info(f"Queued instruction for {call_sid[:12]}")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def pop_instructions(self, call_sid: str) -> list[str]:
        """Consume and return all pending instructions for a call."""
        return self._instructions.pop(call_sid, [])

    def set_active_call(self, call_sid: str):
        self._active_call = call_sid

    def clear_active_call(self, call_sid: str):
        if self._active_call == call_sid:
            self._active_call = None
        self._instructions.pop(call_sid, None)
