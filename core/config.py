"""Read local .env values without dependencies. Never expose keys to the browser."""

from pathlib import Path
import os


def load_env(path=None):
    path = Path(path) if path else Path(__file__).resolve().parents[1] / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip()
        if not key.isidentifier() or not key.startswith(
            ("CONVEXA_", "OPENAI_", "GROQ_", "GEMINI_")
        ):
            continue
        val = val.strip()
        if len(val) >= 2 and val[0] == val[-1] and val[0] in ('"', "'"):
            val = val[1:-1]
        os.environ.setdefault(key, val)
