"""Validate hosted configuration and actual database connectivity before deployment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import hosting, store

try:
    if not hosting.remote_database():
        raise RuntimeError('Set cloud database variables in .env first; see DEPLOYMENT.md.')
    hosting.validate()
    store.init_db()
    with store.db() as c:
        c.execute("SELECT count(*) FROM users").fetchone()
        c.execute("SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 1", ('"preflight"',)).fetchall()
    print('PASS: configuration, database connection, schema and FTS5 queries.')
except Exception as error:
    print('FAIL:', type(error).__name__, '- check configuration, database engine, credentials and connectivity.')
    sys.exit(1)
