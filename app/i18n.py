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
    "es": ("es-ES", "Polly.Lucia"),
    "pt": ("pt-PT", "Polly.Ines"),
    "nl": ("nl-NL", "Polly.Lotte"),
    "ru": ("ru-RU", "Polly.Tatyana"),
    "hi": ("hi-IN", "Polly.Aditi"),
    # cs, sk, uk have no Polly voices — use Twilio basic TTS (no voice param)
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

# Multilingual greeting — played via Twilio Say (Polly), not our TTS voice.
# Asks the caller which language they want, then Whisper auto-detects from their answer.
# Multilingual greeting — played via Twilio Polly in the caller's prefix language.
# Asks which language they want, then Whisper auto-detects from their answer.
GREETING_LANG_QUESTION: dict[str, str] = {
    "en": "Hello! Which language would you like to use for this conversation? Please speak now.",
    "de": "Guten Tag! Welche Sprache möchten Sie für dieses Gespräch verwenden? Bitte sprechen Sie jetzt.",
    "pl": "Dzień dobry! W jakim języku chce Pan lub Pani prowadzić rozmowę? Proszę mówić.",
    "fr": "Bonjour ! Quelle langue souhaitez-vous utiliser pour cette conversation ? Parlez maintenant.",
    "it": "Buongiorno! In quale lingua desidera condurre questa conversazione? Prego, parli ora.",
    "es": "¡Buenos días! ¿En qué idioma desea mantener esta conversación? Hable ahora, por favor.",
    "cs": "Dobrý den! V jakém jazyce chcete vést tento rozhovor? Prosím, mluvte.",
    "sk": "Dobrý deň! V akom jazyku chcete viesť tento rozhovor? Prosím, hovorte.",
    "nl": "Goedendag! In welke taal wilt u dit gesprek voeren? Spreek alstublieft.",
    "pt": "Bom dia! Em que língua gostaria de conduzir esta conversa? Fale agora, por favor.",
    "uk": "Добрий день! Якою мовою ви хочете вести розмову? Будь ласка, говоріть.",
    "ru": "Добрый день! На каком языке вы хотите вести разговор? Пожалуйста, говорите.",
    "hi": "नमस्ते! आप इस बातचीत के लिए कौन सी भाषा इस्तेमाल करना चाहेंगे? कृपया बोलें।",
}

# Played while Whisper + GPT process the first response — via Polly, not our voice.
WHISPER_WAIT: dict[str, str] = {
    "en": "Language detected. Connecting you to the assistant, one moment please.",
    "de": "Sprache erkannt. Sie werden mit dem Assistenten verbunden, einen Moment bitte.",
    "pl": "Język wykryty. Łączę z asystentem, proszę chwilę poczekać.",
    "fr": "Langue détectée. Connexion avec l'assistant, un instant s'il vous plaît.",
    "it": "Lingua rilevata. Collegamento con l'assistente, un momento per favore.",
    "es": "Idioma detectado. Conectando con el asistente, un momento por favor.",
    "cs": "Jazyk rozpoznán. Připojuji k asistentovi, moment prosím.",
    "sk": "Jazyk rozpoznaný. Pripájam k asistentovi, moment prosím.",
    "hi": "भाषा पहचानी गई। सहायक से जोड़ रहे हैं, कृपया एक पल प्रतीक्षा करें।",
}

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
    "pl": "The STT language is set to Polish. Respond in whatever language the caller is ACTUALLY speaking — even if different from Polish. Set meta lang accordingly.",
    "en": "The STT language is set to English. Respond in whatever language the caller is ACTUALLY speaking — even if different from English. Set meta lang accordingly.",
    "de": "The STT language is set to German. Respond in whatever language the caller is ACTUALLY speaking — even if different from German. Set meta lang accordingly.",
    "cs": "The STT language is set to Czech. Respond in whatever language the caller is ACTUALLY speaking — even if different from Czech. Set meta lang accordingly.",
    "sk": "The STT language is set to Slovak. Respond in whatever language the caller is ACTUALLY speaking — even if different from Slovak. Set meta lang accordingly.",
    "fr": "The STT language is set to French. Respond in whatever language the caller is ACTUALLY speaking — even if different from French. Set meta lang accordingly.",
    "uk": "The STT language is set to Ukrainian. Respond in whatever language the caller is ACTUALLY speaking — even if different from Ukrainian. Set meta lang accordingly.",
    "es": "The STT language is set to Spanish. Respond in whatever language the caller is ACTUALLY speaking — even if different from Spanish. Set meta lang accordingly.",
    "it": "The STT language is set to Italian. Respond in whatever language the caller is ACTUALLY speaking — even if different from Italian. Set meta lang accordingly.",
    "hi": "The STT language is set to Hindi. Respond in whatever language the caller is ACTUALLY speaking — even if different from Hindi. Set meta lang accordingly.",
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
