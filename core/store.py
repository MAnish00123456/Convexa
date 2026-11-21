"""SQLite repository with per-user ownership enforcement and FTS5 indexing."""

from __future__ import annotations
import json
import contextvars
import os
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from . import hosting
from .knowledge import chunks_for_item, keywords, snippet, best_caption_segment

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("CONVEXA_DATA_DIR", ("/tmp/convexa" if hosting.serverless() else ROOT / "data"))).resolve()
DB_FILE = DATA_DIR / "convexa.sqlite3"
_ACTIVE_DB = contextvars.ContextVar("convexa_active_db", default=None)


def flush():
    """Finish the transaction BEFORE sending an HTTP response."""
    current = _ACTIVE_DB.get()
    if current is not None:
        current.commit()


@contextmanager
def db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    hosting.validate()
    if hosting.remote_database():
        from .cloud_db import Connection
        conn = Connection(os.environ["CONVEXA_DATABASE_URL"], os.environ["CONVEXA_DATABASE_AUTH_TOKEN"])
    else:
        conn = sqlite3.connect(DB_FILE, timeout=20)
        conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if isinstance(conn, sqlite3.Connection):
        conn.execute("PRAGMA busy_timeout = 10000")
    token = _ACTIVE_DB.set(conn)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _ACTIVE_DB.reset(token)
        conn.close()


def init_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with db() as c:
        c.executescript("""
            PRAGMA journal_mode = WAL;
            CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL, pw TEXT NOT NULL, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE, csrf TEXT NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS collections(id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,name TEXT NOT NULL,created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS items(
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                kind TEXT NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL DEFAULT '',extracted_text TEXT NOT NULL DEFAULT '',transcript TEXT NOT NULL DEFAULT '',url TEXT NOT NULL DEFAULT '',
                tags TEXT NOT NULL DEFAULT '[]',collection_id TEXT REFERENCES collections(id) ON DELETE SET NULL,
                favorite INTEGER NOT NULL DEFAULT 0,archived INTEGER NOT NULL DEFAULT 0,
                filename TEXT NOT NULL DEFAULT '',filepath TEXT NOT NULL DEFAULT '',mime TEXT NOT NULL DEFAULT '',
                meta TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'searchable',
                created_at INTEGER NOT NULL,updated_at INTEGER NOT NULL);
            CREATE INDEX IF NOT EXISTS ix_items_user ON items(user_id,updated_at);
            CREATE TABLE IF NOT EXISTS chunks(
                id INTEGER PRIMARY KEY AUTOINCREMENT,item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                user_id INTEGER NOT NULL,section TEXT NOT NULL,text TEXT NOT NULL,start_seconds REAL NOT NULL DEFAULT 0,
                embedding TEXT NOT NULL DEFAULT '', embedding_model TEXT NOT NULL DEFAULT '');
            CREATE INDEX IF NOT EXISTS ix_chunks_user ON chunks(user_id,item_id);
            CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, tokenize='porter unicode61');
            CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title TEXT NOT NULL,due_at TEXT NOT NULL,done INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS focus_sessions(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                minutes INTEGER NOT NULL,created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS chats(id TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                question TEXT NOT NULL, answer TEXT NOT NULL, sources TEXT NOT NULL, created_at INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS user_ai_preferences(
                user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                preferences TEXT NOT NULL DEFAULT '{}', secrets_ciphertext TEXT NOT NULL DEFAULT '');
            CREATE TABLE IF NOT EXISTS file_parts(
                item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                part INTEGER NOT NULL, content BLOB NOT NULL,
                PRIMARY KEY(item_id,part));
            CREATE TABLE IF NOT EXISTS auth_attempts(
                bucket TEXT PRIMARY KEY, attempts INTEGER NOT NULL, expires INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS mindmap_nodes(
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                item_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                x REAL NOT NULL, y REAL NOT NULL, PRIMARY KEY(user_id,item_id));
            CREATE TABLE IF NOT EXISTS mindmap_edges(
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                source_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
                UNIQUE(user_id,source_id,target_id));
        """)
        # Seamless migration for databases from previous Convexa editions.
        if "embedding_model" not in {r["name"] for r in c.execute("PRAGMA table_info(chunks)")}:
            c.execute("ALTER TABLE chunks ADD COLUMN embedding_model TEXT NOT NULL DEFAULT ''")


def now():
    return int(time.time())


def new_id():
    return uuid.uuid4().hex


def row_item(row):
    o = dict(row)
    o["tags"] = json.loads(o["tags"] or "[]")
    o["meta"] = json.loads(o["meta"] or "{}")
    o["favorite"] = bool(o["favorite"])
    o["archived"] = bool(o["archived"])
    o["has_file"] = bool(o.pop("filepath", ""))
    return o


def one_item(c, user, id):
    row = c.execute("SELECT * FROM items WHERE id=? AND user_id=?", (id, user)).fetchone()
    return row_item(row) if row else None


