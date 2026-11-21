"""Free knowledge capture, extraction, transcription and retrieval helpers.

All functions are designed to work without a cloud account or paid API. Optional
open-source packages improve the result, but cannot guarantee external captions.
"""

from __future__ import annotations
import html
from html.parser import HTMLParser
import importlib.util
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
import zipfile
from xml.etree import ElementTree

MAX_TEXT = 180_000
ALLOWED_EXTENSIONS = {
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".json",
    ".log",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".html",
    ".htm",
    ".pdf",
    ".docx",
    ".mp3",
    ".mp4",
    ".m4a",
    ".wav",
    ".webm",
    ".ogg",
    ".opus",
    ".aac",
    ".flac",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
}
AUDIO_EXTENSIONS = {".mp3", ".m4a", ".wav", ".webm", ".ogg", ".opus", ".aac", ".flac"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".log", ".py", ".js", ".ts", ".tsx"}
VIDEO_ID = re.compile(r"^[a-zA-Z0-9_-]{11}$")
STAMP = re.compile(r"^\s*(?:(\d+):)?(\d{1,2}):(\d{2})[\s|—-]+(.+)$")
WORDS = re.compile(r"[^\W_]+", re.UNICODE)
STOPWORDS = frozenset(
    "a an and are as at be by can could do does for from has have how i in into is it its of on or our the their them these this to was were what when where which who why will with would you your find show me about please saved already".split()
)
# Small, explicit query-expansion dictionary, not a substitute for neural embeddings.
ASSOCIATIONS = {
    "duplicate": ("redundancy", "normalization", "repetition"),
    "duplicates": ("redundancy", "normalization", "repetition"),
    "duplicated": ("redundancy", "normalization"),
    "reduce": ("remove", "eliminate", "minimize"),
    "removing": ("reduce", "eliminate"),
    "database": ("data", "sql", "relational"),
    "data": ("database", "information"),
    "study": ("learn", "lecture", "tutorial"),
    "video": ("youtube", "lecture", "watch"),
    "learn": ("study", "tutorial", "lecture"),
    "python": ("programming", "code"),
    "focus": ("pomodoro", "concentration"),
    "reminder": ("task", "deadline"),
    "memory": ("knowledge", "recall"),
    "explain": ("describe", "definition"),
    "organize": ("categorize", "collection"),
}


def youtube_id(url: str) -> str | None:
    try:
        p = urllib.parse.urlsplit(url.strip())
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme not in ("https", "http") or p.username or p.password:
            return None
        if host in ("youtu.be", "www.youtu.be"):
            candidate = p.path.strip("/").split("/")[0]
        elif host in (
            "youtube.com",
            "www.youtube.com",
            "m.youtube.com",
            "music.youtube.com",
            "youtube-nocookie.com",
            "www.youtube-nocookie.com",
        ):
            parts = p.path.strip("/").split("/")
            if parts[0] in ("shorts", "embed", "live") and len(parts) > 1:
                candidate = parts[1]
            elif parts[0] == "watch":
                candidate = urllib.parse.parse_qs(p.query).get("v", [""])[0]
            else:
                return None
        else:
            return None
        return candidate if VIDEO_ID.fullmatch(candidate) else None
    except (ValueError, IndexError):
        return None


def parse_segments(text: str) -> list[dict]:
    """Support pasted transcripts with hh:mm:ss / mm:ss timestamps."""
    segments = []
    pending = []
    for line in text.splitlines():
        match = STAMP.match(line)
        if match:
            if pending and segments:
                segments[-1]["text"] += "\n" + "\n".join(pending)
            pending = []
            h, m, s, content = match.groups()
            segments.append(
                {"start": int(h or 0) * 3600 + int(m) * 60 + int(s), "text": content.strip()}
            )
        elif line.strip():
            pending.append(line.strip())
    if pending and segments:
        segments[-1]["text"] += "\n" + "\n".join(pending)
    return segments if segments else []


def group_segments(segments: list[dict], max_chars: int = 650) -> list[dict]:
    """Group closely-spaced caption entries into useful timestamped search chunks."""
    out = []
    buf = ""
    start = 0
    for entry in segments:
        txt = str(entry.get("text", "")).strip()
        if not txt:
            continue
        if not buf:
            start = float(entry.get("start", 0) or 0)
        if buf and len(buf) + len(txt) > max_chars:
            out.append({"text": buf, "start": start})
            buf, start = "", float(entry.get("start", 0) or 0)
        buf = (buf + " " + txt).strip()[: max_chars * 2]
    if buf:
        out.append({"text": buf, "start": start})
    return out[:600]


def best_caption_segment(transcript: str, query: str) -> dict | None:
    """Locate the matching spoken passage, not just its coarse group start."""
    segments = parse_segments(transcript)
    if not segments:
        return None
    primary = [w.lower() for w in WORDS.findall(query) if len(w) > 1 and w.lower() not in STOPWORDS]
    expanded = [w for w in keywords(query) if w not in primary]
    chosen = None
    best = 0
    for segment in segments[:12000]:
        words = set(w.lower() for w in WORDS.findall(segment["text"]))
        score = 3 * len(words.intersection(primary)) + len(words.intersection(expanded))
        if score > best:
            best = score
            chosen = segment
    return chosen if best else None


