"""115 网盘操作：分享链接转存 + 磁力/ed2k 离线下载。

复用 p115client，与仓库里 115 系列插件保持一致的调用方式：
  * 转存：share_extract_payload -> share_receive({share_code, receive_code, file_id, cid})
  * 离线：clouddownload_task_add_urls({"url[0]": url, "wp_path_id": cid})
目录一律是 **115 网盘上的路径**（不是本地路径），通过目录 ID 定位。
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import posixpath
import random
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

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
_BASE32_BT = re.compile(r"[A-Za-z2-7]{32}\Z")
_ED2K_HASH = re.compile(r"ed2k://\|file\|[^|]+\|\d+\|([0-9a-fA-F]{32})\|(?:[^\s]*)\Z", re.I)
_NOT_FOUND_CODES = {10014, 20009, 20013, 20018, 31001, 31003, 50015, 70005, 70008, 90008, 430004, 800001}
_RETRY_CODES = {990005, 990009, 990019, 590075, 40110000}


def normalize_info_hash(value: str) -> str:
    """Canonical BTIH hex; a 32-character hexadecimal value may be ED2K."""
    value = str(value or "").strip()
    if _HEX_BT.fullmatch(value) or re.fullmatch(r"[0-9a-fA-F]{32}", value):
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


def normalize_115_share(url: str) -> str:
    """把 115cdn.com 的分享链接规范成 115.com，便于解析分享码。"""
    u = (url or "").strip()
    return u.replace("115cdn.com/s/", "115.com/s/").replace("//115cdn.com", "//115.com")


class P115Error(RuntimeError):
    pass


class P115NotFound(P115Error):
    """Confirmed absent path, distinct from an unavailable listing."""


@dataclass
class OfflineSubmission:
    accepted: bool = False
    duplicate: bool = False
    info_hash: str = ""
    task: Dict[str, Any] = field(default_factory=dict)
    file_id: str = ""
    requested_cid: str = ""
    actual_cid: str = ""
    save_path: str = ""
    message: str = ""
    recoverable: bool = False
    uncertain: bool = False

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
    account = re.search(r"(?:^|;)\s*UID=([^;]+)", cookie, re.I)
    identity = (account.group(1).split("_")[0] if account else cookie)
    key = hashlib.sha256(identity.encode()).hexdigest()
    with _LIMITERS_LOCK:
        return _LIMITERS.setdefault(key, _RateLimiter())


class P115Transfer:
    """115 网盘操作封装。"""

    def __init__(self, cookie: str, timeout: int = 30):
        if not P115_AVAILABLE:
            raise P115Error("未安装 p115client，请重装插件以安装依赖")
        if not cookie:
            raise P115Error("缺少 115 Cookie")
        self.client = P115Client(cookie)
        self.timeout = max(1.0, float(timeout))
        self._limiter = _shared_limiter(cookie)
        self._dir_cache: Dict[str, int] = {}
        self.last_offline_result: Optional[OfflineSubmission] = None
        self.last_share_names: List[str] = []
        self.last_share_result: Dict[str, Any] = {}

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

    def _call(self, name: str, *args) -> Dict[str, Any]:
        self._limiter.wait()
        try:
            result = getattr(self.client, name)(*args, **self._timeout_kwargs())
        except FileNotFoundError as exc:
            raise P115NotFound(f"115 {name} 确认路径不存在") from exc
        except Exception as exc:
            raise P115Error(f"115 {name} 请求失败：{type(exc).__name__}: {exc}") from exc
        if not isinstance(result, dict):
            raise P115Error(f"115 {name} 返回格式错误")
        return result

    @staticmethod
    def _error(resp: Dict[str, Any]) -> str:
        return str(resp.get("error") or resp.get("message") or resp.get("msg") or resp.get("errno") or "未知错误")

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

    def path_to_id(self, path: str, mkdir: bool = True) -> int:
        """115 目录路径 -> 目录 ID（必要时逐级创建）。根目录为 0。"""
        p = (path or "").replace("\\", "/")
        if not p.startswith("/"):
            p = "/" + p
        p = p.rstrip("/")
        if p in ("", "/"):
            return 0
        if p in self._dir_cache:
            return self._dir_cache[p]
        resp = self._call("fs_dir_getid", p)
        try:
            self._require_success(resp, "目录查询")
        except P115NotFound:
            if not mkdir:
                raise
            resp = {"id": 0}
        if str(resp.get("id") or "0") != "0":
            cid = int(resp["id"])
            self._dir_cache[p] = cid
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
            r = self._call("fs_dir_getid", built)
            try:
                self._require_success(r, "目录查询")
            except P115NotFound:
                r = {"id": 0}
            if str(r.get("id") or "0") != "0":
                cur = int(r["id"])
                continue
            if "id" not in r:
                raise P115Error("目录查询返回缺少 id")
            r2 = self._call("fs_makedirs_app", built)
            self._require_success(r2, "创建目录")
            data = r2.get("data") if isinstance(r2.get("data"), dict) else r2
            cid = data.get("cid") or data.get("id")
            if not cid:
                raise P115Error(f"创建目录失败：{built} -> {r2}")
            cur = int(cid)
        self._dir_cache[p] = cur
        return cur

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

    def share_receive(self, share_url: str, save_path: str) -> bool:
        """把 115 分享链接整体转存到目标目录。"""
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
            for attempt in range(3):
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
                    break
                if resp.get("state") in (True, 1, "1", False, 0, "0"):
                    self.last_share_result["uncertain"] = False
                if resp.get("state") in (True, 1, "1"):
                    completed += len(batch)
                    self.last_share_names.extend(it["name"] for it in batch if it["name"])
                    self.last_share_result["received"] = completed
                    break
                last_err = self._error(resp)
                if resp.get("errno") in _RETRY_CODES and attempt < 2:
                    time.sleep((attempt + 1) * 2)
                    continue
                break
            else:
                last_err = last_err or "重试次数耗尽"
            if completed != min(start + len(batch), len(items)):
                self.last_share_result["failed"] = len(items) - completed
                self.last_share_result["error"] = last_err
                self.last_share_result["partial"] = completed > 0
                raise P115Error(f"转存未完成（{completed}/{len(items)} 项）：{last_err}")
        return True

    # -- 离线下载 -----------------------------------------------------------
    _DUP_WORDS = ("已推送", "已经推送", "推送过", "重复", "已存在", "已添加")

    @staticmethod
    def task_failed(task: Dict[str, Any]) -> bool:
        """Cookie API status 2 is failed (not finished); preserve source fields."""
        status = str(task.get("status", "")).lower()
        return status in ("-1", "-2", "2", "failed", "error", "cancelled", "canceled") or task.get("failed") is True

    def find_task(self, info_hash: str) -> Optional[Dict[str, Any]]:
        wanted = normalize_info_hash(info_hash)
        return next((task for task in self.list_tasks()
                     if task.get("info_hash") == wanted), None) if wanted else None

    def _recover_offline(self, result: OfflineSubmission) -> OfflineSubmission:
        task = self.find_task(result.info_hash)
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
        if pct >= 100:
            if not name or not result.file_id or not self.file_in_directory(result.file_id, result.save_path):
                result.message = "重复离线任务已完成，但未确认原文件ID位于当前暂存目录，未视为提交成功"
                return result
        result.recoverable = True
        result.uncertain = False
        result.message = "已恢复已有离线任务跟踪" if pct < 100 else "已找到已有离线文件，等待搬运"
        return result

    def offline_add(self, url: str, save_path: str) -> OfflineSubmission:
        """Submit only trackable links; reconcile duplicate/uncertain outcomes."""
        info_hash = extract_hash(url)
        if not info_hash:
            raise P115Error("磁力或 ed2k 哈希无效，未提交无法自动跟踪的离线任务")
        cid = self.path_to_id(save_path, mkdir=True)
        result = OfflineSubmission(info_hash=info_hash, requested_cid=str(cid),
                                   actual_cid=str(cid), save_path=save_path)
        self.last_offline_result = result
        last_err = ""
        for attempt in range(3):
            try:
                result.uncertain = True
                resp = self._call("clouddownload_task_add_urls", {
                    "url[0]": url.strip(), "wp_path_id": cid,
                })
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
                        result.accepted = True
                        result.message = "已提交离线下载"
                        if isinstance(data, dict):
                            result.file_id = str(data.get("file_id") or "")
                            result.task = data if data.get("info_hash") else {}
                        return result
                last_err = self._error(resp)
                if any(word in last_err for word in self._DUP_WORDS):
                    result.duplicate = True
                    self._recover_offline(result)
                    if result:
                        return result
                    raise P115Error(result.message)
                if resp.get("errno") in _RETRY_CODES and attempt < 2:
                    time.sleep((attempt + 1) * 2)
                    continue
                break
            except P115Error as exc:
                last_err = str(exc)
                if result.duplicate:
                    raise
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

    def list_tasks(self, page_size: int = 100) -> list:
        """列出 115 离线下载任务（含 info_hash / percentDone / file_id）。"""
        out: list = []
        seen = set()
        for page in range(1, 10001):
            resp = self._call("clouddownload_task_list", {"page": page, "page_size": page_size})
            self._require_success(resp, "查询离线任务")
            data = resp.get("data") if isinstance(resp.get("data"), dict) else resp
            tasks = data.get("tasks")
            if not isinstance(tasks, list):
                raise P115Error("离线任务列表返回格式错误")
            total = self._total(resp, data)
            if not tasks:
                if total is not None and len(out) < total:
                    raise P115Error(f"离线任务分页不完整：{len(out)}/{total}")
                return out
            added = 0
            for task in tasks:
                if not isinstance(task, dict):
                    raise P115Error("离线任务条目格式错误")
                normalized = dict(task)
                h = normalize_info_hash(task.get("info_hash") or task.get("hash") or "")
                if not h:
                    raise P115Error("离线任务缺少有效哈希，无法确认任务状态")
                if h in seen:
                    continue
                seen.add(h)
                normalized["info_hash"] = h
                out.append(normalized)
                added += 1
            if not added:
                raise P115Error("离线任务分页重复，未返回不完整的任务列表")
            if total is not None and len(out) >= total:
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

    def get_file_info(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Read an exact file/folder ID; None means confirmed absence only."""
        fid = str(file_id or "")
        if not fid.isdigit() or int(fid) <= 0:
            raise P115Error("无效的115文件ID")
        try:
            resp = self._call("fs_file", fid)
            self._require_success(resp, "文件信息查询")
        except P115NotFound:
            return None
        data = resp.get("data")
        if isinstance(data, list):
            data = next((item for item in data if isinstance(item, dict) and
                         str(item.get("file_id") or item.get("fid") or item.get("id") or item.get("cid")) == fid), None)
        if not isinstance(data, dict):
            raise P115Error("文件信息返回缺少匹配ID，无法确认文件是否存在")
        actual = str(data.get("file_id") or data.get("fid") or data.get("id") or data.get("cid") or "")
        parent = data.get("parent_id", data.get("pid"))
        if actual != fid or parent is None:
            raise P115Error("文件信息返回的ID或父目录无效")
        return {**data, "id": fid, "parent_id": str(parent),
                "name": str(data.get("file_name") or data.get("n") or data.get("fn") or "")}

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
            api = P115Api(client=self.client, disk_name="115网盘Plus")
            lookup = getattr(api, "get_item_strict", api.get_item)
            item = lookup(Path(src_path))
            if not item:
                return False, f"源路径不存在：{src_path}"
            if file_id and str(getattr(item, "fileid", "")) != str(file_id):
                return False, "源路径指向不同的115文件ID，未执行搬运，请核对同名文件"
            name = getattr(item, "name", None) or Path(src_path).name
            if api.move(item, Path(dest_dir), name):
                return True, ""
            return False, f"移动失败：{src_path} -> {dest_dir}"
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
