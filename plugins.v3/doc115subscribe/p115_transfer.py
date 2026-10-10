"""115 网盘操作：分享链接转存 + 磁力/ed2k 离线下载。

复用 p115client，与仓库里 115 系列插件保持一致的调用方式：
  * 转存：share_extract_payload -> share_receive({share_code, receive_code, file_id, cid})
  * 离线：clouddownload_task_add_urls({"url[0]": url, "wp_path_id": cid})
目录一律是 **115 网盘上的路径**（不是本地路径），通过目录 ID 定位。
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import inspect
import json
import posixpath
import random
import re
import threading
import time
import zlib
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit, urlencode
from urllib.error import HTTPError
from urllib.request import Request, build_opener, HTTPCookieProcessor, HTTPRedirectHandler

try:
    from p115client import P115Client
    from p115client.util import share_extract_payload

    P115_AVAILABLE = True
except Exception:  # noqa: BLE001
    P115Client = None  # type: ignore
    share_extract_payload = None  # type: ignore
    P115_AVAILABLE = False

try:
    from .link_router import LINK_115_SHARE, LINK_ED2K, LINK_MAGNET
except ImportError:  # 直接作为顶层模块加载（脚本/单测）
    from link_router import LINK_115_SHARE, LINK_ED2K, LINK_MAGNET


_HEX_BT = re.compile(r"[0-9a-fA-F]{40}\Z")
_HEX_ED2K = re.compile(r"[0-9a-fA-F]{32}\Z")
_BASE32_BT = re.compile(r"[A-Za-z2-7]{32}\Z")
# ed2k://|file|<名称，可含空格>|<字节数>|<32位MD4>|[h=...|]...
_ED2K_HASH = re.compile(r"ed2k://\|file\|[^|]+\|\d+\|([0-9a-fA-F]{32})\|(?:[^\s]*)\Z", re.I)
_NOT_FOUND_CODES = {10014, 20009, 20013, 20018, 31001, 31003, 50015, 70005, 70008, 90008, 430004, 800001}
# 115「操作过于频繁 / 风控」类错误码：统一进入限流冷却，不在本进程内立即重试。
_RATE_LIMIT_CODES = {429, 590075, 990005, 990009, 990019, 40110000}
# 离线任务「已存在 / 重复提交」错误码（真实接口 errcode=10008：任务已存在）。
_DUPLICATE_CODES = {10008}
# 115 离线任务 status 约定：-1 失败，0 等待，1 下载中，2 已完成。
_TASK_FAILED_STATUS = ("-1", "-2", "failed", "error", "cancelled", "canceled")


def normalize_info_hash(value: str) -> str:
    """Canonical lowercase hex: 40-char BTIH, base32 BTIH or 32-char ED2K MD4."""
    value = str(value or "").strip()
    if _HEX_BT.fullmatch(value) or _HEX_ED2K.fullmatch(value):
        return value.lower()
    if _BASE32_BT.fullmatch(value):
        return base64.b32decode(value.upper()).hex()
    return ""


def extract_hash(url: str) -> str:
    """从磁力/ed2k 链接里取信息哈希，用于和 115 离线任务匹配。"""
    u = (url or "").strip()
    if u.lower().startswith("magnet:?"):
        query = parse_qs(urlsplit(u).query)
        for xt in [value for key, values in query.items() if key.lower() == "xt" for value in values]:
            if xt.lower().startswith("urn:btih:"):
                value = xt[9:]
                if _HEX_BT.fullmatch(value):
                    return value.lower()
                if _BASE32_BT.fullmatch(value):
                    return base64.b32decode(value.upper()).hex()
        return ""
    match = _ED2K_HASH.fullmatch(u)
    return match.group(1).lower() if match else ""


def _normalize_task_url(url: str) -> str:
    """Comparable link text: unquote, strip wrapper prefixes/trailing slash, lowercase."""
    from urllib.parse import unquote
    u = unquote(str(url or "")).strip()
    low = u.lower()
    for prefix in ("https://", "http://"):
        if low.startswith(prefix) and low[len(prefix):].startswith(("ed2k://", "magnet:")):
            u, low = u[len(prefix):], low[len(prefix):]
    return u.rstrip("/").lower()


def _ed2k_name(url: str) -> str:
    from urllib.parse import unquote
    parts = str(url or "").split("|")
    return unquote(parts[2]).strip().lower() if len(parts) > 3 and parts[1].lower() == "file" else ""


def _ed2k_size(url: str) -> int:
    parts = str(url or "").split("|")
    try:
        return int(parts[3]) if len(parts) > 4 and parts[1].lower() == "file" else 0
    except ValueError:
        return 0


def match_task(task: Dict[str, Any], link: str = "", info_hash: str = "") -> bool:
    """Whether a 115 offline task belongs to ``link`` (magnet/ed2k) or ``info_hash``.

    BTIH 直接比较哈希。ed2k 的 32 位 MD4 在 115 列表里可能被换成 40 位内部哈希，
    此时回退比较规范化后的 url，最后比较 ed2k 文件名与任务 name。
    """
    if not isinstance(task, dict):
        return False
    wanted = normalize_info_hash(info_hash) or extract_hash(link)
    got = normalize_info_hash(task.get("info_hash") or task.get("hash") or "")
    if wanted and got and wanted == got:
        return True
    if not link:
        return False
    if got and wanted and len(got) == len(wanted):
        # Same hash family but different value: a different resource.
        return False
    task_url = task.get("url") or ""
    if task_url and _normalize_task_url(task_url) == _normalize_task_url(link):
        return True
    if task_url and wanted and extract_hash(_normalize_task_url(task_url)) == wanted:
        return True
    name = _ed2k_name(link)
    if not name or str(task.get("name") or "").strip().lower() != name:
        return False
    # 同名不等于同一资源（不同版本常同名）：名字回退必须再比对 ed2k 链接里的文件大小，
    # 任务没有大小或大小不一致都不认，宁可等待也不误搬运别人的文件。
    want_size = _ed2k_size(link)
    try:
        got_size = int(task.get("size") or task.get("file_size") or 0)
    except (TypeError, ValueError):
        got_size = 0
    return bool(want_size) and want_size == got_size


_115_SHARE_RE = re.compile(
    r"https?://(?:[A-Za-z0-9-]+\.)*(?:115|115cdn|anxia)\.com(?::(?:80|443))?/s/([A-Za-z0-9]+)/?"
    r"(?:\?(?:[^#]*&)?(?:password|pwd)=([A-Za-z0-9]{4})[^#]*)?(?:#.*)?\Z", re.I)


def normalize_115_share(url: str) -> str:
    """115.com / 115cdn.com / anxia.com（含子域）分享统一成 https://115.com/s/<code>?password=xxxx。

    与 link_router.normalize_115_share 的规范化目标一致，p115client 可直接解析分享码。
    """
    u = (url or "").strip()
    m = _115_SHARE_RE.fullmatch(u)
    if not m:
        return u.replace("115cdn.com/s/", "115.com/s/").replace("//115cdn.com", "//115.com")
    return f"https://115.com/s/{m.group(1)}" + (f"?password={m.group(2)}" if m.group(2) else "")


try:
    from .request_budget import P115Error, P115Deferred, account_budget, account_identity
except ImportError:  # standalone inspection/test import without changing sys.path
    import importlib.util
    import sys
    _budget_name = "_doc115subscribe_request_budget"
    if _budget_name not in sys.modules:
        _budget_spec = importlib.util.spec_from_file_location(
            _budget_name, Path(__file__).with_name("request_budget.py"))
        _budget_module = importlib.util.module_from_spec(_budget_spec)
        sys.modules[_budget_name] = _budget_module
        _budget_spec.loader.exec_module(_budget_module)
    _budget_module = sys.modules[_budget_name]
    P115Error, P115Deferred = _budget_module.P115Error, _budget_module.P115Deferred
    account_budget = _budget_module.account_budget
    account_identity = _budget_module.account_identity


class P115NotFound(P115Error):
    """Confirmed absent path, distinct from an unavailable listing."""


def _response_codes(resp: Dict[str, Any]) -> List[int]:
    codes = []
    for name in ("errno", "errcode", "code", "error_code"):
        try:
            value = int(resp.get(name) or 0)
        except (TypeError, ValueError):
            continue
        if value:
            codes.append(value)
    return codes


def _account_failure(resp: Dict[str, Any]) -> str:
    codes = set(_response_codes(resp))
    message = str(resp.get("error_msg") or resp.get("error") or resp.get("message") or resp.get("msg") or "").lower()
    if codes & {99, 401, 403, 990001, 40140125} or any(
        text in message for text in ("请重新登录", "登陆超时", "登录超时", "not logged", "authentication")):
        return "authentication"
    if codes & _RATE_LIMIT_CODES or any(text in message for text in (
            "操作太频繁", "请求太频繁", "操作过于频繁", "访问过于频繁", "请求过于频繁", "rate limit", "too many requests")):
        return "rate_limit"
    if 911 in codes or any(text in message for text in ("请验证账号", "风控", "验证码", "账号异常")):
        return "risk_control"
    return ""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # No automatic hidden second HTTP request, especially for write calls.
        return None


class _BudgetTransport:
    """The SDK's supported request callback, with no retry or hidden redirect."""
    def __init__(self, budget, timeout):
        self.budget, self.timeout = budget, timeout
        self.local = threading.local()

    def _pause_uncertain(self):
        try:
            self.budget.pause("uncertain", 60)
        except P115Deferred as exc:
            # A disk failure after a lost network response cannot turn the
            # already-sent write back into a safe-to-resend operation.
            exc.uncertain, exc.not_sent = True, False
            raise

    def __call__(self, *, url, method="GET", params=None, data=None, json=None,
                 headers=None, cookies=None, parse=True, async_=False,
                 follow_redirects=False, raise_for_status=True, **kwargs):
        if async_ or kwargs.get("files"):
            raise P115Deferred("当前SDK请求契约不兼容，已暂停本插件云端操作", reason="capability")
        if params:
            query = params if isinstance(params, str) else urlencode(params, doseq=True)
            url = str(url) + ("&" if "?" in str(url) else "?") + query
        request_headers = dict(headers or {})
        request_headers["accept-encoding"] = "gzip, deflate"
        if json is not None:
            data = __import__("json").dumps(json).encode()
            request_headers.setdefault("content-type", "application/json")
        elif data is not None and not isinstance(data, (str, bytes, bytearray, memoryview)):
            data = urlencode(data, doseq=True).encode()
            request_headers.setdefault("content-type", "application/x-www-form-urlencoded")
        if isinstance(data, str):
            data = data.encode()
        handlers = [_NoRedirect()]
        if cookies is not None:
            handlers.append(HTTPCookieProcessor(cookies))
        opener = build_opener(*handlers)
        operation = getattr(self.local, "operation", "")
        path = urlsplit(str(url)).path.lower()
        writing = method.upper() not in ("GET", "HEAD") and (
            operation in {"share_receive", "clouddownload_task_add_urls", "fs_makedirs_app"} or any(
                term in path for term in ("/move", "/rename", "/add_task", "/receive", "/mkdir", "/add_path", "/add_urls")))
        # Creating a directory is re-entrant: a lost reply is reconciled by a
        # read (fs_dir_getid) before any retry, so it is not an uncertain write.
        idempotent = writing and (operation == "fs_makedirs_app" or (
            not operation and any(term in path for term in ("/mkdir", "/add_path"))))
        with self.budget.request():
            if writing:
                callback = getattr(self.local, "before_submit", None)
                if callback:
                    # A failed durable intent callback must prevent the write.
                    callback(getattr(self.local, "intent", {}))
                self.local.write_attempted = True
            try:
                with opener.open(Request(str(url), data=data, headers=request_headers, method=method),
                                 timeout=self.timeout) as response:
                    content = response.read()
                    encoding = response.headers.get("content-encoding", "").lower()
                    if encoding == "gzip":
                        content = gzip.decompress(content)
                    elif encoding == "deflate":
                        content = zlib.decompress(content)
                    if callable(parse):
                        try:
                            arity = len(inspect.signature(parse).parameters)
                        except (TypeError, ValueError):
                            arity = 2
                        result = parse(response, content) if arity >= 2 else parse(response)
                    elif parse is False:
                        result = content
                    elif parse is None or parse is Ellipsis:
                        raise P115Error("本插件不使用流式SDK响应")
                    else:
                        result = __import__("json").loads(content)
                    reason = _account_failure(result) if isinstance(result, dict) else ""
                    if reason:
                        self.budget.pause(reason, 900 if reason != "rate_limit" else 300)
                        state = self.budget.snapshot()
                        raise P115Deferred("115鉴权、限流或风控响应，已暂停本账号请求",
                                           reason=reason, retry_at=state["retry_at"], not_sent=not writing)
                    if writing:
                        self.local.write_completed = True
                    return result
            except P115Deferred:
                raise
            except HTTPError as exc:
                reason = "authentication" if exc.code in (401, 403) else "rate_limit" if exc.code == 429 else ""
                if reason:
                    try:
                        delay = float(exc.headers.get("Retry-After", 300))
                    except (ValueError, TypeError):
                        delay = 300
                    self.budget.pause(reason, max(300, delay) if reason == "rate_limit" else 900)
                    raise P115Deferred("115账号鉴权或限流，已暂停后续请求", reason=reason,
                                       retry_at=self.budget.snapshot()["retry_at"], not_sent=not writing) from exc
                if idempotent:
                    raise P115Deferred("115建目录响应未确认，将先核对目录再重试", reason="reconcile",
                                       retry_at=time.time() + 2, uncertain=False, not_sent=True) from exc
                if writing:
                    self._pause_uncertain()
                    raise P115Deferred("115写操作响应未确认，等待对账，未重试", reason="uncertain",
                                       retry_at=self.budget.snapshot()["retry_at"], uncertain=True) from exc
                raise P115Error(f"115查询HTTP响应错误：{exc.code}") from exc
            except P115Error:
                raise
            except Exception as exc:
                if idempotent:
                    raise P115Deferred("115建目录响应丢失，将先核对目录再重试", reason="reconcile",
                                       retry_at=time.time() + 2, uncertain=False, not_sent=True) from exc
                if writing:
                    self._pause_uncertain()
                    raise P115Deferred("115写操作响应丢失，等待对账，未重试", reason="uncertain",
                                       retry_at=self.budget.snapshot()["retry_at"], uncertain=True) from exc
                raise P115Error(f"115查询请求失败：{type(exc).__name__}") from exc


