"""
AVA – TTS Provider
==================
Generates speech audio and returns a URL that Twilio can fetch.

Priority:
  1. ElevenLabs  (highest quality, supports Polish natively)
  2. OpenAI TTS  (good quality, multilingual)
  3. None        (caller falls back to Twilio's built-in Polly voices)

Audio files are cached on disk keyed by MD5(lang:text) to avoid
redundant API calls for repeated phrases (greetings, clarifications, etc.).
"""

import asyncio
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx
from app import i18n

logger = logging.getLogger(__name__)

AUDIO_DIR  = Path("/tmp/tts_cache")
AUDIO_DIR.mkdir(exist_ok=True)

PUBLIC_URL = os.getenv("PUBLIC_URL", "https://your-domain.com")


class TTSProvider:

    def __init__(self):
        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        self.openai_key     = os.getenv("OPENAI_API_KEY")
        self._client        = httpx.AsyncClient(timeout=15)
        # Circuit breaker: skip ElevenLabs for 10 min after a quota/auth failure
        self._elevenlabs_disabled_until: float = 0
        # Per-call usage tracking: call_sid -> {"elevenlabs_chars": N, "openai_chars": N}
        self._usage: dict[str, dict[str, int]] = {}
        # Per-call timing tracking: call_sid -> [{"provider": str, "chars": int, "latency": float}, ...]
        self._timings: dict[str, list[dict]] = {}

    async def generate_and_upload(
        self, text: str, language: str, call_sid: Optional[str] = None,
    ) -> Optional[str]:
        """
        Synthesise text to speech and return a public HTTPS URL.
        Returns None if all providers fail (Twilio will use built-in Polly).
        """
        key  = hashlib.md5(f"{language}:{text}".encode()).hexdigest()
        path = AUDIO_DIR / f"{key}.mp3"

        # Serve from disk cache if available
        if path.exists():
            return f"{PUBLIC_URL}/audio/{key}.mp3"

        use_elevenlabs = (
            self.elevenlabs_key
            and time.monotonic() > self._elevenlabs_disabled_until
        )

        _tts_start = time.monotonic()
        audio = (
            await self._elevenlabs(text, language)
            if use_elevenlabs
            else await self._openai(text)
        )
        _tts_elapsed = round(time.monotonic() - _tts_start, 3)

        if audio and call_sid:
            # Track characters consumed (cache miss only)
            u = self._usage.setdefault(call_sid, {"elevenlabs_chars": 0, "openai_chars": 0})
            provider = "elevenlabs" if use_elevenlabs else "openai_tts"
            if use_elevenlabs:
                u["elevenlabs_chars"] += len(text)
            else:
                u["openai_chars"] += len(text)
            # Track timing
            self._timings.setdefault(call_sid, []).append({
                "provider": provider, "chars": len(text), "latency": _tts_elapsed,
            })

        if audio:
            await asyncio.to_thread(path.write_bytes, audio)
            return f"{PUBLIC_URL}/audio/{key}.mp3"

        return None  # caller will fall back to Twilio <Say>

    def get_usage(self, call_sid: str) -> dict[str, int]:
        """Return and clear usage counters for a call."""
        return self._usage.pop(call_sid, {"elevenlabs_chars": 0, "openai_chars": 0})

    def get_timings(self, call_sid: str) -> list[dict]:
        """Return and clear TTS timing data for a call."""
        return self._timings.pop(call_sid, [])

    # ── ElevenLabs ────────────────────────────────────────────────────────────

    async def _elevenlabs(self, text: str, language: str) -> Optional[bytes]:
        voice_id = os.getenv("ELEVENLABS_VOICE_ID", "WAhoMTNdLdMoq1j3wf3I")
        model_id = os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2")

        try:
            resp = await self._client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key":   self.elevenlabs_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text":     text,
                    "model_id": model_id,
                    "voice_settings": {
                        "stability":        0.7,
                        "similarity_boost": 0.85,
                        "style":            0.0,
                        "use_speaker_boost": True,
                    },
                },
            )

            if resp.status_code == 200:
                return resp.content

            logger.error(f"ElevenLabs {resp.status_code}: {resp.text[:200]}")
            # Disable ElevenLabs for 10 min on auth/quota failures
            if resp.status_code in (401, 403, 429):
                self._elevenlabs_disabled_until = time.monotonic() + 600
                logger.warning("ElevenLabs disabled for 10 min (quota/auth)")
            return await self._openai(text)

        except Exception as exc:
            logger.error(f"ElevenLabs request failed: {exc}")
            return await self._openai(text)

    # ── OpenAI TTS ────────────────────────────────────────────────────────────

    async def _openai(self, text: str) -> Optional[bytes]:
        """
        OpenAI TTS – language-agnostic fallback.
        Voice configurable via OPENAI_TTS_VOICE env var (default: nova).
        """
        if not self.openai_key:
            return None

        voice = os.getenv("OPENAI_TTS_VOICE", "nova")
        try:
            resp = await self._client.post(
                "https://api.openai.com/v1/audio/speech",
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "model":           "tts-1",
                    "input":           text,
                    "voice":           voice,
                    "response_format": "mp3",
                },
            )

            if resp.status_code == 200:
                return resp.content

            logger.error(f"OpenAI TTS {resp.status_code}")
            return None

        except Exception as exc:
            logger.error(f"OpenAI TTS request failed: {exc}")
            return None
