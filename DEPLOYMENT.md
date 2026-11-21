# Convexa: local use and Vercel deployment

This edition preserves the existing UI and supports two storage modes. Local mode uses SQLite and local files. Hosted mode connects directly to a persistent **Turso/libSQL** database; it never keeps the authoritative database in Vercel `/tmp`.

## Changes in this edition

1. Added `api/index.py`, Vercel routing and Python 3.12 configuration.
2. Added remote libSQL storage while retaining local SQLite mode.
3. Persisted uploaded files as database chunks, with account-protected downloads and audio byte-range support. No separate object-storage account is required.
4. Added a stable environment encryption key for saved per-user AI credentials.
5. Hosted imports finish inside the HTTP request instead of relying on background threads that can stop after a serverless response. Errors leave a retryable item with an explanation.
6. Fixed voice retry to load the actual stored audio and use the requesting user's provider settings.
7. Changed semantic indexing to resumable batches of 10 passages. Repeated clicks skip already indexed passages; interruption does not discard completed batches.
8. Made full-text reindexing set-based to reduce cloud round trips and transaction duration.
9. Added cloud upload limits and small list previews to avoid oversized function payloads. Opening/editing an item still loads its full content; server-side search and ARIA use full source text.
10. Added mandatory cloud configuration checks, database-aware health checks, secure cookies on Vercel, a durable per-email sign-in limit and optional invitation-only registration.
11. Updated local-only UI claims and fixed the launcher to detect Windows/MSYS2 and Unix virtual-environment paths.
12. Added hosted-handler regression tests, cloud preflight and a live-deployment smoke-test command.

## Run locally (your existing MSYS2/Zsh terminal)

From the extracted `Convexa` folder:

```sh
python -m venv .venv
./.venv/bin/python -m ensurepip --upgrade
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python app.py
```

Open http://127.0.0.1:8765. The shorter launcher is `python launch.py`.
If you use standard Windows Python in PowerShell instead:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m ensurepip --upgrade
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

Linux/macOS use the MSYS2 commands, replacing the first `python` with `python3` if needed. For hosted database preflight, use Python 3.12 on Linux/WSL because the packaged libSQL driver is installed on Linux. Local Windows mode does not require libSQL.

## Deploy to Vercel

### 1. Create persistent storage

Create a database at https://turso.tech using the **libSQL engine**, with a location near your Vercel function. This project requires SQLite-compatible FTS5, not the newer Turso rewrite engine. Copy its `libsql://...` URL and a read/write database token. Follow the provider's dashboard/CLI instructions for creating that engine and token.

The application creates its tables automatically on first request. Do not select a read-only token. A cloud database is necessary even if you do not use AI.

### 2. Generate one encryption key

After installing requirements, run:

```sh
./.venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Keep it private and retain a backup. Reuse it for every redeployment of the same database. Changing it prevents previously saved provider keys from being decrypted.

### 3. Import the project

Upload the extracted source to your GitHub repository, then import that repository in Vercel. Never upload `.env`, `data`, `.venv`, real keys or local databases.

Vercel settings:

| Setting | Value |
| --- | --- |
| Root Directory | The directory containing `app.py`, `api/`, `requirements.txt`, and `vercel.json`; select `Convexa` if the repository contains that outer folder |
| Framework Preset | Other |
| Build Command | Leave unset / override disabled |
| Output Directory | Leave unset / override disabled |
| Install Command | Leave automatic; Python dependencies are declared in `pyproject.toml` and mirrored in `requirements.txt` |
| Python | 3.12, specified by `.python-version` |
| Function duration | 300 seconds, specified in `vercel.json`; enable Fluid Compute if required by your project settings |

Do **not** set `python app.py` as a Vercel build command. Vercel invokes `api/index.py` per request.

### 4. Add environment variables before deploying

| Name | Value |
| --- | --- |
| `CONVEXA_DATABASE_URL` | Your Turso **libSQL** database URL |
| `CONVEXA_DATABASE_AUTH_TOKEN` | Database read/write token |
| `CONVEXA_SECRET_KEY` | Generated Fernet key |
| `CONVEXA_INVITE_CODE` | A private code you choose; recommended for limiting registration to your demonstration users |

The first three are required. Add them to Production. If enabling Preview deployments, use a separate preview database and matching secret key so preview code cannot change production data. Vercel supplies `VERCEL=1`; do not add it to your local `.env`.

Do not use `NEXT_PUBLIC_` or expose these variables in JavaScript. Add Gemini/Groq/OpenAI keys through **Convexa Settings after login**. Using global provider environment keys would share that provider's quota across accounts.

Deploy. Environment-variable changes require redeployment.

### 5. Verify the real deployment

1. Open `https://YOUR-PROJECT.vercel.app/api/health`. Expect `status: ok` and `storage: cloud`. A 503 means configuration/database setup needs attention; it is not a successful deployment.
2. Register your account using the invitation code if configured.
3. Save a note, upload a small PDF/TXT, search its contents, connect/disconnect map nodes, and refresh the page.
4. Add your provider keys in Settings, save and run **Test connections**. A saved key alone is not proof of a working provider.
5. If embeddings connect, run **Build semantic index**. Ask a short question grounded in saved content, such as “What is a foreign key? Answer in one sentence.”
6. Test voice with an actual short recording. Test YouTube separately; hosting providers' IPs can be blocked by YouTube even with valid application code. Retry or manually paste published captions if import is unavailable.
7. Redeploy once, sign in again, reopen the saved note and download its file. This checks persistence outside a single process.

Optional command against the deployed HTTPS URL (create a dedicated test account first):

```sh
python scripts/smoke_deployment.py https://YOUR-PROJECT.vercel.app
# Also run provider diagnostics, using a small amount of your provider quota:
python scripts/smoke_deployment.py https://YOUR-PROJECT.vercel.app --ai
```

The script prompts for credentials, creates two temporary knowledge items, verifies their attachment/search/map behavior, and removes those items. Vercel deployment protection must allow access. An AI diagnostic report must be inspected separately; storage success does not mean all providers passed.

## Optional database preflight before deployment

On Linux/WSL, copy `.env.example` to `.env`, fill the first three variables, install requirements, then run:

```sh
python scripts/preflight.py
```

This performs real connection, schema and FTS5 checks using your credentials. Never commit `.env`.

## Limits and existing data

- Hosted file limit: **4,000,000 bytes per file** (4 MB). Local SQLite mode retains 40 MiB. Vercel limits function request/response payloads to 4.5 MB, so larger cloud uploads need a separate direct-upload object-storage design. Use shorter audio or smaller PDFs for this edition.
- Cloud attachments count against database storage and transfer allowances. Hosting/database/AI plan limits still apply; this package does not guarantee zero usage charges.
- Existing local accounts/files are not automatically uploaded. Keep the old `data` folder as a backup. A new cloud database starts empty; register and add your samples/content there. Do not upload the local data folder to GitHub/Vercel.
- The workspace initially lists up to the existing 60-item browse limit; searches return matching items. The knowledge map displays up to 40 non-archived items, as in the previous edition.
- PDF extraction requires selectable text; OCR was not added. Browser microphone capture requires HTTPS or localhost and user permission. Reminders alert while the page is open; this does not add an email/push scheduler.
- Provider permissions, quotas, model availability and third-party caption access require live testing. The test report explicitly distinguishes simulated provider tests from real calls.

## Regression tests

On Linux/WSL after installing requirements:

```sh
python -m unittest discover -s tests -v
node tests/test_samples.js
node tests/test_review_ui.js
```

`tests/test_hosting.py` exercises the production handler and official libSQL engine with a disposable local database. It does not claim a real Turso network call. See `TEST_REPORT.md` for results and remaining live checks.

## Reference documentation

- https://vercel.com/docs/functions/runtimes/python
- https://vercel.com/docs/functions/limitations
- https://vercel.com/docs/functions/runtimes
- https://docs.turso.tech/sdk/python/quickstart
