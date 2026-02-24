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
from typing import Optional

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
SYSTEM_PROMPT = f"""You are AVA – a professional AI voice assistant answering calls on behalf of the phone owner.
The owner is currently unavailable and has asked you to handle incoming calls.

== WHO YOU ARE ==
You are a natural, warm, professional assistant – not an IVR robot.
You speak like a human: naturally, without corporate filler phrases.
You automatically match the language of the caller.
Do not volunteer that you are an AI. If asked directly ("are you a robot / AI?"), say you are a virtual assistant.

== ABOUT THE OWNER ==
{OWNER_CONTEXT}

== HOW TO RUN THE CALL ==
1. Greet: "Hello, this is the owner's assistant. How can I help you?"
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

<meta>{{"end_call": false, "urgency": "low|medium|high", "topic": "short topic in English", "caller_name": "first name if given, else empty"}}</meta>

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

            # Parse <meta> block
            end_call, urgency, topic, caller_name = False, "low", "", ""
            if "<meta>" in raw and "</meta>" in raw:
                try:
                    meta_json = raw.split("<meta>")[1].split("</meta>")[0]
                    meta      = json.loads(meta_json)
                    end_call    = meta.get("end_call", False)
                    urgency     = meta.get("urgency", "low")
                    topic       = meta.get("topic", "")
                    caller_name = meta.get("caller_name", "")
                    raw         = raw.split("<meta>")[0].strip()
                except Exception:
                    pass  # if meta parsing fails, continue without it

            # Persist extracted metadata
            meta_update = {k: v for k, v in {
                "urgency": urgency, "topic": topic,
                "caller_name_detected": caller_name,
            }.items() if v}
            self.call_meta.setdefault(call_sid, {}).update(meta_update)

            history.append({"role": "assistant", "content": raw})

            return {
                "text": raw,
                "end_call": end_call or force_end,
                "urgency": urgency,
                "topic": topic,
                "caller_name_detected": caller_name,
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

    def get_call_meta(self, call_sid: str) -> dict:
        return self.call_meta.get(call_sid, {})

    async def summarize(self, transcript: str, lang: str, call_meta: dict) -> str:
        """
        Ask GPT-4o to produce a concise English summary of the full call.
        Always returns English regardless of the call language.
        """
        urgency_map   = {"low": "🟢 Low", "medium": "🟡 Medium", "high": "🔴 HIGH"}
        urgency_label = urgency_map.get(call_meta.get("urgency", "low"), "🟢 Low")

        try:
            resp = await client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Summarise the following phone call transcript in English. "
                            "Be concise (max 5 sentences). Cover: "
                            "1) reason for the call, "
                            "2) caller's name and company if mentioned, "
                            "3) whether a callback is needed and when, "
                            "4) any action items."
                        ),
                    },
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
