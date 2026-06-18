"""
AVA – TTS Provider
==================
Generates speech audio and returns a URL that Twilio can fetch.

The primary provider is chosen at runtime via the TTS_PROVIDER env var
("elevenlabs" (default), "sixtydb", or "openai"). The chain always falls
through to OpenAI TTS, then to None (Twilio's built-in Polly voices):

  TTS_PROVIDER=elevenlabs  →  ElevenLabs → 60db → OpenAI → Polly
  TTS_PROVIDER=sixtydb     →  60db → ElevenLabs → OpenAI → Polly
  TTS_PROVIDER=openai      →  OpenAI → Polly

Each premium provider (ElevenLabs, 60db) has an independent 10-minute
circuit breaker that trips on auth/quota errors (401/403/429) and skips
that provider until it expires.

Audio files are cached on disk keyed by MD5(lang:text) to avoid
redundant API calls for repeated phrases (greetings, clarifications, etc.).
"""

import asyncio
import base64
import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Optional

import httpx
from app import i18n

logger = logging.getLogger(__name__)

# Internal provider name → (usage-counter key, human-readable timing label)
_PROVIDER_META = {
    "elevenlabs": ("elevenlabs_chars", "elevenlabs"),
    "sixtydb":    ("sixtydb_chars",    "60db"),
    "openai":     ("openai_chars",     "openai_tts"),
}

# Ordered fallback chains keyed by the configured primary provider.
# Unknown/unset TTS_PROVIDER falls back to the ElevenLabs-first chain.
_PROVIDER_CHAINS = {
    "elevenlabs": ["elevenlabs", "sixtydb", "openai"],
    "sixtydb":    ["sixtydb", "elevenlabs", "openai"],
    "openai":     ["openai"],
}

_EMPTY_USAGE = {"elevenlabs_chars": 0, "sixtydb_chars": 0, "openai_chars": 0}

AUDIO_DIR  = Path("/tmp/tts_cache")
AUDIO_DIR.mkdir(exist_ok=True)

PUBLIC_URL = os.getenv("PUBLIC_URL", "https://your-domain.com")


class TTSProvider:

    def __init__(self):
        self.elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
        self.sixtydb_key    = os.getenv("SIXTYDB_API_KEY")
        self.openai_key     = os.getenv("OPENAI_API_KEY")
        # Primary provider selector: "elevenlabs" (default), "sixtydb", or "openai"
        self.tts_provider   = os.getenv("TTS_PROVIDER", "elevenlabs").strip().lower()
        self._client        = httpx.AsyncClient(timeout=15)
        # Circuit breakers: skip a premium provider for 10 min after a quota/auth failure
        self._elevenlabs_disabled_until: float = 0
        self._sixtydb_disabled_until: float    = 0
        # Per-call usage tracking: call_sid -> {"elevenlabs_chars": N, "sixtydb_chars": N, "openai_chars": N}
        self._usage: dict[str, dict[str, int]] = {}
        # Per-call timing tracking: call_sid -> [{"provider": str, "chars": int, "latency": float}, ...]
        self._timings: dict[str, list[dict]] = {}

    def _chain(self) -> list[str]:
        """Ordered list of providers to try, based on TTS_PROVIDER."""
        return _PROVIDER_CHAINS.get(self.tts_provider, _PROVIDER_CHAINS["elevenlabs"])

    def primary_label(self) -> str:
        """Human label of the provider that would be tried first (display only)."""
        keys = {"elevenlabs": self.elevenlabs_key, "sixtydb": self.sixtydb_key, "openai": True}
        for name in self._chain():
            if keys.get(name):
                return _PROVIDER_META[name][1]
        return "openai_tts"

    async def _try_provider(self, name: str, text: str, language: str) -> Optional[bytes]:
        """Dispatch to a single provider, honouring key presence + circuit breaker."""
        now = time.monotonic()
        if name == "elevenlabs":
            if not (self.elevenlabs_key and now > self._elevenlabs_disabled_until):
                return None
            return await self._elevenlabs(text, language)
        if name == "sixtydb":
            if not (self.sixtydb_key and now > self._sixtydb_disabled_until):
                return None
            return await self._sixtydb(text, language)
        if name == "openai":
            return await self._openai(text)
        return None

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

        # Walk the provider chain until one returns audio.
        _tts_start = time.monotonic()
        audio: Optional[bytes] = None
        provider: Optional[str] = None
        for name in self._chain():
            audio = await self._try_provider(name, text, language)
            if audio:
                provider = name
                break
        _tts_elapsed = round(time.monotonic() - _tts_start, 3)

        if audio and call_sid:
            # Track characters consumed by the provider that actually answered (cache miss only)
            usage_key, label = _PROVIDER_META[provider]
            u = self._usage.setdefault(call_sid, dict(_EMPTY_USAGE))
            u[usage_key] += len(text)
            self._timings.setdefault(call_sid, []).append({
                "provider": label, "chars": len(text), "latency": _tts_elapsed,
            })

        if audio:
            await asyncio.to_thread(path.write_bytes, audio)
            return f"{PUBLIC_URL}/audio/{key}.mp3"

        return None  # caller will fall back to Twilio <Say>

    def get_usage(self, call_sid: str) -> dict[str, int]:
        """Return and clear usage counters for a call."""
        return self._usage.pop(call_sid, dict(_EMPTY_USAGE))

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
            return None  # chain falls through to the next provider

        except Exception as exc:
            logger.error(f"ElevenLabs request failed: {exc}")
            return None

    # ── 60db ──────────────────────────────────────────────────────────────────

    async def _sixtydb(self, text: str, language: str) -> Optional[bytes]:
        """
        60db.ai synchronous TTS. Returns MP3 bytes.

        Unlike ElevenLabs (raw audio body), 60db returns JSON with a
        base64-encoded audio payload, which we decode here so the rest of
        the pipeline sees plain MP3 bytes regardless of provider.
        """
        voice_id = os.getenv("SIXTYDB_VOICE_ID", "fbb75ed2-975a-40c7-9e06-38e30524a9a1")

        try:
            resp = await self._client.post(
                "https://api.60db.ai/tts-synthesize",
                headers={
                    "Authorization": f"Bearer {self.sixtydb_key}",
                    "Content-Type":  "application/json",
                },
                json={
                    "text":          text,
                    "voice_id":      voice_id,
                    "output_format": "mp3",   # must stay mp3 for the .mp3 cache + Twilio playback
                    "enhance":       True,
                    "speed":         float(os.getenv("SIXTYDB_SPEED", "1")),
                    "stability":     int(os.getenv("SIXTYDB_STABILITY", "50")),   # 0–100
                    "similarity":    int(os.getenv("SIXTYDB_SIMILARITY", "75")),  # 0–100
                },
            )

            if resp.status_code == 200:
                data = resp.json()
                if data.get("success") and data.get("audio_base64"):
                    return base64.b64decode(data["audio_base64"])
                logger.error(f"60db returned no audio: {str(data.get('message'))[:200]}")
                return None

            logger.error(f"60db {resp.status_code}: {resp.text[:200]}")
            # Disable 60db for 10 min on auth/quota failures
            if resp.status_code in (401, 403, 429):
                self._sixtydb_disabled_until = time.monotonic() + 600
                logger.warning("60db disabled for 10 min (quota/auth)")
            return None  # chain falls through to the next provider

        except Exception as exc:
            logger.error(f"60db request failed: {exc}")
            return None

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
