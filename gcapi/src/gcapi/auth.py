from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionRecord:
    session_id: str
    expires_at: float

    def is_expired(self, now: float) -> bool:
        return self.expires_at <= now


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def get(self, session_id: str, *, now: float | None = None) -> SessionRecord | None:
        current_time = time.time() if now is None else now
        with self._lock:
            self._purge_expired_locked(current_time)
            session = self._sessions.get(session_id)
            if session is None or session.is_expired(current_time):
                self._sessions.pop(session_id, None)
                return None
            return session

    def create(self, *, ttl_seconds: int, now: float | None = None) -> SessionRecord:
        current_time = time.time() if now is None else now
        session = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            expires_at=current_time + ttl_seconds,
        )
        with self._lock:
            self._purge_expired_locked(current_time)
            self._sessions[session.session_id] = session
        return session

    def delete(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def _purge_expired_locked(self, now: float) -> None:
        expired_ids = [
            session_id
            for session_id, session in self._sessions.items()
            if session.is_expired(now)
        ]
        for session_id in expired_ids:
            self._sessions.pop(session_id, None)
