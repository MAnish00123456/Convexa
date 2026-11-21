# Convexa interface and behavior verification — November 2026

## Changes to the active application

1. Consistent, responsive app shell with a mobile navigation drawer and readable search results.
2. ARIA composition area visible within the viewport, with internally scrollable history.
3. YouTube split view: embedded player and searchable timestamped transcript together.
4. Convexa Settings with per-account Groq/Gemini/OpenAI credential fields, provider preferences and status actions.
5. Focus sessions with 1–240 minute custom durations.
6. Separate public **Why Convexa?** page and in-app page with a section index.
7. Interactive knowledge map with draggable nodes, saved coordinates, custom links and automatically inferred tag/collection associations.
8. More precise full-phrase search when multiple direct query words are present.

## Verification scope

- 65 Python tests passed, including authenticated HTTP API tests and negative authorization cases.
- Playwright smoke passed: public guide, signup, file upload and search, YouTube side-by-side view, transcript filtering and timestamp seeking, settings save, custom timer, map connections and drag persistence, mobile navigation, zero page errors.
- Browser test used an HTTP API relay due to sandbox browser restrictions; the frontend HTML, CSS and JS were unmodified apart from virtual navigation substitution.
- Real Groq/Gemini/OpenAI requests, public YouTube embed rendering in external browsers, live captions retrieval, browser microphone hardware and release hosting were not verified by this automated suite.

## Privacy and account boundaries

Credential values are stored as encrypted bytes server-side. Browser responses return only boolean presence flags and preferences; they never echo saved credentials. Account ownership is checked on map positions and edges. The local encryption key and database reside on the same machine: back them up together and do not expose the application as a public multi-tenant service without additional hardening.

## Preserving earlier data

The existing `data/convexa.sqlite3` is not bundled. SQLite tables are migrated on first launch. Users should copy their previous `data/` directory into the new Convexa directory while the server is stopped.