def _private_client(cookie, transport):
    """Only this instance is adapted; no global SDK or Plus monkeypatch."""
    base_request = getattr(P115Client, "request", None)
    try:
        params = inspect.signature(base_request).parameters
        if "request" not in params or "async_" not in params:
            raise ValueError("unsupported request callback")
        for name in ("fs_file", "fs_files", "fs_dir_getid", "share_snap", "share_receive",
                     "clouddownload_task_list", "clouddownload_task_add_urls", "fs_move", "fs_move_app", "fs_makedirs_app"):
            if not callable(getattr(P115Client, name, None)):
                raise ValueError("missing SDK capability")
            source = inspect.getsource(getattr(P115Client, name))
            route = re.search(r"self\.(?:request|clouddownload_request|fs_move)\s*\(|request_kwargs\[['\"]self['\"]\]\s*=\s*self", source)
            if not route:
                raise ValueError("uncontrolled SDK endpoint")
        if hasattr(P115Client, "clouddownload_request"):
            for name in ("_clouddownload_web_request", "_clouddownload_request", "_clouddownload_lixianssp_request"):
                source = inspect.getsource(getattr(P115Client, name))
                if "self.request(" not in source:
                    raise ValueError("uncontrolled offline SDK endpoint")
    except (AttributeError, OSError, TypeError, ValueError):
        raise P115Deferred("已安装的115 SDK不兼容；搜索可用，云端获取与搬运已暂停", reason="capability")

    class _PrivateP115Client(P115Client):
        def request(self, *args, **kwargs):
            if kwargs.get("async_"):
                raise P115Deferred("本插件仅支持受控同步115请求", reason="capability")
            kwargs["request"] = transport
            try:
                return base_request(self, *args, **kwargs)
            except P115Deferred as exc:
                transport.local.last_deferred = exc
                raise

    client = _PrivateP115Client(cookie)
    client._doc115_budget_transport = transport
    return client


@dataclass
class OfflineSubmission:
    accepted: bool = False
    duplicate: bool = False
    info_hash: str = ""
    link: str = ""
    task: Dict[str, Any] = field(default_factory=dict)
    file_id: str = ""
    requested_cid: str = ""
    actual_cid: str = ""
    save_path: str = ""
    message: str = ""
    recoverable: bool = False
    uncertain: bool = False
    recovery_pending: bool = False
    recovery_cursor: Optional[Dict[str, Any]] = None

    def __bool__(self) -> bool:
        return self.accepted or self.recoverable

    def as_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


class _RateLimiter:
    def __init__(self, min_interval: float = 1.2, jitter: float = 0.3):
        self.min_interval = min_interval
        self.jitter = jitter
        self._last = 0.0
        self._lock = threading.Lock()

    def wait(self):
        with self._lock:
            gap = max(0.0, self.min_interval + random.uniform(-self.jitter, self.jitter))
            delta = time.monotonic() - self._last
            if delta < gap:
                time.sleep(gap - delta)
            self._last = time.monotonic()


_LIMITERS: Dict[str, _RateLimiter] = {}
_LIMITERS_LOCK = threading.Lock()


def _shared_limiter(cookie: str) -> _RateLimiter:
    # Different cookie strings for one account (e.g. refresh) still share a
    # limiter when UID is available; never retain credentials as dictionary keys.
    key = account_identity(cookie)
    with _LIMITERS_LOCK:
        return _LIMITERS.setdefault(key, _RateLimiter())


class _ThreadLocalAttr:
    """Per-thread instance attribute: one worker never reads another's last_* result."""

    def __init__(self, default=lambda: None):
        self.default = default
        self.name = ""

    def __set_name__(self, owner, name):
        self.name = name

    @staticmethod
    def _local(instance):
        # dict.setdefault is atomic, so concurrent first use shares one local.
        return instance.__dict__.setdefault("_doc115_thread_state", threading.local())

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        local = self._local(instance)
        if not hasattr(local, self.name):
            setattr(local, self.name, self.default())
        return getattr(local, self.name)

    def __set__(self, instance, value):
        setattr(self._local(instance), self.name, value)


