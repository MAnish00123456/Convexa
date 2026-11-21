# Recommended start for this update

Read `REVIEW_CHECK.md` first. From the folder containing app.py, run `python launch.py` (Windows/MSYS/Zsh) or `python3 launch.py` (Linux/WSL). This creates/selects the correct virtual environment and installs missing dependencies. The start scripts use this launcher too.

# Run Convexa

## Windows (PowerShell or Command Prompt)

1. Extract the ZIP. Open a terminal in the inner `Convexa` folder containing `app.py`.
2. Check Python (3.10 or newer; Python 3.11 is supported):

   ```powershell
   python --version
   ```

3. Create a virtual environment and install the extraction/caption/encryption packages:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\python.exe -m ensurepip --upgrade
   .\.venv\Scripts\python.exe -m pip install -r requirements-optional.txt
   ```

4. Start the app:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

5. Open **http://127.0.0.1:8765** and create a local account (or sign in if you preserved your data).
6. Keep the terminal open while using Convexa. Stop it with **Ctrl+C**.

If Windows recognizes `py` instead of `python`, use `py -3` for steps 2 and the first command of step 3. The remaining commands use the virtual environment directly; activation is not required.

For subsequent runs, open the same folder and run only:

```powershell
.\.venv\Scripts\python.exe app.py
```

If port 8765 is in use:

```powershell
.\.venv\Scripts\python.exe app.py --port 8766
```

Then open http://127.0.0.1:8766.

## Linux / WSL / macOS

From the extracted `Convexa` folder:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-optional.txt
.venv/bin/python app.py
```

Open http://127.0.0.1:8765. If Ubuntu reports that venv is unavailable, install the Python venv package for your Python version first.

## Keep existing knowledge

Stop the previous server. Copy its `data/` folder into the new `Convexa` folder before starting. Keep a backup of that folder and your existing `.env` file, if used. If you configured `CONVEXA_DATA_DIR`, continue using that same data location. Never share your data folder or API keys in a project ZIP.

## Try the samples

Open **Add knowledge → select a type → Use sample → review → Save to knowledge**.

Samples exist for Note, YouTube, Web link, Chat, File and Code; Voice is excluded. Save the Note, Chat and File samples, then search for `normalization` or `Atomicity`. See `docs/SAMPLE_DEMO.md` for a presentation walkthrough.

Basic storage and keyword search work without API keys. Published YouTube captions and web extraction need network access and source availability. For cloud AI, open **Settings → AI connections**, enter your own provider keys and save. See `CLOUD_AI_SETUP.md` for details.

## Developer checks and formatting

Python tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

JavaScript sample tests (requires Node.js, which is not needed to run Convexa):

```bash
node tests/test_samples.js
```

Python files use Black with four-space indentation. JavaScript, HTML, CSS and Markdown use Prettier with two-space indentation. Configuration files are included. To format future edits, install the optional developer tools:

```powershell
.\.venv\Scripts\python.exe -m pip install black
.\.venv\Scripts\python.exe -m black .
npx prettier --write "web/**/*.{js,css,html}" "tests/*.js" "*.md" "docs/*.md" .prettierrc.json
```

The Prettier command requires Node.js and may download Prettier. These formatting tools are not application dependencies.
