# Convexa synopsis alignment

The approved Convexa concept — combining notes, documents, YouTube lectures, voice recordings, chats, retrieval and productivity into a single knowledge base — is preserved in the active application.

## Implemented

- Unified web workspace with local accounts and source capture
- Collections, tags, favourites and archive
- TXT/DOCX/PDF extraction and indexed text search
- Accessible YouTube captions and timestamped transcript retrieval
- Audio capture/storage, optional transcription and searchable transcripts
- ARIA knowledge retrieval and optional source-grounded cloud AI responses
- Optional neural semantic embeddings, reminders and configurable focus sessions
- Knowledge map of saved source items, positions and relationships

## Technology clarification for the college report

The project synopsis originally described React, Django REST Framework, PostgreSQL, ChromaDB, Celery and Redis. The **current runnable Convexa edition** uses a Python HTTP server, SQLite FTS5, HTML/CSS/JavaScript and optional HTTP-based AI providers. This simpler architecture keeps the core application manageable on a student laptop. Update the report's Methodology and Software/Hardware sections to reflect the current source code before submission; do not claim the older services are deployed in this edition.

Provider-backed semantic search and voice transcription are conditional on configuration. Automatically searchable spoken YouTube content requires accessible captions or a supplied transcript. Scanned PDFs require OCR beyond this edition's text extraction capabilities.
