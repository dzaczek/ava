"""
AVA – Internationalization & Configuration
==========================================
Centralized storage for multilingual strings, voice mappings, and language-specific hints.
"""

import os

# ── Signal notification language ─────────────────────────────────────────────
# Set SIGNAL_LANG in .env to control the language of Signal messages (pl / en).
SIGNAL_LANG: str = os.getenv("SIGNAL_LANG", "en")

# ── Twilio Language Codes ─────────────────────────────────────────────────────
# Mapping from short language code to BCP-47 locale for Twilio STT/TTS
TWILIO_LANG_CODES: dict[str, str] = {
    "pl": "pl-PL",
    "en": "en-US",
    "cs": "cs-CZ",
    "sk": "sk-SK",
    "de": "de-DE",
    "fr": "fr-FR",
    "it": "it-IT",
    "hi": "hi-IN",
    "uk": "uk-UA",
    "es": "es-ES",
}

# ── Polly Voice Mapping ───────────────────────────────────────────────────────
# (BCP-47 locale, Voice ID)
POLLY_VOICES: dict[str, tuple[str, str]] = {
    "pl": ("pl-PL", "Polly.Ewa"),
    "en": ("en-US", "Polly.Joanna"),
    "de": ("de-DE", "Polly.Marlene"),
    "fr": ("fr-FR", "Polly.Lea"),
    "it": ("it-IT", "Polly.Bianca"),
    "hi": ("hi-IN", "Polly.Aditi"),
}

# ── ElevenLabs Voice IDs ──────────────────────────────────────────────────────
ELEVENLABS_VOICES: dict[str, str] = {
    "pl": os.getenv("ELEVENLABS_VOICE_PL", "pNInz6obpgDQGcFmaJgB"),
    "en": os.getenv("ELEVENLABS_VOICE_EN", "EXAVITQu4vr4xnSDxMaL"),
    "de": os.getenv("ELEVENLABS_VOICE_DE", "pNInz6obpgDQGcFmaJgB"),
    "fr": os.getenv("ELEVENLABS_VOICE_FR", "pNInz6obpgDQGcFmaJgB"),
    "it": os.getenv("ELEVENLABS_VOICE_IT", "pNInz6obpgDQGcFmaJgB"),
    "hi": os.getenv("ELEVENLABS_VOICE_HI", "pNInz6obpgDQGcFmaJgB"),
}
ELEVENLABS_DEFAULT = os.getenv("ELEVENLABS_VOICE_DEFAULT", "pNInz6obpgDQGcFmaJgB")

# ── Interaction Strings ───────────────────────────────────────────────────────

GREETINGS: dict[str, str] = {
    "pl": "Dzień dobry, tu asystentka właściciela telefonu. W czym mogę pomóc?",
    "de": "Guten Tag, hier ist die Assistentin des Telefoneigentümers. Wie kann ich Ihnen helfen?",
    "fr": "Bonjour, je suis l'assistante du propriétaire. Comment puis-je vous aider?",
    "es": "Buenos días, soy la asistente del propietario. ¿En qué puedo ayudarle?",
    "cs": "Dobrý den, jsem asistentka majitele telefonu. Jak vám mohu pomoci?",
    "sk": "Dobrý deň, som asistentka majiteľa telefónu. Ako vám môžem pomôcť?",
    "it": "Buongiorno, sono l'assistente del proprietario. Come posso aiutarla?",
    "nl": "Goedendag, ik ben de assistent van de eigenaar. Hoe kan ik u helpen?",
    "pt": "Bom dia, sou a assistente do proprietário. Como posso ajudar?",
    "ru": "Добрый день, я ассистент владельца телефона. Чем могу помочь?",
    "hi": "नमस्ते, मैं फ़ोन के मालिक की सहायक हूँ। मैं आपकी कैसे मदद कर सकती हूँ?",
    "uk": "Добрий день, я асистент власника телефону. Чим можу допомогти?",
    "en": "Hello, this is the owner's assistant. How can I help you?",
}

NO_INPUT_PROMPTS: dict[str, str] = {
    "en": "Is anyone there? Please speak if you'd like to leave a message.",
    "pl": "Przepraszam, czy jest tam ktoś? Proszę mówić.",
    "de": "Ist jemand da? Bitte sprechen Sie.",
    "fr": "Il y a quelqu'un ? Parlez si vous souhaitez laisser un message.",
    "it": "C'è qualcuno? Parli pure se desidera lasciare un messaggio.",
    "hi": "क्या कोई है? कृपया बोलें अगर आप संदेश छोड़ना चाहते हैं।",
}

NO_INPUT_GOODBYES: dict[str, str] = {
    "en": "No response detected. Thank you for calling. Goodbye.",
    "pl": "Nie słyszę odpowiedzi. Dziękuję za telefon. Do widzenia.",
    "de": "Keine Antwort. Danke für Ihren Anruf. Auf Wiederhören.",
    "fr": "Aucune réponse détectée. Merci d'avoir appelé. Au revoir.",
    "it": "Nessuna risposta rilevata. Grazie per la chiamata. Arrivederci.",
    "hi": "कोई जवाब नहीं मिला। कॉल करने के लिए धन्यवाद। अलविदा।",
}

CLARIFICATIONS: dict[str, str] = {
    "en": "I'm sorry, I didn't catch that. Could you please repeat?",
    "pl": "Przepraszam, nie dosłyszałam. Czy mógłby Pan/Pani powtórzyć?",
    "de": "Entschuldigung, ich habe das nicht verstanden. Könnten Sie das bitte wiederholen?",
    "fr": "Excusez-moi, je n'ai pas compris. Pourriez-vous répéter ?",
    "it": "Mi scusi, non ho capito. Potrebbe ripetere per favore?",
    "hi": "क्षमा करें, मुझे समझ नहीं आया। क्या आप दोहरा सकते हैं?",
}