def chunks_for_item(title: str, body: str, transcript: str, kind: str) -> list[dict]:
    chunks = []
    if title:
        chunks.append({"text": title[:300], "start": 0.0, "section": "title"})
    for section, content in [("transcript", transcript), ("body", body)]:
        content = (content or "")[:MAX_TEXT].strip()
        if not content:
            continue
        segments = parse_segments(content) if section == "transcript" else []
        if segments:
            chunks.extend(
                {"text": c["text"], "start": c["start"], "section": section}
                for c in group_segments(segments)
            )
            continue
        # Paragraph aware splitting with overlap to preserve phrase context.
        words = content.split()
        for offset in range(0, len(words), 90):
            cut = words[max(0, offset - 15) : offset + 105]
            if cut:
                chunks.append({"text": " ".join(cut)[:1000], "start": 0.0, "section": section})
            if len(chunks) > 510:
                break
    return chunks[:600]


def extract_docx(path: Path):
    with zipfile.ZipFile(path) as archive:
        info = archive.getinfo("word/document.xml")
        if info.file_size > 6_000_000:
            return "", "DOCX document XML is too large"
        data = archive.read(info)
    root = ElementTree.fromstring(data)
    ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs = []
    for p in root.iter(ns + "p"):
        line = "".join(t.text or "" for t in p.iter(ns + "t"))
        if line.strip():
            paragraphs.append(line)
    text = "\n".join(paragraphs)[:MAX_TEXT]
    return (text, "") if text.strip() else ("", "No selectable text in DOCX")


def extract_file(path: str | Path, filename: str) -> tuple[str, str]:
    """Returns (extracted_text, explanation_if_not_searchable)."""
    path = Path(path)
    ext = Path(filename).suffix.lower()
    if ext in TEXT_EXTENSIONS:
        text = path.read_bytes()[: MAX_TEXT * 4].decode("utf-8-sig", errors="replace")[:MAX_TEXT]
        return (text, "") if text.strip() else ("", "File contains no readable text")
    if ext in (".html", ".htm"):
        raw = path.read_bytes()[: MAX_TEXT * 4].decode("utf-8", errors="replace")
        obj = ReadableHTML()
        obj.feed(raw)
        return obj.text()[:MAX_TEXT], ""
    if ext == ".docx":
        try:
            return extract_docx(path)
        except Exception as e:
            return "", f"DOCX extraction failed ({type(e).__name__})"
    if ext == ".pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(path, strict=False)
            text = "\n".join((p.extract_text() or "") for p in list(reader.pages)[:150])[:MAX_TEXT]
            return (
                (text, "")
                if text.strip()
                else ("", "Scanned PDF: no selectable text. OCR is not configured.")
            )
        except ImportError:
            # Poppler is common on Linux; Python-only deployments can install pypdf.
            if shutil.which("pdftotext"):
                try:
                    r = subprocess.run(
                        ["pdftotext", "-layout", str(path), "-"], capture_output=True, timeout=25
                    )
                    text = r.stdout.decode(errors="replace")[:MAX_TEXT]
                    if r.returncode == 0 and text.strip():
                        return text, ""
                except (OSError, subprocess.TimeoutExpired):
                    pass
            return "", "Install free pypdf to index selectable PDF text: pip install pypdf"
        except Exception as e:
            return "", f"PDF extraction failed ({type(e).__name__})"
    if ext in AUDIO_EXTENSIONS:
        return "", "Audio saved; add a transcript or enable free local Whisper transcription"
    if ext in IMAGE_EXTENSIONS:
        return "", "Image saved; add descriptive notes. OCR is not enabled."
    return "", "File saved; there is no text extractor for this format"


class ReadableHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript", "svg"):
            self.skip = max(0, self.skip - 1)

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.parts.append(data.strip())

    def text(self):
        return "\n".join(self.parts)


