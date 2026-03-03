"""
AVA – Conversation Manager
==========================
Drives the LLM conversation loop (OpenAI or Groq).

Key features:
- Stateful per-call message history
- Owner instructions injected mid-turn
- Automatic language adaptation
- Structured <meta> block in every response (end_call, urgency, topic)
- Intelligent call termination after 10 exchanges
"""

import os
import json
import logging
import re
import time
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI
from app import i18n

logger = logging.getLogger(__name__)

# ── LLM clients ──────────────────────────────────────────────────────────────
# LLM_PROVIDER: "openai" (default) or "groq"
# Groq uses an OpenAI-compatible API, so we reuse AsyncOpenAI with a different base_url.
_openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

_groq_key = os.getenv("GROQ_API_KEY")
_groq_client = (
    AsyncOpenAI(
        api_key=_groq_key,
        base_url="https://api.groq.com/openai/v1",
    )
    if _groq_key
    else None
)

_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()

# Default models per provider
_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "groq": "llama-3.3-70b-versatile",
}

def _get_client(provider: str = "") -> AsyncOpenAI:
    """Return the LLM client for the given provider."""
    p = provider or _LLM_PROVIDER
    if p == "groq" and _groq_client:
        return _groq_client
    return _openai_client

# ── Owner context ─────────────────────────────────────────────────────────────
# Customise via OWNER_CONTEXT env var – no code changes needed.
OWNER_CONTEXT = os.getenv("OWNER_CONTEXT", """
The phone owner is away and unavailable to take calls at the moment.
Working hours: Monday–Friday, 9:00–17:00.
If asked about a callback: "The owner will call back as soon as possible, usually within a few hours during business hours."
IT/infrastructure emergencies: always treat as high priority.
Recruiters and sales calls: politely thank them and end the call.
""").strip()

# ── System prompt ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are a personal assistant answering calls for the phone owner.
{OWNER_CONTEXT}

Match the caller's language. If asked to switch, do so immediately.
NEVER admit being AI. Deflect naturally if pressed.

Call flow: greet → find out why they call (one question per turn) → collect name, company, topic, callback number → confirm you'll pass the message → close warmly.
Max 2–3 sentences per turn. Max 10 exchanges. End when you have all info.

Owner instructions mid-call:
[OWNER_INSTRUCTION: text] → act on it. [RELAY_TO_CALLER: text] → relay naturally. [ASK_CALLER: q] → ask it. END_CALL_NOW → wrap up immediately.

