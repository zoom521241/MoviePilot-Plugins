# -*- coding: utf-8 -*-
"""夸克网盘客户端。

封装插件需要的目录枚举、路径解析与下载直链获取能力，并内建限流。

**必须注意**：夸克 ``drive-pc`` 系列接口要求同时携带 ``pr=ucpro`` 与 ``fr=pc``
两个参数，缺失任意一个都会返回 401 且响应体为加密串，排查成本很高。
本模块统一在 ``_request`` 中补齐这两个参数。
"""

import threading
import time
from typing import Any, Dict, Iterator, List, Optional

import requests

from .quark_auth import (
    API_SUCCESS,
    LIST_URL,
    ORIGIN,
    REFERER,
    USER_AGENT,
)

# 固定请求参数，缺一即 401
BASE_PARAMS = {"pr": "ucpro", "fr": "pc"}
DOWNLOAD_URL = "https://drive-pc.quark.cn/1/clouddrive/file/download"


class RateLimiter:
    """基于滑动时间窗口的限流器。

    插件长时间无人值守运行，宁可比官方更保守。
    """

    def __init__(self, max_calls: int = 1, time_window: float = 1.0):
        """初始化限流器。

        :param max_calls: 时间窗口内允许的调用次数
        :param time_window: 时间窗口长度（秒）
        """
        self.max_calls = max(1, max_calls)
        self.time_window = max(0.1, float(time_window))
        self._lock = threading.Lock()
        self._calls: List[float] = []

    def acquire(self) -> None:
        """获取一次调用许可，超出限制时阻塞等待。"""
        with self._lock:
            now = time.monotonic()
            self._calls = [t for t in self._calls if now - t < self.time_window]
            if len(self._calls) >= self.max_calls:
                sleep_time = self.time_window - (now - min(self._calls))
                if sleep_time > 0:
                    time.sleep(sleep_time)
                    now = time.monotonic()
                    self._calls = [t for t in self._calls if now - t < self.time_window]
            self._calls.append(now)


