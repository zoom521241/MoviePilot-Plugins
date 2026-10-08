"""链接类型识别与分派。

表格里可能出现三类可转存链接：
  * 115 分享链接   -> 走 115 转存（share_receive）
  * magnet 磁力     -> 走 115 离线下载
  * ed2k 电驴       -> 走 115 离线下载
其余 http（如 themoviedb.org 的网页链接）不是资源链接，需排除。

注意（真实文档踩坑）：
  * ed2k 链接的字段分隔符是 ``|``，所以**不能**把它并进通用 URL 正则的字符集里
    （那会把 ``|`` 排除掉，导致 ``ed2k://|file|...`` 永远匹配不到）；
  * 腾讯文档里部分链接单元格的超链接会被写成 ``https://ed2k://...``（多了个
    http 前缀），需要先剥掉前缀再分类。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

LINK_115_SHARE = "115_share"
LINK_MAGNET = "magnet"
LINK_ED2K = "ed2k"
LINK_OTHER_HTTP = "http"

# 通用资源链接（不含 ed2k：ed2k 用 `|` 分隔，单独匹配）
_URL_RE = re.compile(r"(?:https?://|magnet:\?)[^\s\"'<>]{6,600}")
# ed2k 专用：允许 `|`
_ED2K_FULL_RE = re.compile(r"ed2k://[^\s\"'<>]+", re.I)
# 115 分享链接的域名（分享页可能用 115.com 或 115cdn.com）
_115_SHARE_RE = re.compile(r"^https?://(?:www\.)?115(?:cdn)?\.com/s/[A-Za-z0-9]+", re.I)
_MAGNET_RE = re.compile(r"^magnet:\?", re.I)
_ED2K_RE = re.compile(r"^ed2k://", re.I)


def normalize_url(url: str) -> str:
    """剥掉错误叠加的 http 前缀（如 ``https://ed2k://...`` / ``https://magnet:?...``）。

    正常的 ``https://115.com/s/...`` 不受影响。
    """
    u = (url or "").strip()
    while True:
        low = u.lower()
        if low.startswith("https://") and low[8:].startswith(("ed2k://", "magnet:")):
            u = u[8:]
            continue
        if low.startswith("http://") and low[7:].startswith(("ed2k://", "magnet:")):
            u = u[7:]
            continue
        break
    return u


def classify_link(url: str) -> Optional[str]:
    """判断单个链接属于哪一类；不是资源链接则返回 None。"""
    u = normalize_url(url)
    if not u:
        return None
    if _MAGNET_RE.match(u):
        return LINK_MAGNET
    if _ED2K_RE.match(u):
        return LINK_ED2K
    if _115_SHARE_RE.match(u):
        return LINK_115_SHARE
    if u.startswith(("http://", "https://")):
        # 115 分享的其它写法（如 115.com/s/ 短链被重定向域名）
        if "115.com/s/" in u or "115cdn.com/s/" in u:
            return LINK_115_SHARE
        return LINK_OTHER_HTTP
    return None


def is_resource_link(kind: Optional[str]) -> bool:
    return kind in (LINK_115_SHARE, LINK_MAGNET, LINK_ED2K)


def extract_links(text: str, include_other: bool = False) -> List[Tuple[str, str]]:
    """从一段文本里抽出所有资源链接 -> [(kind, url)]。"""
    out: List[Tuple[str, str]] = []
    t = text or ""

    # ed2k 单独扫描（`|` 分隔，通用正则匹配不到）
    for m in _ED2K_FULL_RE.findall(t):
        out.append((LINK_ED2K, m.rstrip("#&")))

    for m in _URL_RE.findall(t):
        u = normalize_url(m)
        kind = classify_link(u)
        if kind is None:
            continue
        # `https://ed2k://` 会被通用正则截成 `ed2k://`（无字段），跳过这个残片
        if kind == LINK_ED2K and "|" not in u:
            continue
        if kind == LINK_OTHER_HTTP and not include_other:
            continue
        out.append((kind, u.rstrip("#&")))
    return out


def dedup_links(links: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen, out = set(), []
    for kind, url in links:
        key = url.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append((kind, url))
    return out