Output ONLY spoken text (no markdown). Append at the end:
<meta>{{"end_call": false, "urgency": "low|medium|high", "topic": "short English topic", "caller_name": "first name or empty", "lang": "pl|en|de|..."}}</meta>
Set end_call=true when: info collected + goodbye said, END_CALL_NOW received, caller says goodbye, or turn > 9.
"""

class ConversationManager:

    def __init__(self):
        default_model = _DEFAULT_MODELS.get(_LLM_PROVIDER, "gpt-4o-mini")
        self.model         = os.getenv("LLM_MODEL", default_model)
        self.summary_model = os.getenv("LLM_SUMMARY_MODEL", self.model)
        self.client        = _get_client()
        # Summary always uses OpenAI (better multilingual quality)
        self.summary_client = _openai_client
        self.histories: dict[str, list] = {}
        self.call_meta: dict[str, dict] = {}
        logger.info(f"LLM provider: {_LLM_PROVIDER}, model: {self.model}, summary: {self.summary_model}")

    # ── Public API ────────────────────────────────────────────────────────────

    async def respond(
        self,
        call_sid: str,
        user_text: str,
        language: str,
        call_state: dict,
        owner_instructions: Optional[list[str]] = None,
    ) -> dict:
        """
        Generate AVA's next response.

        Returns dict with keys:
          text, end_call, urgency, topic, caller_name_detected
        """
        history    = self._history(call_sid)
        force_end  = False

        # Inject owner instructions into the user turn as hidden context markers
        if owner_instructions:
            for instr in owner_instructions:
                if instr == "__END_CALL__":
                    force_end = True
                    user_text += "\n\nEND_CALL_NOW"
                elif instr.startswith(("RELAY_TO_CALLER:", "ASK_CALLER:")):
                    user_text += f"\n\n[{instr}]"
                else:
                    user_text += f"\n\n[OWNER_INSTRUCTION: {instr}]"

        history.append({"role": "user", "content": user_text})

        # Build the system prompt for this turn
        system = SYSTEM_PROMPT
        if language in i18n.LANG_HINTS:
            system += f"\n\n{i18n.LANG_HINTS[language]}"

        # Provide caller's contact-book name if we have it
        if call_state.get("caller_name"):
            system += f"\n\nThe caller appears in the owner's contacts as: {call_state['caller_name']}"

        # Warn AVA when it's time to wrap up
        n_user_turns = sum(1 for m in history if m["role"] == "user")
        if n_user_turns >= 8:
            system += "\n\n⚠️ You are at 8+ exchanges. End the call at the very next natural opportunity."

        try:
            completion = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    *history[-20:],  # keep context window manageable
                ],
                max_tokens=180,
                temperature=0.75,
            )

            raw = completion.choices[0].message.content or ""
            usage = completion.usage

            parsed = self._parse_meta(raw)
            self._persist_meta(call_sid, parsed)
            history.append({"role": "assistant", "content": parsed["text"]})

            return {
                "text": parsed["text"],
                "end_call": parsed["end_call"] or force_end,
                "urgency": parsed["urgency"],
                "topic": parsed["topic"],
                "caller_name_detected": parsed["caller_name"],
                "lang": parsed["lang"],
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
            }

        except Exception as exc:
            logger.error(f"OpenAI error: {exc}")
            return {
                "text": i18n.ERROR_FALLBACKS.get(
                    language, i18n.ERROR_FALLBACKS["en"]
                ),
                "end_call": True, "urgency": "low",
                "topic": "", "caller_name_detected": "",
            }

    # ── Streaming API ────────────────────────────────────────────────────────

    _SENTENCE_END = re.compile(r'(?<=[.!?])\s')

    async def respond_streaming(
        self,
        call_sid: str,
        user_text: str,
        language: str,
        call_state: dict,
        owner_instructions: Optional[list[str]] = None,
    ) -> AsyncIterator[dict]:
        """
        Stream GPT-4o response, yielding complete sentences as they arrive.

        Yields dicts:
          {"type": "sentence", "text": "..."}   — a complete sentence ready for TTS
          {"type": "done", "text": "...", "end_call": ..., ...}  — final result with meta
        """
        history   = self._history(call_sid)
        force_end = False

        if owner_instructions:
            for instr in owner_instructions:
                if instr == "__END_CALL__":
                    force_end = True
                    user_text += "\n\nEND_CALL_NOW"
                elif instr.startswith(("RELAY_TO_CALLER:", "ASK_CALLER:")):
                    user_text += f"\n\n[{instr}]"
                else:
                    user_text += f"\n\n[OWNER_INSTRUCTION: {instr}]"

        history.append({"role": "user", "content": user_text})

        system = SYSTEM_PROMPT
        if language in i18n.LANG_HINTS:
            system += f"\n\n{i18n.LANG_HINTS[language]}"
        if call_state.get("caller_name"):
            system += f"\n\nThe caller appears in the owner's contacts as: {call_state['caller_name']}"

        n_user_turns = sum(1 for m in history if m["role"] == "user")
        if n_user_turns >= 8:
            system += "\n\n⚠️ You are at 8+ exchanges. End the call at the very next natural opportunity."

        try:
            stream_kwargs: dict = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system},
                    *history[-20:],
                ],
                "max_tokens": 180,
                "temperature": 0.75,
                "stream": True,
            }
            # Groq doesn't support stream_options
            if _LLM_PROVIDER != "groq":
                stream_kwargs["stream_options"] = {"include_usage": True}

            _llm_start = time.monotonic()
            stream = await self.client.chat.completions.create(**stream_kwargs)

            buffer = ""
            full_response = ""
            usage = None
            _first_token_time = None

            async for chunk in stream:
                if chunk.usage:
                    usage = chunk.usage
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
                if _first_token_time is None:
                    _first_token_time = time.monotonic()
                buffer += delta
                full_response += delta

                # Yield complete sentences as soon as they arrive
                while True:
                    match = self._SENTENCE_END.search(buffer)
                    if not match:
                        break
                    sentence = buffer[:match.start() + 1].strip()
                    buffer = buffer[match.end():]
                    # Don't yield the <meta> block as a sentence
                    if "<meta>" not in sentence:
                        yield {"type": "sentence", "text": sentence}

            # Process remaining buffer
            parsed = self._parse_meta(full_response)
            remaining = buffer.split("<meta>")[0].strip()
            if remaining:
                yield {"type": "sentence", "text": remaining}

            self._persist_meta(call_sid, parsed)
            history.append({"role": "assistant", "content": parsed["text"]})

            _llm_end = time.monotonic()
            yield {
                "type": "done",
                "text": parsed["text"],
                "end_call": parsed["end_call"] or force_end,
                "urgency": parsed["urgency"],
                "topic": parsed["topic"],
                "caller_name_detected": parsed["caller_name"],
                "lang": parsed["lang"],
                "prompt_tokens": usage.prompt_tokens if usage else 0,
                "completion_tokens": usage.completion_tokens if usage else 0,
                "timing": {
                    "llm_first_token": round((_first_token_time or _llm_end) - _llm_start, 3),
                    "llm_total": round(_llm_end - _llm_start, 3),
                },
            }

        except Exception as exc:
            logger.error(f"OpenAI streaming error: {exc}")
            fallback_text = i18n.ERROR_FALLBACKS.get(
                language, i18n.ERROR_FALLBACKS["en"]
            )
            yield {
                "type": "done",
                "text": fallback_text,
                "end_call": True, "urgency": "low",
                "topic": "", "caller_name_detected": "",
            }

    # ── Meta parsing helpers ───────────────────────────────────────────────

    @staticmethod
    def _parse_meta(raw: str) -> dict:
        """Extract <meta> JSON block from GPT response and return parsed data."""
        end_call, urgency, topic, caller_name, lang = False, "low", "", "", ""
        text = raw

        if "<meta>" in raw and "</meta>" in raw:
            try:
                meta_json = raw.split("<meta>")[1].split("</meta>")[0]
                meta = json.loads(meta_json)
                end_call    = meta.get("end_call", False)
                urgency     = meta.get("urgency", "low")
                topic       = meta.get("topic", "")
                caller_name = meta.get("caller_name", "")
                lang        = meta.get("lang", "")
                text        = raw.split("<meta>")[0].strip()
            except Exception:
                pass

        return {
            "text": text,
            "end_call": end_call,
            "urgency": urgency,
            "topic": topic,
            "caller_name": caller_name,
            "lang": lang,
        }

    def _persist_meta(self, call_sid: str, parsed: dict):
        """Store extracted metadata for the call."""
        meta_update = {k: v for k, v in {
            "urgency": parsed["urgency"],
            "topic": parsed["topic"],
            "caller_name_detected": parsed["caller_name"],
        }.items() if v}
        self.call_meta.setdefault(call_sid, {}).update(meta_update)

    def get_call_meta(self, call_sid: str) -> dict:
        return self.call_meta.get(call_sid, {})

    async def summarize(self, transcript: str, lang: str, call_meta: dict) -> tuple[str, int, int]:
        """
        Ask GPT-4o to produce a concise English summary of the full call.
        Always returns English regardless of the call language.

        Returns (summary_text, prompt_tokens, completion_tokens).
        """
        urgency_map   = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🔴 HIGH"}
        urgency_label = urgency_map.get(call_meta.get("urgency", "low"), "🟢 Low")

        _sl = i18n.SIGNAL_LANG
        summary_prompt = i18n.SUMMARIZE_SYSTEM_PROMPT.get(
            _sl, i18n.SUMMARIZE_SYSTEM_PROMPT["en"]
        )

        try:
            resp = await self.summary_client.chat.completions.create(
                model=self.summary_model,
                messages=[
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": f"Transcript:\n\n{transcript}"},
                ],
                max_tokens=400,
                temperature=0.2,
            )
            summary = resp.choices[0].message.content or "No content to summarise."
            usage = resp.usage
            return (
                f"Priority: {urgency_label}\n\n{summary}",
                usage.prompt_tokens if usage else 0,
                usage.completion_tokens if usage else 0,
            )

        except Exception as exc:
            logger.error(f"Summary error: {exc}")
            return "Could not generate summary.", 0, 0

    def cleanup(self, call_sid: str):
        """Free memory for a completed call."""
        self.histories.pop(call_sid, None)
        self.call_meta.pop(call_sid, None)

    # ── Private ───────────────────────────────────────────────────────────────

    def _history(self, call_sid: str) -> list:
        if call_sid not in self.histories:
            self.histories[call_sid] = []
        return self.histories[call_sid]