class P115Transfer:
    """115 网盘操作封装。

    ``last_*`` 回执与离线分页游标按线程隔离；目录缓存与分享续作状态在实例内共享并加锁。
    """

    last_offline_result = _ThreadLocalAttr()
    last_share_names = _ThreadLocalAttr(list)
    last_share_result = _ThreadLocalAttr(dict)
    last_tasks_skipped = _ThreadLocalAttr(int)
    _task_cursor = _ThreadLocalAttr()

    @property
    def _state_lock(self):
        return self.__dict__.setdefault("_doc115_state_lock", threading.RLock())

    def __init__(self, cookie: str, timeout: int = 30):
        if not P115_AVAILABLE:
            raise P115Deferred("未安装兼容的115网盘Plus SDK；搜索可用，云端获取暂不可用", reason="capability")
        if not cookie:
            raise P115Error("缺少 115 Cookie")
        self.timeout = max(1.0, float(timeout))
        self._budget = account_budget(cookie)
        self._transport = _BudgetTransport(self._budget, self.timeout)
        self.client = _private_client(cookie, self._transport)
        self._limiter = _shared_limiter(cookie)
        self._dir_cache: Dict[str, int] = {}
        self._dir_cache_times: Dict[str, float] = {}
        self._p115_api = None
        self._share_states: Dict[str, Dict[str, Any]] = {}

    @contextmanager
    def work_slice(self, *, cancelled=None, max_requests=5, max_seconds=15):
        """Use around a resumable worker stage; reads cache only in this slice."""
        with self._budget.work_slice(cancelled=cancelled, max_requests=max_requests,
                                     max_seconds=max_seconds) as work:
            yield work

    @property
    def budget_state(self):
        return self._budget.snapshot()

    def attach_state(self, path):
        self._budget.attach_state(path)

    def _timeout_kwargs(self) -> Dict[str, Any]:
        """Older p115client uses httpcore extensions; newer versions accept timeout."""
        try:
            provider = self.client.request.__func__.__globals__.get("get_request")
            source = inspect.getsource(provider).lower()
        except (AttributeError, OSError, TypeError):
            source = ""
        if ("httpcore_request" in source or "httpx_request" in source) and "urllib3_future_request" not in source:
            return {"extensions": {"timeout": {
                "connect": self.timeout, "read": self.timeout,
                "write": self.timeout, "pool": self.timeout,
            }}}
        return {"timeout": self.timeout}

    def _call(self, name: str, *args, before_submit=None, intent=None) -> Dict[str, Any]:
        transport = getattr(self, "_transport", None)
        if transport:
            transport.local.operation = name
            transport.local.before_submit = before_submit
            transport.local.intent = intent or {}
        else:  # explicit __new__ test doubles, never the production constructor
            self._limiter.wait()
            if before_submit:
                before_submit(intent or {})
        try:
            result = getattr(self.client, name)(*args, **self._timeout_kwargs())
        except P115Deferred:
            raise
        except FileNotFoundError as exc:
            raise P115NotFound(f"115 {name} 确认路径不存在") from exc
        except Exception as exc:
            raise P115Error(f"115 {name} 请求失败：{type(exc).__name__}") from exc
        finally:
            if transport:
                transport.local.operation = ""
                transport.local.before_submit = None
                transport.local.intent = {}
        if not isinstance(result, dict):
            raise P115Error(f"115 {name} 返回格式错误")
        reason = _account_failure(result)
        if reason and hasattr(self, "_budget"):
            self._budget.pause(reason, 300 if reason == "rate_limit" else 900)
            raise P115Deferred("115账号鉴权、限流或风控，已暂停后续请求", reason=reason,
                               retry_at=self._budget.snapshot()["retry_at"])
        return result

    @staticmethod
    def _error(resp: Dict[str, Any]) -> str:
        text = str(resp.get("error_msg") or resp.get("error") or resp.get("message") or resp.get("msg") or "")
        codes = _response_codes(resp)
        if set(codes) & _DUPLICATE_CODES:
            # Recognised by _DUP_WORDS even when 115 sends only the code.
            return f"任务已存在（{text}）" if text and "已存在" not in text else (text or "任务已存在")
        return text or (str(codes[0]) if codes else "未知错误")

    @classmethod
    def _require_success(cls, resp: Dict[str, Any], operation: str) -> None:
        if resp.get("state") in (False, 0, "0") or resp.get("success") is False:
            try:
                absent = int(resp.get("errno", resp.get("errcode", 0))) in _NOT_FOUND_CODES
            except (TypeError, ValueError):
                absent = False
            if absent:
                raise P115NotFound(f"{operation}失败：{cls._error(resp)}")
            raise P115Error(f"{operation}失败：{cls._error(resp)}")
        error_code = resp.get("errno", resp.get("errcode", 0))
        if error_code not in (None, 0, "0", ""):
            raise P115Error(f"{operation}失败：{cls._error(resp)}")

    @staticmethod
    def _total(resp: Dict[str, Any], data: Any = None) -> Optional[int]:
        for source in (data, resp):
            if isinstance(source, dict):
                for name in ("count", "total", "total_count"):
                    if source.get(name) is not None:
                        try:
                            return max(0, int(source[name]))
                        except (TypeError, ValueError):
                            raise P115Error("115 分页总数格式错误")
        return None

    # -- 基础 ---------------------------------------------------------------
    def check_login(self) -> bool:
        try:
            resp = self._call("user_info")
            self._require_success(resp, "登录校验")
            return bool(resp) and resp.get("state") not in (False, 0, "0")
        except Exception:  # noqa: BLE001
            return False

    def _remember_directory(self, path: str, cid: int):
        with self._state_lock:
            self._dir_cache[path] = int(cid)
            if hasattr(self, "_dir_cache_times"):
                self._dir_cache_times[path] = time.time()

    def _cached_directory(self, path: str, refresh: bool = False) -> Optional[int]:
        if refresh:
            return None
        with self._state_lock:
            fresh = not hasattr(self, "_dir_cache_times") or time.time() - self._dir_cache_times.get(path, 0) < 300
            return self._dir_cache.get(path) if fresh else None

    def _forget_directory_tree(self, src: str):
        with self._state_lock:
            for cached in list(self._dir_cache):
                if cached == src or cached.startswith(src + "/"):
                    self._dir_cache.pop(cached, None)
                    getattr(self, "_dir_cache_times", {}).pop(cached, None)

    def path_to_id(self, path: str, mkdir: bool = True, refresh: bool = False) -> int:
        """115 目录路径 -> 目录 ID（必要时逐级创建）。根目录为 0。"""
        p = (path or "").replace("\\", "/")
        if not p.startswith("/"):
            p = "/" + p
        p = p.rstrip("/")
        if p in ("", "/"):
            return 0
        cached = self._cached_directory(p, refresh)
        if cached is not None:
            return cached
        resp = self._call("fs_dir_getid", p)
        try:
            self._require_success(resp, "目录查询")
        except P115NotFound:
            if not mkdir:
                raise
            resp = {"id": 0}
        if str(resp.get("id") or "0") != "0":
            cid = int(resp["id"])
            self._remember_directory(p, cid)
            return cid
        if "id" not in resp:
            raise P115Error("目录查询返回缺少 id")
        if not mkdir:
            raise P115NotFound(f"目录不存在：{p}")
        # 逐级创建
        cur = 0
        built = ""
        for part in [x for x in p.split("/") if x]:
            built = f"{built}/{part}"
            cached = self._cached_directory(built, refresh)
            if cached is not None:
                cur = cached
                continue
            r = self._call("fs_dir_getid", built)
            try:
                self._require_success(r, "目录查询")
            except P115NotFound:
                r = {"id": 0}
            if str(r.get("id") or "0") != "0":
                cur = int(r["id"])
                self._remember_directory(built, cur)
                continue
            if "id" not in r:
                raise P115Error("目录查询返回缺少 id")
            try:
                r2 = self._call("fs_makedirs_app", built)
            except P115Deferred as exc:
                if exc.reason != "reconcile":
                    raise
                cur = self._reconcile_directory(built, exc)
                continue
            except P115NotFound:
                raise
            except P115Error as exc:
                # Transport failure of a re-entrant mkdir: read before retrying.
                cur = self._reconcile_directory(built, exc)
                continue
            self._require_success(r2, "创建目录")
            data = r2.get("data") if isinstance(r2.get("data"), dict) else r2
            cid = data.get("cid") or data.get("id")
            if not cid:
                raise P115Error(f"创建目录失败：{built} -> {r2}")
            cur = int(cid)
            self._remember_directory(built, cur)
        self._remember_directory(p, cur)
        return cur

    def _reconcile_directory(self, path: str, error: Exception) -> int:
        """After a lost mkdir reply: existing directory is success; absent means retry later."""
        resp = self._call("fs_dir_getid", path)
        try:
            self._require_success(resp, "目录对账")
        except P115NotFound:
            resp = {"id": 0}
        if str(resp.get("id") or "0") != "0":
            cid = int(resp["id"])
            self._remember_directory(path, cid)
            return cid
        if "id" not in resp:
            raise P115Error("目录对账返回缺少 id") from error
        raise P115Deferred(f"创建目录未确认且目录不存在，稍后重试：{path}", reason="reconcile",
                           retry_at=time.time() + 30, uncertain=False, not_sent=True) from error

    # -- 转存 ---------------------------------------------------------------
    def check_share(self, share_url: str) -> Tuple[bool, str]:
        """只读校验分享是否可用，返回 (是否可用, 不可用原因)。

        115 对「分享已取消 / 已过期 / 提取码错误」等情况，在转存接口里只回一句
        「参数错误」，很难排查；先探一次分享信息，就能给出确切原因。

        ⚠️ 必须用 ``share_snap``（``/share/snap``，第三方分享接口）而不是
        ``share_info``（``/share/shareinfo``，**只能查当前账号自己的分享**）：
        用 share_info 查别人的分享，115 一律返回「分享已取消」，会把
        **所有**第三方 115 分享误判为失效。
        """
        url = normalize_115_share(share_url)
        try:
            info = share_extract_payload(url)
        except Exception:
            return False, "无法解析分享链接"
        code = info.get("share_code")
        if not code:
            return False, "无法解析分享链接"
        try:
            resp = self._call("share_snap", {
                "share_code": code,
                "receive_code": info.get("receive_code") or "",
                "cid": 0,
                "limit": 1,
                "offset": 0,
            })
            self._require_success(resp, "分享查询")
        except Exception as exc:
            return False, str(exc)
        if resp.get("state") in (True, 1, "1"):
            return True, ""
        err = str((resp or {}).get("error") or (resp or {}).get("errno") or "分享不可用")
        return False, err

    def share_items(self, share_code: str, receive_code: str) -> List[Dict[str, Any]]:
        """读分享内的条目列表：[{"id": 真实id, "name": 名称, "is_dir": 是否文件夹}]。

        115 转存需要**真实条目 id**（文件夹取 ``cid``、文件取 ``fid``）。只读接口。
        """
        out: List[Dict[str, Any]] = []
        seen = set()
        offset = 0
        for _page in range(10000):
            resp = self._call("share_snap", {
                "share_code": share_code,
                "receive_code": receive_code,
                "cid": 0,
                "limit": 200,
                "offset": offset,
            })
            self._require_success(resp, "读取分享目录")
            data = resp.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                raise P115Error("分享目录返回格式错误")
            entries = data["list"]
            total = self._total(resp, data)
            if not entries:
                if total is not None and offset < total:
                    raise P115Error(f"分享目录分页不完整：已读 {offset}/{total}")
                return out
            added = 0
            for it in entries:
                if not isinstance(it, dict):
                    raise P115Error("分享条目格式错误")
                fid = it.get("fid") or it.get("id") or it.get("cid")
                if not fid:
                    raise P115Error("分享条目缺少真实 ID，已停止转存")
                if str(fid) in seen:
                    continue
                seen.add(str(fid))
                added += 1
                out.append({
                    "id": str(fid),
                    "name": str(it.get("n") or it.get("fn") or it.get("file_name") or ""),
                    "is_dir": str(it.get("fc")) == "0" or (not it.get("fid") and bool(it.get("cid"))),
                })
            if not added:
                raise P115Error("分享目录分页重复，已停止以免漏转存")
            offset += len(entries)
            if total is not None and offset >= total:
                return out
        raise P115Error("分享目录超过分页保护上限，未执行转存")

    def _share_item_ids(self, share_code: str, receive_code: str) -> List[str]:
        """取分享内所有条目的 id（文件夹取 ``cid``、文件取 ``fid``）。

        ⚠️ 转存时 ``file_id`` 必须传这些**真实 id**。传 ``"0"`` 只在部分单文件分享上凑巧可用；
        当分享里是**文件夹**（例如整季剧集）时会直接返回「参数错误」。
        """
        return [it["id"] for it in self.share_items(share_code, receive_code)]

    def prepare_share(self, share_url: str, save_path: str, state=None) -> Dict[str, Any]:
        """Resume root enumeration; never receive an incomplete share."""
        info = share_extract_payload(normalize_115_share(share_url))
        code, password = info.get("share_code"), info.get("receive_code") or ""
        if not code:
            raise P115Error("无法解析分享链接")
        identity = hashlib.sha256((str(code) + "\0" + save_path).encode()).hexdigest()
        state = dict(state or {"identity": identity, "items": [], "cursor": 0,
                               "complete": False, "received": 0, "done": False})
        state["items"] = list(state.get("items") or [])
        if state.get("identity") != identity:
            raise P115Error("分享续作身份不匹配，未执行转存")
        try:
            if not state.get("complete"):
                seen = {it["id"] for it in state["items"]}
                for _ in range(3):
                    verify = state.get("verify", False)
                    resp = self._call("share_snap", {"share_code": code, "receive_code": password,
                         "cid": 0, "limit": 200, "offset": 0 if verify else state["cursor"]})
                    self._require_success(resp, "读取分享目录")
                    data = resp.get("data")
                    if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                        raise P115Error("分享目录返回格式错误")
                    entries = data["list"]
                    total = self._total(resp, data)
                    if "total" in state and total != state["total"]:
                        raise P115Error("分享分页总数变化，需重新读取，未执行转存")
                    state["total"] = total
                    page_ids = [str(item.get("fid") or item.get("id") or item.get("cid") or "")
                                for item in entries if isinstance(item, dict)]
                    if verify:
                        if page_ids != state["first_page"]:
                            raise P115Error("分享分页顺序变化，未执行转存")
                        state["complete"] = True
                        state.pop("verify", None)
                        break
                    if state["cursor"] == 0:
                        state["first_page"] = page_ids
                    if not entries:
                        if total is not None and state["cursor"] < total:
                            raise P115Error("分享分页不完整，未执行转存")
                        if state["cursor"] <= 200:
                            state["complete"] = True
                            break
                        state["verify"] = True
                        continue
                    for item in entries:
                        if not isinstance(item, dict):
                            raise P115Error("分享条目格式错误")
                        fid = str(item.get("fid") or item.get("id") or item.get("cid") or "")
                        if not fid.isdigit() or int(fid) <= 0 or fid in seen:
                            raise P115Error("分享条目缺少ID或分页发生重叠，未执行转存")
                        seen.add(fid)
                        state["items"].append({"id": fid,
                            "name": str(item.get("n") or item.get("fn") or item.get("file_name") or ""),
                            "is_dir": str(item.get("fc")) == "0" or (not item.get("fid") and bool(item.get("cid")))})
                    state["cursor"] += len(entries)
                    if total is not None and state["cursor"] >= total:
                        if state["cursor"] <= len(entries):
                            state["complete"] = True
                            break
                        state["verify"] = True
            if state.get("complete"):
                if not state["items"]:
                    raise P115Error("分享目录为空，未执行转存")
                if not state.get("cid"):
                    state["cid"] = self.path_to_id(save_path, mkdir=True)
                    state["cid_verified_at"] = time.time()
            return state
        except P115Deferred as exc:
            exc.state = state
            raise

    def receive_prepared(self, share_url: str, save_path: str, state: Dict[str, Any],
                         before_submit=None) -> Dict[str, Any]:
        """One batch of <=200 IDs; state is safe to persist after each receipt."""
        info = share_extract_payload(normalize_115_share(share_url))
        identity = hashlib.sha256((str(info.get("share_code")) + "\0" + save_path).encode()).hexdigest()
        if state.get("identity") != identity or not state.get("complete") or not state.get("cid"):
            raise P115Error("分享尚未完整枚举及确认目标目录，未执行转存")
        if state.get("uncertain"):
            raise P115Deferred("上一批转存响应未确认，禁止重复提交", reason="uncertain",
                               uncertain=True, state=state)
        state.setdefault("uncertain", False)
        offset = int(state.get("received") or 0)
        batch = state["items"][offset:offset + 200]
        if not batch:
            state["done"] = True
            return state
        try:
            if time.time() - state.get("cid_verified_at", time.time()) >= 300:
                current_cid = self.path_to_id(save_path, mkdir=False, refresh=True)
                if str(current_cid) != str(state["cid"]):
                    raise P115Deferred("目标目录身份已变化，转存暂停，请核实保存目录", reason="target_changed", state=state)
                state["cid_verified_at"] = time.time()
            if hasattr(self, "_budget") and not state.get("submission_claimed"):
                self._budget.claim_submission()
                state["submission_claimed"] = True
            def before(intent):
                if before_submit:
                    before_submit(intent)
                state["uncertain"] = True
            resp = self._call("share_receive", {"share_code": info["share_code"],
                "receive_code": info.get("receive_code") or "", "file_id": ",".join(it["id"] for it in batch),
                "cid": state["cid"], "is_check": 0}, before_submit=before,
                intent={"kind": "share_receive", "offset": offset, "count": len(batch)})
            state["uncertain"] = resp.get("state") not in (True, 1, "1", False, 0, "0")
            self._require_success(resp, "分享转存")
            if resp.get("state") not in (True, 1, "1"):
                raise P115Error("转存响应缺少明确成功标记，需人工核实")
            state["received"] = offset + len(batch)
            state["done"] = state["received"] >= len(state["items"])
            self.last_share_names = [it["name"] for it in state["items"][:state["received"]] if it["name"]]
            self.last_share_result = {"total": len(state["items"]), "received": state["received"],
                "failed": 0, "partial": not state["done"], "uncertain": False,
                "source_items": state["items"], "target_cid": str(state["cid"])}
            return state
        except P115Deferred as exc:
            state["uncertain"] = exc.uncertain
            exc.state = state
            raise
        except P115Error:
            self.last_share_result = {"total": len(state["items"]), "received": offset,
                "failed": len(state["items"]) - offset, "partial": offset > 0,
                "uncertain": state.get("uncertain", False)}
            raise

    def share_receive(self, share_url: str, save_path: str) -> bool:
        """把 115 分享链接整体转存到目标目录。"""
        if hasattr(self, "_budget"):
            key = hashlib.sha256((share_url + "\0" + save_path).encode()).hexdigest()
            with self._state_lock:
                state = self._share_states.get(key)
            try:
                state = self.prepare_share(share_url, save_path, state)
                with self._state_lock:
                    self._share_states[key] = state
                if not state["complete"]:
                    raise P115Deferred("分享分页未读完，等待续作", reason="pagination", state=state)
                state = self.receive_prepared(share_url, save_path, state)
                if not state["done"]:
                    raise P115Deferred("已收到部分转存回执，等待下一批", reason="slice", state=state)
                with self._state_lock:
                    self._share_states.pop(key, None)
                return True
            except P115Deferred as exc:
                if exc.state is not None:
                    with self._state_lock:
                        self._share_states[key] = exc.state
                raise
        self.last_share_names = []
        self.last_share_result = {}
        url = normalize_115_share(share_url)
        try:
            payload_info = share_extract_payload(url)
        except Exception as exc:
            raise P115Error("无法解析分享链接") from exc
        share_code = payload_info.get("share_code")
        receive_code = payload_info.get("receive_code") or ""
        if not share_code:
            raise P115Error(f"无法解析分享链接：{share_url}")
        # Enumerate and validate the complete share before creating directories
        # or sending any receive request; never fall back to ambiguous id "0".
        items = self.share_items(share_code, receive_code)
        if not items:
            raise P115Error("分享目录为空，未执行转存")
        cid = self.path_to_id(save_path, mkdir=True)
        completed = 0
        self.last_share_result = {"total": len(items), "received": 0, "failed": 0,
                                  "uncertain": False, "partial": False}
        for start in range(0, len(items), 200):
            batch = items[start:start + 200]
            last_err = ""
            try:
                self.last_share_result["uncertain"] = True
                resp = self._call("share_receive", {
                    "share_code": share_code, "receive_code": receive_code,
                    "file_id": ",".join(it["id"] for it in batch),
                    "cid": cid, "is_check": 0,
                })
            except P115Error as exc:
                # A transport error has an unknown server-side outcome.
                # Do not claim success or blindly resend the entire share.
                last_err = str(exc)
            else:
                if resp.get("state") in (True, 1, "1", False, 0, "0"):
                    self.last_share_result["uncertain"] = False
                if resp.get("state") in (True, 1, "1"):
                    completed += len(batch)
                    self.last_share_names.extend(it["name"] for it in batch if it["name"])
                    self.last_share_result["received"] = completed
                else:
                    last_err = self._error(resp)
            if completed != min(start + len(batch), len(items)):
                self.last_share_result["failed"] = len(items) - completed
                self.last_share_result["error"] = last_err
                self.last_share_result["partial"] = completed > 0
                raise P115Error(f"转存未完成（{completed}/{len(items)} 项）：{last_err}")
        return True

    # -- 离线下载 -----------------------------------------------------------
    _DUP_WORDS = ("已推送", "已经推送", "推送过", "重复", "已存在", "已添加", "任务已存在")

    @staticmethod
    def task_failed(task: Dict[str, Any]) -> bool:
        """115 status: -1 failed, 0 waiting, 1 downloading, 2 finished (NOT failed)."""
        status = str(task.get("status", "")).strip().lower()
        return status in _TASK_FAILED_STATUS or task.get("failed") is True

    @staticmethod
    def task_done(task: Dict[str, Any]) -> bool:
        """Finished on 115's side: status 2 or percentDone >= 100 (file evidence still required)."""
        if P115Transfer.task_failed(task):
            return False
        if str(task.get("status", "")).strip() == "2":
            return True
        try:
            return float(task.get("percentDone") or task.get("percent_done") or 0) >= 100
        except (TypeError, ValueError):
            return False

    @staticmethod
    def match_task(task: Dict[str, Any], link: str = "", info_hash: str = "") -> bool:
        return match_task(task, link, info_hash)

    def find_task(self, info_hash: str, link: str = "") -> Optional[Dict[str, Any]]:
        wanted = normalize_info_hash(info_hash)
        return next((task for task in self.list_tasks()
                     if match_task(task, link, wanted)), None) if wanted else None

    def _recover_offline(self, result: OfflineSubmission) -> OfflineSubmission:
        if hasattr(self, "_budget"):
            try:
                page = self.list_tasks_slice(cursor=result.recovery_cursor)
                result.recovery_cursor = page["cursor"]
                task = next((item for item in page["items"]
                             if match_task(item, result.link, result.info_hash)), None)
                if not task and not page["complete"]:
                    raise P115Deferred("已有离线任务仍在分页恢复，未再次提交", reason="pagination",
                                       state=result.recovery_cursor)
            except P115Deferred as exc:
                # The deferred operation is a read AFTER an explicit duplicate
                # response. Do not misreport the earlier submit as not sent or
                # turn an unscanned list into a terminal acquire failure.
                result.recovery_cursor = exc.state or result.recovery_cursor
                result.recovery_pending = True
                result.message = "已有离线任务恢复待续作，未再次提交"
                exc.state = result.as_dict()
                if result.duplicate:
                    exc.not_sent, exc.uncertain, exc.reconcile_only = False, False, True
                raise
            except P115Error as exc:
                if not result.duplicate:
                    raise
                result.recovery_pending = True
                result.recovery_cursor = None  # a failed/drifting page must be reread
                deferred = P115Deferred("已有离线任务查询失败，等待核实，未再次提交", reason="reconciliation",
                                        retry_at=time.time() + 30, state=result.as_dict(), not_sent=False)
                deferred.reconcile_only = True
                raise deferred from exc
        else:
            task = self.find_task(result.info_hash, result.link)
        if not task:
            result.message = "115 提示重复，但未找到可跟踪的离线任务；请确认原文件位置后重试"
            return result
        result.task = task
        result.file_id = str(task.get("file_id") or task.get("fid") or "")
        result.actual_cid = str(task.get("wp_path_id") or task.get("cid") or "")
        if self.task_failed(task):
            result.message = "已存在的 115 离线任务失败，需在 115 中处理后重试"
            return result
        # An active task in the requested staging directory is trackable. A
        # completed task additionally requires actual file evidence; a stale
        # 115 task entry does not prove that its file still exists.
        try:
            pct = float(task.get("percentDone") or task.get("percent_done") or 0)
        except (ValueError, TypeError):
            pct = 0
        if result.actual_cid != result.requested_cid:
            result.message = "重复离线任务位于其他目录，未自动搬运；请确认原任务和文件位置"
            return result
        name = str(task.get("name") or "")
        if pct >= 100 or self.task_done(task):
            pct = max(pct, 100)
            if not name or not result.file_id or not self.file_in_directory(result.file_id, result.save_path):
                result.message = "重复离线任务已完成，但未确认原文件ID位于当前暂存目录，未视为提交成功"
                return result
        result.recoverable = True
        result.recovery_pending = False
        result.recovery_cursor = None
        result.uncertain = False
        result.message = "已恢复已有离线任务跟踪" if pct < 100 else "已找到已有离线文件，等待搬运"
        return result

    def recover_offline(self, state) -> OfflineSubmission:
        """Read-only continuation of one existing submission; never add again."""
        if isinstance(state, OfflineSubmission):
            result = state
        elif isinstance(state, dict):
            result = OfflineSubmission(**{name: state[name] for name in OfflineSubmission.__dataclass_fields__ if name in state})
        else:
            raise P115Error("离线恢复状态格式无效")
        if not normalize_info_hash(result.info_hash) or not result.requested_cid:
            raise P115Error("离线恢复缺少原始哈希或目标目录身份")
        self.last_offline_result = result
        try:
            return self._recover_offline(result)
        except P115Deferred as exc:
            if result.duplicate:
                result.recovery_pending = True
                exc.state = result.as_dict()
                exc.not_sent, exc.uncertain, exc.reconcile_only = False, False, True
            raise
        except P115Error as exc:
            if not result.duplicate:
                raise
            result.recovery_pending = True
            deferred = P115Deferred("已有离线文件证据查询失败，等待核实，未再次提交", reason="reconciliation",
                                    retry_at=time.time() + 30, state=result.as_dict(), not_sent=False)
            deferred.reconcile_only = True
            raise deferred from exc

    def offline_add(self, url: str, save_path: str, before_submit=None) -> OfflineSubmission:
        """Submit only trackable links; reconcile duplicate/uncertain outcomes."""
        info_hash = extract_hash(url)
        if not info_hash:
            raise P115Error("磁力或 ed2k 哈希无效，未提交无法自动跟踪的离线任务")
        cid = self.path_to_id(save_path, mkdir=True)
        result = OfflineSubmission(info_hash=info_hash, link=url.strip(), requested_cid=str(cid),
                                   actual_cid=str(cid), save_path=save_path)
        self.last_offline_result = result
        if hasattr(self, "_budget"):
            self._budget.claim_submission()
        last_err = ""
        try:
            def before(intent):
                if before_submit:
                    before_submit(intent)
                result.uncertain = True
            resp = self._call("clouddownload_task_add_urls", {
                "url[0]": url.strip(), "wp_path_id": cid,
            }, before_submit=before, intent={"kind": "offline_add", "info_hash": info_hash,
                                             "requested_cid": str(cid)})
            if resp.get("state") in (True, 1, "1", False, 0, "0"):
                result.uncertain = False
            if resp.get("state") in (True, 1, "1"):
                data = resp.get("data")
                # Some endpoint versions return outer success but report
                # per-link failure in result/data. Validate that inner row.
                candidates = (resp.get("result"), data)
                for inner in candidates:
                    row = inner[0] if isinstance(inner, list) and inner else inner
                    if isinstance(row, dict) and row.get("state") in (False, 0, "0"):
                        resp = row
                        break
                else:
                    self._require_success(resp, "离线提交")
                    result.accepted = True
                    result.message = "已提交离线下载"
                    if isinstance(data, dict):
                        result.file_id = str(data.get("file_id") or data.get("fid") or "")
                        result.task = data if data.get("info_hash") else {}
                    return result
            last_err = self._error(resp)
            if any(word in last_err for word in self._DUP_WORDS):
                result.duplicate = True
                self.recover_offline(result)
                if result:
                    return result
                raise P115Error(result.message)
        except P115Deferred as exc:
            result.uncertain = exc.uncertain
            result.message = str(exc)
            if result.duplicate:
                # File evidence can also exhaust the slice after finding
                # the duplicate task; preserve that identity for recovery.
                result.recovery_pending = True
                exc.not_sent, exc.uncertain, exc.reconcile_only = False, False, True
            exc.state = result.as_dict()
            raise
        except P115Error as exc:
            last_err = str(exc)
            if result.duplicate:
                raise
            if not result.uncertain:
                raise
            if hasattr(self, "_budget") and result.uncertain:
                raise P115Deferred("离线提交结果未确认，等待对账，未重复提交", reason="uncertain",
                                   uncertain=True, state=result.as_dict()) from exc
            # The request may have reached 115 before its response timed
            # out. Recover a matching task, but never report blind success.
            try:
                self._recover_offline(result)
            except P115Error as recovery_error:
                raise P115Error(f"离线提交结果未确认：{last_err}；任务对账失败：{recovery_error}") from exc
            if result:
                result.message = "提交响应异常，已恢复实际离线任务跟踪"
                return result
            raise P115Error(f"离线提交结果未确认：{last_err}；未找到安全可恢复的任务") from exc
        result.message = f"离线下载提交失败：{last_err}"
        raise P115Error(result.message)

    def list_tasks_slice(self, cursor=None, page_size: int = 100, max_pages: int = 3) -> Dict[str, Any]:
        """At most three pages. Only complete=True proves a task is absent."""
        state = dict(cursor or {"page": 1, "items": [], "complete": False})
        state["items"] = list(state.get("items") or [])
        # Entries without a usable hash (e.g. plain http tasks) are skipped but
        # still counted, so that pagination totals stay comparable.
        state.setdefault("skipped", 0)
        state.setdefault("scanned", len(state["items"]) + state["skipped"])
        seen = {item["info_hash"] for item in state["items"]}
        try:
            for _ in range(min(3, max_pages)):
                if state.get("complete"):
                    break
                verify = state.get("verify", False)
                page = 1 if verify else state["page"]
                resp = self._call("clouddownload_task_list", {"page": page, "page_size": page_size})
                self._require_success(resp, "查询离线任务")
                data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
                tasks = data.get("tasks")
                if not isinstance(tasks, list):
                    raise P115Error("离线任务列表返回格式错误")
                total = self._total(resp, data)
                if "total" in state and total != state["total"]:
                    raise P115Error("离线列表分页总数变化，不能判断任务缺失")
                state["total"] = total
                normalized, skipped = [], 0
                for task in tasks:
                    if not isinstance(task, dict):
                        raise P115Error("离线任务条目格式错误")
                    h = normalize_info_hash(task.get("info_hash") or task.get("hash") or "")
                    if not h:
                        skipped += 1
                        continue
                    normalized.append({**task, "info_hash": h})
                identity = [t["info_hash"] for t in normalized]
                if verify:
                    if identity != state["first_page"]:
                        raise P115Error("离线列表分页排序发生变化，不能判断任务缺失")
                    state["complete"] = True
                    state.pop("verify", None)
                    break
                if page == 1:
                    state["first_page"] = identity
                if not tasks and total is not None and state["scanned"] < total:
                    raise P115Error("离线列表分页不完整，不能判断任务缺失")
                for task in normalized:
                    # Only hashed entries take part in the overlap check.
                    if task["info_hash"] in seen:
                        raise P115Error("离线列表分页重叠，不能判断任务缺失")
                    seen.add(task["info_hash"])
                    state["items"].append(task)
                state["skipped"] += skipped
                state["scanned"] += len(tasks)
                state["page"] += 1
                ended = not tasks or (total is not None and state["scanned"] >= total)
                if ended:
                    if page == 1:
                        state["complete"] = True
                    else:
                        state["verify"] = True
            return {"items": state["items"], "complete": bool(state.get("complete")),
                    "cursor": None if state.get("complete") else state,
                    "skipped": state["skipped"]}
        except P115Deferred as exc:
            exc.state = state
            raise

    def list_tasks(self, page_size: int = 100) -> list:
        """列出 115 离线下载任务（含 info_hash / percentDone / file_id）。"""
        if hasattr(self, "_budget"):
            try:
                page = self.list_tasks_slice(self._task_cursor, page_size)
                self._task_cursor = page["cursor"]
                if not page["complete"]:
                    raise P115Deferred("离线任务列表尚未完整读取，等待续作", reason="pagination",
                                       state=page["cursor"])
                return page["items"]
            except P115Deferred as exc:
                if exc.state:
                    self._task_cursor = exc.state
                raise
        out: list = []
        seen = set()
        scanned = 0
        self.last_tasks_skipped = 0
        for page in range(1, 10001):
            resp = self._call("clouddownload_task_list", {"page": page, "page_size": page_size})
            self._require_success(resp, "查询离线任务")
            data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
            tasks = data.get("tasks")
            if not isinstance(tasks, list):
                raise P115Error("离线任务列表返回格式错误")
            total = self._total(resp, data)
            if not tasks:
                if total is not None and scanned < total:
                    raise P115Error(f"离线任务分页不完整：{scanned}/{total}")
                return out
            added = hashed = 0
            for task in tasks:
                if not isinstance(task, dict):
                    raise P115Error("离线任务条目格式错误")
                normalized = dict(task)
                h = normalize_info_hash(task.get("info_hash") or task.get("hash") or "")
                if not h:
                    self.last_tasks_skipped += 1
                    continue
                hashed += 1
                if h in seen:
                    continue
                seen.add(h)
                normalized["info_hash"] = h
                out.append(normalized)
                added += 1
            scanned += len(tasks)
            if hashed and not added:
                raise P115Error("离线任务分页重复，未返回不完整的任务列表")
            if total is not None and scanned >= total:
                return out
        raise P115Error("离线任务超过分页保护上限")

    # -- 目录/搬运（走 115网盘Plus 插件）-------------------------------------
    def list_names(self, path: str) -> List[str]:
        """列出 115 网盘某个目录下的名字（只读）。"""
        cid = self.path_to_id(path, mkdir=False)
        out: List[str] = []
        seen = set()
        offset = 0
        for _page in range(10000):
            resp = self._call("fs_files", {"cid": cid, "limit": 400, "offset": offset,
                                           "show_dir": 1, "o": "file_name", "asc": 1})
            self._require_success(resp, "读取目录")
            returned_path = resp.get("path")
            if isinstance(returned_path, list) and returned_path:
                actual_cid = returned_path[-1].get("cid")
                if actual_cid is not None and str(actual_cid) != str(cid):
                    raise P115Error("目录接口返回了其他目录，未使用该列表确认文件状态")
            data = resp.get("data")
            entries = data.get("list") if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise P115Error("目录列表返回格式错误")
            total = self._total(resp, data)
            if not entries:
                if total is not None and offset < total:
                    raise P115Error(f"目录分页不完整：{offset}/{total}")
                return out
            added = 0
            for item in entries:
                if not isinstance(item, dict):
                    raise P115Error("目录条目格式错误")
                name = str(item.get("n") or item.get("fn") or item.get("file_name") or "")
                identity = str(item.get("fid") or item.get("id") or item.get("cid") or name)
                if not name:
                    raise P115Error("目录条目缺少名称")
                if identity in seen:
                    continue
                seen.add(identity)
                out.append(name)
                added += 1
            if not added:
                raise P115Error("目录分页重复，无法确认文件存在状态")
            offset += len(entries)
            if total is not None and offset >= total:
                return out
        raise P115Error("目录超过分页保护上限")

    def path_exists(self, path: str) -> bool:
        """判断 115 网盘上的某个路径是否存在（用于离线下载落盘校验）。"""
        p = posixpath.normpath(str(path).replace("\\", "/"))
        if p in (".", "/"):
            return True
        try:
            return posixpath.basename(p) in self.list_names(posixpath.dirname(p) or "/")
        except P115NotFound:
            return False

    # -- 媒体文件统计（核对"整包是否全部整理入库"）----------------------------
    VIDEO_EXTS = (".mkv", ".mp4", ".ts", ".m2ts", ".avi", ".mov", ".wmv", ".flv",
                  ".rmvb", ".rm", ".iso", ".mpg", ".mpeg", ".m4v", ".webm", ".vob", ".tp")
    _EP_RE = re.compile(r"[sS](\d{1,2})[eE](\d{1,3})")

    @classmethod
    def _media_entry(cls, item, parent_path, parent_id):
        fid = str(item.get("fid") or item.get("file_id") or item.get("id") or item.get("cid") or "")
        name = str(item.get("n") or item.get("fn") or item.get("file_name") or item.get("name") or "")
        if not fid.isdigit() or int(fid) <= 0 or not name or "/" in name or "\\" in name or name in (".", ".."):
            raise P115Error("清单条目缺少真实ID或名称")
        is_dir = bool(item.get("is_dir")) or str(item.get("fc", "")) == "0" or (
            not item.get("fid") and not item.get("file_id") and bool(item.get("cid")))
        optional = bool(re.search(r"(?:^|[ ._\-])(sample|trailer|extras?)(?:[ ._\-]|$)|预告|花絮|样片", name, re.I))
        video = name.lower().endswith(cls.VIDEO_EXTS)
        episodes = []
        match = re.search(r"[sS](\d{1,2})((?:[eE]\d{1,3})+)", name)
        if match:
            episodes = [(int(match.group(1)), int(value))
                        for value in re.findall(r"[eE](\d{1,3})", match.group(2))]
        return {"id": fid, "name": name, "path": posixpath.join(parent_path, name),
                "parent_id": str(parent_id), "is_dir": is_dir, "size": item.get("s", item.get("size")),
                "required": video and not optional, "role": "optional" if optional else "media" if video else "other",
                "episodes": episodes}

    def share_manifest_slice(self, share_url: str, cursor=None, *, max_pages: int = 3,
                             max_dirs: int = 80) -> Dict[str, Any]:
        """Snapshot required source units before receive; IDs are SOURCE IDs."""
        info = share_extract_payload(normalize_115_share(share_url))
        code = str(info.get("share_code") or "")
        if not code:
            raise P115Error("无法解析分享链接")
        identity = hashlib.sha256(code.encode()).hexdigest()
        state = dict(cursor or {"identity": identity, "queue": [{"cid": "0", "path": "/", "offset": 0}],
                               "items": [], "dirs": 0, "complete": False, "unresolved": []})
        state["queue"] = [dict(row) for row in state.get("queue", [])]
        state["items"] = list(state.get("items", []))
        state["unresolved"] = list(state.get("unresolved", []))
        if state.get("identity") != identity:
            raise P115Error("分享原始清单续作身份不匹配")
        try:
            for _ in range(min(3, max_pages)):
                if not state["queue"]:
                    break
                current = state["queue"][0]
                if current["offset"] == 0 and not current.get("started"):
                    if state["dirs"] >= max_dirs:
                        state["unresolved"].append("分享目录数量超过扫描上限")
                        break
                    state["dirs"] += 1
                    current["started"] = True
                verify = current.get("verify", False)
                resp = self._call("share_snap", {"share_code": code,
                    "receive_code": info.get("receive_code") or "", "cid": current["cid"],
                    "limit": 200, "offset": 0 if verify else current["offset"]})
                self._require_success(resp, "读取分享原始清单")
                data = resp.get("data")
                if not isinstance(data, dict) or not isinstance(data.get("list"), list):
                    raise P115Error("分享原始清单格式错误")
                entries = data["list"]
                total = self._total(resp, data)
                if "total" in current and current["total"] != total:
                    raise P115Error("分享原始清单扫描期间数量变化")
                current["total"] = total
                normalized = [self._media_entry(item, current["path"], current["cid"]) for item in entries]
                ids = [item["id"] for item in normalized]
                if verify:
                    if ids != current["first_page"]:
                        raise P115Error("分享原始清单分页顺序变化")
                    state["queue"].pop(0)
                    continue
                if current["offset"] == 0:
                    current["first_page"] = ids
                if not entries and total is not None and current["offset"] < total:
                    raise P115Error("分享原始清单分页不完整")
                seen = {item["source_file_id"] for item in state["items"]}
                for item in normalized:
                    if item["id"] in seen:
                        raise P115Error("分享原始清单分页重叠")
                    seen.add(item["id"])
                    if item["is_dir"]:
                        state["queue"].append({"cid": item["id"], "path": item["path"], "offset": 0})
                    if item["name"].lower() in ("bdmv", "video_ts") or item["name"].lower().endswith((".zip", ".rar", ".7z")):
                        state["unresolved"].append("压缩或蓝光资源的必要单元需进一步识别")
                    item["source_file_id"] = item.pop("id")
                    item["source_parent_id"] = item.pop("parent_id")
                    item["relative_path"] = item.pop("path").lstrip("/")
                    # A received share has new target IDs. Never reuse source IDs.
                    item["target_file_id"] = ""
                    state["items"].append(item)
                current["offset"] += len(entries)
                if not entries or (total is not None and current["offset"] >= total):
                    if current["offset"] <= len(entries):
                        state["queue"].pop(0)
                    else:
                        current["verify"] = True
            state["complete"] = not state["queue"] and not state["unresolved"]
            return {"items": state["items"], "complete": state["complete"],
                    "cursor": None if state["complete"] else state,
                    "error": "; ".join(state["unresolved"]), "origin": "share_source"}
        except P115Deferred as exc:
            exc.state = state
            raise
        except P115Error as exc:
            return {"items": state["items"], "complete": False, "cursor": state,
                    "error": str(exc), "origin": "share_source"}

    def manifest_slice(self, path: str, cursor=None, *, file_id: str = "", max_pages: int = 3,
                       max_dirs: int = 80) -> Dict[str, Any]:
        """Read only this batch's subtree, preserving exact IDs and completeness."""
        path = posixpath.normpath(str(path).replace("\\", "/"))
        state = dict(cursor or {"root": path, "queue": [{"path": path, "offset": 0}],
                               "items": [], "dirs": 0, "complete": False, "unresolved": []})
        state["queue"] = [dict(entry) for entry in state.get("queue", [])]
        state["items"] = list(state.get("items", []))
        state["unresolved"] = list(state.get("unresolved", []))
        if state.get("root") != path:
            raise P115Error("清单续作根路径不匹配")
        try:
            if file_id and path.lower().endswith(self.VIDEO_EXTS) and not cursor:
                info = self.get_file_info(file_id)
                if info is None:
                    return {"items": [], "complete": False, "cursor": None, "error": "源文件已删除"}
                state["items"] = [self._media_entry(info, posixpath.dirname(path), info["parent_id"])]
                state["queue"] = []
            elif file_id and not cursor:
                # Caller already verified this exact directory ID before scanning.
                self._remember_directory(path, int(file_id))
            for _ in range(min(3, max_pages)):
                if not state["queue"]:
                    break
                current = state["queue"][0]
                if not current.get("cid"):
                    if state["dirs"] >= max_dirs:
                        state["unresolved"].append("目录数量超过本批次扫描上限")
                        break
                    current["cid"] = self.path_to_id(current["path"], mkdir=False)
                    state["dirs"] += 1
                verify = current.get("verify", False)
                resp = self._call("fs_files", {"cid": current["cid"], "offset": 0 if verify else current["offset"],
                    "limit": 400, "show_dir": 1, "o": "file_name", "asc": 1})
                self._require_success(resp, "读取本批次清单")
                returned_path = resp.get("path")
                if isinstance(returned_path, list) and returned_path and str(
                        returned_path[-1].get("cid", current["cid"])) != str(current["cid"]):
                    raise P115Error("清单接口返回其他目录")
                data = resp.get("data")
                entries = data.get("list") if isinstance(data, dict) else data
                if not isinstance(entries, list):
                    raise P115Error("清单目录列表格式错误")
                total = self._total(resp, data)
                if "total" in current and total != current["total"]:
                    raise P115Error("清单扫描期间文件数量变化，完整性待核实")
                current["total"] = total
                normalized = [self._media_entry(item, current["path"], current["cid"]) for item in entries]
                identity = [item["id"] for item in normalized]
                if verify:
                    if identity != current["first_page"]:
                        raise P115Error("清单分页排序变化，完整性待核实")
                    state["queue"].pop(0)
                    continue
                if current["offset"] == 0:
                    current["first_page"] = identity
                seen = {item["id"] for item in state["items"]}
                if not entries and total is not None and current["offset"] < total:
                    raise P115Error("清单分页不完整")
                for item in normalized:
                    if item["id"] in seen:
                        raise P115Error("清单分页重复，完整性待核实")
                    seen.add(item["id"])
                    state["items"].append(item)
                    if item["is_dir"]:
                        self._remember_directory(item["path"], int(item["id"]))
                        state["queue"].append({"path": item["path"], "offset": 0})
                    if item["name"].lower().endswith((".zip", ".rar", ".7z", ".bdmv")):
                        state["unresolved"].append("包含需进一步识别的压缩或蓝光资源")
                current["offset"] += len(entries)
                if not entries or (total is not None and current["offset"] >= total):
                    if current["offset"] <= len(entries):
                        state["queue"].pop(0)
                    else:
                        current["verify"] = True
            state["complete"] = not state["queue"] and not state["unresolved"]
            return {"items": state["items"], "complete": state["complete"],
                    "cursor": None if state["complete"] else state,
                    "error": "; ".join(state["unresolved"]), "dirs": state["dirs"]}
        except P115Deferred as exc:
            exc.state = state
            raise
        except P115Error as exc:
            state["complete"] = False
            return {"items": state["items"], "complete": False, "cursor": state,
                    "error": str(exc), "dirs": state["dirs"]}

    def _list_items(self, path: str) -> List[Dict[str, Any]]:
        """列出目录下的条目（含是否文件夹），用于统计媒体文件。"""
        cid = self.path_to_id(path, mkdir=False)
        out: List[Dict[str, Any]] = []
        offset = 0
        for _page in range(100):
            resp = self._call("fs_files", {"cid": cid, "limit": 400, "offset": offset,
                                           "show_dir": 1, "o": "file_name", "asc": 1})
            self._require_success(resp, "读取目录")
            data = resp.get("data")
            entries = data.get("list") if isinstance(data, dict) else data
            if not isinstance(entries, list):
                raise P115Error("目录列表返回格式错误")
            total = self._total(resp, data)
            if not entries:
                break
            for item in entries:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("n") or item.get("fn") or item.get("file_name") or "")
                if not name:
                    continue
                # 115 目录列表里「文件夹」没有 fid、只有 cid
                is_dir = bool(item.get("is_dir")) or (not item.get("fid") and bool(item.get("cid")))
                out.append({"name": name, "is_dir": is_dir})
            offset += len(entries)
            if total is not None and offset >= total:
                break
        return out

    def count_media_files(self, path: str, max_dirs: int = 80) -> Dict[str, Any]:
        """递归统计目录下的**视频文件数**与**集号集合**。

        用于搬运时记录"源侧预期规模"，之后拿 MP 整理记录里的入库集数对比，
        判断这一整包（尤其整季剧集）是否**全部**整理入库。
        """
        if hasattr(self, "_budget"):
            page = self.manifest_slice(path, max_dirs=max_dirs)
            media = [item for item in page["items"] if item.get("required")]
            episodes = {tuple(ep) for item in media for ep in item.get("episodes", [])}
            return {"files": len(media), "episodes": sorted(episodes), "dirs": page["dirs"],
                    "complete": page["complete"], "items": page["items"], "cursor": page["cursor"],
                    "error": page["error"]}
        files, episodes = 0, set()
        queue = [posixpath.normpath(str(path).replace("\\", "/"))]
        visited = 0
        while queue and visited < max_dirs:
            cur = queue.pop(0)
            visited += 1
            try:
                items = self._list_items(cur)
            except Exception:  # noqa: BLE001
                break
            for it in items:
                if it["is_dir"]:
                    queue.append(f"{cur.rstrip('/')}/{it['name']}")
                elif it["name"].lower().endswith(self.VIDEO_EXTS):
                    files += 1
                    m = self._EP_RE.search(it["name"])
                    if m:
                        episodes.add((int(m.group(1)), int(m.group(2))))
        return {"files": files, "episodes": sorted(episodes), "dirs": visited}

    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Read an exact file/folder ID; None means confirmed absence only."""
        fid = str(file_id or "")
        if not fid.isdigit() or int(fid) <= 0:
            raise P115Error("无效的115文件ID")
        work = self._budget.current_slice if hasattr(self, "_budget") else None
        if work is not None and fid in work.file_cache:
            return work.file_cache[fid]
        try:
            resp = self._call("fs_file", fid)
            self._require_success(resp, "文件信息查询")
        except P115NotFound:
            if work is not None:
                work.file_cache[fid] = None
            return None
        data = resp.get("data")
        if isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict) and
                         str(item.get("file_id") or item.get("fid") or item.get("id") or item.get("cid")) == fid), None)
        if not isinstance(data, dict):
            raise P115Error("文件信息返回缺少匹配ID，无法确认文件是否存在")
        actual = str(data.get("file_id") or data.get("fid") or data.get("id") or data.get("cid") or "")
        if "is_dir" in data:
            is_dir = bool(data["is_dir"])
        elif "fc" in data:
            is_dir = str(data["fc"]) == "0"
        elif "fid" in data:
            is_dir = False
        elif "cid" in data and "pid" in data:
            is_dir = True
        elif "sha1" in data or "file_sha1" in data:
            is_dir = not (data.get("sha1") or data.get("file_sha1"))
        else:
            is_dir = None
        parent = data.get("parent_id", data.get("pid") if is_dir else data.get("cid"))
        if actual != fid or parent is None:
            raise P115Error("文件信息返回的ID或父目录无效")
        result = {**data, "id": fid, "parent_id": str(parent),
                  "name": str(data.get("file_name") or data.get("n") or data.get("fn") or data.get("name") or ""),
                  "is_dir": is_dir}
        if work is not None:
            work.file_cache[fid] = result
        return result

    def invalidate_file_info(self, file_id: str):
        work = self._budget.current_slice if hasattr(self, "_budget") else None
        if work is not None:
            work.file_cache.pop(str(file_id), None)

    def file_in_directory(self, file_id: str, directory: str) -> bool:
        """Verify file identity and its immediate parent, including crash recovery."""
        info = self.get_file_info(file_id)
        if info is None:
            return False
        try:
            cid = self.path_to_id(directory, mkdir=False)
        except P115NotFound:
            return False
        return info["parent_id"] == str(cid)

    def move_via_p115disk(self, src_path: str, dest_dir: str, file_id: str = "") -> Tuple[bool, str]:
        """把网盘上的 ``src_path`` 移动到 ``dest_dir``。

        ⚠️ 按约定，115 网盘上的移动**必须走 115网盘Plus（P115Disk）插件**，
        所以这里直接复用它的存储实现 ``P115Api``（含限速与缓存维护），
        而不是自己调 fs_move。
        """
        try:
            from app.plugins.p115disk.p115_api import P115Api  # type: ignore
        except Exception as exc:  # noqa: BLE001
            return False, f"115网盘Plus 未安装/不可用：{exc}"
        try:
            if hasattr(self, "_budget") and not getattr(self.client, "_doc115_budget_transport", None):
                raise P115Deferred("当前Plus SDK无法逐请求控制，已暂停本插件搬运", reason="capability")
            if getattr(self, "_p115_api", None) is None:
                self._p115_api = P115Api(client=self.client, disk_name="115网盘Plus")
            api = self._p115_api
            if api.client is not self.client:
                raise P115Deferred("Plus没有复用本插件私有受控client，已暂停搬运", reason="capability")
            transport = getattr(self, "_transport", None)
            if transport:
                transport.local.last_deferred = None
                transport.local.write_attempted = False
                transport.local.write_completed = False
            if hasattr(self, "_budget"):
                if not file_id:
                    return False, "缺少本批次真实文件ID，未执行搬运"
                # Plus's strict lookup can fall back to the host u115 client.
                # Resolve identity here, then seed only this private API cache.
                info = self.get_file_info(file_id)
                if info is None:
                    return False, "本批次源文件已不存在，未执行搬运"
                src = posixpath.normpath(src_path.replace("\\", "/"))
                dest = posixpath.normpath(dest_dir.replace("\\", "/"))
                if info["name"] != posixpath.basename(src):
                    return False, "源路径名称与确切文件ID不匹配，未执行搬运"
                if info["parent_id"] != str(self.path_to_id(posixpath.dirname(src) or "/", mkdir=False)):
                    return False, "源文件ID已不在本批次源目录，未执行搬运"
                if info["is_dir"] is None:
                    raise P115Deferred("SDK文件信息缺少文件/目录类型，已暂停搬运", reason="capability")
                cid = self.path_to_id(dest, mkdir=True)
                cache = getattr(api, "_id_cache", None)
                if not callable(getattr(cache, "add_cache", None)):
                    raise P115Deferred("Plus目标目录缓存契约不兼容，已暂停搬运", reason="capability")
                try:
                    move_source = inspect.getsource(type(api).move)
                except (OSError, TypeError):
                    raise P115Deferred("无法验证Plus搬运请求契约，已暂停搬运", reason="capability")
                if any(word in move_source for word in ("StorageChain", "self.get_item(", "self.get_item_strict(", "get_attr(")):
                    raise P115Deferred("Plus搬运含不可控降级查询，已暂停搬运", reason="capability")
                from app.schemas import FileItem  # type: ignore
                is_dir = info["is_dir"]
                item = FileItem(storage="115网盘Plus", fileid=str(file_id), parent_fileid=info["parent_id"],
                    path=src + ("/" if is_dir else ""), name=info["name"],
                    basename=info["name"] if is_dir else posixpath.splitext(info["name"])[0],
                    extension="" if is_dir else posixpath.splitext(info["name"])[1].lstrip("."),
                    type="dir" if is_dir else "file", size=info.get("s", info.get("size", info.get("file_size"))),
                    pickcode=info.get("pc") or info.get("pick_code") or info.get("pickcode"))
                cache.add_cache(id=cid, directory=dest)
                dest_dir = dest
            else:  # standalone mocked compatibility path
                lookup = getattr(api, "get_item_strict", None)
                if not callable(lookup):
                    raise P115Deferred("当前Plus缺少严格查询能力，已暂停搬运", reason="capability")
                item = lookup(Path(src_path))
            if not item:
                return False, f"源路径不存在：{src_path}"
            if file_id and str(getattr(item, "fileid", "")) != str(file_id):
                return False, "源路径指向不同的115文件ID，未执行搬运，请核对同名文件"
            name = getattr(item, "name", None) or Path(src_path).name
            if api.move(item, Path(dest_dir), name):
                self.invalidate_file_info(file_id or str(getattr(item, "fileid", "")))
                src = posixpath.normpath(src_path.replace("\\", "/"))
                if getattr(item, "type", "") == "dir":
                    self._forget_directory_tree(src)
                    self._remember_directory(posixpath.join(dest_dir, name), int(file_id))
                return True, ""
            if transport and transport.local.last_deferred:
                deferred = transport.local.last_deferred
                if transport.local.write_attempted:
                    deferred.not_sent = False
                    deferred.uncertain = deferred.uncertain or (
                        not transport.local.write_completed and deferred.reason in ("slice", "account_budget", "cancelled", "capability"))
                raise deferred
            return False, f"移动失败：{src_path} -> {dest_dir}"
        except P115Deferred:
            raise
        except Exception as exc:  # noqa: BLE001
            return False, f"移动异常：{type(exc).__name__}: {exc}"

    # -- 统一入口 -----------------------------------------------------------
    def add_resource(self, kind: str, url: str, save_path: str) -> Tuple[bool, str]:
        """按链接类型分派：115分享->转存；磁力/ed2k->离线下载。"""
        if kind == LINK_115_SHARE:
            self.share_receive(url, save_path)
            return True, "已转存"
        if kind in (LINK_MAGNET, LINK_ED2K):
            result = self.offline_add(url, save_path)
            return bool(result), result.message
        return False, f"不支持的链接类型：{kind}"
