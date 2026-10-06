"""Sessions, credential encryption and login throttling (guideline 4.3 and 15).

* Credentials live ONLY inside the server-side session, Fernet-encrypted, with an idle TTL; never in the DB or logs.
* The browser only gets an opaque, HTTP-only session id.
* Login attempts are counted per (client ip, login) and locked out after repeated failures.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from typing import Callable, Protocol

from cryptography.fernet import Fernet, InvalidToken

from .config import Settings, get_settings


# ---- credential encryption --------------------------------------------------------------------

def _fernet(secret_key: str) -> Fernet:
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest()))


def encrypt_secret(plain: str, settings: Settings | None = None) -> str:
    s = settings or get_settings()
    return _fernet(s.app_secret_key).encrypt(plain.encode()).decode()


def decrypt_secret(token: str, settings: Settings | None = None) -> str | None:
    s = settings or get_settings()
    try:
        return _fernet(s.app_secret_key).decrypt(token.encode()).decode()
    except InvalidToken:
        return None


# ---- session store ------------------------------------------------------------------------------

class SessionStore(Protocol):
    def create(self, data: dict, ttl: int) -> str: ...
    def get(self, sid: str, ttl: int) -> dict | None: ...
    def delete(self, sid: str) -> None: ...


class MemorySessionStore:
    """In-process store for dev/tests. `clock` is injectable so tests can prove the idle timeout."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._d: dict[str, tuple[float, dict]] = {}
        self._lock = threading.Lock()
        self.clock = clock

    def create(self, data: dict, ttl: int) -> str:
        sid = secrets.token_urlsafe(32)
        with self._lock:
            self._d[sid] = (self.clock() + ttl, data)
        return sid

    def get(self, sid: str, ttl: int) -> dict | None:
        with self._lock:
            item = self._d.get(sid)
            if not item:
                return None
            exp, data = item
            if exp < self.clock():  # idle timeout elapsed
                del self._d[sid]
                return None
            self._d[sid] = (self.clock() + ttl, data)  # sliding window
            return data

    def delete(self, sid: str) -> None:
        with self._lock:
            self._d.pop(sid, None)


class RedisSessionStore:
    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True)

    def create(self, data: dict, ttl: int) -> str:
        sid = secrets.token_urlsafe(32)
        self.r.set(f"sess:{sid}", json.dumps(data), ex=ttl)
        return sid

    def get(self, sid: str, ttl: int) -> dict | None:
        key = f"sess:{sid}"
        raw = self.r.get(key)
        if raw is None:
            return None
        self.r.expire(key, ttl)  # sliding idle window
        return json.loads(raw)

    def delete(self, sid: str) -> None:
        self.r.delete(f"sess:{sid}")


_store: SessionStore | None = None


def get_session_store() -> SessionStore:
    global _store
    if _store is None:
        s = get_settings()
        _store = RedisSessionStore(s.redis_url) if s.redis_url else MemorySessionStore()
    return _store


def set_session_store(store: SessionStore | None) -> None:
    global _store
    _store = store


# ---- login throttle -----------------------------------------------------------------------------

class LoginLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}
        self._lock = threading.Lock()
        self.clock = clock

    def retry_after(self, key: str, settings: Settings | None = None) -> int:
        with self._lock:
            until = self._locked.get(key)
            if until and until > self.clock():
                return int(until - self.clock()) + 1
            self._locked.pop(key, None)
            return 0

    def failed(self, key: str, settings: Settings | None = None) -> None:
        s = settings or get_settings()
        now = self.clock()
        with self._lock:
            window = [t for t in self._fails.get(key, []) if now - t < s.login_lockout_seconds] + [now]
            self._fails[key] = window
            if len(window) >= s.login_max_fails:
                self._locked[key] = now + s.login_lockout_seconds
                self._fails[key] = []

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._fails.pop(key, None)
            self._locked.pop(key, None)


_limiter = LoginLimiter()


def get_limiter() -> LoginLimiter:
    return _limiter


def set_limiter(limiter: LoginLimiter) -> None:
    global _limiter
    _limiter = limiter
