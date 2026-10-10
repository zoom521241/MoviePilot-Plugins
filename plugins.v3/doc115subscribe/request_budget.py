"""Plugin-owned account budget; never changes the host/Plus rate limiters."""
from __future__ import annotations

from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import threading
import time
import uuid
from typing import Callable, Optional


class P115Error(RuntimeError):
    """A confirmed API failure (unless explicitly marked uncertain)."""


class P115Deferred(P115Error):
    """No subsequent request is allowed; persist state and resume later."""
    def __init__(self, message: str, *, reason: str = "budget", retry_at: float = 0,
                 uncertain: bool = False, state=None, not_sent: Optional[bool] = None):
        super().__init__(message)
        self.reason = reason
        self.retry_at = retry_at or time.time() + 2
        self.uncertain = uncertain
        self.state = state
        self.not_sent = not uncertain if not_sent is None else not_sent


@dataclass
class WorkSlice:
    started: float
    max_requests: int = 5
    max_seconds: float = 15
    cancelled: Optional[Callable[[], bool]] = None
    requests: int = 0
    file_cache: dict = field(default_factory=dict)


class AccountBudget:
    def __init__(self, min_interval: float = 2, max_requests: int = 20,
                 window: float = 60, max_submissions: int = 3,
                 clock=time.monotonic, wall_clock=time.time, sleep=time.sleep):
        self.min_interval = min_interval
        self.max_requests = max_requests
        self.window = window
        self.max_submissions = max_submissions
        self.clock, self.wall_clock, self.sleep = clock, wall_clock, sleep
        self._request_times = deque()
        self._submission_times = deque()
        # Hold the lock for the entire HTTP call, not just admission.
        self._lock = threading.RLock()
        self._local = threading.local()
        self._cooldown_until = 0.0
        self._cooldown_reason = ""
        self._state_path = None
        self._state_error = False

    def attach_state(self, path):
        """Restore only this account's plugin-owned, credential-free budget."""
        path = Path(path).resolve()
        with self._lock:
            if self._state_path == path and not self._state_error:
                return
            if self._state_path is not None and self._state_path != path:
                self._defer("local_state", 900, "115账号预算已绑定其它文件，云端操作暂停")
            self._state_error = True
            try:
                state = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
                if state is not None:
                    if not isinstance(state, dict) or state.get("version") != 1:
                        raise ValueError("invalid budget format")
                    saved_at = float(state["saved_at"])
                    if not math.isfinite(saved_at):
                        raise ValueError("invalid clock")
                    elapsed = max(0, self.wall_clock() - saved_at)
                    now = self.clock()
                    for key, target, maximum in (("requests", self._request_times, self.max_requests),
                                                 ("submissions", self._submission_times, self.max_submissions)):
                        rows = state.get(key)
                        if not isinstance(rows, list) or len(rows) > maximum:
                            raise ValueError("invalid request history")
                        recovered = []
                        for stamp in rows:
                            value = float(stamp)
                            if not math.isfinite(value) or value > saved_at + 1:
                                raise ValueError("invalid request timestamp")
                            age = max(0, saved_at - value) + elapsed
                            if age < self.window:
                                recovered.append(now - age)
                        # An existing account object may already have admissions.
                        target.extend(recovered)
                        recovered_order = sorted(target)
                        target.clear()
                        target.extend(recovered_order[-maximum:])
                    remaining = float(state.get("cooldown_remaining", 0)) - elapsed
                    if not math.isfinite(remaining):
                        raise ValueError("invalid cooldown")
                    if remaining > 0 and now + remaining >= self._cooldown_until:
                        self._cooldown_until = now + remaining
                        self._cooldown_reason = str(state.get("cooldown_reason") or "cooldown")
                path.parent.mkdir(parents=True, exist_ok=True)
                self._state_path = path
                self._persist()
                self._state_error = False
            except P115Deferred:
                raise
            except Exception as exc:
                self._defer("local_state", 900, "115账号预算文件无法读取或保存，云端操作暂停")

    def _persist(self):
        if self._state_path is None:
            return
        now, wall = self.clock(), self.wall_clock()
        # Discard expired entries even when persistence is triggered by a pause.
        requests = [stamp for stamp in self._request_times if stamp > now - self.window]
        submissions = [stamp for stamp in self._submission_times if stamp > now - self.window]
        state = {"version": 1, "saved_at": wall,
                 "requests": [wall - max(0, now - stamp) for stamp in requests],
                 "submissions": [wall - max(0, now - stamp) for stamp in submissions],
                 "cooldown_remaining": max(0, self._cooldown_until - now),
                 "cooldown_reason": self._cooldown_reason if self._cooldown_until > now else ""}
        temp = self._state_path.with_name(self._state_path.name + "." + uuid.uuid4().hex + ".tmp")
        try:
            with temp.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(state, handle, ensure_ascii=False, separators=(",", ":"))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, self._state_path)
        except Exception:
            self._state_error = True
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            self._defer("local_state", 900, "115账号预算无法持久化，未继续发送请求")

    def _defer(self, reason: str, delay: float, message: str, uncertain=False):
        raise P115Deferred(message, reason=reason,
                           retry_at=self.wall_clock() + max(0, delay), uncertain=uncertain)

    def _check(self, work: Optional[WorkSlice]):
        now = self.clock()
        if self._state_error:
            self._defer("local_state", 900, "115账号预算文件尚未恢复，云端操作暂停")
        if work and work.cancelled and work.cancelled():
            self._defer("cancelled", 2, "任务已停用或配置已更新，未发出后续115请求")
        if self._cooldown_until > now:
            self._defer(self._cooldown_reason, self._cooldown_until - now,
                        "115账号正在冷却，已暂停本插件云端请求")
        if work and (work.requests >= work.max_requests or
                     now - work.started >= work.max_seconds):
            self._defer("slice", 2, "本轮115工作预算已用完，等待续作")

    @contextmanager
    def work_slice(self, *, cancelled=None, max_requests=5, max_seconds=15):
        previous = getattr(self._local, "work", None)
        if previous is not None:
            yield previous
            return
        work = WorkSlice(self.clock(), min(5, max_requests), min(15, max_seconds), cancelled)
        self._local.work = work
        try:
            yield work
        finally:
            self._local.work = previous

    @property
    def current_slice(self):
        return getattr(self._local, "work", None)

    def claim_submission(self):
        with self._lock:
            now = self.clock()
            self._check(self.current_slice)
            while self._submission_times and self._submission_times[0] <= now - self.window:
                self._submission_times.popleft()
            if len(self._submission_times) >= self.max_submissions:
                self._defer("submission_budget", self._submission_times[0] + self.window - now,
                            "本账号新资源提交额度已用完，等待续作")
            self._submission_times.append(now)
            self._persist()

    def pause(self, reason: str, seconds: float = 900):
        with self._lock:
            until = self.clock() + max(2, seconds)
            if until >= self._cooldown_until:
                self._cooldown_until, self._cooldown_reason = until, reason
                self._persist()

    def snapshot(self):
        with self._lock:
            return {"reason": self._cooldown_reason if self._cooldown_until > self.clock() else "",
                    "retry_at": self.wall_clock() + max(0, self._cooldown_until - self.clock()),
                    "request_count": len(self._request_times)}

    @contextmanager
    def request(self):
        with self._lock:
            work = self.current_slice
            self._check(work)
            now = self.clock()
            while self._request_times and self._request_times[0] <= now - self.window:
                self._request_times.popleft()
            if len(self._request_times) >= self.max_requests:
                self._defer("account_budget", self._request_times[0] + self.window - now,
                            "本账号115请求额度已用完，等待续作")
            gap = max(0, (self._request_times[-1] + self.min_interval - now)
                      if self._request_times else 0)
            if work and now + gap - work.started >= work.max_seconds:
                self._defer("slice", 2, "本轮115工作时间预算已用完，等待续作")
            if gap:
                self.sleep(gap)
            self._check(work)
            self._request_times.append(self.clock())
            if work:
                work.requests += 1
            # Durable admission precedes every actual HTTP request, including
            # Plus-internal calls; reloading the plugin cannot reset the quota.
            self._persist()
            yield


