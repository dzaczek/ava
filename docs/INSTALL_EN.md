# AVA -- AI Voice Assistant

## Installation and Configuration Guide

---

### Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Downloading the Project](#2-downloading-the-project)
3. [Environment Variables](#3-environment-variables)
4. [Signal Bot Registration](#4-signal-bot-registration)
5. [Twilio Configuration](#5-twilio-configuration)
6. [Domain and DNS Setup](#6-domain-and-dns-setup)
7. [Cloudflare Tunnel (Alternative to Caddy)](#7-cloudflare-tunnel-alternative-to-caddy)
8. [Starting the Application](#8-starting-the-application)
9. [Phone Call Forwarding](#9-phone-call-forwarding)
10. [Contact Book (Optional)](#10-contact-book-optional)
11. [ElevenLabs TTS (Optional)](#11-elevenlabs-tts-optional)
12. [Customising the Assistant](#12-customising-the-assistant)
13. [Verifying the Setup](#13-verifying-the-setup)
14. [Call Logs](#14-call-logs)
15. [Signal Commands During a Call](#15-signal-commands-during-a-call)
16. [Running Costs](#16-running-costs)
17. [Troubleshooting](#17-troubleshooting)
18. [Security](#18-security)

---

### 1. Prerequisites

Before starting the installation, make sure you have the following:

**Infrastructure:**

- A VPS or dedicated server with a public IP address
- Operating system: Linux (Ubuntu 22.04+, Debian 12+, or any OS with Docker support)
- Ports 80 and 443 open and reachable from the internet
- Docker Engine (version 20.10 or later)
- Docker Compose v2 (`docker compose` command)
- A domain name with access to DNS settings (A/AAAA records)

**Accounts and services:**

- Twilio account (https://console.twilio.com) with a purchased phone number
- OpenAI API key (https://platform.openai.com)
- A separate phone number (SIM card) to register as the Signal bot
- Your personal Signal number to receive notifications

**Optional:**

- ElevenLabs account (https://elevenlabs.io) for higher-quality speech synthesis

---

### 2. Downloading the Project

Copy the project files to your server:

```bash
cd /opt
git clone <repository-url> ava
cd ava
```

If you are not using git, upload the files via SCP or SFTP to `/opt/ava`.

Create the required directories:

```bash
mkdir -p data/calls
```

---

### 3. Environment Variables

Copy the template file and open it in your editor:

```bash
cp .env.example .env
nano .env
```

Below is a description of each variable:

#### Twilio Voice

| Variable | Description | Example |
|----------|-------------|---------|
| `TWILIO_ACCOUNT_SID` | Your Twilio account identifier. Found on the Twilio Console dashboard. | `ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_AUTH_TOKEN` | Twilio auth token. Also used for webhook signature validation. | `xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` |
| `TWILIO_PHONE_NUMBER` | The Twilio phone number that will receive forwarded calls. | `+48123456789` |

#### Signal

| Variable | Description | Example |
|----------|-------------|---------|
| `SIGNAL_CLI_URL` | Internal address of the signal-cli container. Do not change this value. | `http://signal-cli:8080` |
| `SIGNAL_SENDER_NUMBER` | The Signal bot phone number (a separate SIM card, registered in step 4). | `+48111222333` |
| `SIGNAL_RECIPIENT` | Your personal Signal number. AVA sends all notifications here. | `+48999888777` |

#### OpenAI

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENAI_API_KEY` | Your OpenAI API key. | `sk-proj-...` |
| `OPENAI_MODEL` | _(deprecated, use LLM_MODEL)_ GPT model for conversations. | `gpt-4o` |
| `LLM_PROVIDER` | LLM backend: `openai` (default) or `groq`. | `openai` |
| `LLM_MODEL` | Model name. Default: `gpt-4o-mini` (OpenAI), `llama-3.3-70b-versatile` (Groq). | `gpt-4o-mini` |
| `LLM_SUMMARY_MODEL` | Model for call summaries. Defaults to `LLM_MODEL`. | `gpt-4o-mini` |
| `GROQ_API_KEY` | Groq API key. Required when `LLM_PROVIDER=groq`. | (blank or key) |

#### ElevenLabs TTS (Optional)

| Variable | Description | Example |
|----------|-------------|---------|
| `ELEVENLABS_API_KEY` | ElevenLabs API key. Leave blank to skip ElevenLabs. | (blank or key) |
| `ELEVENLABS_VOICE_ID` | Single multilingual voice ID (used for all languages). Browse at https://elevenlabs.io/voice-library | `WAhoMTNdLdMoq1j3wf3I` |
| `ELEVENLABS_MODEL` | ElevenLabs model. `eleven_multilingual_v2` (best quality) or `eleven_turbo_v2_5` (faster, lower latency). | `eleven_turbo_v2_5` |
| `OPENAI_TTS_VOICE` | Fallback OpenAI TTS voice (used when ElevenLabs is unavailable). Options: alloy, echo, fable, onyx, nova, shimmer. | `nova` |

#### Personalisation

| Variable | Description |
|----------|-------------|
| `OWNER_CONTEXT` | Assistant persona + owner information, injected into the GPT-4o system prompt. Must be a single line (no newlines). This is your private configuration — it stays in `.env` and is never committed to git. See section 12 for details. |

#### Language

| Variable | Description | Example |
|----------|-------------|---------|
| `DEFAULT_STT_LANG` | Default Twilio STT language before prefix detection. | `en-US` |
| `SIGNAL_LANG` | Language for Signal notifications and summaries (`en` or `pl`). | `en` |

#### Infrastructure

| Variable | Description | Example |
|----------|-------------|---------|
| `COMPOSE_PROFILES` | Docker Compose profile controlling the ingress method. `caddy` = Caddy + Let's Encrypt, `tunnel` = Cloudflare Tunnel. | `caddy` |
| `PUBLIC_URL` | The public HTTPS address where the server is reachable from the internet. | `https://ava.your-domain.com` |
| `DOMAIN` | The domain name (without https://). Used by Caddy to obtain an SSL certificate. Required only with the `caddy` profile. | `ava.your-domain.com` |
| `CLOUDFLARE_TUNNEL_TOKEN` | Tunnel token from the Cloudflare Zero Trust dashboard. Required only with the `tunnel` profile. | `eyJhIjo...` |

---

### 4. Signal Bot Registration

AVA communicates with you through Signal. You need a separate SIM card whose number will be registered as the "bot".

> **Important:** Signal requires a CAPTCHA verification during registration. You must complete it in a browser first, then pass the token to the API.

Start the signal-cli container:

```bash
docker compose up signal-cli -d
```

Wait about 15 seconds for the container to start.

#### Step 1: Get the CAPTCHA token

Open this URL in your browser:

```
https://signalcaptchas.org/registration/generate.html
```

Complete the CAPTCHA challenge. After solving it, the page will redirect to a URL starting with `signalcaptcha://`. **Copy the entire value after `signalcaptcha://`** — this is your captcha token.

> **Tip:** In most browsers, the redirect will fail (page not found). That's expected. Just copy the full URL from the address bar and extract everything after `signalcaptcha://`.

#### Step 2: Register the bot number

```bash
curl -X POST "http://localhost:8080/v1/register/+48BOT_NUMBER" \
  -H "Content-Type: application/json" \
  -d '{"use_voice": false, "captcha": "PASTE_CAPTCHA_TOKEN_HERE"}'
```

Replace `+48BOT_NUMBER` with the phone number of your bot SIM card (E.164 format).

#### Step 3: Verify with SMS code

You will receive an SMS with a verification code on the bot SIM card. Enter it:

```bash
curl -X POST "http://localhost:8080/v1/register/+48BOT_NUMBER/verify/YOUR_CODE"
```

Verify that the registration was successful:

```bash
curl http://localhost:8080/v1/accounts
```

You should see your number listed among the registered accounts.

Enter this number as `SIGNAL_SENDER_NUMBER` in the `.env` file.

---

### 5. Twilio Configuration

#### Purchasing a Phone Number

1. Log in to the Twilio Console: https://console.twilio.com
2. Navigate to: Phone Numbers > Manage > Buy a Number
3. Select a number with the appropriate country prefix (e.g. +48 for Poland)
4. Purchase the number

#### Configuring Webhooks

After starting the server (step 7), return to the Twilio Console:

1. Go to: Phone Numbers > Manage > Active Numbers
2. Click on your purchased number
3. In the "Voice & Fax" section, set:

| Field | Value |
|-------|-------|
| A Call Comes In | Webhook, POST, `https://your-domain.com/twilio/incoming` |
| Call Status Changes | `https://your-domain.com/twilio/status`, POST |

Replace `your-domain.com` with the actual address of your server.

---

### 6. Domain and DNS Setup

Twilio requires webhooks to be served over HTTPS. Caddy (included in the project) automatically obtains a Let's Encrypt certificate.

1. In your domain registrar's DNS panel, add a record:

| Type | Name | Value |
|------|------|-------|
| A | `ava` (or `@`) | Your server's IP address |

2. Wait for DNS propagation (usually a few minutes to a few hours)

3. Make sure that the `DOMAIN` and `PUBLIC_URL` variables in `.env` are correct:

```
DOMAIN=ava.your-domain.com
PUBLIC_URL=https://ava.your-domain.com
```

---

### 7. Cloudflare Tunnel (Alternative to Caddy)

If you prefer not to open ports 80/443 on your server, you can use **Cloudflare Tunnel** to securely expose AVA to the internet through Cloudflare's network. The tunnel establishes an outbound connection from your server -- no public IP or open ports required.

#### Creating the Tunnel

1. Log in to the Cloudflare Zero Trust dashboard: https://one.dash.cloudflare.com
2. Navigate to: **Networks > Tunnels > Create a tunnel**
3. Choose the **Cloudflared** connector type and give the tunnel a name (e.g. `ava`)
4. Copy the tunnel token and paste it into `.env`:

```env
CLOUDFLARE_TUNNEL_TOKEN=eyJhIjoiYWJjZGVmLi4uIn0=...
```

#### Configuring the Public Hostname

In the tunnel settings, add a route (Public Hostname):

| Subdomain | Domain | Service |
|-----------|--------|---------|
| `ava` | `your-domain.com` | `http://ava:8000` |

Cloudflare will automatically provision an SSL certificate and proxy traffic to the AVA container.

#### Selecting the Profile

In `.env`, set the profile to `tunnel`:

```env
COMPOSE_PROFILES=tunnel
```

Then start normally — only the `cloudflared` container will run (Caddy will not):

```bash
docker compose up -d
```

#### Notes

- The `COMPOSE_PROFILES` variable in `.env` controls which ingress service runs: `caddy` (default) or `tunnel`
- Update `PUBLIC_URL` in `.env` to match the hostname configured in the tunnel
- Check the tunnel status: `docker compose logs ava-cloudflared`

---

### 8. Starting the Application

Once steps 3 through 7 are complete, start the full stack:

```bash
docker compose up -d
```

Check the status of the containers:

```bash
docker compose ps
```

You should see the running containers: `ava`, `ava-signal-cli`, `ava-caddy` (or `ava-cloudflared` if using Cloudflare Tunnel).

Follow the logs in real time:

```bash
docker compose logs -f ava
```

Test that the server is responding:

```bash
curl https://your-domain.com/health
```

Expected response:

```json
{"status": "ok"}
```

---

### 9. Phone Call Forwarding

Forward calls from your personal phone to the Twilio number.

#### Android

1. Open the Phone app
2. Menu (three dots) > Settings > Call forwarding
3. Set forwarding for "When busy" or "When declined" to your Twilio number

Alternatively, dial from the keypad:

```
**67*TWILIO_NUMBER#
```

#### iOS

1. Settings > Phone > Call Forwarding
2. Enter the Twilio number

The exact path may vary depending on your carrier. If you run into issues, contact your carrier and ask them to enable conditional forwarding (CFB/CFNRy).

---

### 10. Contact Book (Optional)

To allow AVA to recognise callers by name, copy the example file and edit it:

```bash
cp data/contacts.json.example data/contacts.json
nano data/contacts.json
```

The file uses a dictionary format. Values can be a simple name string or an object with `name` and optional `lang`:

```json
{
  "+48123456789": "Jan Kowalski",
  "+48987654321": "Anna Nowak",
  "+41761234567": {"name": "Hans Müller", "lang": "de"},
  "+44207123456": {"name": "John Smith", "lang": "en"}
}
```

The optional `lang` field forces the STT language for this contact, overriding automatic phone prefix detection. Useful when someone calls from a foreign number but speaks a different language.

Notes:

- **Direct call access**: contacts in the contact book can call the Twilio number directly (without forwarding) and AVA will answer. Unknown callers must go through call forwarding.
- Numbers should be in E.164 format (with country prefix, e.g. `+48`)
- Bare 9-digit numbers without a prefix are automatically treated as Polish (+48)
- The file is loaded once at container startup; changes require a restart: `docker compose restart ava`
- If a contact is not found locally, AVA attempts a Twilio CNAM Lookup (approximately $0.01 per query)

---

### 11. ElevenLabs TTS (Optional)

By default, AVA uses OpenAI TTS (model `tts-1`, voice `nova`). For higher voice quality:

1. Create an account at https://elevenlabs.io
2. Go to: Profile > API Keys and create a key
3. Browse the Voice Library (https://elevenlabs.io/voice-library) and copy the Voice ID
4. Enter the key and voice ID in `.env`:

```
ELEVENLABS_API_KEY=your_key
ELEVENLABS_VOICE_ID=WAhoMTNdLdMoq1j3wf3I
ELEVENLABS_MODEL=eleven_multilingual_v2
```

A single multilingual voice is used for all languages. The `eleven_multilingual_v2` model supports 29 languages.

TTS fallback chain: ElevenLabs (with circuit breaker) > OpenAI TTS (`OPENAI_TTS_VOICE`) > Twilio Polly.

After changing voice/model, clear the cache: `docker exec ava sh -c 'rm -f /tmp/tts_cache/*.mp3'`

---

### 12. Customising the Assistant

AVA adjusts its behaviour based on the `OWNER_CONTEXT` variable in the `.env` file. This text is injected into the GPT-4o system prompt.

Example configuration:

```
OWNER_CONTEXT=The phone owner is John Smith. \
Birthday: 15 March 1990. \
Working hours: Monday-Friday, 9:00-17:00 CET. \
Expected calls: clients asking about project status, suppliers confirming deliveries, IT team reporting infrastructure issues. \
IT/infrastructure emergencies: always treat as HIGH priority and note as an urgent callback. \
Recruiters and sales calls: politely thank them and end the call. \
Callback policy: "The owner will call back as soon as possible during working hours."
```

For more advanced changes, edit the `SYSTEM_PROMPT` variable in `app/conversation.py`.

---

### 13. Verifying the Setup

After completing the configuration, run the following tests:

1. Check server availability:

```bash
curl https://your-domain.com/health
```

2. Review logs for errors:

```bash
docker compose logs ava | tail -50
docker compose logs ava-signal-cli | tail -20
docker compose logs caddy | tail -20
```

3. Send a test message to the Signal bot (from the SIGNAL_RECIPIENT number):

```
status
```

You should receive a reply: "No active call at the moment."

4. Call your personal number from a different phone (or call the Twilio number directly). AVA should answer, greet the caller, and carry on a conversation.

5. After the call ends, verify that:
   - You received a summary on Signal
   - A JSON file appeared in the `data/calls/` directory

---

### 14. Call Logs

After every call (including missed calls), AVA saves the data to a JSON file in the `data/calls/` directory.

File naming: `YYYYMMDD_HHMMSS_CALLSID.json`

Example contents:

```json
{
  "call_sid": "CA1a2b3c4d...",
  "caller_number": "+48123456789",
  "caller_name": "John Smith",
  "start_time": "2026-02-23T14:32:15",
  "end_time": "2026-02-23T14:35:02",
  "language": "pl-PL",
  "summary": "John Smith from Acme Corp called about invoice #456...",
  "transcript": [
    {"role": "user", "text": "Good afternoon, I'm calling about the invoice...", "time": "..."},
    {"role": "assistant", "text": "Good afternoon, please tell me...", "time": "..."}
  ],
  "call_meta": {
    "urgency": "medium",
    "topic": "invoice dispute",
    "caller_name_detected": "John"
  }
}
```

---

### 15. Signal Commands

#### During a call

When AVA is handling a call, you can send instructions via Signal:

| Command | Effect |
|---------|--------|
| `status` or `?` | Reports whether a call is currently active |
| `end`, `stop`, `finish`, `hang up` | AVA wraps up and ends the call |
| `tell him/her <message>` | AVA relays the message to the caller |
| `ask him/her <question>` | AVA asks the caller that question |
| Any other text | Forwarded to AVA as a general instruction |

Polish equivalents also work: `koniec`, `zakoncz`, `powiedz <wiadomosc>`, `zapytaj <pytanie>`.

AVA confirms every instruction with a reply on Signal.

#### Slash commands (no active call needed)

| Command | Description |
|---------|-------------|
| `/ping` | Alive check + timestamp |
| `/status` | Uptime, active calls, public URL |
| `/stats` | Call count, memory, TTS cache size |
| `/calls` | Last 5 call records with topics |
| `/debug` | Latency breakdown (avg from last 10 calls). `/debug -1` for last call detail. |
| `/billings` | Check API balances (ElevenLabs characters, Twilio balance, OpenAI costs) |
| `/recording-on` | Start recording calls via Twilio |
| `/recording-off` | Stop recording calls |
| `/restart` | Restart AVA (requires `/restart confirm`) |
| `/help` | Command list |

---

### 16. Running Costs

Estimated costs for a typical 2-minute call:

| Service | Rate | Cost per call |
|---------|------|---------------|
| Twilio Voice | $0.013/min | approx. $0.03 |
| Twilio STT (enhanced) | $0.02/15 s | approx. $0.16 |
| OpenAI GPT-4o-mini | approx. $0.0006/1k tokens | approx. $0.001 |
| ElevenLabs | from $5/month (30k chars free) | -- |
| Twilio CNAM Lookup | $0.01/query | $0.01 (unknown numbers only) |

Total cost of a typical call: approximately $0.20-0.25.

---

### 17. Troubleshooting

#### Twilio cannot reach the webhook

```bash
# Check if the server responds
curl -I https://your-domain.com/health

# Check the SSL certificate
docker compose logs caddy | grep -i "certificate"

# Check that ports 80/443 are open
ss -tlnp | grep -E ':(80|443)'
```

#### No TTS audio

```bash
# Check TTS logs
docker compose logs ava | grep -i tts

# Make sure PUBLIC_URL is reachable from the internet
curl https://your-domain.com/audio/test.mp3
# Expected: 404 (file does not exist, but the endpoint works)
```

#### Signal is not sending notifications

```bash
# Check signal-cli logs
docker compose logs ava-signal-cli

# Check registered accounts
curl http://localhost:8080/v1/accounts

# Check AVA logs for Signal errors
docker compose logs ava | grep -i signal
```

#### AVA does not answer calls

- Make sure the Twilio Console webhooks point to the correct address
- Verify that call forwarding is active on your phone
- Review the logs: `docker compose logs -f ava`

#### Restarting after changes

```bash
# Restart all services
docker compose restart

# Rebuild after code changes
docker compose up -d --build
```

---

### 18. Security

AVA includes the following security mechanisms:

| Mechanism | Description |
|-----------|-------------|
| Twilio signature validation | Every request to `/twilio/*` must carry a valid `X-Twilio-Signature` header. Forged requests are rejected with HTTP 403. |
| Direct call rejection | Only forwarded calls are answered. Direct calls to the Twilio number are rejected (busy), unless the caller is in `contacts.json`. |
| Rate limiting | A maximum of 30 requests per minute from a single IP address. Exceeding the limit results in HTTP 429. |
| Hidden application port | Port 8000 is not exposed to the internet. Traffic passes exclusively through Caddy (HTTPS on port 443). |
| Signal sender filtering | Signal messages are accepted only from the `SIGNAL_RECIPIENT` number. All others are logged and ignored. |
| Audio file protection | File names are validated with a regular expression (MD5 hash + .mp3 only). Path traversal attacks are blocked. |
| Security headers | Caddy adds: HSTS, X-Frame-Options DENY, X-Content-Type-Options nosniff, and strips the Server header. |
| Disabled API documentation | The `/docs`, `/redoc`, and `/openapi.json` endpoints are turned off. |

---

### System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                       EXTERNAL SERVICES                         │
│  ┌──────────┐      ┌───────────┐      ┌──────────────┐         │
│  │  Twilio   │      │  OpenAI   │      │  ElevenLabs  │         │
│  │ Voice/STT │      │  GPT-4o   │      │  TTS (voice) │         │
│  └─────┬─────┘      │  TTS fbk  │      └──────┬───────┘         │
│        │            └─────┬─────┘             │                 │
└────────┼──────────────────┼───────────────────┼─────────────────┘
         │ HTTPS            │ HTTPS             │ HTTPS
         ▼                  ▼                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DOCKER HOST (your server)                     │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ Caddy :443 (Let's Encrypt) OR Cloudflare Tunnel           │  │
│  └──────────────────────┬─────────────────────────────────────┘  │
│                         │ ava-net (Docker bridge)                │
│                         ▼                                        │
│  ┌──────────────────────────────────────────────────────┐       │
│  │              AVA (FastAPI :8000)                       │       │
│  │                                                       │       │
│  │  main.py ─── conversation.py ─── tts.py               │       │
│  │     │              │                │                  │       │
│  │  Twilio hooks    GPT-4o/Groq    ElevenLabs→OpenAI    │       │
│  │  Rate limiter    Streaming       →Polly fallback      │       │
│  │  Audio serve     Meta parsing    TTS cache (MD5)      │       │
│  │  Diagnostics     Summarizer      Circuit breaker      │       │
│  │     │                                                  │       │
│  │  owner_channel.py ─── contact_lookup.py ─── i18n.py   │       │
│  │     │                      │                           │       │
│  │  Signal notify          contacts.json             11+ langs   │
│  │  Signal poll (3s)       CNAM lookup                Signal     │
│  │  Slash commands         Lang from prefix           templates  │
│  │  Owner instructions     Per-contact lang                      │
│  └─────────┬────────────────────────────────────────────┘       │
│            │ HTTP                                                │
│            ▼                                                     │
│  ┌─────────────────┐   ┌──────────────────────┐                 │
│  │ signal-cli :8080 │   │ Volumes:              │                 │
│  │ REST API         │   │  tts_cache (MP3s)     │                 │
│  │ Signal servers   │   │  /data/calls/ (JSON)  │                 │
│  └─────────────────┘   │  /data/contacts.json  │                 │
│                         └──────────────────────┘                 │
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ Signal protocol
         ▼
   ┌────────────┐
   │  Owner's   │
   │  Signal    │
   └────────────┘
```

#### Timeouts & Limits

| Parameter | Value | Description |
|-----------|-------|-------------|
| `speech_timeout` | 1 s | Silence after speech before Twilio fires callback |
| LLM `max_tokens` | 180 | Max response length per turn |
| Hard turn limit | 10 exchanges | AVA wraps up the call |
| ElevenLabs timeout | 15 s | HTTP timeout for TTS API |
| ElevenLabs circuit breaker | 10 min | Auto-disable on 401/403/429 |
| Signal poll interval | 3 s | Check for new owner messages |
| Rate limiter | 30 req/min/IP | Sliding window |
| Call cleanup | 90 s delay | Cleanup after call ends |
| TTS cache | no expiry | Persists in Docker volume |

Internet traffic reaches AVA via Caddy (ports 80/443) or Cloudflare Tunnel (no open ports required). All other services run exclusively on the internal Docker network.
