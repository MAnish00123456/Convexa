# AI connections in Convexa

Open **Settings → AI connections**. Add a provider key (Groq, Gemini or OpenAI), then choose your preferred service for ARIA answers, semantic embeddings and voice transcription. Click **Save connections**. Keys are sent only to the local Convexa server and encrypted in your account's SQLite record. The encryption key is kept separately within your local data directory; do not share either file.

- **Groq:** available for ARIA chat and speech transcription, subject to plan quotas.
- **Gemini:** available for semantic search embeddings and ARIA chat, subject to the provider's quotas.
- **OpenAI:** available as an optional API provider, with separate usage billing.

The **Test connections** control sends synthetic text requests, not your private notes. Voice recognition needs a real recording. After enabling embeddings, use **Build semantic index** to index saved passages. If you switch embedding providers, rebuild the index for the new model.

If a provider is absent or unavailable, Convexa continues supporting local knowledge, document search, reminders, and source-backed ARIA retrieval. Published YouTube captions require source availability and the optional caption library; some videos will need a manually supplied transcript.

Advanced users may still configure `.env` directly. For a typical local setup, browser settings are sufficient.
