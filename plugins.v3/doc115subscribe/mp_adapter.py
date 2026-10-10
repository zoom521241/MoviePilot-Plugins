"""Read-only, bounded MoviePilot access owned exclusively by this plugin."""
from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from contextlib import contextmanager


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class MPDeferred(RuntimeError):
    def __init__(self, message, retry_at=0):
        super().__init__(message)
        self.retry_at = retry_at


class MPAdapter:
    """No mutation, retries, redirects, shared client changes or port storms."""
    ALLOWED = {"/api/v1/history/transfer", "/api/v1/subscribe/", "/api/v1/subscribe/list",
               "/api/v1/storage/directories", "/api/v1/storage/options"}

    def __init__(self, settings, *, clock=time.time, opener=None):
        self.settings, self.clock = settings, clock
        self.opener = opener or urllib.request.build_opener(_NoRedirect()).open
        self._lock = threading.Lock()
        self._calls = deque()
        self._port = None
        self._cooldown = 0
        self._slice_count = 0
        self._slice_deadline = 0
        self._cancelled = lambda: False
        self.last_error = ""
        self._subscribe_endpoint = "/api/v1/subscribe/"

    @contextmanager
    def work_slice(self, cancelled=lambda: False):
        if not self._lock.acquire(blocking=False):
            raise MPDeferred("MP读取已排队", self.clock() + 2)
        self._slice_count, self._slice_deadline = 0, self.clock() + 15
        self._cancelled = cancelled
        try:
            yield self
        finally:
            self._cancelled = lambda: False
            self._lock.release()

    def _permit(self):
        now = self.clock()
        while self._calls and self._calls[0] <= now - 60:
            self._calls.popleft()
        if self._cancelled():
            raise MPDeferred("插件已停止，取消后续MP读取", now + 60)
        if now < self._cooldown:
            raise MPDeferred("MP接口处于冷却", self._cooldown)
        if len(self._calls) >= 20:
            raise MPDeferred("等待MP读取额度", self._calls[0] + 60)
        if self._slice_deadline and (self._slice_count >= 5 or now >= self._slice_deadline):
            raise MPDeferred("MP读取切片已用尽", now + 2)
        self._calls.append(now)
        self._slice_count += 1

    def get(self, path, params=None):
        if path not in self.ALLOWED:
            raise ValueError("不允许的MP只读接口")
        token = str(getattr(self.settings, "API_TOKEN", "") or "").strip()
        if not token:
            raise MPDeferred("MP未配置API_TOKEN", self.clock() + 900)
        ports = [self._port] if self._port else list(dict.fromkeys(
            int(p) for p in (getattr(self.settings, "PORT", 0), 5001, 5000, 3000)
            if str(p).isdigit() and int(p) > 0))
        last = "MP接口不可用"
        for port in ports:
            self._permit()
            query = urllib.parse.urlencode(params or {})
            url = f"http://127.0.0.1:{port}{path}" + ("?" + query if query else "")
            req = urllib.request.Request(url, headers={"X-API-KEY": token,
                                                       "User-Agent": "MoviePilot-Doc115Subscribe"})
            try:
                with self.opener(req, timeout=8) as response:
                    # A redirect to login/another origin is not a successful API contract.
                    if hasattr(response, "geturl") and response.geturl() != url:
                        raise ValueError("MP只读接口发生重定向")
                    body = json.loads(response.read().decode("utf-8"))
                if not isinstance(body, dict) or body.get("success") is False:
                    raise ValueError("MP接口响应格式不兼容")
                self._port = port
                self.last_error = ""
                return body
            except urllib.error.HTTPError as exc:
                last = f"MP接口HTTP {exc.code}"
                self._cooldown = self.clock() + 900
                self.last_error = last
                raise MPDeferred(last, self._cooldown) from None
            except MPDeferred:
                raise
            except ValueError:
                last = "MP接口响应格式或重定向不兼容"
                self._cooldown = self.clock() + 900
                self.last_error = last
                raise MPDeferred(last, self._cooldown) from None
            except Exception:
                last = "MP接口连接或响应异常"
                if self._port:
                    self._cooldown = self.clock() + 900
                    self.last_error = last
                    raise MPDeferred(last, self._cooldown) from None
        self._cooldown = self.clock() + 900
        self.last_error = last
        raise MPDeferred(last, self._cooldown)

    @staticmethod
    def page(body):
        data = body.get("data", body)
        if isinstance(data, list):
            return data, None
        if not isinstance(data, dict):
            raise ValueError("MP分页响应不兼容")
        rows = data.get("list", data.get("items"))
        if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
            raise ValueError("MP分页缺少有效列表")
        total = data.get("total")
        return rows, int(total) if total is not None else None

    def diagnostics(self):
        return {"port_ready": bool(self._port), "cooldown_until": self._cooldown,
                "last_error": self.last_error, "calls_last_minute": len(self._calls)}