class QuarkClient:
    """夸克网盘客户端。"""

    def __init__(self, cookie: str, timeout: int = 20, qps: float = 1.0):
        """初始化客户端。

        :param cookie: 夸克网盘 cookie
        :param timeout: 单次请求超时秒数
        :param qps: 每秒允许的 API 调用次数
        """
        self.cookie = (cookie or "").strip()
        self.timeout = timeout
        self.limiter = RateLimiter(max_calls=max(1, int(qps)), time_window=1.0)
        self._session = requests.Session()
        # 路径 -> fid 缓存，避免重复遍历
        self._path_cache: Dict[str, str] = {"/": "0"}

    # ------------------------------------------------------------------ #
    # 基础请求
    # ------------------------------------------------------------------ #
    def _request(self, method: str, url: str, params: dict = None,
                 json_body: dict = None) -> Optional[dict]:
        """发起一次接口请求并返回业务数据。

        :param method: HTTP 方法
        :param url: 接口地址
        :param params: 查询参数，会自动合并 pr/fr
        :param json_body: JSON 请求体
        :return: 响应中的 data 字段，失败返回 None
        """
        self.limiter.acquire()
        query = dict(BASE_PARAMS)
        if params:
            query.update(params)
        try:
            resp = self._session.request(
                method,
                url,
                params=query,
                json=json_body,
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": REFERER,
                    "Origin": ORIGIN,
                    "Cookie": self.cookie,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            body = resp.json()
            if body.get("status") not in (API_SUCCESS, 0):
                return None
            return body.get("data") or {}
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # 目录操作
    # ------------------------------------------------------------------ #
    def list_dir(self, pdir_fid: str = "0", page: int = 1,
                 size: int = 100) -> Optional[dict]:
        """列出指定目录下的对象。

        :param pdir_fid: 父目录 fid，根目录为 "0"
        :param page: 页码，从 1 开始
        :param size: 每页条数
        :return: 含 list / total 的字典，失败返回 None
        """
        return self._request(
            "GET",
            LIST_URL,
            params={
                "pdir_fid": pdir_fid,
                "_page": page,
                "_size": size,
                "_fetch_total": 1,
                "_fetch_sub_dirs": 0,
                "_sort": "file_type:asc,updated_at:desc",
            },
        )

    def iter_dir(self, pdir_fid: str = "0", page_size: int = 100) -> Iterator[dict]:
        """分页遍历目录下的全部对象。

        :param pdir_fid: 父目录 fid
        :param page_size: 每页条数
        :return: 逐条产出对象字典
        """
        page = 1
        while True:
            data = self.list_dir(pdir_fid, page=page, size=page_size)
            if not data:
                return
            items = data.get("list") or []
            if not items:
                return
            for item in items:
                yield item
            total = data.get("total")
            if isinstance(total, int) and page * page_size >= total:
                return
            if len(items) < page_size:
                return
            page += 1

    def resolve_path(self, path: str) -> Optional[str]:
        """把网盘绝对路径解析为 fid。

        逐级向下查找并缓存中间结果，避免重复请求。

        :param path: 形如 /影视/电影 的绝对路径
        :return: 目录 fid，找不到返回 None
        """
        normalized = (path or "/").strip()
        if not normalized.startswith("/"):
            normalized = f"/{normalized}"
        normalized = normalized.rstrip("/") or "/"
        if normalized in self._path_cache:
            return self._path_cache[normalized]

        parent_fid = "0"
        current = ""
        for segment in [s for s in normalized.split("/") if s]:
            current = f"{current}/{segment}"
            if current in self._path_cache:
                parent_fid = self._path_cache[current]
                continue
            found = None
            for item in self.iter_dir(parent_fid):
                if item.get("dir") and item.get("file_name") == segment:
                    found = item.get("fid")
                    break
            if not found:
                return None
            self._path_cache[current] = found
            parent_fid = found
        return parent_fid

    def walk(self, pdir_fid: str = "0", max_depth: int = 3, max_nodes: int = 500,
             _prefix: str = "", _depth: int = 0,
             _counter: Optional[List[int]] = None) -> Iterator[dict]:
        """按深度优先递归遍历目录树。

        遍历深度与节点数双重受限，避免误填根目录时把整个网盘翻一遍——
        那既慢又容易触发风控。

        :param pdir_fid: 起始目录 fid
        :param max_depth: 最大递归深度，根目录自身为第 0 层
        :param max_nodes: 最多枚举的对象总数，超出即停止
        :return: 逐条产出带 path 字段的对象字典
        """
        if _counter is None:
            _counter = [0]
        if max_depth <= 0:
            max_depth = 1
        if max_nodes <= 0:
            max_nodes = 100
        if _depth >= max_depth or _counter[0] >= max_nodes:
            return

        for item in self.iter_dir(pdir_fid):
            if _counter[0] >= max_nodes:
                return
            _counter[0] += 1
            name = item.get("file_name") or ""
            item["path"] = f"{_prefix}/{name}".replace("//", "/")
            yield item
            if item.get("dir") and _depth + 1 < max_depth:
                yield from self.walk(
                    item.get("fid"),
                    max_depth=max_depth,
                    max_nodes=max_nodes,
                    _prefix=item["path"],
                    _depth=_depth + 1,
                    _counter=_counter,
                )

    # ------------------------------------------------------------------ #
    # 下载
    # ------------------------------------------------------------------ #
    def get_download_url(self, fid: str) -> Optional[str]:
        """获取文件的临时下载直链。

        直链有时效与防盗链限制，取得后应尽快使用，不要把直链长期缓存。

        :param fid: 文件 fid
        :return: 下载直链，失败返回 None
        """
        data = self._request("POST", DOWNLOAD_URL, json_body={"fids": [fid]})
        if not data:
            return None
        for item in data if isinstance(data, list) else []:
            if item.get("fid") == fid:
                return item.get("download_url")
        return None

    def download_file(self, fid: str, local_path: str,
                      chunk_size: int = 1024 * 1024) -> bool:
        """把网盘文件下载到本地。

        :param fid: 文件 fid
        :param local_path: 本地保存路径
        :param chunk_size: 分块大小
        :return: 成功返回 True
        """
        url = self.get_download_url(fid)
        if not url:
            return False
        self.limiter.acquire()
        try:
            with self._session.get(url, stream=True, timeout=60) as resp:
                if resp.status_code != 200:
                    return False
                with open(local_path, "wb") as fp:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            fp.write(chunk)
            return True
        except Exception:
            return False

    def close(self) -> None:
        """关闭底层会话释放连接。"""
        try:
            self._session.close()
        except Exception:
            pass
