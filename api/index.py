"""Vercel entry point. Initialization errors return a safe 503, not a broken import."""
import threading
from app import Handler
from core import store, assistant, hosting

_ready = False
_lock = threading.Lock()


class handler(Handler):
    def _dispatch(self, action):
        global _ready
        token = assistant.set_user_settings({})
        try:
            if not _ready:
                with _lock:
                    if not _ready:
                        hosting.validate()
                        store.init_db()
                        _ready = True
            getattr(super(), action)()
        except Exception:
            # Never reveal a database URL/token or raw driver exception publicly.
            self.error('Service setup unavailable. Check deployment configuration and database access.', 503)
        finally:
            assistant._ACTIVE_SETTINGS.reset(token)

    def do_GET(self):
        self._dispatch('do_GET')

    def do_POST(self):
        self._dispatch('do_POST')

    def do_PUT(self):
        self._dispatch('do_PUT')

    def do_PATCH(self):
        self._dispatch('do_PATCH')

    def do_DELETE(self):
        self._dispatch('do_DELETE')
