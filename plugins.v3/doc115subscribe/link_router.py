"""链接类型识别与分派。

表格里可能出现三类可转存链接：
  * 115 分享链接   -> 走 115 转存（share_receive）
  * magnet 磁力     -> 走 115 离线下载
  * ed2k 电驴       -> 走 115 离线下载
其余 http（如 themoviedb.org 的网页链接）不是资源链接，需排除。
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

LINK_115_SHARE = "115_share"
LINK_MAGNET = "magnet"
LINK_ED2K = "ed2k"
LINK_OTHER_HTTP = "http"

# 资源链接统一匹配
_URL_RE = re.compile(r"(?:https?://|magnet:\?|ed2k://)[^\s\"'<>|]{6,600}")
# 115 分享链接的域名（分享页可能用 115.com 或 115cdn.com）
_115_SHARE_RE = re.compile(r"^https?://(?:www\.)?115(?:cdn)?\.com/s/[A-Za-z0-9]+", re.I)
_MAGNET_RE = re.compile(r"^magnet:\?", re.I)
_ED2K_RE = re.compile(r"^ed2k://", re.I)


def classify_link(url: str) -> Optional[str]:
    """判断单个链接属于哪一类；不是资源链接则返回 None。"""
    u = (url or "").strip()
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


def extract_links(text: str, include_other: bool = False) -> List[Tuple[str, str]]:
    """从一段文本里抽出所有资源链接 -> [(kind, url)]。"""
    out: List[Tuple[str, str]] = []
    for m in _URL_RE.findall(text or ""):
        kind = classify_link(m)
        if kind is None:
            continue
        if kind == LINK_OTHER_HTTP and not include_other:
            continue
        out.append((kind, m.rstrip("#&")))
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


def is_resource_link(kind: Optional[str]) -> bool:
    return kind in (LINK_115_SHARE, LINK_MAGNET, LINK_ED2K)
