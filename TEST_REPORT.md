# Convexa Vercel edition — verification report

Date: 20 November 2026
Base: Convexa-ARIA-Fix.zip, source version 4.

## Passed

- **111 Python tests** in a fresh Python 3.12 virtual environment using the packaged requirements (final run: 10.581 seconds).
- These comprise the existing 70 tests and 41 hosted-handler/configuration tests. The hosted tests use the official libSQL engine against a disposable local database; only the database connection target is substituted.
- Both Node test suites: `tests/test_samples.js` and `tests/test_review_ui.js`.
- JavaScript syntax checks for the changed browser scripts.
- **Official `@vercel/python` 33.0.0 builder completed successfully**, targeting `api/index.py` on Python 3.12. This is a local builder invocation, not a deployment to a Vercel account.
- Dependencies installed by that builder import successfully: libsql 0.1.11, pypdf 6.21.4, youtube-transcript-api 1.2.5, cryptography 46.0.7.

## Coverage

Registration/login/logout; password validation; CSRF; account ownership; note/chat/code capture; file extraction; lexical search; map operations; reminders and focus sessions; provider settings; encrypted-key persistence; source-grounded ARIA behavior and provider response contracts.

Hosted-specific checks include:

- Blob upload/download and byte-range responses.
- Uploaded content retained after deleting scratch storage and resetting cold-start initialization.
- Cross-account file access denied and attachment data deleted with its item.
- Atomic file replacement: a simulated database write failure retains the prior attachment.
- Successful 4,000,000-byte upload; oversized requests rejected.
- List previews bounded while full item detail remains intact.
- Caption work completes before the response; timeout produces a retryable explanatory state.
- Voice retry reads persistent audio and the correct user's AI settings.
- Saved encrypted credentials survive handler reinitialization.
- Semantic indexing resumes in batches and skips completed work.
- Invitation checks, persistent per-email authentication throttling, Secure cookies on Vercel.
- Missing hosted database or encryption configuration is rejected.

## Not verified here

- A real Vercel deployment, domain and platform routing. No Vercel account/project credentials were available.
- Real network access to a Turso database. No user database URL/token was available. `scripts/preflight.py` performs this check once configured.
- Live Gemini/Groq/OpenAI account permissions, quotas, models and audio transcription. Provider-contract tests use fixtures, not paid/live requests.
- YouTube caption availability from Vercel IP addresses. YouTube may block hosted requests or omit captions. The application preserves the video and supports retry/manual transcript input.
- Full browser end-to-end execution: Chromium could not start because this environment denies a required browser socket operation. The two JavaScript suites passed, but this is not a visual browser pass.

## Required live acceptance check

Follow DEPLOYMENT.md. Run `scripts/smoke_deployment.py` against the real HTTPS URL using a dedicated test account, then save a permanent test note/file, redeploy and confirm both remain accessible. Test provider connections and a short recording separately. Do not treat this report as a guarantee of zero production errors.
