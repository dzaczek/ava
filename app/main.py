"""
AVA – AI Voice Assistant
========================
Core FastAPI application.

Call flow:
  Twilio (incoming) → STT → GPT-4o (conversation) → ElevenLabs TTS → back to caller
  Notifications → Signal (self-hosted signal-cli)
  Owner instructions → Signal messages polled in background every 3 s
"""

import asyncio
import collections
import json
import logging
import os
import platform
import re
import resource
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin

from fastapi import FastAPI, Form, Request, BackgroundTasks, HTTPException, Depends
from fastapi.responses import Response, FileResponse
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse, Gather

from app.conversation import ConversationManager
from app.owner_channel import OwnerChannel
from app.contact_lookup import ContactLookup
from app.tts import TTSProvider
from app import i18n
from langdetect import detect as _langdetect_detect, LangDetectException

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AVA – AI Voice Assistant",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# ── Singletons ────────────────────────────────────────────────────────────────
conversation = ConversationManager()
owner        = OwnerChannel()
contacts     = ContactLookup()
tts          = TTSProvider()

active_calls: dict[str, dict] = {}
URGENCY_EMOJI = {"low": "🟢", "medium": "🟡", "high": "🔴"}
AUDIO_DIR = Path("/tmp/tts_cache")
CALLS_DIR = Path("/data/calls")

# ── Diagnostics tracking ─────────────────────────────────────────────────────
_start_time = time.monotonic()
_call_count = 0
_recording_state = {"enabled": False}

# ── API usage / cost tracking ────────────────────────────────────────────────
# Approximate pricing ($/unit)
GPT4O_INPUT  = 2.50 / 1_000_000   # $/token
GPT4O_OUTPUT = 10.0 / 1_000_000   # $/token
ELEVENLABS   = 0.30 / 1_000       # $/char
OPENAI_TTS   = 0.015 / 1_000      # $/char

_total_usage: dict[str, int] = {
    "gpt_prompt_tokens": 0,
    "gpt_completion_tokens": 0,
    "summary_prompt_tokens": 0,
    "summary_completion_tokens": 0,
    "tts_elevenlabs_chars": 0,
    "tts_openai_chars": 0,
}

def _empty_call_usage() -> dict[str, int]:
    return {
        "gpt_prompt_tokens": 0, "gpt_completion_tokens": 0,
        "summary_prompt_tokens": 0, "summary_completion_tokens": 0,
        "tts_elevenlabs_chars": 0, "tts_openai_chars": 0,
    }

def _compute_cost(u: dict) -> float:
    gpt_in = u.get("gpt_prompt_tokens", 0) + u.get("summary_prompt_tokens", 0)
    gpt_out = u.get("gpt_completion_tokens", 0) + u.get("summary_completion_tokens", 0)
    return (
        gpt_in * GPT4O_INPUT
        + gpt_out * GPT4O_OUTPUT
        + u.get("tts_elevenlabs_chars", 0) * ELEVENLABS
        + u.get("tts_openai_chars", 0) * OPENAI_TTS
    )

# ── Twilio webhook signature validation ──────────────────────────────────────

_twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
if not _twilio_token:
    raise ValueError("TWILIO_AUTH_TOKEN must be set")
_twilio_validator = RequestValidator(_twilio_token)
_public_url = os.getenv("PUBLIC_URL", "")

async def verify_twilio_signature(request: Request):
    """
    FastAPI dependency that validates the X-Twilio-Signature header.
    Rejects any request not genuinely sent by Twilio.
    """
    signature = request.headers.get("X-Twilio-Signature", "")
    # Reconstruct the full URL Twilio used to sign the request
    url = urljoin(_public_url + "/", request.url.path.lstrip("/"))

    # Use request.form() which FastAPI/Starlette caches properly,
    # avoiding "Stream consumed" errors with middleware + Form() params.
    form = await request.form()
    form_data = dict(form)

    logger.debug(f"Twilio sig check: url={url} sig={signature[:20]}... params={sorted(form_data.keys())}")

    if not _twilio_validator.validate(url, form_data, signature):
        logger.warning(f"Rejected invalid Twilio signature from {request.client.host} url={url}")
        raise HTTPException(status_code=403, detail="Invalid signature")


