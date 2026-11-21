"""Full HTTP integration tests, with a real SQLite server and no third-party packages."""

import http.cookiejar
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


class BrowserClient:
    def __init__(self, url):
        self.url = url
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def call(self, path, method="GET", body=None, raw=None, filename=None, csrf=True):
        headers = {}
        if csrf and method not in ("GET", "HEAD") and self.csrf:
            headers["X-CSRF-Token"] = self.csrf
        if raw is not None:
            data = raw
            headers["Content-Type"] = "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            data = None
        request = urllib.request.Request(self.url + path, method=method, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=35) as resp:
                result = resp.read()
                if "/file" in path and method == "GET":
                    return resp.status, result
                if resp.headers.get_content_type() == "application/json":
                    return resp.status, json.loads(result)
                return resp.status, result
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def register(self, email=None):
        r = self.call(
            "/api/register",
            "POST",
            {
                "email": email or f"test-{uuid.uuid4().hex}@example.org",
                "password": "testPassword123!",
            },
        )
        assert r[0] == 200, r
        self.csrf = r[1]["csrf"]
        return r[1]["user"]


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="convexa-integration-")
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        cls.port = s.getsockname()[1]
        s.close()
        cls.base = f"http://127.0.0.1:{cls.port}"
        env = os.environ.copy()
        env["CONVEXA_DATA_DIR"] = cls.temp.name
        env.pop("CONVEXA_LOCAL_WHISPER", None)
        cls.proc = subprocess.Popen(
            [sys.executable, "app.py", "--port", str(cls.port)],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for _ in range(65):
            try:
                with urllib.request.urlopen(cls.base + "/api/health", timeout=0.5) as r:
                    if r.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                time.sleep(0.1)
        else:
            raise RuntimeError("Local Convexa server failed to start")

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        try:
            cls.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.proc.kill()
        cls.temp.cleanup()

    def setUp(self):
        self.client = BrowserClient(self.base)
        self.user = self.client.register()

    def add(
        self,
        kind="note",
        title="Knowledge",
        body="Knowledge can be retrieved later",
        transcript="",
        url="",
        tags=None,
    ):
        code, data = self.client.call(
            "/api/items",
            "POST",
            {
                "kind": kind,
                "title": title,
                "body": body,
                "transcript": transcript,
                "url": url,
                "tags": tags or [],
            },
        )
        self.assertEqual(code, 201, data)
        return data["item"]

    def query(self, term):
        code, data = self.client.call("/api/items?q=" + urllib.parse.quote(term))
        self.assertEqual(code, 200, data)
        return data["results"]

    def test_landing_is_served_and_branded(self):
        code, data = self.client.call("/")
        self.assertEqual(code, 200)
        self.assertIn(b"Convexa", data)

    def test_local_capabilities_are_reported(self):
        status, data = self.client.call("/api/capabilities")
        self.assertEqual(status, 200)
        self.assertTrue(data["no_paid_api"])

    def test_create_and_retrieve_note(self):
        item = self.add(body="An immutable data structure")
        code, data = self.client.call("/api/items/" + item["id"])
        self.assertEqual(code, 200)
        self.assertIn("immutable", data["item"]["body"])

    def test_search_keyword(self):
        item = self.add(body="Advanced graph traversal algorithm")
        self.assertIn(item["id"], [x["item"]["id"] for x in self.query("traversal")])

    def test_search_synonym_across_youtube_transcript(self):
        video = self.add(
            "youtube",
            "Normalization lecture",
            "",
            "01:25 Database normalization reduces redundancy in relational tables.",
            "https://www.youtube.com/watch?v=jfKfPfyJRdk",
        )
        hits = self.query("reduce duplicate data")
        self.assertTrue(any(x["item"]["id"] == video["id"] for x in hits))
        hit = next(x for x in hits if x["item"]["id"] == video["id"])
        self.assertEqual(hit["match"]["start_seconds"], 85.0)
        self.assertIn("t=85s", hit["match"]["video_url"])

    def test_search_chat_excerpt(self):
        item = self.add(
            "chat",
            "Class conversation",
            "A professor discussed CAP theorem, consistency and partition tolerance",
        )
        self.assertTrue(
            any(h["item"]["id"] == item["id"] for h in self.query("partition tolerance"))
        )

    def test_grounded_assistant_and_citations(self):
        item = self.add(body="Binary search divides the sorted array in halves")
        code, data = self.client.call(
            "/api/ask", "POST", {"question": "explain binary search array"}
        )
        self.assertEqual(code, 200)
        self.assertEqual(data["mode"], "offline evidence retrieval")
        self.assertEqual(data["sources"][0]["id"], item["id"])
        self.assertIn("Binary search", data["answer"])

    def test_ai_does_not_invent_without_sources(self):
        code, data = self.client.call(
            "/api/ask", "POST", {"question": "quantum teleportation details"}
        )
        self.assertEqual(code, 200)
        self.assertFalse(data["sources"])

    def test_chat_history_is_saved(self):
        self.add(body="Memory retrieval test")
        self.client.call("/api/ask", "POST", {"question": "memory retrieval"})
        code, data = self.client.call("/api/chat/history")
        self.assertEqual(code, 200)
        self.assertEqual(len(data["messages"]), 1)

    def test_create_and_filter_tags(self):
        item = self.add(tags=["DBMS", "Revision"])
        self.assertEqual(item["tags"], ["dbms", "revision"])

    def test_collection_create_and_assign(self):
        status, c = self.client.call("/api/collections", "POST", {"name": "Semester 7"})
        self.assertEqual(status, 201)
        id = c["collection"]["id"]
        item = self.add()
        status, data = self.client.call("/api/items/" + item["id"], "PATCH", {"collection_id": id})
        self.assertEqual(status, 200)
        self.assertEqual(data["item"]["collection_id"], id)
        code, found = self.client.call("/api/items?collection=" + id)
        self.assertEqual(found["count"], 1)

    def test_favourites(self):
        item = self.add()
        self.client.call("/api/items/" + item["id"], "PATCH", {"favorite": True})
        code, data = self.client.call("/api/items?favorites=1")
        self.assertEqual(data["count"], 1)

    def test_archiving_hides_from_default_but_not_archive(self):
        item = self.add()
        self.client.call("/api/items/" + item["id"], "PATCH", {"archived": True})
        self.assertEqual(self.client.call("/api/items")[1]["count"], 0)
        self.assertEqual(self.client.call("/api/items?archived=1")[1]["count"], 1)

    def test_edit_reindexes_search(self):
        item = self.add(body="Sodium ion channel")
        self.client.call("/api/items/" + item["id"], "PATCH", {"body": "Potassium ion channel"})
        self.assertEqual(len(self.query("sodium")), 0)
        self.assertEqual(len(self.query("potassium")), 1)

    def test_delete_removes_from_index(self):
        item = self.add(body="Anemometer wind speed measuring")
        self.assertEqual(self.client.call("/api/items/" + item["id"], "DELETE")[0], 200)
        self.assertEqual(len(self.query("Anemometer")), 0)

    def test_txt_document_uploaded_and_searchable(self):
        item = self.add("file", "Lab notes", "")
        path = "/api/items/" + item["id"] + "/file?filename=lab.txt"
        code, data = self.client.call(
            path, "PUT", raw=b"Anaconda installations and NumPy matrix multiplication"
        )
        self.assertEqual(code, 201, data)
        self.assertGreater(data["extracted_chars"], 0)
        self.assertIn(
            "NumPy", self.client.call("/api/items/" + item["id"])[1]["item"]["extracted_text"]
        )
        self.assertEqual(len(self.query("matrix multiplication")), 1)

    def test_docx_document_uploaded_and_searchable(self):
        import io, zipfile

        blob = io.BytesIO()
        with zipfile.ZipFile(blob, "w") as z:
            z.writestr(
                "word/document.xml",
                """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Quantum computing qubits</w:t></w:r></w:p></w:body></w:document>""",
            )
        item = self.add("file", "DOCX knowledge", "")
        code, data = self.client.call(
            "/api/items/" + item["id"] + "/file?filename=study.docx", "PUT", raw=blob.getvalue()
        )
        self.assertEqual(code, 201, data)
        self.assertEqual(len(self.query("qubits")), 1)

    def test_voice_recording_and_manual_transcript(self):
        item = self.add(
            "voice",
            "Field recording",
            "",
            transcript="00:12 Sunlight drives photosynthesis in plants",
        )
        code, data = self.client.call(
            "/api/items/" + item["id"] + "/file?filename=voice.wav",
            "PUT",
            raw=b"RIFF\x00\x00\x00\x00WAVE",
        )
        self.assertEqual(code, 201, data)
        self.assertEqual(data["item"]["kind"], "voice")
        self.assertTrue(data["item"]["has_file"])
        self.assertEqual(len(self.query("photosynthesis")), 1)
        status, blob = self.client.call("/api/items/" + item["id"] + "/file")
        self.assertEqual(status, 200)
        self.assertIn(b"RIFF", blob)

    def test_untranscribed_voice_is_not_marked_searchable(self):
        item = self.add("voice", "Audio research", "")
        self.client.call(
            "/api/items/" + item["id"] + "/file?filename=note.wav",
            "PUT",
            raw=b"RIFF" + b"\x00" * 32,
        )
        for _ in range(35):
            status = self.client.call("/api/items/" + item["id"])[1]["item"]["status"]
            if status != "transcription_pending":
                break
            time.sleep(0.1)
        self.assertEqual(status, "audio_saved_no_transcript")

    def test_link_saved_without_internet_access(self):
        status, data = self.client.call(
            "/api/items",
            "POST",
            {
                "kind": "web",
                "title": "Reading list",
                "url": "https://example.com/article",
                "body": "Relational consistency patterns",
            },
        )
        self.assertEqual(status, 201, data)
        self.assertEqual(len(self.query("relational consistency")), 1)

    def test_youtube_rejects_invalid_domain(self):
        code, data = self.client.call(
            "/api/items",
            "POST",
            {
                "kind": "youtube",
                "title": "Bad link",
                "url": "https://www.youtube.com.evil.com/watch?v=jfKfPfyJRdk",
            },
        )
        self.assertEqual(code, 400)

    def test_unsafe_scheme_rejected_for_website(self):
        code, data = self.client.call(
            "/api/items", "POST", {"kind": "web", "title": "Bad", "url": "file:///etc/passwd"}
        )
        self.assertEqual(code, 400)

    def test_cross_user_cannot_download_private_attachment(self):
        item = self.add("file", "Private audio", "")
        self.client.call(
            "/api/items/" + item["id"] + "/file?filename=secret.txt",
            "PUT",
            raw=b"Highly confidential transcript",
        )
        another = BrowserClient(self.base)
        another.register()
        code, data = another.call("/api/items/" + item["id"] + "/file")
        self.assertEqual(code, 404)

    def test_cross_user_access_denied_to_files_and_items(self):
        item = self.add("note", "Private notes", "Secret internals")
        c2 = BrowserClient(self.base)
        c2.register()
        self.assertEqual(c2.call("/api/items/" + item["id"])[0], 404)
        self.assertEqual(c2.call("/api/items/" + item["id"], "PATCH", {"title": "Stolen"})[0], 404)
        self.assertEqual(len(c2.call("/api/items?q=secret")[1]["results"]), 0)

    def test_csrf_blocks_unauthorized_mutation(self):
        status, data = self.client.call(
            "/api/items", "POST", {"title": "Should not work"}, csrf=False
        )
        self.assertEqual(status, 403)

    def test_auth_invalid_password(self):
        code, data = self.client.call(
            "/api/login", "POST", {"email": self.user["email"], "password": "wrongpasswd"}
        )
        self.assertEqual(code, 403)

    def test_reminder_create_complete_delete(self):
        status, data = self.client.call(
            "/api/reminders",
            "POST",
            {"title": "Study algorithms", "due_at": "2027-02-01T09:00:00Z"},
        )
        self.assertEqual(status, 201)
        rid = data["reminder"]["id"]
        self.assertEqual(len(self.client.call("/api/reminders")[1]["reminders"]), 1)
        self.client.call("/api/reminders/" + rid, "PATCH", {"done": True})
        self.assertTrue(self.client.call("/api/reminders")[1]["reminders"][0]["done"])
        self.client.call("/api/reminders/" + rid, "DELETE")
        self.assertEqual(len(self.client.call("/api/reminders")[1]["reminders"]), 0)

    def test_focus_session_saved(self):
        status, data = self.client.call("/api/focus", "POST", {"minutes": 25})
        self.assertEqual(status, 201)
        self.assertEqual(self.client.call("/api/focus")[1]["sessions"][0]["minutes"], 25)

    def test_logout_invalidates_session(self):
        self.client.call("/api/logout", "POST")
        self.assertEqual(self.client.call("/api/me")[0], 401)


if __name__ == "__main__":
    unittest.main()