# ── GPT Assistant Hints & Fallbacks ──────────────────────────────────────────

LANG_HINTS: dict[str, str] = {
    "pl": "The caller is currently speaking Polish. Respond in Polish. If the caller explicitly asks you to switch to another language, do so immediately.",
    "en": "The caller is currently speaking English. Respond in English. If the caller explicitly asks you to switch to another language, do so immediately.",
    "de": "The caller is currently speaking German. Respond in German. If the caller explicitly asks you to switch to another language, do so immediately.",
    "cs": "The caller is currently speaking Czech. Respond in Czech. If the caller explicitly asks you to switch to another language, do so immediately.",
    "sk": "The caller is currently speaking Slovak. Respond in Slovak. If the caller explicitly asks you to switch to another language, do so immediately.",
    "fr": "The caller is currently speaking French. Respond in French. If the caller explicitly asks you to switch to another language, do so immediately.",
    "uk": "The caller is currently speaking Ukrainian. Respond in Ukrainian. If the caller explicitly asks you to switch to another language, do so immediately.",
    "es": "The caller is currently speaking Spanish. Respond in Spanish. If the caller explicitly asks you to switch to another language, do so immediately.",
    "it": "The caller is currently speaking Italian. Respond in Italian. If the caller explicitly asks you to switch to another language, do so immediately.",
    "hi": "The caller is currently speaking Hindi. Respond in Hindi. If the caller explicitly asks you to switch to another language, do so immediately.",
}

ERROR_FALLBACKS: dict[str, str] = {
    "en": "I'm sorry, I'm experiencing a technical issue. Please try again in a moment.",
    "pl": "Przepraszam, mam chwilowy problem techniczny. Proszę spróbować za chwilę.",
}

# ── Signal notification templates ────────────────────────────────────────────
# Keyed by SIGNAL_LANG value. Use .format() placeholders.

SIG_INCOMING: dict[str, str] = {
    "en": (
        "📞 *Incoming call*\n"
        "From: *{display}*\n"
        "Number: {number}\n"
        "🌐 Language: {lang}\n"
        "⏰ {time}\n\n"
        "_Send instructions:_\n"
        "• `tell him I'll call back tomorrow at 10`\n"
        "• `ask for the order number`\n"
        "• `end`"
    ),
    "pl": (
        "📞 *Połączenie przychodzące*\n"
        "Od: *{display}*\n"
        "Numer: {number}\n"
        "🌐 Język: {lang}\n"
        "⏰ {time}\n\n"
        "_Wyślij instrukcje:_\n"
        "• `powiedz mu że oddzwonię jutro o 10`\n"
        "• `zapytaj o numer zamówienia`\n"
        "• `end`"
    ),
}

SIG_LIVE_UPDATE: dict[str, str] = {
    "en": (
        "📞 *Call in progress* – {caller}\n"
        "{emoji} Topic: {topic}\n"
        "Turn: {turn}\n\n"
        "{lines}\n\n"
        "_Reply to send instructions_"
    ),
    "pl": (
        "📞 *Rozmowa w toku* – {caller}\n"
        "{emoji} Temat: {topic}\n"
        "Tura: {turn}\n\n"
        "{lines}\n\n"
        "_Odpowiedz aby wysłać instrukcje_"
    ),
}

SIG_MISSED_CALL: dict[str, str] = {
    "en": (
        "📵 *Missed call (no conversation)*\n"
        "From: {caller} ({number})\n"
        "Time: {time}"
    ),
    "pl": (
        "📵 *Nieodebrane połączenie (brak rozmowy)*\n"
        "Od: {caller} ({number})\n"
        "Czas: {time}"
    ),
}

SIG_SUMMARY: dict[str, str] = {
    "en": (
        "📋 *Call summary*\n"
        "━━━━━━━━━━━━━━\n"
        "From: *{caller}*\n"
        "Number: {number}\n"
        "Language: {lang}\n"
        "Started: {start}\n\n"
        "*Summary:*\n{summary}"
    ),
    "pl": (
        "📋 *Podsumowanie rozmowy*\n"
        "━━━━━━━━━━━━━━\n"
        "Od: *{caller}*\n"
        "Numer: {number}\n"
        "Język: {lang}\n"
        "Rozpoczęto: {start}\n\n"
        "*Podsumowanie:*\n{summary}"
    ),
}

SIG_TRANSCRIPT_HEADER: dict[str, str] = {
    "en": "*Transcript:*",
    "pl": "*Transkrypcja:*",
}

SUMMARIZE_SYSTEM_PROMPT: dict[str, str] = {
    "en": (
        "Summarise the following phone call transcript in English. "
        "Be concise (max 5 sentences). Cover: "
        "1) reason for the call, "
        "2) caller's name and company if mentioned, "
        "3) whether a callback is needed and when, "
        "4) any action items."
    ),
    "pl": (
        "Podsumuj poniższą transkrypcję rozmowy telefonicznej po polsku. "
        "Bądź zwięzły (maks. 5 zdań). Zawrzyj: "
        "1) powód połączenia, "
        "2) imię i firmę dzwoniącego (jeśli podane), "
        "3) czy potrzebne jest oddzwonienie i kiedy, "
        "4) zadania do wykonania."
    ),
}
