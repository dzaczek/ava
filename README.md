# AVA – AI Voice Assistant

> **AVA** answers your calls when you can't, holds a natural conversation, and keeps you in the loop via Signal. You can send live instructions mid-call from your phone.

---

## How it works

```
Your phone (you decline / busy)
  → Call forwarding → Twilio number
  → HTTPS webhook → AVA (FastAPI / Docker)
  → GPT-4o: natural multilingual conversation
  → ElevenLabs TTS: human-sounding voice
  → Signal: live updates + you can text instructions
  → On hang-up: full summary + transcript → Signal + saved to file
```

---

## Signal commands (during a call)

When a call is active, send any of these to the AVA bot on Signal:

| Message | What happens |
|---------|--------------|
| `tell him I'll call back tomorrow at 10` | AVA naturally relays this to the caller |
| `ask for the order number` | AVA asks the caller |
| `end` | AVA wraps up the call gracefully |
| `status` or `?` | Confirms whether a call is active |
| Any other text | Forwarded as a generic instruction |

### Example Signal flow

```
AVA → You:
📞 Incoming call
From: Jan Kowalski (+48123…)
🌐 Language: pl-PL
⏰ 14:32
Send instructions to influence the conversation.

You → AVA:
ask for the invoice number

AVA → You:
✅ AVA will ask: invoice number

AVA → You (live update after 2 exchanges):
📞 Call in progress – Jan Kowalski
🟡 Topic: invoice dispute
👤 I'm calling about invoice #456, there's an error in the address
🤖 I understand, I'll make sure to pass that on to the owner…

AVA → You (after hang-up):
📋 Call summary
━━━━━━━━━━━━━━
From: Jan Kowalski
Priority: 🟡 Medium
Jan Kowalski from Acme Corp called about invoice #456.
The billing address needs to be corrected. He'd like a callback by end of day.
```

---

## Call logs

After every call (including missed calls), AVA saves a JSON file to `./data/calls/`:

```
data/calls/20260223_143215_CA1a2b3c.json
```

Each file contains: caller info, transcript, AI summary, language, timestamps, and call metadata.

---

## Setup

### 1. Twilio – voice number

1. Create an account at https://console.twilio.com
2. **Phone Numbers → Buy a Number** – pick a Polish (+48) or US number
3. Open the number settings and configure:
   - **Voice → A CALL COMES IN** → Webhook `https://your-domain.com/twilio/incoming` (POST)
   - **Voice → Call Status Changes** → `https://your-domain.com/twilio/status` (POST)

### 2. Call forwarding on your phone

**Android**
Phone app → ⋮ Menu → Settings → Call forwarding → *When busy / When declined*
Enter your Twilio number.
GSM code: `**67*<twilio_number>#`

**iOS**
Settings → Phone → Call Forwarding (carrier-dependent).
Or ask your carrier to set conditional forwarding.

### 3. Signal setup

```bash
docker compose up signal-cli -d

# Register the bot number
curl -X POST "http://localhost:8080/v1/register/+48XXXXXXXXX" \
  -H "Content-Type: application/json" \
  -d '{"use_voice": false}'

# Verify with the SMS code
curl -X POST "http://localhost:8080/v1/register/+48XXXXXXXXX/verify/123456"
```

### 4. ElevenLabs (optional – better voice quality)

1. Sign up at https://elevenlabs.io
2. **Profile → API Keys** → create a key
3. Browse the **Voice Library** and copy the Voice ID of your preferred voice
   (multilingual recommendations: *Charlotte*, *Alice*, *Aria*)
4. Set `ELEVENLABS_API_KEY` and voice IDs in `.env`

Without a key AVA falls back to OpenAI TTS, then Twilio Polly.

### 5. Deploy

```bash
# 1. Clone / copy the project
cp .env.example .env
# Fill in all API keys and OWNER_CONTEXT in .env

mkdir -p data/calls

# 2. Start everything
docker compose up -d

# View logs
docker compose logs -f ava

# Health check
curl https://your-domain.com/health
```

---

## Customising AVA's behaviour

The simplest way is via the `OWNER_CONTEXT` env variable – no code changes:

```env
OWNER_CONTEXT=The phone owner is Jan Kowalski. \
Birthday: 15 March 1990. \
Working hours Mon–Fri 9:00–17:00 CET. \
Expected calls: clients, suppliers, IT team. \
IT incidents are always high priority. \
Recruiters and sales calls: politely decline.
```

For deeper changes, edit `SYSTEM_PROMPT` in `app/conversation.py`.

---

## Cost estimate

| Service | Rate | Typical 2-min call |
|---------|------|--------------------|
| Twilio Voice | $0.013 / min | ~$0.03 |
| Twilio STT (enhanced) | $0.02 / 15 s | ~$0.16 |
| OpenAI GPT-4o | ~$0.01 / 1k tokens | ~$0.005 |
| ElevenLabs | from $5 / month | (30 k chars free tier) |

**Typical call: ~$0.20–0.25**

---

## Troubleshooting

```bash
# Twilio can't reach the webhook?
curl -I https://your-domain.com/health

# TTS audio not playing?
# Check that PUBLIC_URL is reachable from the internet
docker compose logs ava | grep -i tts

# Signal not sending?
docker compose logs ava-signal-cli
curl http://localhost:8080/v1/accounts
```

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                      Docker host                     │
│                                                      │
│  ┌──────────┐    ┌──────────────────┐               │
│  │  Caddy   │───▶│   AVA (FastAPI)  │               │
│  │  HTTPS   │    │                  │    ┌────────┐ │
│  └──────────┘    │  ┌────────────┐  │───▶│signal  │ │
│                  │  │conversation│  │    │  cli   │ │
│                  │  │  (GPT-4o)  │  │    └────────┘ │
│                  │  └────────────┘  │               │
│                  │  ┌────────────┐  │               │
│                  │  │owner_chan. │  │               │
│                  │  │ (Signal)   │  │               │
│                  │  └────────────┘  │               │
│                  │  ┌────────────┐  │  ┌──────────┐ │
│                  │  │ElevenLabs  │  │  │data/calls│ │
│                  │  │    TTS     │  │  │  (JSON)  │ │
│                  │  └────────────┘  │  └──────────┘ │
│                  └──────────────────┘               │
└─────────────────────────────────────────────────────┘
         ▲                    │
         │ webhooks           │ API calls
         ▼                    ▼
      Twilio            OpenAI / ElevenLabs
     (Voice)
```
