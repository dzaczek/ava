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

    # Parse form body for POST validation
    body = await request.body()
    form_data = {}
    if body:
        from urllib.parse import parse_qs
        parsed = parse_qs(body.decode("utf-8"))
        form_data = {k: v[0] for k, v in parsed.items()}

    if not _twilio_validator.validate(url, form_data, signature):
        logger.warning(f"Rejected invalid Twilio signature from {request.client.host}")
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
    # We use getlist() to combine all X-Forwarded-For headers, preventing spoofing via multiple headers.
    xff_list = request.headers.getlist("X-Forwarded-For")
    if xff_list:
        client_ip = ",".join(xff_list).split(",")[-1].strip()

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

        return "\n".join([
            "AVA Statistics",
            "━━━━━━━━━━━━━━━━",
            f"Uptime: {_format_uptime()}",
            f"Total calls handled: {_call_count}",
            f"Saved call records: {len(call_files)}",
            f"TTS cache: {tts_count} files ({tts_size_mb:.1f} MB)",
            f"Memory (RSS): {rss_mb:.1f} MB",
            f"Python: {platform.python_version()}",
        ])

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

    async def _cmd_help(_args: str) -> str:
        return "\n".join([
            "AVA Signal Commands",
            "━━━━━━━━━━━━━━━━━━━━",
            "/ping     — alive check",
            "/status   — system status & active calls",
            "/stats    — statistics (calls, memory, cache)",
            "/calls    — recent call history",
            "/restart  — restart AVA process",
            "/help     — this message",
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

    # Detect language from caller's country prefix (+48 → pl, +49 → de, etc.)
    lang_code, twilio_locale = contacts.language_from_number(From)

    active_calls[CallSid] = {
        "from":              From,
        "caller_name":       caller_name,
        "start_time":        datetime.utcnow().isoformat(),
        "transcript":        [],
        "summary_sent":      False,
        "language_detected": twilio_locale,   # pre-populated from prefix
    }
    owner.set_active_call(CallSid)

    # Notify owner – include detected language so they know what to expect
    background_tasks.add_task(
        owner.notify,
        f"📞 *Incoming call*\n"
        f"From: *{display}*\n"
        f"Number: {From}\n"
        f"🌐 Language: {twilio_locale}\n"
        f"⏰ {datetime.now().strftime('%H:%M:%S')}\n\n"
        f"_Send instructions:_\n"
        f"• `tell him I'll call back tomorrow at 10`\n"
        f"• `ask for the order number`\n"
        f"• `end`",
        CallSid,
    )

    # Greet in the caller's detected language
    greeting  = i18n.GREETINGS.get(lang_code, i18n.GREETINGS["en"])
    audio_url = await tts.generate_and_upload(greeting, lang_code)

    response = VoiceResponse()
    gather   = Gather(
        input="speech",
        action=f"/twilio/process_speech/{CallSid}",
        method="POST",
        speech_timeout="auto",
        language=twilio_locale,   # Twilio STT also starts in detected language
        enhanced=True,
        speech_model="phone_call",
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
    logger.info(f"Speech [{call_sid[:12]}]: [REDACTED] lang={LanguageCode}")

    call_state = active_calls.get(call_sid, {})
    if not SpeechResult:
        return await _clarification_response(call_sid, call_state)

    detected_lang = LanguageCode or call_state.get("language_detected") or "en-US"
    lang_code     = detected_lang.split("-")[0].lower()

    if call_sid in active_calls:
        if not active_calls[call_sid].get("language_detected"):
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
                first_audio_url = await tts.generate_and_upload(part["text"], lang_code)
        elif part["type"] == "done":
            ai = part

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
        url = await tts.generate_and_upload(sentence, lang_code)
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
        gather = Gather(
            input="speech",
            action=f"/twilio/process_speech/{call_sid}",
            method="POST",
            speech_timeout="auto",
            language=_twilio_lang(lang_code),
            enhanced=True,
            speech_model="phone_call",
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
        speech_timeout="auto",
        language=_twilio_lang(lang_code),
    )
    prompt    = i18n.NO_INPUT_PROMPTS.get(lang_code, i18n.NO_INPUT_PROMPTS["en"])
    audio_url = await tts.generate_and_upload(prompt, lang_code)
    if audio_url:
        gather.play(audio_url)
    else:
        gather.say(prompt, language=_twilio_lang(lang_code))

    response.append(gather)
    response.say(
        i18n.NO_INPUT_GOODBYES.get(lang_code, i18n.NO_INPUT_GOODBYES["en"]),
        language=_twilio_lang(lang_code)
    )
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
        speech_timeout="auto",
        language=_twilio_lang(lang_code),
    )
    audio_url = await tts.generate_and_upload(text, lang_code)
    if audio_url:
        gather.play(audio_url)
    else:
        gather.say(text, language=_twilio_lang(lang_code))
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
    await owner.notify(
        f"📞 *Call in progress* – {caller}\n"
        f"{emoji} Topic: {ai.get('topic') or '(detecting…)'}\n"
        f"Turn: {len(transcript) // 2}\n\n"
        + "\n".join(lines)
        + "\n\n_Reply to send instructions_",
        call_sid,
    )


async def _send_final_summary(call_sid: str):
    state = active_calls.get(call_sid)
    if not state or state.get("summary_sent"):
        return
    active_calls[call_sid]["summary_sent"] = True

    transcript = state.get("transcript", [])
    caller     = state.get("caller_name") or state.get("from", "Unknown")

    if not transcript:
        await owner.notify(
            f"📵 *Missed call (no conversation)*\n"
            f"From: {caller} ({state.get('from', '?')})\n"
            f"Time: {state.get('start_time', '?')}",
            call_sid,
        )
        await _save_call_to_file(call_sid, "Missed call (no conversation)")
        return

    full_text = "\n".join(
        f"{'Caller' if e['role'] == 'user' else 'AVA'}: {e['text']}"
        for e in transcript
    )
    call_meta = conversation.get_call_meta(call_sid)
    summary   = await conversation.summarize(full_text, state.get("language_detected", "en"), call_meta)

    await owner.notify(
        f"📋 *Call summary*\n"
        f"━━━━━━━━━━━━━━\n"
        f"From: *{caller}*\n"
        f"Number: {state.get('from', '?')}\n"
        f"Language: {state.get('language_detected', '?')}\n"
        f"Started: {state.get('start_time', '?')}\n\n"
        f"*Summary:*\n{summary}",
        call_sid,
    )

    transcript_text = "\n".join(
        f"{'👤' if e['role'] == 'user' else '🤖'} {e['text']}"
        for e in transcript
    )
    if transcript_text:
        await owner.notify(f"*Transcript:*\n{transcript_text[:1800]}", call_sid)

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
    }

    try:
        await asyncio.to_thread(_write_json_file, CALLS_DIR / filename, call_data)
        logger.info(f"Call data saved: /data/calls/{filename}")
    except Exception as exc:
        logger.error(f"Failed to save call data: {exc}")
