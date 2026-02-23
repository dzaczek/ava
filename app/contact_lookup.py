"""
AVA – Contact Lookup
====================
Resolves an incoming phone number to a human-readable name,
and detects the caller's likely language from the country dialling code.

Lookup order:
  1. Local contacts file  (data/contacts.json – exported from your phone)
  2. Twilio Lookup API    (CNAM – carrier-level caller name, costs ~$0.01/lookup)

contacts.json format (either):
  Array:  [{"name": "John Smith", "phones": ["+48123456789"]}]
  Object: {"+48123456789": "John Smith"}
"""

import json
import logging
import os
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

CONTACTS_FILE = Path("/data/contacts.json")


class ContactLookup:

    def __init__(self):
        self.twilio_sid   = os.getenv("TWILIO_ACCOUNT_SID")
        self.twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        self._contacts: dict[str, str] = {}
        self._load()

    def _load(self):
        """Load the contacts file into memory at startup."""
        if not CONTACTS_FILE.exists():
            logger.info("No contacts.json found – skipping local lookup")
            return

        try:
            data = json.loads(CONTACTS_FILE.read_text(encoding="utf-8"))

            if isinstance(data, dict):
                # Simple {number: name} mapping
                self._contacts = {self._e164(k): v for k, v in data.items()}

            elif isinstance(data, list):
                # Array of {name, phones[]}
                for entry in data:
                    name = entry.get("name", "")
                    for phone in entry.get("phones", []):
                        self._contacts[self._e164(phone)] = name

            logger.info(f"Loaded {len(self._contacts)} contacts")
        except Exception as exc:
            logger.error(f"Failed to load contacts.json: {exc}")

    @staticmethod
    def _e164(phone: str) -> str:
        """
        Normalise a phone number to E.164 format.
        Assumes +48 (Poland) for bare 9-digit numbers.
        """
        digits = "".join(c for c in phone if c.isdigit() or c == "+")
        if not digits.startswith("+") and len(digits) == 9:
            digits = "+48" + digits
        return digits

    async def lookup(self, phone: str) -> Optional[str]:
        """
        Return the caller's name or None if unknown.
        """
        normalised = self._e164(phone)

        # 1. Local contacts (free, instant)
        name = self._contacts.get(normalised) or self._contacts.get(phone)
        if name:
            logger.info(f"Local match for {normalised}: {name}")
            return name

        # 2. Twilio Lookup – CNAM (paid, ~$0.01)
        if self.twilio_sid and self.twilio_token:
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.get(
                        f"https://lookups.twilio.com/v2/PhoneNumbers/{phone}",
                        params={"Fields": "caller_name"},
                        auth=(self.twilio_sid, self.twilio_token),
                    )
                    if resp.status_code == 200:
                        cnam = resp.json().get("caller_name", {}).get("caller_name")
                        if cnam and cnam.upper() not in ("UNKNOWN", ""):
                            logger.info(f"CNAM match for {phone}: {cnam}")
                            return cnam
            except Exception as exc:
                logger.warning(f"Twilio CNAM lookup failed: {exc}")

        return None

    def add(self, phone: str, name: str):
        """Add a contact at runtime (not persisted to disk)."""
        self._contacts[self._e164(phone)] = name

    @staticmethod
    def language_from_number(phone: str) -> tuple[str, str]:
        """
        Infer the caller's likely language and Twilio BCP-47 locale
        from the E.164 country dialling prefix.

        Returns (lang_code, twilio_locale), e.g. ("pl", "pl-PL").
        Falls back to ("en", "en-US") for unknown prefixes.

        Prefix matching is longest-match: +1787 (Puerto Rico) wins over +1 (US/CA).
        """
        # (prefix, lang_code, twilio_locale)
        # Ordered longest-first so longest match wins.
        PREFIX_MAP: list[tuple[str, str, str]] = [
            # ── Europe ────────────────────────────────────────────
            ("+48",  "pl", "pl-PL"),   # Poland
            ("+49",  "de", "de-DE"),   # Germany
            ("+43",  "de", "de-AT"),   # Austria
            ("+41",  "de", "de-CH"),   # Switzerland (de as default)
            ("+44",  "en", "en-GB"),   # United Kingdom
            ("+353", "en", "en-IE"),   # Ireland
            ("+420", "cs", "cs-CZ"),   # Czech Republic
            ("+421", "sk", "sk-SK"),   # Slovakia
            ("+36",  "hu", "hu-HU"),   # Hungary
            ("+40",  "ro", "ro-RO"),   # Romania
            ("+359", "bg", "bg-BG"),   # Bulgaria
            ("+380", "uk", "uk-UA"),   # Ukraine
            ("+375", "ru", "ru-RU"),   # Belarus
            ("+7",   "ru", "ru-RU"),   # Russia / Kazakhstan
            ("+370", "lt", "lt-LT"),   # Lithuania
            ("+371", "lv", "lv-LV"),   # Latvia
            ("+372", "et", "et-EE"),   # Estonia
            ("+45",  "da", "da-DK"),   # Denmark
            ("+46",  "sv", "sv-SE"),   # Sweden
            ("+47",  "nb", "nb-NO"),   # Norway
            ("+358", "fi", "fi-FI"),   # Finland
            ("+31",  "nl", "nl-NL"),   # Netherlands
            ("+32",  "nl", "nl-BE"),   # Belgium (nl default)
            ("+33",  "fr", "fr-FR"),   # France
            ("+34",  "es", "es-ES"),   # Spain
            ("+351", "pt", "pt-PT"),   # Portugal
            ("+39",  "it", "it-IT"),   # Italy
            ("+30",  "el", "el-GR"),   # Greece
            ("+386", "sl", "sl-SI"),   # Slovenia
            ("+385", "hr", "hr-HR"),   # Croatia
            ("+381", "sr", "sr-RS"),   # Serbia
            # ── Americas ──────────────────────────────────────────
            ("+1787", "es", "es-PR"),  # Puerto Rico  (before +1)
            ("+1939", "es", "es-PR"),  # Puerto Rico
            ("+52",  "es", "es-MX"),   # Mexico
            ("+54",  "es", "es-AR"),   # Argentina
            ("+57",  "es", "es-CO"),   # Colombia
            ("+56",  "es", "es-CL"),   # Chile
            ("+55",  "pt", "pt-BR"),   # Brazil
            ("+1",   "en", "en-US"),   # US / Canada
            # ── Asia / Pacific ────────────────────────────────────
            ("+81",  "ja", "ja-JP"),   # Japan
            ("+82",  "ko", "ko-KR"),   # South Korea
            ("+86",  "zh", "zh-CN"),   # China
            ("+886", "zh", "zh-TW"),   # Taiwan
            ("+852", "zh", "zh-HK"),   # Hong Kong
            ("+91",  "hi", "hi-IN"),   # India (Hindi default)
            ("+90",  "tr", "tr-TR"),   # Turkey
            ("+972", "he", "he-IL"),   # Israel
            ("+966", "ar", "ar-SA"),   # Saudi Arabia
            ("+971", "ar", "ar-AE"),   # UAE
            ("+61",  "en", "en-AU"),   # Australia
            ("+64",  "en", "en-NZ"),   # New Zealand
            ("+27",  "en", "en-ZA"),   # South Africa
        ]

        normalised = phone if phone.startswith("+") else "+" + phone

        # Sort by prefix length descending to get longest match first
        for prefix, lang, locale in sorted(PREFIX_MAP, key=lambda x: -len(x[0])):
            if normalised.startswith(prefix):
                logger.info(f"Language detected from prefix {prefix}: {lang} ({locale})")
                return lang, locale

        logger.info(f"Unknown prefix for {phone}, defaulting to en-US")
        return "en", "en-US"
