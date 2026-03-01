# AVA — Roadmap

> Last updated: 2026-03-01

---

## Completed

- [x] Core call flow: Twilio STT → GPT-4o → ElevenLabs TTS
- [x] Signal integration: notifications, live updates, owner instructions mid-call
- [x] Multilingual support: 8+ languages, auto-detection, mid-call switching
- [x] Maya persona with full OWNER_CONTEXT customization
- [x] TTS provider chain with circuit breaker (ElevenLabs → OpenAI → Polly)
- [x] TTS disk cache (MD5-keyed, persistent)
- [x] Contact lookup (local JSON + Twilio CNAM)
- [x] Streaming GPT-4o with first-sentence TTS pipelining
- [x] Twilio signature validation + rate limiting
- [x] Cloudflare Tunnel as alternative to Caddy for HTTPS ingress
- [x] Call recording (on/off via Signal `/recording-on`)
- [x] API usage & cost tracking per call (GPT tokens, TTS chars, estimated cost)
- [x] `/stats` with session costs and per-call cost history
- [x] `speech_timeout` reduced to 2s (from 5s)

---

## In Progress

_Nothing currently in progress._

---

## Short-term (quick wins)

### Switch to gpt-4o-mini for conversation
- [ ] Set `OPENAI_MODEL=gpt-4o-mini` (env var, no code changes)
- [ ] Test quality for Polish/German/English phone conversations
- [ ] Benchmark latency improvement (~0.5-0.8s vs ~2s for gpt-4o)
- [ ] Keep gpt-4o for summarization only (separate model config)
- **Impact**: ~1.2s latency reduction, 10x cheaper tokens

### Reduce max_tokens and system prompt
- [ ] Lower `max_tokens` from 350 to 150 (2-3 sentences is enough)
- [ ] Trim system prompt (remove redundant rules, shorten examples)
- **Impact**: ~0.3-0.5s latency reduction

### Pre-warm TTS cache on startup
- [ ] Generate and cache all greetings (8 languages) at boot
- [ ] Cache all clarification phrases and no-input prompts
- **Impact**: eliminates 1-2s TTS delay on first call per language

---

## Medium-term (new capabilities)

### Groq LLaMA 3 support
- [ ] Add Groq as alternative LLM backend (OpenAI-compatible API)
- [ ] Make LLM provider configurable via env var (`LLM_PROVIDER=openai|groq`)
- [ ] Test Polish/German quality on LLaMA 3 70B/405B
- [ ] Benchmark: expected ~0.2-0.3s inference time
- **Impact**: fastest possible LLM response, free tier available
- **Risk**: weaker multilingual support vs GPT

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
| speech_timeout | 2.0s | 2.0s | 2.0s | N/A |
| Twilio STT | 0.5s | 0.5s | 0.5s | N/A |
| LLM inference | 2.0s | 0.7s | 0.3s | — |
| TTS generation | 1.5s | 1.5s | 1.5s | — |
| Network/playback | 0.5s | 0.5s | 0.5s | — |
| **Total** | **~6.5s** | **~5.2s** | **~4.8s** | **~1-2s** |

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
