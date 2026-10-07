"""115 网盘操作：分享链接转存 + 磁力/ed2k 离线下载。

复用 p115client，与仓库里 115 系列插件保持一致的调用方式：
  * 转存：share_extract_payload -> share_receive({share_code, receive_code, file_id, cid})
  * 离线：clouddownload_task_add_urls({"url[0]": url, "wp_path_id": cid})
目录一律是 **115 网盘上的路径**（不是本地路径），通过目录 ID 定位。
"""
from __future__ import annotations

import random
import time
from typing import Any, Dict, Optional, Tuple

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


def normalize_115_share(url: str) -> str:
    """把 115cdn.com 的分享链接规范成 115.com，便于解析分享码。"""
    u = (url or "").strip()
    return u.replace("115cdn.com/s/", "115.com/s/").replace("//115cdn.com", "//115.com")


class P115Error(RuntimeError):
    pass


class _RateLimiter:
    def __init__(self, min_interval: float = 1.2, jitter: float = 0.3):
        self.min_interval = min_interval
        self.jitter = jitter
        self._last = 0.0

    def wait(self):
        now = time.time()
        gap = self.min_interval + random.uniform(-self.jitter, self.jitter)
        delta = now - self._last
        if delta < gap:
            time.sleep(gap - delta)
        self._last = time.time()


class P115Transfer:
    """115 网盘操作封装。"""

    def __init__(self, cookie: str, timeout: int = 30):
        if not P115_AVAILABLE:
            raise P115Error("未安装 p115client，请重装插件以安装依赖")
        if not cookie:
            raise P115Error("缺少 115 Cookie")
        self.client = P115Client(cookie)
        self._limiter = _RateLimiter()
        self._dir_cache: Dict[str, int] = {}

    # -- 基础 ---------------------------------------------------------------
    def check_login(self) -> bool:
        try:
            self._limiter.wait()
            return bool(self.client.user_info())
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
        self._limiter.wait()
        resp = self.client.fs_dir_getid(p)
        if resp.get("id"):
            cid = int(resp["id"])
            self._dir_cache[p] = cid
            return cid
        if not mkdir:
            raise P115Error(f"目录不存在：{p}")
        # 逐级创建
        cur = 0
        built = ""
        for part in [x for x in p.split("/") if x]:
            built = f"{built}/{part}"
            self._limiter.wait()
            r = self.client.fs_dir_getid(built)
            if r.get("id"):
                cur = int(r["id"])
                continue
            self._limiter.wait()
            r2 = self.client.fs_makedirs_app(built)
            cid = r2.get("cid") or r2.get("id")
            if not cid:
                raise P115Error(f"创建目录失败：{built} -> {r2}")
            cur = int(cid)
        self._dir_cache[p] = cur
        return cur

    # -- 转存 ---------------------------------------------------------------
    def check_share(self, share_url: str) -> Tuple[bool, str]:
        """只读校验分享是否可用，返回 (是否可用, 不可用原因)。

        115 对「分享已取消 / 已过期 / 提取码错误」等情况，在转存接口里只回一句
        「参数错误」，很难排查；先用 share_info 探一次，就能给出确切原因。
        """
        url = normalize_115_share(share_url)
        info = share_extract_payload(url)
        code = info.get("share_code")
        if not code:
            return False, "无法解析分享链接"
        try:
            self._limiter.wait()
            resp = self.client.share_info({
                "share_code": code,
                "receive_code": info.get("receive_code") or "",
            })
        except Exception:  # noqa: BLE001
            return True, ""      # 预检本身异常就不拦，交给正式转存去判断
        if (resp or {}).get("state"):
            return True, ""
        err = str((resp or {}).get("error") or (resp or {}).get("errno") or "分享不可用")
        return False, err

    def share_receive(self, share_url: str, save_path: str) -> bool:
        """把 115 分享链接整体转存到目标目录。"""
        ok, reason = self.check_share(share_url)
        if not ok:
            raise P115Error(f"分享已失效（{reason}）")
        url = normalize_115_share(share_url)
        payload_info = share_extract_payload(url)
        share_code = payload_info.get("share_code")
        receive_code = payload_info.get("receive_code") or ""
        if not share_code:
            raise P115Error(f"无法解析分享链接：{share_url}")
        cid = self.path_to_id(save_path, mkdir=True)
        last_err = ""
        for attempt in range(3):
            try:
                self._limiter.wait()
                resp = self.client.share_receive({
                    "share_code": share_code,
                    "receive_code": receive_code,
                    "file_id": "0",
                    "cid": cid,
                    "is_check": 0,
                })
                if resp.get("state"):
                    return True
                last_err = str(resp.get("error") or resp.get("errno") or resp)
                if "重复" in last_err or "已存在" in last_err:
                    return True
                if resp.get("errno") in (990001, 990002, 990009):
                    time.sleep((attempt + 1) * 2)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                last_err = str(exc)
                time.sleep((attempt + 1) * 1.5)
        raise P115Error(f"转存失败：{last_err}")

    # -- 离线下载 -----------------------------------------------------------
    def offline_add(self, url: str, save_path: str) -> bool:
        """把磁力 / ed2k（或其它直链）提交给 115 离线下载。"""
        cid = self.path_to_id(save_path, mkdir=True)
        resp = None
        for attempt in range(3):
            try:
                self._limiter.wait()
                resp = self.client.clouddownload_task_add_urls({
                    "url[0]": url.strip(),
                    "wp_path_id": cid,
                })
                if resp.get("state") or resp.get("errno") in (0, None):
                    if resp.get("state") is False:
                        raise P115Error(str(resp.get("error") or resp))
                    return True
                if resp.get("errno") in (990001, 990002, 990009):
                    time.sleep((attempt + 1) * 2)
                    continue
                break
            except Exception as exc:  # noqa: BLE001
                if attempt >= 2:
                    raise P115Error(f"离线下载提交失败：{exc}") from exc
                time.sleep((attempt + 1) * 1.5)
        raise P115Error(f"离线下载提交失败：{resp}")

    # -- 统一入口 -----------------------------------------------------------
    def add_resource(self, kind: str, url: str, save_path: str) -> Tuple[bool, str]:
        """按链接类型分派：115分享->转存；磁力/ed2k->离线下载。"""
        if kind == LINK_115_SHARE:
            self.share_receive(url, save_path)
            return True, "已转存"
        if kind in (LINK_MAGNET, LINK_ED2K):
            self.offline_add(url, save_path)
            return True, "已提交离线下载"
        return False, f"不支持的链接类型：{kind}"
