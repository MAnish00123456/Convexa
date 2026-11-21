"""User-owned, server-side AI settings; key material is encrypted in local SQLite.

Encryption key and database live on the same computer. This is suitable for a
private workstation, not a substitute for a hosted secrets manager.
"""

import json
import os
from . import store

KEYS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "openai": "OPENAI_API_KEY"}
PREFS = {
    "chat": "CONVEXA_AI_PROVIDER",
    "embeddings": "CONVEXA_EMBEDDING_PROVIDER",
    "voice": "CONVEXA_VOICE_PROVIDER",
}
VALID = {
    "chat": {"auto", "offline", "groq", "gemini", "openai"},
    "embeddings": {"auto", "none", "gemini"},
    "voice": {"auto", "none", "groq", "openai"},
}


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ImportError:
        raise ValueError(
            "Install cryptography from requirements-optional.txt to save API keys securely."
        ) from None
    key = os.environ.get("CONVEXA_SECRET_KEY")
    if key:
        return Fernet(key.encode())
    store.hosting.validate()
    store.DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = store.DATA_DIR / ".convexa_secret_key"
    if not path.exists():
        try:
            with path.open("xb") as f:
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return Fernet(path.read_bytes())


def read(c, user, with_secrets=False):
    row = c.execute(
        "SELECT preferences,secrets_ciphertext FROM user_ai_preferences WHERE user_id=?", (user,)
    ).fetchone()
    prefs = json.loads(row["preferences"]) if row else {}
    keys = {}
    if row and row["secrets_ciphertext"]:
        try:
            keys = json.loads(_fernet().decrypt(row["secrets_ciphertext"].encode()))
        except Exception:
            raise ValueError(
                "Saved API keys cannot be unlocked. Restore the matching CONVEXA_SECRET_KEY or local encryption key."
            ) from None
    return prefs, (keys if with_secrets else {k: bool(keys.get(k)) for k in KEYS})


def effective(c, user):
    prefs, keys = read(c, user, True)
    config = {PREFS[k]: prefs[k] for k in PREFS if k in prefs}
    for provider, key in KEYS.items():
        if keys.get(provider):
            config[key] = keys[provider]
    return config


def public(c, user):
    from .assistant import get_setting

    prefs, present = read(c, user)
    return {
        "providers": {k: prefs.get(k, "auto") for k in PREFS},
        "keys": {k: bool(present.get(k) or get_setting(key, "")) for k, key in KEYS.items()},
        "storage": "Stored for your account. Saved keys are encrypted at rest.",
    }


def save(c, user, payload):
    if not isinstance(payload, dict):
        raise ValueError("Invalid provider settings")
    prefs, keys = read(c, user, True)
    incoming = payload.get("providers", {}) or {}
    if not isinstance(incoming, dict):
        raise ValueError("Invalid provider options")
    for name, value in incoming.items():
        if name not in VALID or value not in VALID[name]:
            raise ValueError("Unsupported provider selection")
        prefs[name] = value
    changes = payload.get("keys", {}) or {}
    if not isinstance(changes, dict):
        raise ValueError("Invalid API key input")
    for name, value in changes.items():
        if name not in KEYS:
            raise ValueError("Unsupported API provider")
        key = str(value).strip()
        if len(key) > 512:
            raise ValueError("API key is too long")
        if key:
            keys[name] = key
    removes = payload.get("remove_keys", []) or []
    if not isinstance(removes, list):
        raise ValueError("Invalid remove selection")
    for name in removes:
        if name not in KEYS:
            raise ValueError("Unsupported API provider")
        keys.pop(name, None)
    encrypted = _fernet().encrypt(json.dumps(keys).encode()).decode() if keys else ""
    c.execute(
        """INSERT INTO user_ai_preferences(user_id,preferences,secrets_ciphertext)
      VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET preferences=excluded.preferences,
      secrets_ciphertext=excluded.secrets_ciphertext""",
        (user, json.dumps(prefs), encrypted),
    )
    return public(c, user)
