# Vercel-ready edition

Start with [DEPLOYMENT.md](DEPLOYMENT.md) for current commands, required environment variables, cloud limits and deployment tests. [TEST_REPORT.md](TEST_REPORT.md) records what was verified. The historical local-edition notes below remain for background.

# Convexa

**Convexa: An Intelligent Personal Knowledge and Productivity Platform**

Convexa brings your notes, uploaded documents, YouTube transcripts, chat excerpts, voice recordings, links and code into a single searchable knowledge space. It also includes **ARIA**, a source-aware assistant, a **knowledge map**, reminders, focus sessions, and an optional AI connection panel.

## Start

Convexa needs Python 3.10 or later. The core application runs with Python's standard library; the optional packages enable PDF extraction, published YouTube caption import and encrypted storage of API keys entered through Settings.

```bash
python -m pip install -r requirements-optional.txt
python app.py
```

Open **http://127.0.0.1:8765** and sign in. The app also starts without the optional dependencies, but some capture/integration features will be unavailable.

On Windows, double-click `start-windows.bat` after installing the optional packages. For MSYS2 UCRT64, if `python -m pip` isn't installed:

```bash
pacman -S mingw-w64-ucrt-x86_64-python-pip
```

Then create a virtual environment or install packages in the package-managed Python environment. If the `cryptography` package fails to install through pip under MSYS2 UCRT64, install its native package:

```bash
pacman -S mingw-w64-ucrt-x86_64-python-cryptography
```

## What to try first

1. **Add knowledge** → save a note or upload `sample-knowledge/database-test.pdf`.
2. Search for `consistent hashing`; Convexa should find words **inside the PDF**, not just its title.
3. Add a YouTube lecture. If public captions are available, search spoken passages and click timestamps to return to the relevant moment.
4. Open **Knowledge map** → drag your saved items, connect related cards, and revisit the map to confirm the layout persists.
5. Open **ARIA assistant** → ask a question about a saved source and check its citations.
6. Open **Settings** → paste a key for any provider you want to use, choose how each feature should be handled, and save. **There is no need to edit `.env` to configure keys through the interface.**
7. Open **Focus timer** → choose a preset or enter a custom number of minutes.

See [sample-knowledge/README.md](sample-knowledge/README.md) for complete tests that don't require another ZIP download.

## How knowledge retrieval works

- Convexa indexes notes, extracted text, submitted chat content and available transcripts with SQLite FTS5.
- When a YouTube transcript has timing data, search can return a passage and its corresponding video time.
- A saved voice recording remains playable even without a transcript; spoken content becomes searchable only when transcribed.
- Semantic embeddings and generative AI answers are optional cloud features. **Keyword search, knowledge management and source excerpts work independently of API keys.**
- Connecting providers may send selected passages/audio to the provider. Availability, quotas and pricing depend on each provider's terms.

## Files

- `app.py` — authenticated HTTP API and static frontend server.
- `core/store.py` — account-isolated SQLite storage, full-text search and persisted map graph.
- `core/knowledge.py` — document extraction, timestamped captions and text processing.
- `core/assistant.py` — source retrieval and configured AI services.
- `core/user_settings.py` — per-account encrypted credentials, stored server-side.
- `web/` — Convexa's frontend and progressive UI enhancements.
- `tests/` — HTTP, parsing, provider adapters and browser smoke tests.
- `sample-knowledge/` — real PDF, DOCX, TXT and sample conversation for testing.

## Test

```bash
python -m unittest discover -s tests -v
```

The browser smoke test uses Playwright and Chromium; these are development tools, not requirements for running Convexa:

```bash
python tests/browser_redesign_smoke.py
```

A full external-provider test requires a real key, network access and an eligible account. Automated provider contract tests use mocks; they do not guarantee provider uptime or quota.

## Updating from an earlier Convexa edition

**Your knowledge is stored in `data/`, not in the ZIP.** Stop the old server first. Copy the complete `data/` folder from the old Convexa directory into the new one, or replace application code inside the existing directory without deleting `data/`. Convexa automatically creates the additional tables needed for map layout and connections. Preserve any local secret key file in `data/` when moving a database with saved provider keys.

The server binds to `127.0.0.1` by default. This edition is designed for a local, trusted machine rather than direct public hosting. Never publish your `data/` directory, API keys or personal documents.
