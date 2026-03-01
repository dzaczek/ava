# AVA -- Asystent glosowy AI

## Instrukcja instalacji i konfiguracji

---

### Spis tresci

1. [Wymagania](#1-wymagania)
2. [Pobranie projektu](#2-pobranie-projektu)
3. [Konfiguracja zmiennych srodowiskowych](#3-konfiguracja-zmiennych-srodowiskowych)
4. [Rejestracja numeru Signal](#4-rejestracja-numeru-signal)
5. [Konfiguracja Twilio](#5-konfiguracja-twilio)
6. [Konfiguracja domeny i DNS](#6-konfiguracja-domeny-i-dns)
7. [Cloudflare Tunnel (alternatywa dla Caddy)](#7-cloudflare-tunnel-alternatywa-dla-caddy)
8. [Uruchomienie](#8-uruchomienie)
9. [Przekierowanie polaczen z telefonu](#9-przekierowanie-polaczen-z-telefonu)
10. [Ksiazka kontaktow (opcjonalnie)](#10-ksiazka-kontaktow-opcjonalnie)
11. [ElevenLabs TTS (opcjonalnie)](#11-elevenlabs-tts-opcjonalnie)
12. [Personalizacja asystenta](#12-personalizacja-asystenta)
13. [Weryfikacja dzialania](#13-weryfikacja-dzialania)
14. [Logi polaczen](#14-logi-polaczen)
15. [Komendy Signal podczas rozmowy](#15-komendy-signal-podczas-rozmowy)
16. [Koszty eksploatacji](#16-koszty-eksploatacji)
17. [Rozwiazywanie problemow](#17-rozwiazywanie-problemow)
18. [Zabezpieczenia](#18-zabezpieczenia)

---

### 1. Wymagania

Przed rozpoczeciem instalacji upewnij sie, ze dysponujesz:

**Infrastruktura:**

- Serwer VPS lub dedykowany z publicznym adresem IP
- System operacyjny: Linux (Ubuntu 22.04+, Debian 12+, lub inny z obsluga Dockera)
- Porty 80 i 443 otwarte i dostepne z internetu
- Docker Engine (wersja 20.10 lub nowsza)
- Docker Compose v2 (polecenie `docker compose`)
- Domena z dostepem do konfiguracji DNS (rekordy A/AAAA)

**Konta i uslugi:**

- Konto Twilio (https://console.twilio.com) z zakupionym numerem telefonu
- Klucz API OpenAI (https://platform.openai.com)
- Oddzielny numer telefonu (karta SIM) do rejestracji bota Signal
- Osobisty numer Signal, na ktory bedziesz otrzymywac powiadomienia

**Opcjonalnie:**

- Konto ElevenLabs (https://elevenlabs.io) -- lepsza jakosc syntezy mowy

---

### 2. Pobranie projektu

Skopiuj pliki projektu na serwer:

```bash
cd /opt
git clone <adres-repozytorium> ava
cd ava
```

Lub, jesli nie uzywasz git, przeslij pliki przez SCP/SFTP do katalogu `/opt/ava`.

Utworz wymagane katalogi:

```bash
mkdir -p data/calls
```

---

### 3. Konfiguracja zmiennych srodowiskowych

Skopiuj plik szablonu i otworz go w edytorze:

```bash
cp .env.example .env
nano .env
```

Ponizej opis kazdej zmiennej:

#### Twilio Voice

| Zmienna | Opis | Przyklad |
|---------|------|---------|
| `TWILIO_ACCOUNT_SID` | Identyfikator konta Twilio. Znajdziesz go na stronie glownej konsoli Twilio. | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Token autoryzacyjny Twilio. Uzywany rowniez do walidacji podpisow webhookow. | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_PHONE_NUMBER` | Numer telefonu zakupiony w Twilio, na ktory beda przekierowywane polaczenia. | `+48123456789` |

#### Signal

| Zmienna | Opis | Przyklad |
|---------|------|---------|
| `SIGNAL_CLI_URL` | Adres wewnetrzny kontenera signal-cli. Nie zmieniaj tej wartosci. | `http://signal-cli:8080` |
| `SIGNAL_SENDER_NUMBER` | Numer telefonu bota Signal (oddzielna karta SIM, zarejestrowana w kroku 4). | `+48111222333` |
| `SIGNAL_RECIPIENT` | Twoj osobisty numer Signal, na ktory AVA bedzie wysylac powiadomienia. | `+48999888777` |

#### OpenAI

| Zmienna | Opis | Przyklad |
|---------|------|---------|
| `OPENAI_API_KEY` | Klucz API OpenAI. | `sk-proj-...` |
| `OPENAI_MODEL` | Model GPT do rozmow. Domyslnie `gpt-4o`. Mozesz uzyc `gpt-4o-mini` dla nizszych kosztow. | `gpt-4o` |

#### ElevenLabs TTS (opcjonalnie)

| Zmienna | Opis | Przyklad |
|---------|------|---------|
| `ELEVENLABS_API_KEY` | Klucz API ElevenLabs. Pozostaw pusty, aby uzyc OpenAI TTS. | (pusty lub klucz) |
| `ELEVENLABS_VOICE_ID` | Wielojezyczny identyfikator glosu (jeden dla wszystkich jezykow). | `WAhoMTNdLdMoq1j3wf3I` |
| `ELEVENLABS_MODEL` | Model ElevenLabs. `eleven_multilingual_v2` (najlepsza jakosc) lub `eleven_turbo_v2_5` (szybszy). | `eleven_multilingual_v2` |
| `OPENAI_TTS_VOICE` | Zapasowy glos OpenAI TTS: alloy, echo, fable, onyx, nova, shimmer. | `nova` |

#### Personalizacja

| Zmienna | Opis |
|---------|------|
| `OWNER_CONTEXT` | Persona asystentki + informacje o wlascicielu. Wstrzykiwane do promptu GPT-4o. Musi byc jedna linia (bez eneterow). Prywatna konfiguracja — zostaje w `.env`, nie trafia na git. Szczegoly w rozdziale 12. |

#### Jezyk

| Zmienna | Opis | Przyklad |
|---------|------|---------|
| `DEFAULT_STT_LANG` | Domyslny jezyk STT Twilio przed detekcja z prefiksu. | `en-US` |
| `SIGNAL_LANG` | Jezyk powiadomien Signal i podsumowania (`en` lub `pl`). | `pl` |

#### Infrastruktura

| Zmienna | Opis | Przyklad |
|---------|------|---------|
| `COMPOSE_PROFILES` | Profil Docker Compose okreslajacy sposob dostepu z internetu. `caddy` = Caddy + Let's Encrypt, `tunnel` = Cloudflare Tunnel. | `caddy` |
| `PUBLIC_URL` | Publiczny adres HTTPS, pod ktorym serwer jest dostepny z internetu. | `https://ava.twoja-domena.pl` |
| `DOMAIN` | Nazwa domeny (bez https://). Uzywana przez Caddy do uzyskania certyfikatu SSL. Wymagana tylko przy profilu `caddy`. | `ava.twoja-domena.pl` |
| `CLOUDFLARE_TUNNEL_TOKEN` | Token tunelu z panelu Cloudflare Zero Trust. Wymagany tylko przy profilu `tunnel`. | `eyJhIjo...` |

---

### 4. Rejestracja numeru Signal

AVA komunikuje sie z Toba przez Signal. Potrzebujesz oddzielnej karty SIM, ktorej numer zarejestrujesz jako "bota".

Uruchom kontener signal-cli:

```bash
docker compose up signal-cli -d
```

Poczekaj okolo 15 sekund, az kontener sie uruchomi, a nastepnie zarejestruj numer bota:

```bash
curl -X POST "http://localhost:8080/v1/register/+48NUMER_BOTA" \
  -H "Content-Type: application/json" \
  -d '{"use_voice": false}'
```

Otrzymasz SMS z kodem weryfikacyjnym na karte SIM bota. Wprowadz go:

```bash
curl -X POST "http://localhost:8080/v1/register/+48NUMER_BOTA/verify/TWOJ_KOD"
```

Sprawdz, czy rejestracja przebiegla pomyslnie:

```bash
curl http://localhost:8080/v1/accounts
```

Powinienes zobaczyc swoj numer na liscie zarejestrowanych kont.

Wpisz ten numer jako `SIGNAL_SENDER_NUMBER` w pliku `.env`.

---

### 5. Konfiguracja Twilio

#### Zakup numeru telefonu

1. Zaloguj sie do konsoli Twilio: https://console.twilio.com
2. Przejdz do: Phone Numbers > Manage > Buy a Number
3. Wybierz numer z odpowiednim prefiksem krajowym (np. +48 dla Polski)
4. Zakup numer

#### Konfiguracja webhookow

Po uruchomieniu serwera (krok 7) wroc do konsoli Twilio:

1. Przejdz do: Phone Numbers > Manage > Active Numbers
2. Kliknij na zakupiony numer
3. W sekcji "Voice & Fax" ustaw:

| Pole | Wartosc |
|------|---------|
| A Call Comes In | Webhook, POST, `https://twoja-domena.pl/twilio/incoming` |
| Call Status Changes | `https://twoja-domena.pl/twilio/status`, POST |

Zamien `twoja-domena.pl` na faktyczny adres Twojego serwera.

---

### 6. Konfiguracja domeny i DNS

Twilio wymaga, aby webhooki byly dostepne przez HTTPS. Caddy (zawarty w projekcie) automatycznie uzyskuje certyfikat Let's Encrypt.

1. W panelu rejestratora domeny dodaj rekord DNS:

| Typ | Nazwa | Wartosc |
|-----|-------|---------|
| A | `ava` (lub `@`) | Adres IP Twojego serwera |

2. Poczekaj na propagacje DNS (zazwyczaj kilka minut do kilku godzin)

3. Upewnij sie, ze w pliku `.env` zmienne `DOMAIN` i `PUBLIC_URL` sa poprawne:

```
DOMAIN=ava.twoja-domena.pl
PUBLIC_URL=https://ava.twoja-domena.pl
```

---

### 7. Cloudflare Tunnel (alternatywa dla Caddy)

Jesli nie chcesz otwierac portow 80/443 na serwerze, mozesz uzyc **Cloudflare Tunnel** do bezpiecznego udostepnienia AVA przez siec Cloudflare. Tunel nawiazuje polaczenie wychodzace z Twojego serwera -- nie wymaga publicznego IP ani otwartych portow.

#### Utworzenie tunelu

1. Zaloguj sie do panelu Cloudflare Zero Trust: https://one.dash.cloudflare.com
2. Przejdz do: **Networks > Tunnels > Create a tunnel**
3. Wybierz typ konektora **Cloudflared** i nadaj tunelowi nazwe (np. `ava`)
4. Skopiuj token tunelu i wklej go do pliku `.env`:

```env
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiYWJjZGVmLi4uIn0=...
```

#### Konfiguracja publicznego hostname

W ustawieniach tunelu dodaj trase (Public Hostname):

| Subdomain | Domain | Service |
|-----------|--------|---------|
| `ava` | `twoja-domena.pl` | `http://ava:8000` |

Cloudflare automatycznie zapewni certyfikat SSL i bedzie proxy'owal ruch do kontenera AVA.

#### Wybor profilu

W pliku `.env` ustaw profil na `tunnel`:

```env
COMPOSE_PROFILES=tunnel
```

Nastepnie uruchom normalnie -- wystartuje tylko kontener `cloudflared` (Caddy nie zostanie uruchomiony):

```bash
docker compose up -d
```

#### Uwagi

- Zmienna `COMPOSE_PROFILES` w `.env` kontroluje, ktory serwis ingress jest uruchamiany: `caddy` (domyslnie) lub `tunnel`
- Zaktualizuj `PUBLIC_URL` w `.env` tak, aby odpowiadal hostname skonfigurowanemu w tunelu
- Sprawdz status tunelu: `docker compose logs ava-cloudflared`

---

### 8. Uruchomienie

Po wykonaniu krokow 3-7 uruchom caly stos:

```bash
docker compose up -d
```

Sprawdz status kontenerow:

```bash
docker compose ps
```

Powinienes zobaczyc dzialajace kontenery: `ava`, `ava-signal-cli`, `ava-caddy` (lub `ava-cloudflared` jesli uzywasz Cloudflare Tunnel).

Sledz logi w czasie rzeczywistym:

```bash
docker compose logs -f ava
```

Przetestuj, czy serwer odpowiada:

```bash
curl https://twoja-domena.pl/health
```

Oczekiwana odpowiedz:

```json
{"status": "ok"}
```

---

### 9. Przekierowanie polaczen z telefonu

Przekieruj polaczenia ze swojego telefonu osobistego na numer Twilio.

#### Android

1. Otworz aplikacje Telefon
2. Menu (trzy kropki) > Ustawienia > Przekierowanie polaczen
3. Ustaw przekierowanie "Gdy zajety" lub "Gdy odrzucony" na numer Twilio

Alternatywnie, wybierz z klawiatury:

```
**67*NUMER_TWILIO#
```

#### iOS

1. Ustawienia > Telefon > Przekierowanie polaczen
2. Wprowadz numer Twilio

Dokladna sciezka moze sie roznic w zaleznosci od operatora. W razie problemow skontaktuj sie z operatorem i popros o wlaczenie przekierowania warunkowego (CFB/CFNRy).

---

### 10. Ksiazka kontaktow (opcjonalnie)

Aby AVA rozpoznawala dzwoniacych po imieniu, utworz plik `data/contacts.json`.

Format slownikowy (prostszy):

```json
{
  "+48123456789": "Jan Kowalski",
  "+48987654321": "Anna Nowak"
}
```

Format tablicowy (wiele numerow na kontakt):

```json
[
  {
    "name": "Jan Kowalski",
    "phones": ["+48123456789", "+48111222333"]
  },
  {
    "name": "Anna Nowak",
    "phones": ["+48987654321"]
  }
]
```

Uwagi:

- Numery powinny byc w formacie E.164 (z prefiksem krajowym, np. `+48`)
- 9-cyfrowe numery bez prefiksu sa automatycznie traktowane jako polskie (+48)
- Plik jest wczytywany przy starcie kontenera; po zmianach wymagany restart: `docker compose restart ava`
- Jesli kontakt nie zostanie znaleziony lokalnie, AVA probuje rozpoznac numer przez Twilio CNAM Lookup (koszt ok. $0.01 za zapytanie)

---

### 11. ElevenLabs TTS (opcjonalnie)

Domyslnie AVA uzywa OpenAI TTS (model `tts-1`, glos `nova`). Dla lepszej jakosci:

1. Zaloz konto na https://elevenlabs.io
2. Przejdz do: Profile > API Keys i utworz klucz
3. Przegladaj biblioteke glosow (https://elevenlabs.io/voice-library) i skopiuj Voice ID
4. Wpisz klucz i identyfikator w pliku `.env`:

```
ELEVENLABS_API_KEY=twoj_klucz
ELEVENLABS_VOICE_ID=WAhoMTNdLdMoq1j3wf3I
ELEVENLABS_MODEL=eleven_multilingual_v2
```

Jeden wielojezyczny glos uzywany jest dla wszystkich jezykow. Model `eleven_multilingual_v2` wspiera 29 jezykow.

Lancuch awaryjny TTS: ElevenLabs (z circuit breakerem) > OpenAI TTS (`OPENAI_TTS_VOICE`) > Twilio Polly.

Po zmianie glosu/modelu wyczysc cache: `docker exec ava sh -c 'rm -f /tmp/tts_cache/*.mp3'`

---

### 12. Personalizacja asystenta

AVA dostosowuje swoje zachowanie na podstawie zmiennej `OWNER_CONTEXT` w pliku `.env`. Ten tekst jest wstrzykiwany do promptu systemowego GPT-4o.

Przyklad konfiguracji:

```
OWNER_CONTEXT=Wlasciciel telefonu to Jan Kowalski. \
Data urodzenia: 15 marca 1990. \
Godziny pracy: poniedzialek-piatek, 9:00-17:00 CET. \
Oczekiwane polaczenia: klienci pytajacy o status projektow, dostawcy potwierdzajacy dostawy, dzial IT zgaszajacy awarie. \
Awarie IT/infrastruktury: zawsze traktuj jako WYSOKI priorytet i oznacz jako pilne oddzwonienie. \
Rekruterzy i polaczenia sprzedazowe: grzecznie podziekuj i zakoncz rozmowe. \
Polityka oddzwaniania: "Wlasciciel oddzwoni tak szybko jak to mozliwe w godzinach pracy."
```

Dla bardziej zaawansowanych zmian mozesz edytowac zmienna `SYSTEM_PROMPT` w pliku `app/conversation.py`.

---

### 13. Weryfikacja dzialania

Po zakonczeniu konfiguracji wykonaj nastepujace testy:

1. Sprawdz dostepnosc serwera:

```bash
curl https://twoja-domena.pl/health
```

2. Sprawdz logi pod katem bledow:

```bash
docker compose logs ava | tail -50
docker compose logs ava-signal-cli | tail -20
docker compose logs caddy | tail -20
```

3. Wyslij wiadomosc testowa na Signal bota (z numeru SIGNAL_RECIPIENT):

```
status
```

Powinienes otrzymac odpowiedz: "No active call at the moment."

4. Zadzwon z innego telefonu na swoj numer osobisty (lub bezposrednio na numer Twilio). AVA powinna odebrac, przywitac sie i poprowadzic rozmowe.

5. Sprawdz, czy po zakonczeniu rozmowy:
   - Otrzymales podsumowanie na Signal
   - Plik JSON pojawil sie w katalogu `data/calls/`

---

### 14. Logi polaczen

Po kazdym polaczeniu (rowniez nieodebranym) AVA zapisuje dane do pliku JSON w katalogu `data/calls/`.

Nazwa pliku: `RRRRMMDD_HHMMSS_CALLSID.json`

Przyklad zawartosci:

```json
{
  "call_sid": "CA1a2b3c4d...",
  "caller_number": "+48123456789",
  "caller_name": "Jan Kowalski",
  "start_time": "2026-02-23T14:32:15",
  "end_time": "2026-02-23T14:35:02",
  "language": "pl-PL",
  "summary": "Jan Kowalski z firmy Acme zadzwonil w sprawie faktury #456...",
  "transcript": [
    {"role": "user", "text": "Dzien dobry, dzwonie w sprawie faktury...", "time": "..."},
    {"role": "assistant", "text": "Dzien dobry, prosze powiedziec...", "time": "..."}
  ],
  "call_meta": {
    "urgency": "medium",
    "topic": "invoice dispute",
    "caller_name_detected": "Jan"
  }
}
```

---

### 15. Komendy Signal podczas rozmowy

Gdy AVA prowadzi rozmowe, mozesz wysylac instrukcje przez Signal:

| Komenda | Efekt |
|---------|-------|
| `status` lub `?` | Informuje, czy trwa rozmowa |
| `end`, `stop`, `koniec`, `zakoncz` | AVA konczy rozmowe |
| `tell him/her <wiadomosc>` lub `powiedz <wiadomosc>` | AVA przekazuje tresc dzwoniacemu |
| `ask him/her <pytanie>` lub `zapytaj <pytanie>` | AVA zadaje pytanie dzwoniacemu |
| Dowolny inny tekst | Przekazywany AVA jako ogolna instrukcja |

AVA potwierdza kazda instrukcje wiadomoscia zwrotna na Signal.

---

### 16. Koszty eksploatacji

Szacunkowe koszty dla typowej 2-minutowej rozmowy:

| Usluga | Stawka | Koszt na rozmowe |
|--------|--------|-----------------|
| Twilio Voice | $0.013/min | ok. $0.03 |
| Twilio STT (enhanced) | $0.02/15 s | ok. $0.16 |
| OpenAI GPT-4o | ok. $0.01/1k tokenow | ok. $0.005 |
| ElevenLabs | od $5/miesiac (30 tys. znakow gratis) | -- |
| Twilio CNAM Lookup | $0.01/zapytanie | $0.01 (tylko nieznane numery) |

Laczny koszt typowej rozmowy: okolo $0.20-0.25.

---

### 17. Rozwiazywanie problemow

#### Twilio nie moze sie polaczyc z webhookiem

```bash
# Sprawdz, czy serwer odpowiada
curl -I https://twoja-domena.pl/health

# Sprawdz certyfikat SSL
docker compose logs caddy | grep -i "certificate"

# Sprawdz, czy porty 80/443 sa otwarte
ss -tlnp | grep -E ':(80|443)'
```

#### Brak dzwieku TTS

```bash
# Sprawdz logi TTS
docker compose logs ava | grep -i tts

# Upewnij sie, ze PUBLIC_URL jest dostepny z internetu
curl https://twoja-domena.pl/audio/test.mp3
# Oczekiwany wynik: 404 (plik nie istnieje, ale endpoint dziala)
```

#### Signal nie wysyla powiadomien

```bash
# Sprawdz logi signal-cli
docker compose logs ava-signal-cli

# Sprawdz zarejestrowane konta
curl http://localhost:8080/v1/accounts

# Sprawdz logi AVA pod katem bledow Signal
docker compose logs ava | grep -i signal
```

#### AVA nie odbiera polaczen

- Upewnij sie, ze webhooki w konsoli Twilio wskazuja na poprawny adres
- Sprawdz, czy przekierowanie polaczen jest aktywne na Twoim telefonie
- Sprawdz logi: `docker compose logs -f ava`

#### Ponowne uruchomienie po zmianach

```bash
# Restart wszystkich uslug
docker compose restart

# Przebudowanie po zmianach w kodzie
docker compose up -d --build
```

---

### 18. Zabezpieczenia

AVA posiada nastepujace mechanizmy bezpieczenstwa:

| Mechanizm | Opis |
|-----------|------|
| Walidacja podpisu Twilio | Kazdy request na `/twilio/*` musi posiadac prawidlowy naglowek `X-Twilio-Signature`. Podrobione zapytania sa odrzucane z kodem 403. |
| Limitowanie zapytan | Maksymalnie 30 zapytan na minute z jednego adresu IP. Przekroczenie limitu skutkuje kodem 429. |
| Ukryty port aplikacji | Port 8000 nie jest wystawiony na internet. Ruch przechodzi wylacznie przez Caddy (HTTPS na porcie 443). |
| Signal -- filtrowanie nadawcy | Wiadomosci Signal sa akceptowane wylacznie z numeru `SIGNAL_RECIPIENT`. Pozostale sa ignorowane. |
| Ochrona plikow audio | Nazwy plikow sa walidowane wyrazeniem regularnym (tylko hash MD5 + .mp3). Ataki path traversal sa blokowane. |
| Naglowki bezpieczenstwa | Caddy dodaje: HSTS, X-Frame-Options DENY, X-Content-Type-Options nosniff, ukrywa naglowek Server. |
| Wylaczona dokumentacja API | Endpointy `/docs`, `/redoc`, `/openapi.json` sa wylaczone. |

---

### Architektura systemu

```
┌─────────────────────────────────────────────────────────────────┐
│                       USLUGI ZEWNETRZNE                         │
│  ┌──────────┐      ┌───────────┐      ┌──────────────┐         │
│  │  Twilio   │      │  OpenAI   │      │  ElevenLabs  │         │
│  │ Voice/STT │      │  GPT-4o   │      │  TTS (glos)  │         │
│  └─────┬─────┘      │  TTS zap. │      └──────┬───────┘         │
│        │            └─────┬─────┘             │                 │
└────────┼──────────────────┼───────────────────┼─────────────────┘
         │ HTTPS            │ HTTPS             │ HTTPS
         ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DOCKER HOST (twoj serwer)                    │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Caddy :443 (Let's Encrypt) LUB Cloudflare Tunnel          │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
│                         │ ava-net (siec Docker bridge)           │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              AVA (FastAPI :8000)                       │       │
│  │                                                       │       │
│  │  main.py ─── conversation.py ─── tts.py               │       │
│  │     │              │                │                  │       │
│  │  Twilio hooks    GPT-4o loop     ElevenLabs→OpenAI    │       │
│  │  Rate limiter    Streaming       →Polly fallback      │       │
│  │  Audio serwer    Meta parsing    TTS cache (MD5)      │       │
│  │  Diagnostyka     Podsumowania    Circuit breaker      │       │
│  │     │                                                  │       │
│  │  owner_channel.py ─── contact_lookup.py ─── i18n.py   │       │
│  │     │                      │                           │       │
│  │  Signal powiad.         contacts.json              8+ jezykow │
│  │  Signal poll (3s)       CNAM lookup                Signal     │
│  │  Slash komendy          Jezyk z prefiksu           szablony   │
│  │  Instrukcje             Per-kontakt jezyk                     │
│  └─────────┬────────────────────────────────────────────┘       │
│            │ HTTP                                                │
│            ▼                                                     │
│  ┌─────────────────┐   ┌──────────────────────┐                 │
│  │ signal-cli :8080 │   │ Wolumeny:             │                 │
│  │ REST API         │   │  tts_cache (MP3)      │                 │
│  │ Serwery Signal   │   │  /data/calls/ (JSON)  │                 │
│  └─────────────────┘   │  /data/contacts.json  │                 │
│                         └──────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ Protokol Signal
         ▼
   ┌────────────┐
   │  Telefon   │
   │  wlasciciela│
   │  (Signal)  │
   └────────────┘
```

#### Timeouty i limity

| Parametr | Wartosc | Opis |
|----------|---------|------|
| `speech_timeout` | 5 s | Cisza po mowie zanim Twilio uruchomi callback |
| GPT `max_tokens` | 350 | Maks. dlugosc odpowiedzi na ture |
| Limit tur | 10 wymian | AVA konczy rozmowe |
| ElevenLabs timeout | 15 s | Timeout HTTP dla TTS API |
| ElevenLabs circuit breaker | 10 min | Auto-wylaczenie po 401/403/429 |
| Signal poll | 3 s | Sprawdzanie nowych wiadomosci |
| Rate limiter | 30 req/min/IP | Okno przesuwne |
| Czyszczenie rozmowy | 90 s | Opoznione czyszczenie po rozmowie |
| TTS cache | bez wygasania | Persystentny w wolumenie Docker |

Ruch z internetu trafia przez Caddy (porty 80/443) lub Cloudflare Tunnel (bez otwartych portow). Wszystkie pozostale uslugi dzialaja wylacznie w sieci wewnetrznej Docker.
