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

    async def generate_and_upload(self, text: str, language: str) -> Optional[str]:
        """
        Synthesise text to speech and return a public HTTPS URL.
        Returns None if all providers fail (Twilio will use built-in Polly).
        """
        key  = hashlib.md5(f"{language}:{text}".encode()).hexdigest()
        path = AUDIO_DIR / f"{key}.mp3"

        # Serve from disk cache if available
        if path.exists():
            return f"{PUBLIC_URL}/audio/{key}.mp3"

        audio = (
            await self._elevenlabs(text, language)
            if self.elevenlabs_key
            else await self._openai(text)
        )

        if audio:
            await asyncio.to_thread(path.write_bytes, audio)
            return f"{PUBLIC_URL}/audio/{key}.mp3"

        return None  # caller will fall back to Twilio <Say>

    # ── ElevenLabs ────────────────────────────────────────────────────────────

    async def _elevenlabs(self, text: str, language: str) -> Optional[bytes]:
        voice_id = i18n.ELEVENLABS_VOICES.get(
            language, i18n.ELEVENLABS_DEFAULT
        )

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key":   self.elevenlabs_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "text":     text,
                        "model_id": "eleven_turbo_v2_5",  # lowest latency
                        "voice_settings": {
                            "stability":        0.5,
                            "similarity_boost": 0.75,
                            "style":            0.0,
                            "use_speaker_boost": True,
                        },
                        "language_code": language,
                    },
                )

                if resp.status_code == 200:
                    return resp.content

                logger.error(f"ElevenLabs {resp.status_code}: {resp.text[:200]}")
                # Attempt OpenAI TTS as fallback
                return await self._openai(text)

        except Exception as exc:
            logger.error(f"ElevenLabs request failed: {exc}")
            return await self._openai(text)

    # ── OpenAI TTS ────────────────────────────────────────────────────────────

    async def _openai(self, text: str) -> Optional[bytes]:
        """
        OpenAI TTS – language-agnostic, uses the "alloy" voice which
        handles most languages acceptably.
        """
        if not self.openai_key:
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={
                        "Authorization": f"Bearer {self.openai_key}",
                        "Content-Type":  "application/json",
                    },
                    json={
                        "model":           "tts-1",
                        "input":           text,
                        "voice":           "alloy",
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
