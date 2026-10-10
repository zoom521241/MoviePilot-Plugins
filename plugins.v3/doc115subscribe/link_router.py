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
    http 前缀），需要先剥掉前缀再分类；
  * URL 只由 ASCII 可见字符组成，紧跟的中文/全角标点不属于链接；
  * 115 分享（115.com / 115cdn.com / anxia.com 及子域）统一规范为
    ``https://115.com/s/<code>?password=xxxx``，同格文本里的提取码会补进去。
"""
from __future__ import annotations

import re
import html
from typing import List, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

LINK_115_SHARE = "115_share"
LINK_MAGNET = "magnet"
LINK_ED2K = "ed2k"
LINK_OTHER_HTTP = "http"

# 通用资源链接（不含 ed2k：ed2k 用 `|` 分隔，单独匹配）。
# 只允许 ASCII 可见字符 [!-~]：全角标点、中文紧跟在链接后都不会被吞进 URL。
_URL_RE = re.compile(r"(?:https?://|magnet:\?)(?:(?![\"'<>])[!-~])+", re.I)
# 结尾常见的 ASCII 包裹/句读符号，不属于链接本身
_URL_TRAIL = "\"'<>()[]{},.;!?"
# ed2k 结构：ed2k://|file|<名称，可含空格>|<字节数>|<32位MD4>|[h=...|][p=...|]/
_ED2K_FULL_RE = re.compile(
    r"(?:https?://)?(ed2k://\|file\|[^|\r\n]+?\|\d+\|[0-9a-fA-F]{32}\|(?:[a-z]=[^|\s]*\|)*/?)",
    re.I)
# 115 分享链接的域名（分享页可能用 115.com / 115cdn.com / anxia.com 及其子域）
_115_ROOTS = ("115.com", "115cdn.com", "anxia.com")
_115_HOSTS = {"115.com", "www.115.com", "share.115.com", "115cdn.com", "www.115cdn.com",
              "anxia.com", "www.anxia.com"}
# 统一的 115 分享规范化目标（与 p115_transfer.normalize_115_share 一致；p115client 可解析）
SHARE_CANONICAL_HOST = "115.com"
_SHARE_PATH_RE = re.compile(r"/s/([A-Za-z0-9]+)/?")
# 同一文本里的提取码：提取码 / 访问码 / 密码 / pwd / code
_PASSWORD_RE = re.compile(r"(?:提取码|访问码|密码|pwd|code)\s*[:：=]?\s*([A-Za-z0-9]{4})(?![A-Za-z0-9])", re.I)
_MAGNET_RE = re.compile(r"^magnet:\?", re.I)
_ED2K_RE = re.compile(r"^ed2k://", re.I)


def is_115_host(host: str) -> bool:
    host = (host or "").lower().rstrip(".")
    return host in _115_HOSTS or any(host.endswith("." + root) for root in _115_ROOTS)


def share_parts(url: str) -> Optional[Tuple[str, str]]:
    """115 分享链接 -> (分享码, 提取码)；不是 115 分享则返回 None。"""
    try:
        parsed = urlsplit(normalize_url(url))
        if (parsed.scheme.lower() not in ("http", "https") or not is_115_host(parsed.hostname or "")
                or parsed.username or parsed.password or parsed.port not in (None, 80, 443)):
            return None
    except ValueError:
        return None
    m = _SHARE_PATH_RE.fullmatch(parsed.path)
    if not m:
        return None
    query = parse_qs(parsed.query)
    password = ""
    for key in ("password", "pwd", "receive_code"):
        value = (query.get(key) or [""])[0].strip()
        if re.fullmatch(r"[A-Za-z0-9]{4}", value):
            password = value
            break
    if not password:
        fm = re.search(r"(?:password|pwd)=([A-Za-z0-9]{4})", parsed.fragment, re.I)
        password = fm.group(1) if fm else ""
    return m.group(1), password


def normalize_115_share(url: str, password: str = "") -> str:
    """统一成 ``https://115.com/s/<code>?password=xxxx``（无提取码时不带参数）。"""
    parts = share_parts(url)
    if not parts:
        return (url or "").strip()
    code, own = parts
    pwd = own or (password if re.fullmatch(r"[A-Za-z0-9]{4}", password or "") else "")
    return f"https://{SHARE_CANONICAL_HOST}/s/{code}" + (f"?password={pwd}" if pwd else "")


def find_password(text: str) -> str:
    m = _PASSWORD_RE.search(text or "")
    return m.group(1) if m else ""


def normalize_url(url: str) -> str:
    """剥掉错误叠加的 http 前缀（如 ``https://ed2k://...`` / ``https://magnet:?...``）。

    正常的 ``https://115.com/s/...`` 不受影响。
    """
    u = html.unescape(url or "").strip()
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
    try:
        parsed = urlsplit(u)
        if parsed.scheme.lower() in ("http", "https") and parsed.hostname:
            # 只能按 URL 的真实主机判断，不能匹配路径、查询或伪造域名中的 115.com。
            if share_parts(u):
                return LINK_115_SHARE
            return LINK_OTHER_HTTP
    except ValueError:
        return None
    return None


def is_resource_link(kind: Optional[str]) -> bool:
    return kind in (LINK_115_SHARE, LINK_MAGNET, LINK_ED2K)


def extract_links(text: str, include_other: bool = False) -> List[Tuple[str, str]]:
    """从一段文本里抽出所有资源链接 -> [(kind, url)]。

    115 分享链接会规范化，并把同一文本里的「提取码/访问码/密码/pwd/code」补进 ?password=。
    """
    out: List[Tuple[str, str]] = []
    t = html.unescape(text or "")
    password = find_password(t)

    # ed2k 单独按结构扫描（名称可含空格；`https://` 包裹前缀会被去掉）
    spans = []
    for m in _ED2K_FULL_RE.finditer(t):
        out.append((LINK_ED2K, m.group(1)))
        spans.append(m.span())

    for m in _URL_RE.finditer(t):
        if any(a <= m.start() < b for a, b in spans):
            continue
        u = normalize_url(m.group(0).rstrip(_URL_TRAIL)).rstrip("#&")
        kind = classify_link(u)
        if kind is None or kind == LINK_ED2K:
            continue        # ed2k 已按结构匹配；残片跳过
        if kind == LINK_OTHER_HTTP and not include_other:
            continue
        if kind == LINK_115_SHARE:
            u = normalize_115_share(u, password)
        out.append((kind, u))
    return out


def link_key(kind: str, url: str) -> str:
    """去重键：115 分享按分享码，ed2k 按哈希，其余按规范化 URL。"""
    if kind == LINK_115_SHARE:
        parts = share_parts(url)
        if parts:
            return "115:" + parts[0]
    if kind == LINK_ED2K:
        m = re.search(r"\|([0-9a-fA-F]{32})\|", url or "")
        if m:
            return "ed2k:" + m.group(1).lower()
    if kind == LINK_MAGNET:
        m = re.search(r"urn:btih:([0-9a-zA-Z]+)", url or "", re.I)
        if m:
            return "magnet:" + m.group(1).lower()
    return (url or "").rstrip("/")


def dedup_links(links: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """去重；同一个 115 分享保留带提取码的那条。"""
    index, out = {}, []
    for kind, url in links:
        key = link_key(kind, url)
        if key in index:
            pos = index[key]
            if kind == LINK_115_SHARE and "password=" in url and "password=" not in out[pos][1]:
                out[pos] = (kind, url)
            continue
        index[key] = len(out)
        out.append((kind, url))
    return out
