"""Cloud connector contract tests. No real keys, billing or network required."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from core import assistant, store


class CloudProviderTests(unittest.TestCase):
    def test_no_credentials_is_offline(self):
        names = {
            "GROQ_API_KEY",
            "GEMINI_API_KEY",
            "OPENAI_API_KEY",
            "CONVEXA_AI_PROVIDER",
            "CONVEXA_EMBEDDING_PROVIDER",
            "CONVEXA_VOICE_PROVIDER",
        }
        with patch.dict(os.environ, {k: "" for k in names}):
            self.assertIsNone(assistant.chat_provider())
            self.assertIsNone(assistant.embedding_provider())
            self.assertIsNone(assistant.voice_provider())

    def test_groq_chat_and_gemini_embeddings_preferred_without_openai_cost(self):
        with patch.dict(
            os.environ,
            {
                "GROQ_API_KEY": "dummy-groq",
                "GEMINI_API_KEY": "dummy-gemini",
                "OPENAI_API_KEY": "dummy-openai",
                "CONVEXA_AI_PROVIDER": "auto",
                "CONVEXA_EMBEDDING_PROVIDER": "auto",
                "CONVEXA_VOICE_PROVIDER": "auto",
            },
        ):
            self.assertEqual(assistant.chat_provider(), "groq")
            self.assertEqual(assistant.embedding_provider(), "gemini")
            self.assertEqual(assistant.voice_provider(), "groq")
            self.assertFalse(assistant.provider_info()["openai_usage_may_be_billed"])

    def test_openai_chat_when_explicit(self):
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "dummy-openai", "CONVEXA_AI_PROVIDER": "openai"}
        ):
            self.assertEqual(assistant.chat_provider(), "openai")
            self.assertTrue(assistant.provider_info()["openai_usage_may_be_billed"])

    def test_paid_embeddings_requires_opt_in(self):
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "dummy-openai",
                "CONVEXA_EMBEDDING_PROVIDER": "openai",
                "CONVEXA_ALLOW_PAID_EMBEDDINGS": "0",
            },
        ):
            self.assertIsNone(assistant.embedding_provider())
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "dummy-openai",
                "CONVEXA_EMBEDDING_PROVIDER": "openai",
                "CONVEXA_ALLOW_PAID_EMBEDDINGS": "1",
            },
        ):
            self.assertEqual(assistant.embedding_provider(), "openai")

    def test_groq_chat_calls_only_backend_and_handles_response(self):
        captured = []

        def fake(url, data, timeout=0, headers=None):
            captured.append((url, data, headers))
            return {"choices": [{"message": {"content": "Normalization reduces duplication [1]."}}]}

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "dummy-groq", "CONVEXA_AI_PROVIDER": "groq"}),
            patch.object(assistant, "_http", side_effect=fake),
        ):
            result = assistant._chat(
                "Only saved passages",
                "What is normalization?",
                "[1] Normalization reduces redundancy",
                "groq",
            )
        self.assertIn("[1]", result)
        self.assertTrue(captured[0][0].endswith("/chat/completions"))
        self.assertEqual(captured[0][2]["Authorization"], "Bearer dummy-groq")
        self.assertIn("Retrieved passages", captured[0][1]["messages"][-1]["content"])

    def test_gemini_chat_native_adapter(self):
        with (
            patch.dict(os.environ, {"GEMINI_API_KEY": "dummy-gemini"}),
            patch.object(
                assistant,
                "_http",
                return_value={
                    "candidates": [{"content": {"parts": [{"text": "Answer grounded in [1]."}]}}]
                },
            ) as post,
        ):
            answer = assistant._chat("Use evidence", "Question", "[1] Evidence", "gemini")
        self.assertIn("[1]", answer)
        self.assertIn("generateContent", post.call_args.args[0])
        self.assertEqual(post.call_args.kwargs["headers"]["x-goog-api-key"], "dummy-gemini")

    def test_gemini_embedding_task_type_and_dimensions(self):
        data = []

        def fake(url, payload, timeout=0, headers=None):
            data.append(payload)
            return {"embeddings": [{"values": [1.0, 0.0, 0.0]}]}

        with (
            patch.dict(
                os.environ,
                {"GEMINI_API_KEY": "dummy-gemini", "CONVEXA_EMBEDDING_PROVIDER": "gemini"},
            ),
            patch.object(assistant, "_http", side_effect=fake),
        ):
            v = assistant.embed(["duplicate rows"], purpose="document")
            q = assistant.embed(["reduce repeated data"], purpose="query")
        self.assertEqual(v[0], [1.0, 0.0, 0.0])
        self.assertEqual(q[0], [1.0, 0.0, 0.0])
        self.assertEqual(data[0]["requests"][0]["taskType"], "RETRIEVAL_DOCUMENT")
        self.assertEqual(data[1]["requests"][0]["taskType"], "RETRIEVAL_QUERY")
        self.assertEqual(data[0]["requests"][0]["outputDimensionality"], 768)

    def test_cloud_voice_multipart_transcription(self):
        class DummyResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, n=-1):
                return json.dumps({"text": "The concept is explained clearly"}).encode()

        with tempfile.TemporaryDirectory() as tmp:
            file = Path(tmp) / "sample.webm"
            file.write_bytes(b"fake audio sample, not a real microphone recording")
            with (
                patch.dict(
                    os.environ, {"GROQ_API_KEY": "dummy-groq", "CONVEXA_VOICE_PROVIDER": "groq"}
                ),
                patch.object(
                    assistant.urllib.request, "urlopen", return_value=DummyResponse()
                ) as post,
            ):
                text, error = assistant.transcribe_audio(file)
        self.assertIn("concept", text)
        self.assertEqual(error, "")
        request = post.call_args.args[0]
        self.assertIn(b'name="file"', request.data)
        self.assertIn(b"whisper-large-v3-turbo", request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer dummy-groq")

    def test_incompatible_vectors_are_not_mixed_after_provider_change(self):
        with tempfile.TemporaryDirectory() as folder:
            with (
                patch.object(store, "DATA_DIR", Path(folder)),
                patch.object(store, "DB_FILE", Path(folder) / "a.sqlite3"),
            ):
                store.init_db()
                with store.db() as c:
                    user = c.execute(
                        "INSERT INTO users(email,pw,created_at) VALUES(?,?,?)",
                        ("user@example.org", "unused", 0),
                    ).lastrowid
                    item = store.create_item(
                        c,
                        user,
                        {"kind": "note", "title": "Algorithms", "body": "Binary search example"},
                    )
                    c.execute(
                        "UPDATE chunks SET embedding=?,embedding_model=? WHERE item_id=?",
                        ("[1,0,0]", "openai:text-embedding-3-small", item["id"]),
                    )
                    lexical = []
                    with (
                        patch.dict(
                            os.environ,
                            {
                                "GEMINI_API_KEY": "dummy-gemini",
                                "CONVEXA_EMBEDDING_PROVIDER": "gemini",
                            },
                        ),
                        patch.object(
                            assistant,
                            "embed",
                            side_effect=AssertionError("Should not embed when no matching index"),
                        ),
                    ):
                        result, mode = assistant.hybrid_search(c, user, "Algorithms", lexical)
                    self.assertEqual(result, [])
                    self.assertIn("index not built", mode)

    def test_connection_diagnostics_use_only_synthetic_text(self):
        with (
            patch.dict(
                os.environ,
                {
                    "GROQ_API_KEY": "dummy-groq",
                    "GEMINI_API_KEY": "dummy-gemini",
                    "CONVEXA_AI_PROVIDER": "groq",
                    "CONVEXA_EMBEDDING_PROVIDER": "gemini",
                    "CONVEXA_VOICE_PROVIDER": "groq",
                },
            ),
            patch.object(assistant, "_chat", return_value="connectivity") as chat,
            patch.object(assistant, "embed", return_value=[[1.0, 0.0]]) as emb,
        ):
            status = assistant.connection_test()
        self.assertTrue(status["chat"]["ok"])
        self.assertTrue(status["embeddings"]["ok"])
        self.assertEqual(status["voice"]["status"], "Requires a real audio upload to verify")
        self.assertIn("connectivity", str(chat.call_args))
        self.assertIn("diagnostic sample", str(emb.call_args))

    def test_old_sqlite_chunks_schema_is_migrated(self):
        import sqlite3

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old.sqlite3"
            c = sqlite3.connect(path)
            c.execute(
                "CREATE TABLE chunks(id INTEGER PRIMARY KEY,item_id TEXT,user_id INTEGER,section TEXT,text TEXT,start_seconds REAL,embedding TEXT)"
            )
            c.commit()
            c.close()
            with (
                patch.object(store, "DATA_DIR", Path(folder)),
                patch.object(store, "DB_FILE", path),
            ):
                store.init_db()
                with store.db() as conn:
                    self.assertIn(
                        "embedding_model",
                        [r["name"] for r in conn.execute("PRAGMA table_info(chunks)")],
                    )


if __name__ == "__main__":
    unittest.main()
