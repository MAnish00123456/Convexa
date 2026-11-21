"""Hosting configuration; refuse ephemeral storage on Vercel."""
import os
from urllib.parse import urlsplit
from .config import load_env

load_env()


def serverless():
    return os.environ.get('VERCEL') == '1'


def remote_database():
    return bool(os.environ.get('CONVEXA_DATABASE_URL'))


def validate():
    url = os.environ.get('CONVEXA_DATABASE_URL', '')
    if serverless() and not url:
        raise RuntimeError('Set CONVEXA_DATABASE_URL to a persistent libSQL database before deploying.')
    if url:
        parsed = urlsplit(url)
        if parsed.scheme not in ('libsql', 'https') or not parsed.hostname or parsed.username or parsed.password:
            raise RuntimeError('CONVEXA_DATABASE_URL must be a libsql:// or https:// database URL.')
        if not os.environ.get('CONVEXA_DATABASE_AUTH_TOKEN'):
            raise RuntimeError('Set CONVEXA_DATABASE_AUTH_TOKEN.')
    if serverless() or url:
        from cryptography.fernet import Fernet
        key = os.environ.get('CONVEXA_SECRET_KEY', '')
        try:
            Fernet(key.encode())
        except Exception:
            raise RuntimeError('Set a stable CONVEXA_SECRET_KEY generated with Fernet.generate_key().') from None


def upload_limit():
    # Leave headroom below Vercel's 4.5 MB request AND response limit.
    return 4_000_000 if serverless() or remote_database() else 40 * 1024 * 1024
