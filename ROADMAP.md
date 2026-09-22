# AVA — Roadmap

> Last updated: 2026-03-01

---

## Completed

- [x] Core call flow: Twilio STT → GPT-4o → ElevenLabs TTS
- [x] Signal integration: notifications, live updates, owner instructions mid-call
- [x] Multilingual support: 13+ languages, auto-detection, mid-call switching
- [x] Maya persona with full OWNER_CONTEXT customization
- [x] TTS provider chain with circuit breaker (ElevenLabs → OpenAI → Polly)
- [x] TTS disk cache (MD5-keyed, persistent)
- [x] Switch to gpt-4o-mini for conversation
- [x] Reduce max_tokens and system prompt
- [x] Groq LLaMA 3 support
- [x] Contact lookup (local JSON + Twilio CNAM)
- [x] Streaming GPT-4o with first-sentence TTS pipelining
- [x] Twilio signature validation + rate limiting
- [x] Cloudflare Tunnel as alternative to Caddy for HTTPS ingress
- [x] Call recording (on/off via Signal `/recording-on`)
- [x] API usage & cost tracking per call (GPT tokens, TTS chars, estimated cost)
- [x] `/stats` with session costs and per-call cost history
- [x] `speech_timeout` reduced to 1s (from 5s)

---

## In Progress

_Nothing currently in progress._

---

## Short-term (quick wins)

### Pre-warm TTS cache on startup
- [ ] Generate and cache all greetings (13 languages) at boot
- [ ] Cache all clarification phrases and no-input prompts
- **Impact**: eliminates 1-2s TTS delay on first call per language

---

## Medium-term (new capabilities)

### Configurable speech_timeout
- [ ] Make `speech_timeout` configurable via env var
- [ ] Consider per-language tuning (some languages have longer pauses)
- [ ] Test `speech_timeout=1` for aggressive low-latency mode

### Call analytics dashboard
- [ ] Web UI for browsing call history (`/data/calls/*.json`)
- [ ] Charts: calls per day, average cost, language distribution
- [ ] Search by caller name/number/topic

---

## Long-term (architectural changes)

### OpenAI Realtime API
- [ ] Audio-in → Audio-out streaming (bypass separate STT/TTS)
- [ ] WebSocket-based architecture
- [ ] Expected latency: ~1-2s end-to-end
- **Trade-offs**: expensive (~$0.30/min), no ElevenLabs voice, major rewrite

### ElevenLabs Conversational AI Agent
- [ ] Full STT + LLM + TTS pipeline in one service
- [ ] Twilio native integration
- [ ] `contextual_update` WebSocket for owner instructions mid-call
- [ ] Custom tools (webhooks) for meta extraction (urgency, topic, caller_name)
- [ ] Expected latency: <2s (sub-second claimed)
- **Trade-offs**: $0.08-0.10/min, less control over prompt, significant rewrite
- **Advantage**: keeps ElevenLabs voice quality, lowest latency option

### Multi-channel support
- [ ] WhatsApp voice messages (via Twilio)
- [ ] Telegram voice bot
- [ ] Web widget (embed on website)

---

## Latency Reference

Current response time breakdown (user stops speaking → hears response):

| Stage | Current | With gpt-4o-mini | With Groq | With Realtime API |
|-------|---------|-------------------|-----------|-------------------|
| speech_timeout | 1.0s | 1.0s | 1.0s | N/A |
| Twilio STT | 0.5s | 0.5s | 0.5s | N/A |
| LLM inference | 2.0s | 0.7s | 0.3s | — |
| TTS generation | 1.5s | 1.5s | 1.5s | — |
| Network/playback | 0.5s | 0.5s | 0.5s | — |
| **Total** | **~5.5s** | **~4.2s** | **~3.8s** | **~1-2s** |

_With complementary optimizations (shorter prompt, lower max_tokens, pre-warm cache): subtract ~0.5-1s._

---

## Cost Reference

| Service | Rate | Notes |
|---------|------|-------|
| GPT-4o | $2.50/$10.00 per 1M tok (in/out) | Current model |
| GPT-4o-mini | $0.15/$0.60 per 1M tok | 10x cheaper |
| Groq LLaMA 3 70B | $0.59/$0.79 per 1M tok | Free tier: 30 req/min |
| ElevenLabs TTS | ~$0.30/1k chars | Primary voice |
| OpenAI TTS | ~$0.015/1k chars | Fallback voice |
| ElevenLabs Agent | $0.08-0.10/min | All-in-one (+ LLM costs TBD) |
| OpenAI Realtime | ~$0.30/min | Audio-to-audio |
| Twilio Voice | ~$0.02/min | Phone line |
| Twilio STT | ~$0.02/15s | Enhanced mode |