# ── Rate limiter (in-memory, per IP) ─────────────────────────────────────────

class _RateLimiter:
    """Simple sliding-window rate limiter. No external dependencies."""

    def __init__(self, max_requests: int = 30, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, collections.deque] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        if key not in self._hits:
            self._hits[key] = collections.deque()
        q = self._hits[key]
        # Evict old entries
        while q and q[0] < now - self._window:
            q.popleft()
        if len(q) >= self._max:
            return False
        q.append(now)
        return True

    def cleanup(self):
        """Remove stale entries to prevent memory leak."""
        now = time.monotonic()
        stale = [k for k, q in self._hits.items() if not q or q[-1] < now - self._window * 2]
        for k in stale:
            del self._hits[k]

_rate_limiter = _RateLimiter(max_requests=30, window_seconds=60)

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Block IPs that exceed 30 requests per minute."""
    client_ip = request.client.host if request.client else "unknown"

    # AVA runs behind Caddy (trusted proxy). Caddy appends the real client IP to X-Forwarded-For.
    # We take the last IP in the list as the client IP.
    if xff := request.headers.get("X-Forwarded-For"):
        client_ip = xff.split(",")[-1].strip()

    if not _rate_limiter.is_allowed(client_ip):
        logger.warning(f"Rate limit exceeded for {client_ip}")
        return Response(content="Too Many Requests", status_code=429)
    response = await call_next(request)
    return response


# ── Startup: kick off Signal inbound poller ───────────────────────────────────

@app.on_event("startup")
async def startup():
    """Start the Signal inbound polling loop as a background task."""
    _register_slash_commands()
    asyncio.create_task(owner.start_polling(interval=3.0))
    asyncio.create_task(_rate_limiter_cleanup_loop())
    logger.info("AVA started – Signal polling active")


async def _rate_limiter_cleanup_loop():
    """Periodically clean up stale rate limiter entries."""
    while True:
        await asyncio.sleep(300)
        _rate_limiter.cleanup()


@app.on_event("shutdown")
async def shutdown():
    """Close persistent HTTP clients on shutdown."""
    await tts._client.aclose()
    await owner._client.aclose()
    await contacts._client.aclose()


# ── Slash commands (Signal diagnostics) ───────────────────────────────────────

def _format_uptime() -> str:
    """Format uptime as 'Xd Yh Zm'."""
    elapsed = int(time.monotonic() - _start_time)
    days, rem = divmod(elapsed, 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _register_slash_commands():
    """Register all diagnostic slash commands on the owner channel."""

    async def _cmd_ping(_args: str) -> str:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        return f"pong\n{now}"

    async def _cmd_status(_args: str) -> str:
        lines = [
            "AVA Status",
            "━━━━━━━━━━━━",
            f"Uptime: {_format_uptime()}",
            f"Active calls: {len(active_calls)}",
        ]
        for sid, state in active_calls.items():
            caller = state.get("caller_name") or state.get("from", "?")
            start = state.get("start_time", "")
            elapsed = ""
            if start:
                try:
                    dt = datetime.fromisoformat(start)
                    secs = int((datetime.utcnow() - dt).total_seconds())
                    elapsed = f" — {secs // 60}m {secs % 60}s"
                except ValueError:
                    pass
            lines.append(f"  {sid[:8]}... from {caller}{elapsed}")

        # Recording
        lines.append(f"Recording: {'🔴 ON' if _recording_state['enabled'] else '⚪ OFF'}")

        # TTS cache
        tts_files = list(AUDIO_DIR.glob("*.mp3")) if AUDIO_DIR.exists() else []
        tts_size = sum(f.stat().st_size for f in tts_files) / (1024 * 1024)
        lines.append(f"TTS cache: {len(tts_files)} files ({tts_size:.1f} MB)")

        # ElevenLabs circuit breaker
        el_remaining = tts._elevenlabs_disabled_until - time.monotonic()
        if el_remaining > 0:
            lines.append(f"ElevenLabs: ⚠️ disabled ({int(el_remaining)}s remaining)")
        else:
            lines.append(f"ElevenLabs: ✅ active" if tts.elevenlabs_key else "ElevenLabs: ❌ no key")

        # Stats
        lines.append(f"Total calls: {_call_count}")
        lines.append(f"Signal: connected")
        if _public_url:
            lines.append(f"Public URL: {_public_url}")
        return "\n".join(lines)

    async def _cmd_stats(_args: str) -> str:
        # TTS cache stats
        tts_files = list(AUDIO_DIR.glob("*.mp3")) if AUDIO_DIR.exists() else []
        tts_count = len(tts_files)
        tts_size_mb = sum(f.stat().st_size for f in tts_files) / (1024 * 1024)

        # Saved call records
        call_files = list(CALLS_DIR.glob("*.json")) if CALLS_DIR.exists() else []

        # Memory RSS (in MB)
        try:
            rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS returns bytes, Linux returns KB
            if sys.platform == "darwin":
                rss_mb = rss_kb / (1024 * 1024)
            else:
                rss_mb = rss_kb / 1024
        except Exception:
            rss_mb = 0.0

        lines = [
            "AVA Statistics",
            "━━━━━━━━━━━━━━━━",
            f"Uptime: {_format_uptime()}",
            f"Total calls handled: {_call_count}",
            f"Saved call records: {len(call_files)}",
            f"TTS cache: {tts_count} files ({tts_size_mb:.1f} MB)",
            f"Memory (RSS): {rss_mb:.1f} MB",
            f"Python: {platform.python_version()}",
        ]

        # Session API usage & costs
        u = _total_usage
        gpt_tok = (u["gpt_prompt_tokens"] + u["gpt_completion_tokens"]
                    + u["summary_prompt_tokens"] + u["summary_completion_tokens"])
        gpt_cost = ((u["gpt_prompt_tokens"] + u["summary_prompt_tokens"]) * GPT4O_INPUT
                     + (u["gpt_completion_tokens"] + u["summary_completion_tokens"]) * GPT4O_OUTPUT)
        el_cost = u["tts_elevenlabs_chars"] * ELEVENLABS
        oai_tts_cost = u["tts_openai_chars"] * OPENAI_TTS
        total = gpt_cost + el_cost + oai_tts_cost

        lines.append("")
        lines.append("API Usage (session)")
        lines.append("───────────────────")
        lines.append(f"GPT-4o: {gpt_tok} tok (${gpt_cost:.4f})")
        lines.append(f"ElevenLabs TTS: {u['tts_elevenlabs_chars']} chars (${el_cost:.4f})")
        lines.append(f"OpenAI TTS: {u['tts_openai_chars']} chars (${oai_tts_cost:.4f})")
        lines.append(f"Total est: ${total:.4f}")

        # Per-call costs from saved files (last 10)
        recent_files = sorted(CALLS_DIR.glob("*.json"), reverse=True)[:10] if CALLS_DIR.exists() else []
        if recent_files:
            lines.append("")
            lines.append(f"Last {len(recent_files)} calls")
            lines.append("───────────────────")
            cumulative = 0.0
            for f in recent_files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    usage = data.get("usage") or {}
                    cost = usage.get("estimated_cost", 0)
                    cumulative += cost
                    caller = data.get("caller_name") or data.get("caller_number", "?")
                    lines.append(f"  {caller}: ${cost:.4f}")
                except Exception:
                    lines.append(f"  (error reading {f.name})")
            lines.append(f"  Total (last {len(recent_files)}): ${cumulative:.4f}")

        return "\n".join(lines)

    async def _cmd_calls(_args: str) -> str:
        if not CALLS_DIR.exists():
            return "No call records found."
        files = sorted(CALLS_DIR.glob("*.json"), reverse=True)[:5]
        if not files:
            return "No call records found."

        lines = ["Recent calls (last 5)", "━━━━━━━━━━━━━━━━━━━━━"]
        for i, f in enumerate(files, 1):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                caller = data.get("caller_name") or data.get("caller_number", "?")
                number = data.get("caller_number", "")
                topic = data.get("call_meta", {}).get("topic") or data.get("summary", "")[:50]
                start = data.get("start_time", "?")
                try:
                    dt = datetime.fromisoformat(start)
                    start = dt.strftime("%Y-%m-%d %H:%M")
                except ValueError:
                    pass
                urgency = data.get("call_meta", {}).get("urgency", "low")
                emoji = URGENCY_EMOJI.get(urgency, "")
                lines.append(f"{i}. {start} — {caller} ({number})")
                if topic:
                    lines.append(f"   {emoji} Topic: {topic}")
            except Exception:
                lines.append(f"{i}. (error reading {f.name})")
        return "\n".join(lines)

    _restart_pending: dict[str, float] = {}

    async def _cmd_restart(args: str) -> str:
        if args.strip().lower() == "confirm":
            if _restart_pending.get("ts", 0) > time.monotonic() - 30:
                _restart_pending.clear()
                # Schedule exit after response is sent
                asyncio.get_event_loop().call_later(1.0, lambda: sys.exit(0))
                return "Restarting AVA..."
            return "No pending restart request. Send /restart first."

        _restart_pending["ts"] = time.monotonic()
        return "Are you sure? Send `/restart confirm` within 30s to confirm."

    async def _cmd_recording_on(_args: str) -> str:
        _recording_state["enabled"] = True
        return "🔴 Recording ON — next calls will be recorded."

    async def _cmd_recording_off(_args: str) -> str:
        _recording_state["enabled"] = False
        return "⚪ Recording OFF — calls will not be recorded."

    async def _cmd_help(_args: str) -> str:
        return "\n".join([
            "AVA Signal Commands",
            "━━━━━━━━━━━━━━━━━━━━",
            "/ping          — alive check",
            "/status        — system status & active calls",
            "/stats         — statistics (calls, memory, cache)",
            "/calls         — recent call history",
            "/recording-on  — start recording calls",
            "/recording-off — stop recording calls",
            "/restart       — restart AVA process",
            "/help          — this message",
            "",
            "Call commands (no / prefix):",
            "status    — is a call active?",
            "end       — end current call",
            "tell <msg> — relay message to caller",
            "ask <msg>  — ask caller a question",
        ])

    owner.register_slash("/ping", _cmd_ping)
    owner.register_slash("/status", _cmd_status)
    owner.register_slash("/stats", _cmd_stats)
    owner.register_slash("/calls", _cmd_calls)
    owner.register_slash("/recording-on", _cmd_recording_on)
    owner.register_slash("/recording-off", _cmd_recording_off)
    owner.register_slash("/restart", _cmd_restart)
    owner.register_slash("/help", _cmd_help)


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── TTS audio serving ───────────────────────────────────────────────────────

@app.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Serve cached TTS audio files to Twilio."""
    # Only allow safe filenames: hex hash + .mp3
    if not re.fullmatch(r"[a-f0-9]{32}\.mp3", filename):
        raise HTTPException(status_code=404, detail="Not found")
    path = (AUDIO_DIR / filename).resolve()
    # Prevent path traversal
    if not str(path).startswith(str(AUDIO_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    return FileResponse(path, media_type="audio/mpeg")


# ── Incoming call ─────────────────────────────────────────────────────────────

@app.post("/twilio/incoming", dependencies=[Depends(verify_twilio_signature)])
async def incoming_call(
    background_tasks: BackgroundTasks,
    CallSid: str = Form(...),
    From: str   = Form(...),
    To: str     = Form(...),
    CallStatus: str = Form(...),
):
    """
    Twilio calls this endpoint when a forwarded call arrives.
    Greets the caller and starts the conversation loop.
    Sends an immediate Signal notification to the owner.
    """
    global _call_count
    _call_count += 1
    logger.info(f"📞 Incoming call {CallSid}")

    caller_name = await contacts.lookup(From)
    display     = caller_name or From

    # Per-contact language override, or fall back to phone prefix detection
    contact_lang = contacts.contact_language(From)
    if contact_lang:
        lang_code, twilio_locale = contact_lang
        logger.info(f"Using contact language override: {lang_code} ({twilio_locale})")
    else:
        lang_code, twilio_locale = contacts.language_from_number(From)

    active_calls[CallSid] = {
        "from":              From,
        "caller_name":       caller_name,
        "start_time":        datetime.utcnow().isoformat(),
        "transcript":        [],
        "summary_sent":      False,
        "language_detected": twilio_locale,
    }
    owner.set_active_call(CallSid)

    # Start Twilio recording if enabled
    if _recording_state["enabled"]:
        try:
            from twilio.rest import Client as TwilioClient
            twilio_client = TwilioClient(
                os.getenv("TWILIO_ACCOUNT_SID"),
                os.getenv("TWILIO_AUTH_TOKEN"),
            )
            await asyncio.to_thread(
                lambda: twilio_client.calls(CallSid).recordings.create(
                    recording_channels="dual",
                    recording_status_callback=f"{_public_url}/twilio/recording_status",
                    recording_status_callback_method="POST",
                )
            )
            active_calls[CallSid]["recording"] = True
            logger.info(f"Recording started for {CallSid[:12]}")
        except Exception as exc:
            logger.error(f"Failed to start recording: {exc}")

    # Notify owner – include detected language so they know what to expect
    _sl = i18n.SIGNAL_LANG
    background_tasks.add_task(
        owner.notify,
        i18n.SIG_INCOMING.get(_sl, i18n.SIG_INCOMING["en"]).format(
            display=display, number=From, lang=twilio_locale,
            time=datetime.now().strftime("%H:%M:%S"),
        ),
        CallSid,
    )

    # Greet in the caller's detected language
    greeting  = i18n.GREETINGS.get(lang_code, i18n.GREETINGS["en"])
    audio_url = await tts.generate_and_upload(greeting, lang_code, call_sid=CallSid)

    response = VoiceResponse()
    gather   = Gather(
        input="speech",
        action=f"/twilio/process_speech/{CallSid}",
        method="POST",
        speech_timeout="2",
        language=twilio_locale,
        enhanced=True,
    )
    if audio_url:
        gather.play(audio_url)
    else:
        _say(gather, greeting, lang_code)

    response.append(gather)
    response.redirect(f"/twilio/no_input/{CallSid}", method="POST")
    return Response(content=str(response), media_type="text/xml")


# ── Speech processing loop ────────────────────────────────────────────────────

@app.post("/twilio/process_speech/{call_sid}", dependencies=[Depends(verify_twilio_signature)])
async def process_speech(
    call_sid: str,
    background_tasks: BackgroundTasks,
    SpeechResult:  Optional[str] = Form(None),
    Confidence:    Optional[str] = Form(None),
    LanguageCode:  Optional[str] = Form(None),
    CallStatus:    Optional[str] = Form(None),
):
    """
    Called after every caller utterance.
    Pulls pending Signal instructions, generates AI response, returns TwiML.
    """
    logger.info(f"Speech [{call_sid[:12]}]: \"{SpeechResult}\" lang={LanguageCode}")

    call_state = active_calls.get(call_sid, {})
    if not SpeechResult:
        return await _clarification_response(call_sid, call_state)

    prefix_lang = call_state.get("language_detected") or "en-US"
    detected_lang = LanguageCode or _detect_language(SpeechResult, fallback=prefix_lang)
    lang_code     = detected_lang.split("-")[0].lower()
    logger.info(f"Language resolved [{call_sid[:12]}]: twilio={LanguageCode} text_detect={detected_lang}")

    if call_sid in active_calls:
        # Always update to the latest detected language so responses track the caller
        active_calls[call_sid]["language_detected"] = detected_lang
        active_calls[call_sid]["transcript"].append({
            "role": "user",
            "text": SpeechResult,
            "time": datetime.utcnow().isoformat(),
            "lang": detected_lang,
        })

    # Consume any Signal instructions the owner sent while the call was ongoing
    owner_instructions = owner.pop_instructions(call_sid)
    if owner_instructions:
        logger.info(f"Injecting {len(owner_instructions)} owner instruction(s)")

    # Stream GPT-4o and pipeline TTS on first sentence for lower latency
    sentences = []
    ai = {"text": "", "end_call": False, "urgency": "low", "topic": "", "caller_name_detected": ""}
    first_audio_url = None

    async for part in conversation.respond_streaming(
        call_sid=call_sid,
        user_text=SpeechResult,
        language=lang_code,
        call_state=call_state,
        owner_instructions=owner_instructions,
    ):
        if part["type"] == "sentence":
            sentences.append(part["text"])
            # Start TTS on the FIRST sentence immediately while GPT-4o continues
            if first_audio_url is None:
                first_audio_url = await tts.generate_and_upload(part["text"], lang_code, call_sid=call_sid)
        elif part["type"] == "done":
            ai = part

    # Accumulate GPT token usage for this turn
    if call_sid in active_calls:
        u = active_calls[call_sid].setdefault("usage", _empty_call_usage())
        u["gpt_prompt_tokens"] += ai.get("prompt_tokens", 0)
        u["gpt_completion_tokens"] += ai.get("completion_tokens", 0)

    # If GPT switched language (e.g. caller asked for German), update detection
    if ai.get("lang") and ai["lang"] in i18n.TWILIO_LANG_CODES:
        new_locale = i18n.TWILIO_LANG_CODES[ai["lang"]]
        if call_sid in active_calls and active_calls[call_sid].get("language_detected") != new_locale:
            logger.info(f"Language switch [{call_sid[:12]}]: {active_calls[call_sid].get('language_detected')} → {new_locale} (GPT meta)")
            active_calls[call_sid]["language_detected"] = new_locale
            lang_code = ai["lang"]

    if call_sid in active_calls:
        active_calls[call_sid]["transcript"].append({
            "role": "assistant",
            "text": ai["text"],
            "time": datetime.utcnow().isoformat(),
        })
        if ai.get("caller_name_detected") and not active_calls[call_sid].get("caller_name"):
            active_calls[call_sid]["caller_name"] = ai["caller_name_detected"]

    # Live Signal update every 2 exchanges
    n_turns = len(active_calls.get(call_sid, {}).get("transcript", []))
    if n_turns > 0 and n_turns % 4 == 0:
        background_tasks.add_task(_send_live_update, call_sid, ai)

    # Generate TTS for remaining sentences (first one is already done)
    audio_urls = [first_audio_url] if first_audio_url else []
    for sentence in sentences[1:]:
        url = await tts.generate_and_upload(sentence, lang_code, call_sid=call_sid)
        if url:
            audio_urls.append(url)

    # Build TwiML
    response = VoiceResponse()

    if ai.get("end_call"):
        if audio_urls:
            for url in audio_urls:
                response.play(url)
        else:
            _say(response, ai["text"], lang_code)
        response.hangup()
        background_tasks.add_task(_send_final_summary, call_sid)
    else:
        next_locale = _twilio_lang(lang_code)
        logger.info(f"Next Gather [{call_sid[:12]}]: STT={next_locale} lang_code={lang_code}")
        gather = Gather(
            input="speech",
            action=f"/twilio/process_speech/{call_sid}",
            method="POST",
            speech_timeout="2",
            language=next_locale,
            enhanced=True,
        )
        if audio_urls:
            for url in audio_urls:
                gather.play(url)
        else:
            _say(gather, ai["text"], lang_code)
        response.append(gather)
        response.redirect(f"/twilio/no_input/{call_sid}", method="POST")

    return Response(content=str(response), media_type="text/xml")


# ── No-input fallback ─────────────────────────────────────────────────────────

@app.post("/twilio/no_input/{call_sid}", dependencies=[Depends(verify_twilio_signature)])
async def no_input(call_sid: str, background_tasks: BackgroundTasks):
    """Handles silence / speech timeout – prompts once then hangs up."""
    call_state = active_calls.get(call_sid, {})
    lang_code  = (call_state.get("language_detected") or "en-US").split("-")[0].lower()

    response  = VoiceResponse()
    gather    = Gather(
        input="speech",
        action=f"/twilio/process_speech/{call_sid}",
        method="POST",
        speech_timeout="2",
        language=_twilio_lang(lang_code),
        enhanced=True,
    )
    prompt    = i18n.NO_INPUT_PROMPTS.get(lang_code, i18n.NO_INPUT_PROMPTS["en"])
    audio_url = await tts.generate_and_upload(prompt, lang_code, call_sid=call_sid)
    if audio_url:
        gather.play(audio_url)
    else:
        gather.say(prompt, language=_twilio_lang(lang_code))

    response.append(gather)
    goodbye = i18n.NO_INPUT_GOODBYES.get(lang_code, i18n.NO_INPUT_GOODBYES["en"])
    goodbye_url = await tts.generate_and_upload(goodbye, lang_code, call_sid=call_sid)
    if goodbye_url:
        response.play(goodbye_url)
    else:
        response.say(goodbye, language=_twilio_lang(lang_code))
    response.hangup()

    background_tasks.add_task(_send_final_summary, call_sid)
    return Response(content=str(response), media_type="text/xml")


# ── Call status callback ──────────────────────────────────────────────────────

@app.post("/twilio/status", dependencies=[Depends(verify_twilio_signature)])
async def call_status(
    background_tasks: BackgroundTasks,
    CallSid:      str           = Form(...),
    CallStatus:   str           = Form(...),
    CallDuration: Optional[str] = Form(None),
):
    """Twilio posts here on every call state change."""
    logger.info(f"Call status [{CallSid[:12]}]: {CallStatus} ({CallDuration}s)")

    if CallStatus in {"completed", "failed", "busy", "no-answer", "canceled"}:
        state = active_calls.get(CallSid, {})
        if state and not state.get("summary_sent"):
            background_tasks.add_task(_send_final_summary, CallSid)
        # Schedule cleanup in a background coroutine so we don't block Twilio's callback
        asyncio.create_task(_delayed_cleanup(CallSid))

    return Response(content="", status_code=204)


# ── Recording status callback ────────────────────────────────────────────────

@app.post("/twilio/recording_status", dependencies=[Depends(verify_twilio_signature)])
async def recording_status(
    CallSid: str = Form(...),
    RecordingSid: str = Form(...),
    RecordingUrl: str = Form(...),
    RecordingDuration: Optional[str] = Form(None),
):
    """Twilio posts here when a recording status changes."""
    logger.info(f"Recording status [{CallSid[:12]}]: {RecordingSid} duration={RecordingDuration}s")
    if CallSid in active_calls:
        active_calls[CallSid]["recording_url"] = f"{RecordingUrl}.mp3"
        active_calls[CallSid]["recording_sid"] = RecordingSid
    return Response(content="", status_code=204)


# ── Cleanup ──────────────────────────────────────────────────────────

async def _delayed_cleanup(call_sid: str):
    """Clean up call state after a delay, without blocking the HTTP handler."""
    await asyncio.sleep(90)
    active_calls.pop(call_sid, None)
    owner.clear_active_call(call_sid)
    conversation.cleanup(call_sid)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _twilio_lang(lang_code: str) -> str:
    return i18n.TWILIO_LANG_CODES.get(lang_code, "en-US")


def _detect_language(text: str, fallback: str = "en-US") -> str:
    """Detect language from speech text, return Twilio-style locale (e.g. 'pl-PL').

    Falls back to *fallback* if detection fails or text is too short.
    """
    if not text or len(text.split()) < 3:
        return fallback
    try:
        lang = _langdetect_detect(text)          # e.g. "pl", "de", "en"
        locale = i18n.TWILIO_LANG_CODES.get(lang)
        if locale:
            return locale
        return fallback
    except LangDetectException:
        return fallback


_DEFAULT_STT_LANG = os.getenv("DEFAULT_STT_LANG", "en-US")


def _say(parent, text: str, lang_code: str):
    lang_str, voice = i18n.POLLY_VOICES.get(
        lang_code, i18n.POLLY_VOICES["en"]
    )
    parent.say(text, language=lang_str, voice=voice)


async def _clarification_response(call_sid: str, call_state: dict):
    lang_code = (call_state.get("language_detected") or "en-US").split("-")[0].lower()
    text      = i18n.CLARIFICATIONS.get(
        lang_code, "I'm sorry, could you repeat that?"
    )
    response  = VoiceResponse()
    gather    = Gather(
        input="speech",
        action=f"/twilio/process_speech/{call_sid}",
        method="POST",
        speech_timeout="2",
        language=_twilio_lang(lang_code),
        enhanced=True,
    )
    audio_url = await tts.generate_and_upload(text, lang_code, call_sid=call_sid)
    if audio_url:
        gather.play(audio_url)
    else:
        _say(gather, text, lang_code)
    response.append(gather)
    return Response(content=str(response), media_type="text/xml")


async def _send_live_update(call_sid: str, ai: dict):
    state = active_calls.get(call_sid)
    if not state:
        return
    caller     = state.get("caller_name") or state.get("from", "Unknown")
    transcript = state.get("transcript", [])
    lines      = [
        f"{'👤' if e['role'] == 'user' else '🤖'} {e['text'][:150]}"
        for e in transcript[-6:]
    ]
    emoji = URGENCY_EMOJI.get(ai.get("urgency", "low"), "🟢")
    _sl = i18n.SIGNAL_LANG
    await owner.notify(
        i18n.SIG_LIVE_UPDATE.get(_sl, i18n.SIG_LIVE_UPDATE["en"]).format(
            caller=caller,
            emoji=emoji,
            topic=ai.get("topic") or "(detecting…)",
            turn=len(transcript) // 2,
            lines="\n".join(lines),
        ),
        call_sid,
    )


async def _send_final_summary(call_sid: str):
    state = active_calls.get(call_sid)
    if not state or state.get("summary_sent"):
        return
    active_calls[call_sid]["summary_sent"] = True

    transcript = state.get("transcript", [])
    caller     = state.get("caller_name") or state.get("from", "Unknown")

    _sl = i18n.SIGNAL_LANG

    if not transcript:
        await owner.notify(
            i18n.SIG_MISSED_CALL.get(_sl, i18n.SIG_MISSED_CALL["en"]).format(
                caller=caller, number=state.get("from", "?"),
                time=state.get("start_time", "?"),
            ),
            call_sid,
        )
        await _save_call_to_file(call_sid, "Missed call (no conversation)")
        return

    full_text = "\n".join(
        f"{'Caller' if e['role'] == 'user' else 'AVA'}: {e['text']}"
        for e in transcript
    )
    call_meta = conversation.get_call_meta(call_sid)
    summary, sum_prompt_tok, sum_compl_tok = await conversation.summarize(
        full_text, state.get("language_detected", "en"), call_meta,
    )

    # Merge summary tokens and TTS usage into call usage
    u = active_calls[call_sid].setdefault("usage", _empty_call_usage())
    u["summary_prompt_tokens"] += sum_prompt_tok
    u["summary_completion_tokens"] += sum_compl_tok

    tts_usage = tts.get_usage(call_sid)
    u["tts_elevenlabs_chars"] += tts_usage.get("elevenlabs_chars", 0)
    u["tts_openai_chars"] += tts_usage.get("openai_chars", 0)
    u["estimated_cost"] = _compute_cost(u)

    # Update session-wide totals
    for k in _total_usage:
        _total_usage[k] += u.get(k, 0)

    await owner.notify(
        i18n.SIG_SUMMARY.get(_sl, i18n.SIG_SUMMARY["en"]).format(
            caller=caller,
            number=state.get("from", "?"),
            lang=state.get("language_detected", "?"),
            start=state.get("start_time", "?"),
            summary=summary,
        ),
        call_sid,
    )

    transcript_text = "\n".join(
        f"{'👤' if e['role'] == 'user' else '🤖'} {e['text']}"
        for e in transcript
    )
    if transcript_text:
        header = i18n.SIG_TRANSCRIPT_HEADER.get(_sl, i18n.SIG_TRANSCRIPT_HEADER["en"])
        await owner.notify(f"{header}\n{transcript_text[:1800]}", call_sid)

    if state.get("recording_url"):
        await owner.notify(f"🎙 Recording: {state['recording_url']}", call_sid)

    await _save_call_to_file(call_sid, summary)
    logger.info(f"Final summary sent for {call_sid[:12]}")


def _write_json_file(path: Path, data: dict):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


async def _save_call_to_file(call_sid: str, summary: str):
    """Persist call data to /data/calls/ as JSON for later review."""
    state = active_calls.get(call_sid)
    if not state:
        return

    CALLS_DIR.mkdir(parents=True, exist_ok=True)

    date_prefix = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{date_prefix}_{call_sid[:8]}.json"

    call_data = {
        "call_sid": call_sid,
        "caller_number": state.get("from"),
        "caller_name": state.get("caller_name"),
        "start_time": state.get("start_time"),
        "end_time": datetime.utcnow().isoformat(),
        "language": state.get("language_detected"),
        "summary": summary,
        "transcript": state.get("transcript", []),
        "call_meta": conversation.get_call_meta(call_sid),
        "recording_url": state.get("recording_url"),
        "usage": state.get("usage"),
    }

    try:
        await asyncio.to_thread(_write_json_file, CALLS_DIR / filename, call_data)
        logger.info(f"Call data saved: /data/calls/{filename}")
    except Exception as exc:
        logger.error(f"Failed to save call data: {exc}")
