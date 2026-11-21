#!/usr/bin/env python3
"""Convexa self-hosted single-machine knowledge platform.

Run: python app.py     (Python 3.10+, no paid API, no mandatory pip packages)
Data lives in ./data; bind to loopback by default for user privacy.
"""

from __future__ import annotations
from datetime import datetime
import hashlib
import http.cookies
import json
import mimetypes
import contextvars
import math
import os
from pathlib import Path
import re
import secrets
import sys
import threading
import time
import traceback
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from core import store, knowledge, assistant, user_settings, hosting

ROOT = Path(__file__).resolve().parent
WEB = ROOT / "web"
CHUNK = 64 * 1024
MAX_JSON = 2_500_000
MAX_UPLOAD = hosting.upload_limit()
LOCAL_HOSTS = ("127.0.0.1", "localhost", "[::1]")


def pw_hash(password: str):
    salt = secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"{salt.hex()}:{key.hex()}"


def pw_verify(password, stored):
    try:
        salt, expected = stored.split(":", 1)
        got = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=2**14, r=8, p=1)
        return secrets.compare_digest(got, bytes.fromhex(expected))
    except (ValueError, TypeError):
        return False


def worker(item_id, kind, url="", path=""):
    """Non-blocking best-effort import; never invent absent content."""
    try:
        if kind == "youtube":
            transcript, error = knowledge.fetch_youtube_captions(knowledge.youtube_id(url) or "")
        elif kind in ("web", "github"):
            transcript, error = knowledge.fetch_public_web_text(url)
        elif kind == "voice":
            transcript, error = assistant.transcribe_audio(Path(path))
        else:
            return
    except Exception:
        transcript, error = "", "Source import failed. Retry or add the text manually."
    try:
        with store.db() as c:
            row = c.execute(
                "SELECT transcript,body,meta FROM items WHERE id=?", (item_id,)
            ).fetchone()
            if not row:
                return
            meta = json.loads(row["meta"] or "{}")
            if (kind in ("youtube", "voice") and row["transcript"].strip()) or (
                kind in ("web", "github") and row["body"].strip()
            ):
                return  # Never overwrite user-supplied content.
            if transcript:
                field = "body" if kind in ("web", "github") else "transcript"
                meta["transcript_source"] = (
                    "published_youtube_captions"
                    if kind == "youtube"
                    else (
                        (assistant.voice_provider() or "manual")
                        if kind == "voice"
                        else "website_extraction"
                    )
                )
                meta.pop("processing_error", None)
                c.execute(
                    f"UPDATE items SET {field}=?,meta=?,status=?,updated_at=? WHERE id=?",
                    (transcript, json.dumps(meta), "searchable", store.now(), item_id),
                )
                store.reindex_item(c, item_id)
            else:
                meta["processing_error"] = error
                c.execute(
                    "UPDATE items SET meta=?,status=?,updated_at=? WHERE id=?",
                    (
                        json.dumps(meta),
                        "metadata_only" if kind != "voice" else "audio_saved_no_transcript",
                        store.now(),
                        item_id,
                    ),
                )
    except Exception as ex:
        print("Ingestion worker:", type(ex).__name__, file=sys.stderr)


def schedule_worker(item_id, kind, url="", path=""):
    store.flush()
    if hosting.serverless() or hosting.remote_database():
        # Work must finish before responding; serverless background threads may freeze.
        if kind == "voice" and (not path or not Path(path).is_file()):
            with store.db() as c:
                row = c.execute("SELECT filename FROM items WHERE id=?", (item_id,)).fetchone()
                data = store.load_file(c, item_id)
            with tempfile.TemporaryDirectory(prefix="convexa-voice-") as tmp:
                audio = Path(tmp) / ("audio" + Path(row["filename"]).suffix)
                audio.write_bytes(data)
                worker(item_id, kind, url, str(audio))
        else:
            worker(item_id, kind, url, path)
        return
    context = contextvars.copy_context()
    threading.Thread(
        target=lambda: context.run(worker, item_id, kind, url, path),
        daemon=True,
        name="ingest-" + item_id[:8],
    ).start()