_ACCOUNTS = {}
_ACCOUNTS_LOCK = threading.Lock()


# Cookie fields that identify one 115 account across cookie refreshes, in
# order of preference. UID's "_A1_..." suffix differs per login and is dropped.
_IDENTITY_FIELDS = ("UID", "USERID", "USER_ID", "USERSESSIONID")


def account_identity(cookie: str) -> str:
    """Stable, credential-free key for one account.

    Uses UID (account part) or another stable account field. Without one we can
    only hash the sorted cookie pairs; that key changes whenever the cookie is
    refreshed, so such a budget is not preserved across refreshes.
    """
    pairs = {}
    for part in str(cookie or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name and value.strip():
            pairs.setdefault(name.strip().upper(), value.strip())
    for name in _IDENTITY_FIELDS:
        value = pairs.get(name)
        if value:
            account = value.split("_")[0] if name == "UID" else value
            return hashlib.sha256(f"{name}:{account}".encode()).hexdigest()
    canonical = ";".join(f"{k}={v}" for k, v in sorted(pairs.items())) or str(cookie or "")
    return "cookie:" + hashlib.sha256(canonical.encode()).hexdigest()[:32]


def account_budget(cookie: str) -> AccountBudget:
    key = account_identity(cookie)
    with _ACCOUNTS_LOCK:
        return _ACCOUNTS.setdefault(key, AccountBudget())