def ensure_collection(c, user, collection_id):
    if not collection_id:
        return None
    if c.execute(
        "SELECT 1 FROM collections WHERE id=? AND user_id=?", (collection_id, user)
    ).fetchone():
        return collection_id
    raise ValueError("Collection not found")


def reindex_item(c, item_id):
    r = c.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    if not r:
        return
    fragments = chunks_for_item(
        r["title"], (r["body"] + "\n" + r["extracted_text"]).strip(), r["transcript"], r["kind"]
    )
    # Set-based writes keep remote transactions short even for long documents.
    c.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE item_id=?)", (item_id,))
    c.execute("DELETE FROM chunks WHERE item_id=?", (item_id,))
    c.execute("""INSERT INTO chunks(item_id,user_id,section,text,start_seconds)
        SELECT ?,?,json_extract(value,'$.section'),json_extract(value,'$.text'),json_extract(value,'$.start')
        FROM json_each(?)""", (item_id, r["user_id"], json.dumps(fragments)))
    c.execute("INSERT INTO chunks_fts(rowid,text) SELECT id,text FROM chunks WHERE item_id=?", (item_id,))


def create_item(c, user, body):
    kind = str(body.get("kind", "note"))
    if kind not in ("note", "chat", "youtube", "web", "github", "file", "voice", "code", "image"):
        raise ValueError("Unsupported capture type")
    title = str(body.get("title", "")).strip()[:220] or "Untitled"
    text = str(body.get("body", ""))[:180_000]
    transcript = str(body.get("transcript", ""))[:180_000]
    url = str(body.get("url", "")).strip()[:2048]
    tags = clean_tags(body.get("tags", []))
    collection = ensure_collection(c, user, body.get("collection_id"))
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    meta = {k: v for k, v in meta.items() if k in ("transcript_source", "demo")}
    id = new_id()
    t = now()
    status = "searchable" if title != "Untitled" or text or transcript else "saved_without_text"
    c.execute(
        """INSERT INTO items(id,user_id,kind,title,body,transcript,url,tags,collection_id,favorite,archived,meta,status,created_at,updated_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            id,
            user,
            kind,
            title,
            text,
            transcript,
            url,
            json.dumps(tags),
            collection,
            int(bool(body.get("favorite", False))),
            0,
            json.dumps(meta),
            status,
            t,
            t,
        ),
    )
    reindex_item(c, id)
    return one_item(c, user, id)


def clean_tags(tags):
    if isinstance(tags, str):
        tags = tags.split(",")
    if not isinstance(tags, list):
        return []
    result = []
    for raw in tags[:30]:
        tag = str(raw).strip().lower().lstrip("#")[:40]
        if tag and tag not in result:
            result.append(tag)
    return result


def update_item(c, user, id, body):
    existing = one_item(c, user, id)
    if not existing:
        return None
    values = {}
    for key in ("kind", "title", "body", "transcript", "url"):
        if key in body:
            if key == "kind" and body[key] not in (
                "note",
                "chat",
                "youtube",
                "web",
                "github",
                "file",
                "voice",
                "code",
                "image",
            ):
                raise ValueError("Invalid kind")
            values[key] = str(body[key])[
                : 220 if key == "title" else 180_000 if key in ("body", "transcript") else 2048
            ]
    if "tags" in body:
        values["tags"] = json.dumps(clean_tags(body["tags"]))
    if "collection_id" in body:
        values["collection_id"] = ensure_collection(c, user, body["collection_id"])
    for key in ("favorite", "archived"):
        if key in body:
            values[key] = int(bool(body[key]))
    if not values:
        return existing
    values["updated_at"] = now()
    setters = ",".join(k + "=?" for k in values)
    c.execute(f"UPDATE items SET {setters} WHERE id=? AND user_id=?", (*values.values(), id, user))
    if any(k in values for k in ("title", "body", "transcript", "kind")):
        reindex_item(c, id)
    return one_item(c, user, id)


def remove_item(c, user, id):
    r = c.execute("SELECT filepath FROM items WHERE id=? AND user_id=?", (id, user)).fetchone()
    if not r:
        return None
    c.execute("DELETE FROM chunks_fts WHERE rowid IN (SELECT id FROM chunks WHERE item_id=?)", (id,))
    c.execute("DELETE FROM items WHERE id=? AND user_id=?", (id, user))
    return r["filepath"]


def search(c, user, query="", kind="", collection="", favorites=False, archived=False, limit=60):
    query = str(query).strip()[:300]
    limit = min(100, max(1, int(limit)))
    conditions = ["i.user_id=?", "i.archived=?"]
    args = [user, int(bool(archived))]
    if kind:
        conditions.append("i.kind=?")
        args.append(kind)
    if collection:
        conditions.append("i.collection_id=?")
        args.append(collection)
    if favorites:
        conditions.append("i.favorite=1")
    where = " AND ".join(conditions)
    if not query:
        rows = c.execute(
            f"SELECT i.* FROM items i WHERE {where} ORDER BY updated_at DESC LIMIT ?",
            (*args, limit),
        ).fetchall()
        return [{"item": row_item(r), "match": None, "score": 0} for r in rows], "browse"
    terms = keywords(query)
    if not terms:
        return [], "keyword"
    # Escape tokens as quoted phrases to avoid FTS query injection.
    expression = " OR ".join('"' + term.replace('"', "") + '"' for term in terms)
    hits = c.execute(
        f"""SELECT i.*, ch.text AS match_text,ch.section,ch.start_seconds,
                    bm25(chunks_fts) as fts_rank FROM chunks_fts
                    JOIN chunks ch ON ch.id=chunks_fts.rowid
                    JOIN items i ON ch.item_id=i.id
                    WHERE chunks_fts MATCH ? AND {where}
                    ORDER BY fts_rank ASC LIMIT 450""",
        (expression, *args),
    ).fetchall()
    found = {}
    for r in hits:
        id = r["id"]
        rank = float(r["fts_rank"])
        score = (-rank) + (2.0 if r["section"] == "title" else 0)
        # Rank direct phrase matches above expansion-only matches.
        score += 5.0 if query.lower() in r["match_text"].lower() else 0.0
        if id not in found or score > found[id]["score"]:
            video_moment = (
                best_caption_segment(r["transcript"], query) if r["kind"] == "youtube" else None
            )
            start = video_moment["start"] if video_moment else r["start_seconds"]
            found[id] = {
                "item": row_item(r),
                "score": score,
                "match": {
                    "section": r["section"],
                    "excerpt": snippet(r["match_text"], query),
                    "start_seconds": start,
                    "video_url": (
                        video_timestamp_url(r["url"], start) if r["kind"] == "youtube" else None
                    ),
                },
            }
    # If there are strong literal matches for every query word, suppress noisy
    # OR-expansion matches (e.g. DBMS notes for 'breadth-first search' because
    # both happen to contain 'first'). Retain expansion fallback otherwise.
    from .knowledge import WORDS, STOPWORDS

    primary = [w.lower() for w in WORDS.findall(query) if len(w) > 1 and w.lower() not in STOPWORDS]
    if len(primary) >= 2:
        strong = []
        for h in found.values():
            it = h["item"]
            haystack = " ".join(
                [
                    it.get("title", ""),
                    it.get("body", ""),
                    it.get("extracted_text", ""),
                    it.get("transcript", ""),
                ]
            ).lower()
            tokens = set(w.lower() for w in WORDS.findall(haystack))
            if all(w in tokens for w in primary):
                strong.append(h)
        if strong:
            return (
                sorted(strong, key=lambda h: h["score"], reverse=True)[:limit],
                "keyword match + concept expansion",
            )
    return (
        sorted(found.values(), key=lambda h: h["score"], reverse=True)[:limit],
        "lexical + concept expansion",
    )


def video_timestamp_url(url, seconds):
    if not seconds or not url:
        return None
    from .knowledge import youtube_id

    id = youtube_id(url)
    return f"https://www.youtube.com/watch?v={id}&t={int(seconds)}s" if id else None


def collection_list(c, user):
    rows = c.execute(
        """SELECT co.id,co.name,count(i.id) AS item_count FROM collections co
                     LEFT JOIN items i ON i.collection_id=co.id AND i.archived=0
                     WHERE co.user_id=? GROUP BY co.id ORDER BY co.created_at DESC""",
        (user,),
    ).fetchall()
    return [dict(r) for r in rows]


def list_reminders(c, user):
    return [
        dict(r) | {"done": bool(r["done"])}
        for r in c.execute(
            "SELECT * FROM reminders WHERE user_id=? ORDER BY done ASC,due_at ASC", (user,)
        )
    ]


def list_focus(c, user):
    return [
        dict(r)
        for r in c.execute(
            "SELECT * FROM focus_sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 100",
            (user,),
        )
    ]


def get_chat_history(c, user):
    result = []
    for r in c.execute(
        "SELECT * FROM chats WHERE user_id=? ORDER BY created_at DESC LIMIT 100", (user,)
    ):
        d = dict(r)
        d["sources"] = json.loads(d["sources"])
        result.append(d)
    return list(reversed(result))


def save_file(c, item_id, data):
    c.execute("DELETE FROM file_parts WHERE item_id=?", (item_id,))
    parts = [(item_id, offset // 256_000, data[offset:offset+256_000])
             for offset in range(0, len(data), 256_000)]
    if parts:
        c.execute("INSERT INTO file_parts(item_id,part,content) VALUES " + ','.join('(?,?,?)' for _ in parts),
                  tuple(value for part in parts for value in part))


def load_file(c, item_id):
    rows = c.execute("SELECT content FROM file_parts WHERE item_id=? ORDER BY part", (item_id,)).fetchall()
    if not rows:
        raise FileNotFoundError
    return b"".join(r["content"] for r in rows)
