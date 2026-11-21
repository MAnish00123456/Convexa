"""Unit tests for the knowledge transformation layer (standard library only)."""

import tempfile
import unittest
from pathlib import Path
import zipfile
from core import knowledge


class KnowledgeTests(unittest.TestCase):
    def test_youtube_watch_url(self):
        self.assertEqual(
            knowledge.youtube_id("https://www.youtube.com/watch?v=jfKfPfyJRdk"), "jfKfPfyJRdk"
        )

    def test_youtube_short(self):
        self.assertEqual(knowledge.youtube_id("https://youtu.be/jfKfPfyJRdk"), "jfKfPfyJRdk")

    def test_youtube_shorts(self):
        self.assertEqual(
            knowledge.youtube_id("https://youtube.com/shorts/jfKfPfyJRdk"), "jfKfPfyJRdk"
        )

    def test_reject_lookalike_domain(self):
        self.assertIsNone(
            knowledge.youtube_id("https://youtube.com.evil.example/watch?v=jfKfPfyJRdk")
        )

    def test_reject_bad_video_id(self):
        self.assertIsNone(knowledge.youtube_id("https://youtube.com/watch?v=oops"))

    def test_timed_captions(self):
        seg = knowledge.parse_segments(
            "01:25 Normalization reduces redundancy\n02:15 Second normal form"
        )
        self.assertEqual([x["start"] for x in seg], [85, 135])

    def test_precise_video_timestamp(self):
        transcript = "00:30 Introduction to video\n02:12 Normalization removes database redundancy"
        hit = knowledge.best_caption_segment(transcript, "normalization redundancy")
        self.assertEqual(hit["start"], 132)

    def test_hours_captions(self):
        seg = knowledge.parse_segments("02:14:06 Relational algebra")
        self.assertEqual(seg[0]["start"], 8046)

    def test_caption_grouping(self):
        x = knowledge.group_segments(
            [{"text": "one", "start": 10}, {"text": "two", "start": 15}], 100
        )
        self.assertEqual(x[0]["start"], 10)
        self.assertIn("two", x[0]["text"])

    def test_chunking_large_doc_bounded(self):
        c = knowledge.chunks_for_item("Large", "database " * 50000, "", "file")
        self.assertLessEqual(len(c), 600)

    def test_synonyms_for_real_knowledge_query(self):
        k = knowledge.keywords("how to reduce duplicate data")
        self.assertIn("normalization", k)
        self.assertIn("redundancy", k)

    def test_html_removes_scripts(self):
        h = knowledge.ReadableHTML()
        h.feed("<p>Knowledge</p><script>private data</script><p>search</p>")
        self.assertEqual(h.text(), "Knowledge\nsearch")

    def test_document_extract_txt(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.txt"
            f.write_text("This is a searchable resource")
            text, error = knowledge.extract_file(f, "x.txt")
            self.assertIn("searchable", text)
            self.assertEqual(error, "")

    def test_docx_extraction(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "notes.docx"
            with zipfile.ZipFile(f, "w") as z:
                z.writestr(
                    "word/document.xml",
                    """<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Database normalization</w:t></w:r></w:p></w:body></w:document>""",
                )
            text, error = knowledge.extract_file(f, "notes.docx")
            self.assertEqual(text, "Database normalization")

    def test_pdf_text_extraction_when_free_library_available(self):
        import importlib.util

        if importlib.util.find_spec("pypdf") is None:
            self.skipTest("pypdf is optional")
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sample.pdf"
            content = b"BT /F1 18 Tf 50 700 Td (Photosynthesis produces glucose) Tj ET"
            objects = [
                b"<< /Type /Catalog /Pages 2 0 R >>",
                b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
                b"<< /Length "
                + str(len(content)).encode()
                + b" >>\nstream\n"
                + content
                + b"\nendstream",
            ]
            out = bytearray(b"%PDF-1.4\n")
            offsets = [0]
            for i, obj in enumerate(objects, 1):
                offsets.append(len(out))
                out.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
            off = len(out)
            out.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
            for v in offsets[1:]:
                out.extend(f"{v:010} 00000 n \n".encode())
            out.extend(
                f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{off}\n%%EOF".encode()
            )
            f.write_bytes(out)
            text, error = knowledge.extract_file(f, "sample.pdf")
            self.assertIn("Photosynthesis produces glucose", text)

    def test_untranscribed_audio_is_explicit(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "audio.wav"
            f.write_bytes(b"RIFF")
            text, error = knowledge.extract_file(f, "audio.wav")
            self.assertFalse(text)
            self.assertIn("transcript", error)

    def test_local_web_url_is_blocked(self):
        with self.assertRaises(ValueError):
            knowledge.validate_url_syntax("http://127.0.0.1/admin")

    def test_non_web_scheme_is_blocked(self):
        with self.assertRaises(ValueError):
            knowledge.validate_url_syntax("file:///etc/passwd")

    def test_youtube_caption_adapter_with_mocked_published_captions(self):
        import sys
        from unittest.mock import patch
        from types import SimpleNamespace

        class CaptionAPI:
            def __init__(self, http_client=None):
                self.http_client = http_client

            def fetch(self, id, languages):
                return [SimpleNamespace(text="Normalization improves database design", start=85.0)]

        with patch.dict(
            sys.modules,
            {"youtube_transcript_api": SimpleNamespace(YouTubeTranscriptApi=CaptionAPI)},
        ):
            text, error = knowledge.fetch_youtube_captions("jfKfPfyJRdk")
        self.assertEqual(error, "")
        self.assertIn("00:01:25", text)

    def test_embedding_similarity_math(self):
        from core.assistant import similarity

        self.assertAlmostEqual(similarity([1, 0, 0], [1, 0, 0]), 1)
        self.assertAlmostEqual(similarity([1, 0], [0, 1]), 0)

    def test_html_and_js_file_accepted_but_not_executed(self):
        self.assertIn(".html", knowledge.ALLOWED_EXTENSIONS)
        self.assertNotIn(".svg", knowledge.ALLOWED_EXTENSIONS)


if __name__ == "__main__":
    unittest.main()
