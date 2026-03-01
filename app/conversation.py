"""
AVA – Conversation Manager
==========================
Drives the GPT-4o conversation loop.

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
from typing import AsyncIterator, Optional

from openai import AsyncOpenAI
from app import i18n

logger = logging.getLogger(__name__)
client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

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
SYSTEM_PROMPT = f"""You are a personal assistant answering calls on behalf of the phone owner.
The owner is currently unavailable and has asked you to handle incoming calls.

== WHO YOU ARE ==
{OWNER_CONTEXT}

You speak like a real human: naturally, warmly, with personality.
You automatically match the language of the caller.
If the caller asks you to switch language, do so immediately and stay in that language.
NEVER say you are an AI, bot, virtual assistant, or anything non-human. You are a real person.
If pressed ("are you a robot?"), deflect naturally — laugh it off, change the subject, or say something like "No, just tired today" or "I get that a lot, must be my phone voice".

== HOW TO RUN THE CALL ==
1. Greet naturally using your personality (no robotic scripts).
2. Find out why they are calling (one question at a time).
3. Collect key details: name, company, topic, callback number if needed.
4. Let them know you will pass the message on.
5. Close naturally and warmly.

Rules:
- Max 2–3 sentences per turn – speak like a person, not a FAQ page.
- Ask only one question per turn.
- If the caller is upset or the matter is urgent, be empathetic rather than formal.
- Do not promise specific callback times unless you receive an owner instruction to do so.
- Once you have all the relevant information, end the call – don't drag it out.
- Hard limit: 10 exchanges maximum.

== OWNER INSTRUCTIONS ==
During the call you may receive real-time instructions injected into the context:
- [OWNER_INSTRUCTION: text]   → act on this instruction naturally
- [RELAY_TO_CALLER: text]     → relay this information to the caller naturally
- [ASK_CALLER: question]      → ask the caller this question
- END_CALL_NOW                → wrap up and end the call in this very turn

== RESPONSE FORMAT ==
Write ONLY the text to be spoken aloud – plain sentences, no markdown, no lists, no asterisks.
Append metadata at the very end of every response (invisible to the caller):

<meta>{{"end_call": false, "urgency": "low|medium|high", "topic": "short topic in English", "caller_name": "first name if given, else empty", "lang": "two-letter language code you are responding in, e.g. pl, en, de"}}</meta>

Set end_call=true when:
- You have collected the necessary information and said goodbye
- You received END_CALL_NOW
- The caller is saying goodbye
- Exchange count > 9
"""

class ConversationManager:

    def __init__(self):
        self.model    = os.getenv("OPENAI_MODEL", "gpt-4o")
        self.histories: dict[str, list] = {}
        self.call_meta: dict[str, dict] = {}

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
            completion = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    *history[-20:],  # keep context window manageable
                ],
                max_tokens=350,
                temperature=0.75,
            )

            raw = completion.choices[0].message.content or ""

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
            stream = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    *history[-20:],
                ],
                max_tokens=350,
                temperature=0.75,
                stream=True,
            )

            buffer = ""
            full_response = ""

            async for chunk in stream:
                delta = chunk.choices[0].delta.content or ""
                if not delta:
                    continue
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

            yield {
                "type": "done",
                "text": parsed["text"],
                "end_call": parsed["end_call"] or force_end,
                "urgency": parsed["urgency"],
                "topic": parsed["topic"],
                "caller_name_detected": parsed["caller_name"],
                "lang": parsed["lang"],
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

    async def summarize(self, transcript: str, lang: str, call_meta: dict) -> str:
        """
        Ask GPT-4o to produce a concise English summary of the full call.
        Always returns English regardless of the call language.
        """
        urgency_map   = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🔴 HIGH"}
        urgency_label = urgency_map.get(call_meta.get("urgency", "low"), "🟢 Low")

        _sl = i18n.SIGNAL_LANG
        summary_prompt = i18n.SUMMARIZE_SYSTEM_PROMPT.get(
            _sl, i18n.SUMMARIZE_SYSTEM_PROMPT["en"]
        )

        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": summary_prompt},
                    {"role": "user", "content": f"Transcript:\n\n{transcript}"},
                ],
                max_tokens=400,
                temperature=0.2,
            )
            summary = resp.choices[0].message.content or "No content to summarise."
            return f"Priority: {urgency_label}\n\n{summary}"

        except Exception as exc:
            logger.error(f"Summary error: {exc}")
            return "Could not generate summary."

    def cleanup(self, call_sid: str):
        """Free memory for a completed call."""
        self.histories.pop(call_sid, None)
        self.call_meta.pop(call_sid, None)

    # ── Private ───────────────────────────────────────────────────────────────

    def _history(self, call_sid: str) -> list:
        if call_sid not in self.histories:
            self.histories[call_sid] = []
        return self.histories[call_sid]
