# ARIA passage selection update — 16 November 2026

For an existing working installation, stop the server and replace only `core/assistant.py` with the file from this ZIP. Keep your `data/`, `.env` and `.venv-win/` unchanged. Restart with `./.venv-win/Scripts/python.exe app.py`.

This update prevents title-only search matches from being used as the entire evidence passage. ARIA selects actual saved note, chat, extracted document or transcript content instead, retaining a maximum of 950 characters per source and six sources. Regression tests check the actual bundled samples without calling a paid or quota-limited API. Live Gemini responses on your account still require verification.

Ask a new question after restarting: Why do we normalize a database? Answer in one sentence.
Existing chat messages are saved history and will not be rewritten.

---

# Convexa review checks — 14 November 2026

## Install this update

1. Stop the old server (Ctrl+C) and back up the old Convexa folder.
2. Extract this ZIP to a new folder. Copy the complete old `data/` folder into the new inner `Convexa/` folder. Preserve `.env` if you use it. If CONVEXA_DATA_DIR is configured, keep using that location. Copying the complete data folder preserves the encryption key needed for saved credentials.
3. Open a terminal in the inner Convexa folder (the one containing app.py).
4. Run `python launch.py` (Windows/MSYS/Zsh) or `python3 launch.py` (Linux/WSL). The launcher selects the appropriate project virtual environment and installs missing extraction/caption/encryption dependencies. First setup needs internet. Windows users can also double-click start-windows.bat.
5. Open http://127.0.0.1:8765 and hard refresh with Ctrl+Shift+R. Sign into your existing account.

Do not move a Windows virtual environment into WSL or vice versa. If Python cannot create the environment or install packages, resolve the shown setup error before the review.

## Five checks on your actual laptop

1. **YouTube:** Open the existing sample, click Retry captions, and wait for the transcript. The panel now refreshes when import finishes. Confirm searchable text and click a timestamp. After a successful import, the saved transcript remains available offline; video playback still needs internet. Fetch it before presenting. If YouTube blocks captions, use Edit to paste the actual transcript from the video; do not present invented text as captions.
2. **Connections:** Open Knowledge map. Only saved connections appear initially. Click Connect on one card, then Select on another. Reload and verify the saved link. Click Disconnect to remove it. To change the pair, disconnect and connect the intended cards. Show suggestions is optional: shared tags/collections are suggestions, not saved links. The generic sample/demo tags are ignored.
3. **AI:** In Settings, save your keys. Select the intended services explicitly if needed. Test connections checks the selected chat and embeddings providers, not every stored provider key. Read the persistent results. A saved key or Configured badge is not proof of a successful request. Switch chat providers and repeat if you plan to demonstrate more than one. Do not send API keys in screenshots or messages.
4. **Semantic search:** With the selected embedding provider passing, click Build semantic index. Confirm indexed passages, then search for a concept and verify the retrieved source. With no embeddings key, keyword search remains available.
5. **Voice + ARIA:** Upload a short clear recording and confirm that its actual words appear. Voice is NOT verified by the text connection test. Ask ARIA about a saved note and inspect its source citation and response mode. An offline extractive answer is not a successful live cloud AI answer.

Keep the already-imported video transcript and documents ready for the presentation. Do not make the first provider request or first caption import during the live review.

## Verified in this update

- 68 Python tests: storage, authentication, ownership boundaries, search, uploads, map persistence/deletion, encrypted settings, AI adapter contracts and diagnostics.
- JavaScript behavior tests: six capture samples, draft protection, manual map defaults, suggestions, connect/disconnect, duplicate prevention, honest status labels and completed transcript refresh.
- Python compilation and JavaScript syntax checks.
- Live sample YouTube import for video 6Iu45VZGQDk: 11,668 timestamped transcript characters. A temporary real HTTP server saved the transcript and reached searchable status.

## Verification limits

- Groq, Gemini and OpenAI requests were contract-tested with simulated responses. No user API keys were supplied, so live account access, quotas, cloud answers, embeddings and speech recognition are NOT certified.
- Chromium could not launch in the verification environment (socket operation denied). Visual browser testing was not completed. A browser test script covering samples, map persistence and diagnostics is included for an environment supporting Chromium and Playwright.
- Live YouTube success here does not guarantee future availability or success on every network.
- Windows launcher was inspected and compiled but not executed on Windows here.

## Changes

- Standard requirements now include caption/PDF/encryption dependencies, and launchers use a project environment rather than an arbitrary system Python.
- Open pending transcript pages refresh when background work completes; stopped imports no longer say they are awaiting captions indefinitely.
- Caption requests have connection/read timeouts and do not retry unrelated errors as a different language.
- Map defaults to saved links; generic sample tags no longer infer relationships; Disconnect is visible.
- Settings distinguish Not installed / Not configured / Configured. Connection test results remain visible; HTTP authentication, access, quota and model errors are clearer.
- Gemini default chat model updated to gemini-3.5-flash-lite. Existing CONVEXA_GEMINI_CHAT_MODEL environment override remains supported. Google's model documentation currently advises new projects to use newer models because access to 2.5 models is limited to previous users: https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite . Actual access still requires your connection test.
