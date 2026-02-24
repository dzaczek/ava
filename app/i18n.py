"""
AVA – Internationalization & Configuration
==========================================
Centralized storage for multilingual strings, voice mappings, and language-specific hints.
"""

import os

# ── Twilio Language Codes ─────────────────────────────────────────────────────
# Mapping from short language code to BCP-47 locale for Twilio STT/TTS
TWILIO_LANG_CODES: dict[str, str] = {
    "pl": "pl-PL",
    "en": "en-US",
    "cs": "cs-CZ",
    "sk": "sk-SK",
    "de": "de-DE",
    "fr": "fr-FR",
    "uk": "uk-UA",
    "es": "es-ES",
}

# ── Polly Voice Mapping ───────────────────────────────────────────────────────
# (BCP-47 locale, Voice ID)
POLLY_VOICES: dict[str, tuple[str, str]] = {
    "pl": ("pl-PL", "Polly.Ewa"),
    "en": ("en-US", "Polly.Joanna"),
    "de": ("de-DE", "Polly.Marlene"),
}

# ── ElevenLabs Voice IDs ──────────────────────────────────────────────────────
ELEVENLABS_VOICES: dict[str, str] = {
    "pl": os.getenv("ELEVENLABS_VOICE_PL", "pNInz6obpgDQGcFmaJgB"),
    "en": os.getenv("ELEVENLABS_VOICE_EN", "EXAVITQu4vr4xnSDxMaL"),
    "de": os.getenv("ELEVENLABS_VOICE_DE", "pNInz6obpgDQGcFmaJgB"),
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
    "uk": "Добрий день, я асистент власника телефону. Чим можу допомогти?",
    "en": "Hello, this is the owner's assistant. How can I help you?",
}

NO_INPUT_PROMPTS: dict[str, str] = {
    "en": "Is anyone there? Please speak if you'd like to leave a message.",
    "pl": "Przepraszam, czy jest tam ktoś? Proszę mówić.",
    "de": "Ist jemand da? Bitte sprechen Sie.",
}

NO_INPUT_GOODBYES: dict[str, str] = {
    "en": "No response detected. Thank you for calling. Goodbye.",
    "pl": "Nie słyszę odpowiedzi. Dziękuję za telefon. Do widzenia.",
    "de": "Keine Antwort. Danke für Ihren Anruf. Auf Wiederhören.",
}

CLARIFICATIONS: dict[str, str] = {
    "en": "I'm sorry, I didn't catch that. Could you please repeat?",
    "pl": "Przepraszam, nie dosłyszałam. Czy mógłby Pan/Pani powtórzyć?",
}

# ── GPT Assistant Hints & Fallbacks ──────────────────────────────────────────

LANG_HINTS: dict[str, str] = {
    "pl": "Respond ONLY in Polish.",
    "en": "Respond ONLY in English.",
    "de": "Respond ONLY in German.",
    "cs": "Respond ONLY in Czech.",
    "sk": "Respond ONLY in Slovak.",
    "fr": "Respond ONLY in French.",
    "uk": "Respond ONLY in Ukrainian.",
    "es": "Respond ONLY in Spanish.",
}

ERROR_FALLBACKS: dict[str, str] = {
    "en": "I'm sorry, I'm experiencing a technical issue. Please try again in a moment.",
    "pl": "Przepraszam, mam chwilowy problem techniczny. Proszę spróbować za chwilę.",
}