def fetch_youtube_captions(video_id: str) -> tuple[str, str]:
    """Free official publicly exposed caption data when accessible. No fabrication."""
    if not VIDEO_ID.fullmatch(video_id):
        return "", "Invalid video ID"
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return "", "Caption package missing in the Python running Convexa. Stop the app, install requirements.txt with that same Python, restart, then click Retry captions."
    try:
        from requests import Session
        class CaptionSession(Session):
            def request(self, method, url, **kwargs):
                kwargs.setdefault("timeout", (8, 20))
                return super().request(method, url, **kwargs)
        api = YouTubeTranscriptApi(http_client=CaptionSession())
        if hasattr(api, "fetch"):
            try:
                data = api.fetch(video_id, languages=("en", "en-US"))
            except Exception as exc:
                if type(exc).__name__ != "NoTranscriptFound":
                    raise
                # Prefer English; some videos only have other languages.
                tracks = api.list(video_id)
                track = next(iter(tracks))
                data = track.fetch()
        else:
            data = YouTubeTranscriptApi.get_transcript(video_id, languages=["en", "en-US"])
        parts = []
        for s in list(data)[:12000]:
            if isinstance(s, dict):
                txt = s.get("text", "")
                start = s.get("start", 0)
            else:
                txt = getattr(s, "text", "")
                start = getattr(s, "start", 0)
            txt = re.sub(r"\s+", " ", html.unescape(str(txt))).strip()
            if txt:
                parts.append(
                    f"{int(float(start)//3600):02}:{int(float(start)%3600//60):02}:{int(float(start)%60):02} {txt}"
                )
        transcript = "\n".join(parts)[:MAX_TEXT]
        return (transcript, "") if transcript else ("", "Published captions are empty")
    except Exception as e:
        return (
            "",
            f"Could not obtain public captions ({type(e).__name__}). Paste a transcript instead.",
        )


def validate_url_syntax(url: str) -> str:
    """Allow saving a public web link offline; fetching later enforces SSRF checks."""
    if len(url) > 2048:
        raise ValueError("URL is too long")
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        raise ValueError("Use an http(s) URL")
    if p.hostname.lower() in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Local network URLs cannot be fetched")
    return url


def validate_public_url(url: str) -> str:
    """Prevent SSRF on web text extraction; never fetch local addresses or credentials."""
    if len(url) > 2048:
        raise ValueError("Link too long")
    p = urllib.parse.urlsplit(url)
    if p.scheme not in ("https", "http") or not p.hostname or p.username or p.password:
        raise ValueError("Use a valid http(s) URL")
    if p.port not in (None, 80, 443):
        raise ValueError("Only standard web ports are allowed")
    host = p.hostname.lower().rstrip(".")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise ValueError("Local network URL blocked")
    try:
        ips = socket.getaddrinfo(
            host, p.port or (443 if p.scheme == "https" else 80), type=socket.SOCK_STREAM
        )
    except socket.gaierror:
        raise ValueError("Cannot resolve website host")
    if not ips or any(not ipaddress.ip_address(info[4][0]).is_global for info in ips):
        raise ValueError("Private or non-public URL blocked")
    return url


class PublicRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public_web_text(url: str) -> tuple[str, str]:
    try:
        validate_public_url(url)
        opener = urllib.request.build_opener(PublicRedirect())
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "ConvexaKnowledgeClient/1.0 (personal research)",
                "Accept": "text/html,text/plain",
            },
        )
        with opener.open(req, timeout=7) as resp:
            typ = resp.headers.get_content_type()
            if typ not in ("text/plain", "text/html", "application/xhtml+xml"):
                return "", "Website is not a readable text page"
            raw = resp.read(800_000)
            charset = resp.headers.get_content_charset() or "utf-8"
        text = raw.decode(charset, errors="replace")
        if typ in ("text/html", "application/xhtml+xml"):
            p = ReadableHTML()
            p.feed(text)
            text = p.text()
        text = text[:MAX_TEXT]
        return (text, "") if text.strip() else ("", "Website contains no readable text")
    except Exception as e:
        return (
            "",
            f"Website extraction unavailable ({type(e).__name__}). Paste the relevant content manually.",
        )


def optional_transcription(path: Path) -> tuple[str, str]:
    if os.environ.get("CONVEXA_LOCAL_WHISPER", "0") != "1":
        return "", "Free speech-to-text is optional. Enable local Whisper or provide a transcript."
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return "", "Install free faster-whisper and ffmpeg, then enable CONVEXA_LOCAL_WHISPER=1"
    try:
        model = WhisperModel(
            os.environ.get("CONVEXA_WHISPER_MODEL", "tiny"), device="cpu", compute_type="int8"
        )
        segments, _ = model.transcribe(str(path), beam_size=3, vad_filter=True)
        transcript = "\n".join(
            f"{int(seg.start//3600):02}:{int(seg.start%3600//60):02}:{int(seg.start%60):02} {seg.text.strip()}"
            for seg in segments
        )[:MAX_TEXT]
        return (transcript, "") if transcript.strip() else ("", "Speech recognizer found no words")
    except Exception as e:
        return "", f"Whisper transcription failed ({type(e).__name__}); enter transcript manually"


def keywords(query: str) -> list[str]:
    words = [w.lower() for w in WORDS.findall(query) if len(w) > 1 and w.lower() not in STOPWORDS][
        :12
    ]
    expansions = []
    for w in words:
        for related in ASSOCIATIONS.get(w, ()):
            if related not in words and related not in expansions:
                expansions.append(related)
    return (words + expansions)[:22]


def snippet(text: str, query: str, limit=320) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text).strip()
    positions = [
        text.lower().find(word) for word in keywords(query) if text.lower().find(word) >= 0
    ]
    index = min(positions) if positions else 0
    start = max(0, index - 65)
    return (
        ("…" if start else "")
        + text[start : start + limit]
        + ("…" if len(text) > start + limit else "")
    )