class Handler(BaseHTTPRequestHandler):
    server_version = "Convexa/2.0"
    sys_version = ""

    def log_message(self, fmt, *args):
        print("%s %s" % (self.log_date_time_string(), fmt % args), file=sys.stderr)

    def _headers(
        self,
        status=200,
        content_type="application/json; charset=utf-8",
        length=None,
        cookie=None,
        additional=None,
    ):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header(
            "Cache-Control",
            "no-store" if content_type.startswith("application/json") else "private, max-age=120",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://i.ytimg.com; media-src 'self' blob:; connect-src 'self'; frame-src https://www.youtube.com; object-src 'none'; base-uri 'self'; form-action 'self'",
        )
        if cookie:
            self.send_header("Set-Cookie", cookie)
        for k, v in (additional or {}).items():
            self.send_header(k, str(v))
        self.end_headers()

    def send_json(self, payload, status=200, cookie=None):
        store.flush()
        blob = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self._headers(status, length=len(blob), cookie=cookie)
        self.wfile.write(blob)

    def error(self, message, status=400):
        self.send_json({"error": str(message)}, status)

    def _path(self):
        p = urlsplit(self.path)
        params = {k: v[0] for k, v in parse_qs(p.query).items() if v}

        original = params.pop("__convexa_route", None)
        path = p.path

        if path in ("/api/index", "/api/index.py") and original and original.startswith("/"):
            path = original

        return path, params

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > MAX_JSON:
            raise ValueError("Request too large")
        if length and "application/json" not in self.headers.get("Content-Type", ""):
            raise ValueError("JSON Content-Type required")
        raw = self.rfile.read(length)
        value = json.loads(raw) if raw else {}
        if not isinstance(value, dict):
            raise ValueError("Expected JSON object")
        return value

    def _session(self, c):
        try:
            ck = http.cookies.SimpleCookie()
            ck.load(self.headers.get("Cookie", ""))
            token = ck.get("convexa_session")
            if not token:
                return None
            digest = hashlib.sha256(token.value.encode()).hexdigest()
            return c.execute(
                """SELECT s.user_id,s.csrf,u.email FROM sessions s
              JOIN users u ON u.id=s.user_id WHERE s.token_hash=? AND s.expires>?""",
                (digest, store.now()),
            ).fetchone()
        except Exception:
            return None

    def _current(self, c):
        row = self._session(c)
        if not row:
            raise PermissionError("Please sign in to continue")
        if self.command not in ("GET", "HEAD"):
            if self.headers.get("X-CSRF-Token", "") != row["csrf"]:
                raise PermissionError("Invalid CSRF token; refresh the page and retry")
        assistant.set_user_settings(user_settings.effective(c, row["user_id"]))
        return row["user_id"]

    def _cookie(self, token, maxage):
        secure = "; Secure" if hosting.serverless() or self.headers.get("X-Forwarded-Proto", "") == "https" else ""
        return f"convexa_session={token}; HttpOnly; Path=/; SameSite=Lax; Max-Age={maxage}{secure}"

    def _auth_action(self, login=False):
        body = self._read_json()
        email = str(body.get("email", "")).strip().lower()
        password = str(body.get("password", ""))
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email) or len(email) > 180:
            raise ValueError("Enter a valid email")
        if len(password) < 8 or len(password) > 256:
            raise ValueError("Password must have 8–256 characters")
        if hosting.serverless() or hosting.remote_database():
            bucket = hashlib.sha256((email + ":auth").encode()).hexdigest()
            with store.db() as c:
                c.execute("DELETE FROM auth_attempts WHERE expires<?", (store.now(),))
                c.execute("INSERT INTO auth_attempts(bucket,attempts,expires) VALUES(?,?,?) ON CONFLICT(bucket) DO UPDATE SET attempts=attempts+1",
                          (bucket, 1, store.now() + 900))
                count = c.execute("SELECT attempts FROM auth_attempts WHERE bucket=?", (bucket,)).fetchone()[0]
            if count > 20:
                return self.error("Too many sign-in attempts. Try again in 15 minutes.", 429)
            if not login:
                invite = os.environ.get("CONVEXA_INVITE_CODE", "")
                if invite and not secrets.compare_digest(str(body.get("invite_code", "")), invite):
                    raise PermissionError("A valid invitation code is required")
        with store.db() as c:
            existing = c.execute("SELECT id,pw FROM users WHERE email=?", (email,)).fetchone()
            if login:
                if not existing or not pw_verify(password, existing["pw"]):
                    raise PermissionError("Invalid email or password")
                user = existing["id"]
            else:
                if existing:
                    raise ValueError("This account already exists")
                cur = c.execute(
                    "INSERT INTO users(email,pw,created_at) VALUES(?,?,?)",
                    (email, pw_hash(password), store.now()),
                )
                user = cur.lastrowid
            token = secrets.token_urlsafe(40)
            csrf = secrets.token_urlsafe(24)
            c.execute(
                "INSERT INTO sessions(token_hash,user_id,csrf,expires) VALUES(?,?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user, csrf, store.now() + 30 * 86400),
            )
        self.send_json(
            {"user": {"id": user, "email": email}, "csrf": csrf},
            cookie=self._cookie(token, 30 * 86400),
        )

    def do_GET(self):
        try:
            self._route_get()
        except Exception as ex:
            self._failure(ex)

    def do_POST(self):
        try:
            self._route_post()
        except Exception as ex:
            self._failure(ex)

    def do_PATCH(self):
        try:
            self._route_patch()
        except Exception as ex:
            self._failure(ex)

    def do_PUT(self):
        try:
            self._route_put()
        except Exception as ex:
            self._failure(ex)

    def do_DELETE(self):
        try:
            self._route_delete()
        except Exception as ex:
            self._failure(ex)

    def _failure(self, ex):
        if isinstance(ex, PermissionError):
            self.error(str(ex), 401 if "sign in" in str(ex).lower() else 403)
        elif isinstance(ex, (ValueError, json.JSONDecodeError)):
            self.error(str(ex), 400)
        elif isinstance(ex, FileNotFoundError):
            self.error("Not found", 404)
        else:
            print("Unexpected Convexa server error:", repr(ex), file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            self.error("Internal error (see server logs)", 500)

    def _static(self, path):
        mapping = {
            "/": "index.html",
            "/app": "index.html",
            "/login": "index.html",
            "/why-convexa": "index.html",
            "/styles.css": "styles.css",
            "/samples.js": "samples.js",
            "/main.js": "main.js",
            "/enhancements.js": "enhancements.js",
            "/enhancements.css": "enhancements.css",
            "/favicon.svg": "favicon.svg",
        }
        filename = mapping.get(path)
        if not filename:
            self.error("Not found", 404)
            return
        file = WEB / filename
        data = file.read_bytes()
        content_type = {
            "html": "text/html; charset=utf-8",
            "css": "text/css; charset=utf-8",
            "js": "text/javascript; charset=utf-8",
            "svg": "image/svg+xml",
        }.get(file.suffix[1:], "application/octet-stream")
        self._headers(200, content_type, len(data))
        self.wfile.write(data)

    def _route_get(self):
        path, p = self._path()
        if not path.startswith("/api/"):
            return self._static(path)
        if path == "/api/health":
            with store.db() as c:
                c.execute("SELECT count(*) FROM users").fetchone()
            return self.send_json({"status": "ok", "product": "Convexa", "storage": "cloud" if hosting.remote_database() else "local", "max_upload_bytes": MAX_UPLOAD})
        with store.db() as c:
            user = self._current(c)
            if path == "/api/ai/settings":
                return self.send_json({"settings": user_settings.public(c, user)})
            if path == "/api/mindmap":
                nodes = [
                    dict(r)
                    for r in c.execute(
                        "SELECT item_id,x,y FROM mindmap_nodes WHERE user_id=?", (user,)
                    )
                ]
                edges = [
                    dict(r)
                    for r in c.execute(
                        "SELECT id,source_id,target_id FROM mindmap_edges WHERE user_id=?", (user,)
                    )
                ]
                return self.send_json({"nodes": nodes, "edges": edges})
            if path == "/api/me":
                ses = self._session(c)
                return self.send_json(
                    {"user": {"id": user, "email": ses["email"]}, "csrf": ses["csrf"]}
                )
            if path == "/api/capabilities":
                from importlib.util import find_spec

                return self.send_json(
                    {
                        "max_upload_bytes": MAX_UPLOAD,
                        "storage": "cloud" if hosting.remote_database() else "local",
                        "youtube_captions": find_spec("youtube_transcript_api") is not None,
                        "pdf": find_spec("pypdf") is not None,
                        "voice_auto": assistant.voice_provider() is not None,
                        "ollama": (
                            assistant.available_models()
                            if os.environ.get("CONVEXA_AI_PROVIDER") == "ollama"
                            or os.environ.get("CONVEXA_EMBEDDING_PROVIDER") == "ollama"
                            else {"online": False, "chat": False, "embeddings": False}
                        ),
                        "ai": assistant.provider_info(),
                        "no_paid_api": not assistant.provider_info()["openai_usage_may_be_billed"],
                        "vector_chunks": c.execute(
                            "SELECT count(*) FROM chunks WHERE user_id=? AND embedding!=?",
                            (user, ""),
                        ).fetchone()[0],
                        "total_chunks": c.execute(
                            "SELECT count(*) FROM chunks WHERE user_id=?", (user,)
                        ).fetchone()[0],
                    }
                )
            if path == "/api/items":
                rows, mode = store.search(
                    c,
                    user,
                    p.get("q", ""),
                    p.get("kind", ""),
                    p.get("collection", ""),
                    p.get("favorites") == "1",
                    p.get("archived") == "1",
                )
                if p.get("q") and p.get("semantic") == "1":
                    rows, mode = assistant.hybrid_search(c, user, p["q"], rows, limit=60)
                if hosting.serverless() or hosting.remote_database():
                    for hit in rows:
                        for field in ("body", "extracted_text", "transcript"):
                            hit["item"][field] = hit["item"][field][:1000]
                return self.send_json({"results": rows, "mode": mode, "count": len(rows)})
            if path == "/api/collections":
                return self.send_json({"collections": store.collection_list(c, user)})
            if path == "/api/reminders":
                return self.send_json({"reminders": store.list_reminders(c, user)})
            if path == "/api/focus":
                return self.send_json({"sessions": store.list_focus(c, user)})
            if path == "/api/chat/history":
                return self.send_json({"messages": store.get_chat_history(c, user)})
            if path.startswith("/api/items/"):
                segment = path.split("/")
                id = segment[3]
                row = c.execute(
                    "SELECT * FROM items WHERE id=? AND user_id=?", (id, user)
                ).fetchone()
                if not row:
                    raise FileNotFoundError
                if len(segment) == 5 and segment[4] == "file":
                    return self._download(row)
                if len(segment) == 4:
                    return self.send_json({"item": store.row_item(row)})
        self.error("Not found", 404)

    def _route_post(self):
        path, p = self._path()
        if path == "/api/register":
            return self._auth_action(login=False)
        if path == "/api/login":
            return self._auth_action(login=True)
        with store.db() as c:
            user = self._current(c)
            if path == "/api/logout":
                ck = http.cookies.SimpleCookie()
                ck.load(self.headers.get("Cookie", ""))
                token = ck.get("convexa_session")
                if token:
                    c.execute(
                        "DELETE FROM sessions WHERE token_hash=?",
                        (hashlib.sha256(token.value.encode()).hexdigest(),),
                    )
                return self.send_json({"ok": True}, cookie=self._cookie("", 0))
            body = self._read_json()
            if path == "/api/ai/settings":
                saved = user_settings.save(c, user, body)
                assistant.set_user_settings(user_settings.effective(c, user))
                return self.send_json({"settings": saved, "ai": assistant.provider_info()})
            if path == "/api/mindmap/edge":
                source = str(body.get("source", ""))
                target = str(body.get("target", ""))
                if not source or not target or source == target:
                    raise ValueError("Select two different knowledge items")
                count = c.execute(
                    "SELECT COUNT(DISTINCT id) FROM items WHERE user_id=? AND archived=0 AND id IN (?,?)",
                    (user, source, target),
                ).fetchone()[0]
                if count != 2:
                    raise ValueError("Knowledge item not found")
                exists = c.execute(
                    "SELECT id FROM mindmap_edges WHERE user_id=? AND ((source_id=? AND target_id=?) OR (source_id=? AND target_id=?))",
                    (user, source, target, target, source),
                ).fetchone()
                if exists:
                    raise ValueError("These items are already connected")
                edge_id = store.new_id()
                c.execute(
                    "INSERT INTO mindmap_edges(id,user_id,source_id,target_id) VALUES(?,?,?,?)",
                    (edge_id, user, source, target),
                )
                return self.send_json(
                    {"edge": {"id": edge_id, "source_id": source, "target_id": target}}, 201
                )
            if path == "/api/items":
                item = store.create_item(c, user, body)
                if item["kind"] == "youtube":
                    if not knowledge.youtube_id(item["url"]):
                        raise ValueError("Enter a valid YouTube video URL")
                    if not item["transcript"].strip():
                        c.execute(
                            "UPDATE items SET status=? WHERE id=?",
                            ("fetching_captions", item["id"]),
                        )
                        item["status"] = "fetching_captions"
                        store.flush()
                        schedule_worker(item["id"], "youtube", item["url"])
                elif (
                    item["kind"] in ("web", "github")
                    and item["url"].strip()
                    and not item["body"].strip()
                ):
                    knowledge.validate_url_syntax(item["url"])
                    c.execute(
                        "UPDATE items SET status=? WHERE id=?", ("fetching_webpage", item["id"])
                    )
                    item["status"] = "fetching_webpage"
                    store.flush()
                    schedule_worker(item["id"], item["kind"], item["url"])
                return self.send_json({"item": item}, 201)
            if path == "/api/collections":
                name = str(body.get("name", "")).strip()[:90]
                if not name:
                    raise ValueError("Collection name is required")
                id = store.new_id()
                c.execute(
                    "INSERT INTO collections(id,user_id,name,created_at) VALUES(?,?,?,?)",
                    (id, user, name, store.now()),
                )
                return self.send_json(
                    {"collection": {"id": id, "name": name, "item_count": 0}}, 201
                )
            if path == "/api/reminders":
                title = str(body.get("title", "")).strip()[:220]
                due = str(body.get("due_at", ""))
                if not title:
                    raise ValueError("Reminder title is required")
                try:
                    datetime.fromisoformat(due.replace("Z", "+00:00"))
                except ValueError:
                    raise ValueError("Invalid due date")
                id = store.new_id()
                c.execute(
                    "INSERT INTO reminders(id,user_id,title,due_at,created_at) VALUES(?,?,?,?,?)",
                    (id, user, title, due, store.now()),
                )
                return self.send_json(
                    {"reminder": {"id": id, "title": title, "due_at": due, "done": False}}, 201
                )
            if path == "/api/focus":
                minutes = int(body.get("minutes", 0))
                if minutes < 1 or minutes > 240:
                    raise ValueError("Minutes must be between 1 and 240")
                id = store.new_id()
                c.execute(
                    "INSERT INTO focus_sessions(id,user_id,minutes,created_at) VALUES(?,?,?,?)",
                    (id, user, minutes, store.now()),
                )
                return self.send_json({"id": id, "minutes": minutes}, 201)
            if path == "/api/ai/test":
                return self.send_json(
                    {
                        "results": assistant.connection_test(),
                        "note": "Diagnostic uses only synthetic text; provider quota or charges may apply.",
                    }
                )
            if path == "/api/ask":
                question = str(body.get("question", "")).strip()[:700]
                if not question:
                    raise ValueError("Question is required")
                hits, _ = store.search(c, user, question, limit=12)
                hits, mode = assistant.hybrid_search(c, user, question, hits, limit=12)
                store.flush()
                result = assistant.answer(question, hits)
                result["search_mode"] = mode
                c.execute(
                    "INSERT INTO chats(id,user_id,question,answer,sources,created_at) VALUES(?,?,?,?,?,?)",
                    (
                        store.new_id(),
                        user,
                        question,
                        result["answer"],
                        json.dumps(result["sources"]),
                        store.now(),
                    ),
                )
                return self.send_json(result)
            if path == "/api/semantic/reindex":
                if not assistant.embedding_provider():
                    raise ValueError(
                        "Connect Gemini embeddings in Convexa Settings before indexing"
                    )
                provider = assistant.embedding_provider()
                model_tag = provider + ":" + assistant.model_for(provider, "embedding")
                records = c.execute(
                    "SELECT id,text FROM chunks WHERE user_id=? AND (embedding='' OR embedding_model!=?) ORDER BY id LIMIT 10", (user, model_tag)
                ).fetchall()
                if len(records) > 2500:
                    raise ValueError(
                        "Please reduce the index to 2,500 chunks for this local edition"
                    )
                store.flush()
                done = 0
                for offset in range(0, len(records), 10):
                    batch = records[offset : offset + 10]
                    try:
                        vectors = assistant.embed([r["text"] for r in batch])
                    except Exception as e:
                        raise ValueError(
                            "Embedding provider unavailable or over quota. Check your provider settings, usage limit and connection."
                        ) from None
                    for r, vec in zip(batch, vectors):
                        c.execute(
                            "UPDATE chunks SET embedding=?,embedding_model=? WHERE id=?",
                            (json.dumps(vec), model_tag, r["id"]),
                        )
                    done += len(batch)
                return self.send_json(
                    {
                        "indexed_chunks": done,
                        "remaining": c.execute("SELECT count(*) FROM chunks WHERE user_id=? AND (embedding='' OR embedding_model!=?)", (user, model_tag)).fetchone()[0],
                        "model": assistant.model_for(assistant.embedding_provider(), "embedding"),
                    }
                )
            if path.startswith("/api/items/") and path.endswith("/refresh"):
                id = path.split("/")[3]
                item = store.one_item(c, user, id)
                if not item:
                    raise FileNotFoundError
                if item["kind"] not in ("youtube", "web", "github", "voice"):
                    raise ValueError("This source does not support automatic refresh")
                c.execute("UPDATE items SET status=? WHERE id=?", ("processing", id))
                file_row = c.execute("SELECT filepath FROM items WHERE id=? AND user_id=?", (id, user)).fetchone()
                store.flush()
                schedule_worker(id, item["kind"], item["url"], str(store.DATA_DIR / file_row["filepath"]) if file_row["filepath"] and not file_row["filepath"].startswith("db:") else "")
                return self.send_json({"status": "processing"})
        self.error("Not found", 404)

    def _route_patch(self):
        path, p = self._path()
        with store.db() as c:
            user = self._current(c)
            body = self._read_json()
            if path.startswith("/api/mindmap/nodes/"):
                item_id = path.split("/")[-1]
                if not store.one_item(c, user, item_id):
                    raise FileNotFoundError
                x = float(body.get("x"))
                y = float(body.get("y"))
                if not math.isfinite(x) or not math.isfinite(y) or abs(x) > 10000 or abs(y) > 10000:
                    raise ValueError("Invalid map coordinates")
                c.execute(
                    "INSERT INTO mindmap_nodes(user_id,item_id,x,y) VALUES(?,?,?,?) ON CONFLICT(user_id,item_id) DO UPDATE SET x=excluded.x,y=excluded.y",
                    (user, item_id, x, y),
                )
                return self.send_json({"ok": True})
            if path.startswith("/api/items/"):
                id = path.split("/")[3]
                previous = store.one_item(c, user, id)
                if previous and previous["kind"] == "youtube" and "url" in body:
                    if not knowledge.youtube_id(body["url"]):
                        raise ValueError("Enter a valid YouTube URL")
                    if (
                        body["url"] != previous["url"]
                        and body.get("transcript", previous["transcript"]) == previous["transcript"]
                    ):
                        # Never retain captions tied to a different video by accident.
                        body["transcript"] = ""
                item = store.update_item(c, user, id, body)
                if not item:
                    raise FileNotFoundError
                if "transcript" in body and item["kind"] in ("youtube", "voice"):
                    populated = bool(item["transcript"].strip())
                    status = (
                        "searchable"
                        if populated
                        else (
                            "metadata_only"
                            if item["kind"] == "youtube"
                            else "audio_saved_no_transcript"
                        )
                    )
                    meta = item["meta"]
                    if populated:
                        meta.update({"transcript_source": "manual", "processing_error": None})
                    else:
                        meta.pop("transcript_source", None)
                    c.execute(
                        "UPDATE items SET status=?,meta=? WHERE id=?",
                        (status, json.dumps(meta), id),
                    )
                    item["status"] = status
                    item["meta"] = meta
                if (
                    previous
                    and item["kind"] == "youtube"
                    and item["url"] != previous["url"]
                    and not item["transcript"].strip()
                ):
                    c.execute("UPDATE items SET status=? WHERE id=?", ("fetching_captions", id))
                    item["status"] = "fetching_captions"
                    store.flush()
                    schedule_worker(id, "youtube", item["url"])
                return self.send_json({"item": item})
            if path.startswith("/api/reminders/"):
                id = path.split("/")[3]
                existing = c.execute(
                    "SELECT 1 FROM reminders WHERE id=? AND user_id=?", (id, user)
                ).fetchone()
                if not existing:
                    raise FileNotFoundError
                if "done" in body:
                    c.execute(
                        "UPDATE reminders SET done=? WHERE id=?", (int(bool(body["done"])), id)
                    )
                return self.send_json({"ok": True})
            if path.startswith("/api/collections/"):
                id = path.split("/")[3]
                name = str(body.get("name", "")).strip()[:90]
                if not name:
                    raise ValueError("Name required")
                cur = c.execute(
                    "UPDATE collections SET name=? WHERE id=? AND user_id=?", (name, id, user)
                )
                if not cur.rowcount:
                    raise FileNotFoundError
                return self.send_json({"ok": True})
        self.error("Not found", 404)

    def _route_delete(self):
        path, p = self._path()
        with store.db() as c:
            user = self._current(c)
            if path.startswith("/api/mindmap/edges/"):
                edge_id = path.split("/")[-1]
                cur = c.execute(
                    "DELETE FROM mindmap_edges WHERE id=? AND user_id=?", (edge_id, user)
                )
                if not cur.rowcount:
                    raise FileNotFoundError
                return self.send_json({"deleted": True})
            if path == "/api/mindmap/layout":
                c.execute("DELETE FROM mindmap_nodes WHERE user_id=?", (user,))
                return self.send_json({"ok": True})
            if path.startswith("/api/items/"):
                id = path.split("/")[3]
                old = store.remove_item(c, user, id)
                if old is None:
                    raise FileNotFoundError
                if old:
                    try:
                        (store.DATA_DIR / old).unlink(missing_ok=True)
                    except OSError:
                        pass
                return self.send_json({"deleted": True})
            if path.startswith("/api/collections/"):
                cur = c.execute(
                    "DELETE FROM collections WHERE id=? AND user_id=?", (path.split("/")[3], user)
                )
                if not cur.rowcount:
                    raise FileNotFoundError
                return self.send_json({"deleted": True})
            if path.startswith("/api/reminders/"):
                cur = c.execute(
                    "DELETE FROM reminders WHERE id=? AND user_id=?", (path.split("/")[3], user)
                )
                if not cur.rowcount:
                    raise FileNotFoundError
                return self.send_json({"deleted": True})
        self.error("Not found", 404)

    def _route_put(self):
        path, p = self._path()
        if not (path.startswith("/api/items/") and path.endswith("/file")):
            return self.error("Not found", 404)
        filename = p.get("filename", "").strip().replace("\\", "/").split("/")[-1][:180]
        ext = Path(filename).suffix.lower()
        if ext not in knowledge.ALLOWED_EXTENSIONS:
            raise ValueError("Unsupported upload format")
        length = int(self.headers.get("Content-Length", "0"))
        if length < 1 or length > MAX_UPLOAD:
            raise ValueError(f"File must be 1 byte to {MAX_UPLOAD / 1_000_000:g} MB")
        with store.db() as c:
            user = self._current(c)
            id = path.split("/")[3]
            item = store.one_item(c, user, id)
            if not item:
                raise FileNotFoundError
            upload = store.DATA_DIR / "uploads"
            upload.mkdir(parents=True, exist_ok=True)
            rel = Path("uploads") / (secrets.token_hex(22) + ext)
            location = store.DATA_DIR / rel
            replaced_row = c.execute(
                "SELECT filepath FROM items WHERE id=? AND user_id=?", (id, user)
            ).fetchone()
            replaced_path = replaced_row["filepath"] if replaced_row else ""
            remaining = length
            try:
                with location.open("wb") as f:
                    while remaining:
                        chunk = self.rfile.read(min(CHUNK, remaining))
                        if not chunk:
                            raise ValueError("Incomplete upload")
                        f.write(chunk)
                        remaining -= len(chunk)
                text, error = knowledge.extract_file(location, filename)
                status = (
                    "searchable"
                    if text.strip() or item["transcript"].strip()
                    else "file_saved_no_text"
                )
                body = item["body"]
                kind = (
                    "voice"
                    if ext in knowledge.AUDIO_EXTENSIONS
                    else "image" if ext in knowledge.IMAGE_EXTENSIONS else "file"
                )
                mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
                meta = item["meta"]
                if error:
                    meta["processing_error"] = error
                else:
                    meta.pop("processing_error", None)
                c.execute(
                    """UPDATE items SET kind=?,body=?,extracted_text=?,filename=?,filepath=?,mime=?,status=?,meta=?,updated_at=?
                             WHERE id=? AND user_id=?""",
                    (
                        kind,
                        body,
                        text,
                        filename,
                        str(rel),
                        mime,
                        status,
                        json.dumps(meta),
                        store.now(),
                        id,
                        user,
                    ),
                )
                if hosting.remote_database() or hosting.serverless():
                    store.save_file(c, id, location.read_bytes())
                    c.execute("UPDATE items SET filepath=? WHERE id=?", ("db:" + id, id))
                store.reindex_item(c, id)
                if kind == "voice" and not item["transcript"]:
                    c.execute("UPDATE items SET status=? WHERE id=?", ("transcription_pending", id))
                    store.flush()
                    schedule_worker(id, "voice", path=str(location))
                response = {"item": store.one_item(c, user, id), "extracted_chars": len(text)}
                store.flush()
                if replaced_path and replaced_path != str(rel):
                    old = (store.DATA_DIR / replaced_path).resolve()
                    if old.is_relative_to((store.DATA_DIR / "uploads").resolve()):
                        old.unlink(missing_ok=True)
                return self.send_json(response, 201)
            except Exception:
                location.unlink(missing_ok=True)
                raise
            finally:
                if hosting.remote_database() or hosting.serverless():
                    location.unlink(missing_ok=True)

    def _download(self, row):
        if row["filepath"].startswith("db:"):
            # Authorization was checked by the caller before any blob is read.
            with store.db() as c:
                data = store.load_file(c, row["id"])
            size = len(data)
            start, end = 0, size - 1
            partial = False
            requested = self.headers.get("Range", "")
            if requested:
                match = re.fullmatch(r"bytes=(\d+)-(\d*)", requested)
                if not match:
                    return self._headers(416, length=0, additional={"Content-Range": f"bytes */{size}"})
                start = int(match[1])
                end = min(size - 1, int(match[2])) if match[2] else size - 1
                if start > end or start >= size:
                    return self._headers(416, length=0, additional={"Content-Range": f"bytes */{size}"})
                partial = True
            headers = {"Cache-Control": "no-store", "Accept-Ranges": "bytes",
                       "Content-Disposition": ("inline" if row["kind"] in ("voice", "image") else "attachment") + '; filename="' + re.sub(r"[^A-Za-z0-9._-]", "_", row["filename"]) + '"'}
            if partial:
                headers["Content-Range"] = f"bytes {start}-{end}/{size}"
            self._headers(206 if partial else 200, row["mime"] or "application/octet-stream", end-start+1, additional=headers)
            self.wfile.write(data[start:end+1])
            return
        rel = row["filepath"]
        if not rel:
            raise FileNotFoundError
        file = (store.DATA_DIR / rel).resolve()
        if not file.is_relative_to((store.DATA_DIR / "uploads").resolve()) or not file.is_file():
            raise FileNotFoundError
        size = file.stat().st_size
        mime = row["mime"] or "application/octet-stream"
        is_media = row["kind"] in ("voice", "image")
        range_value = self.headers.get("Range", "")
        start, end = 0, size - 1
        if range_value.startswith("bytes="):
            m = re.fullmatch(r"bytes=(\d+)-(\d*)", range_value)
            if m:
                start = int(m.group(1))
                end = min(size - 1, int(m.group(2))) if m.group(2) else size - 1
                if start > end or start >= size:
                    self._headers(416, additional={"Content-Range": f"bytes */{size}"})
                    return
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Disposition": ("inline" if is_media else "attachment")
            + '; filename="'
            + re.sub(r"[^A-Za-z0-9._-]", "_", row["filename"])
            + '"',
        }
        if start != 0 or end != size - 1:
            headers["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(
            206 if "Content-Range" in headers else 200, mime, end - start + 1, additional=headers
        )
        with file.open("rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(CHUNK, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except BrokenPipeError:
                    break
                remaining -= len(chunk)


def serve(port=8765, host="127.0.0.1"):
    store.init_db()

    class Server(ThreadingHTTPServer):
        daemon_threads = True

    with Server((host, port), Handler) as server:
        print(
            f"Convexa running at http://{host}:{port} — private SQLite data in {store.DATA_DIR}",
            flush=True,
        )
        print(
            "Press Ctrl+C to stop. Cloud AI is optional; local storage and offline search remain available.",
            flush=True,
        )
        try:
            server.serve_forever(poll_interval=0.2)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.environ.get("CONVEXA_PORT", "8765")))
    parser.add_argument("--host", default=os.environ.get("CONVEXA_HOST", "127.0.0.1"))
    args = parser.parse_args()
    serve(args.port, args.host)
