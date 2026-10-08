"""表格解析：把「单元格网格」变成可用的资源记录。

表格结构在不同工作表之间并不统一（列名、列数、链接是文本还是超链接都不一样），
所以这里采用**宽容解析**：
  * 先在前若干行里找表头（含「名称/标题/片名…」），定位名称列；
  * 链接不依赖固定列，**扫描整行的文本与超链接**，再用 link_router 过滤出资源链接；
  * 分辨率/字幕等规格信息按关键字从整行文本里提取，用于选片排序。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

try:  # 作为包的一部分加载（MoviePilot 运行时）
    from .link_router import (LINK_115_SHARE, LINK_ED2K, LINK_MAGNET,
                              LINK_OTHER_HTTP, classify_link, dedup_links,
                              extract_links, is_resource_link, normalize_url)
except ImportError:  # 直接作为顶层模块加载（脚本/单测）
    from link_router import (LINK_115_SHARE, LINK_ED2K, LINK_MAGNET,
                             LINK_OTHER_HTTP, classify_link, dedup_links,
                             extract_links, is_resource_link, normalize_url)

# 工作表 -> 资源大类
SHEET_KINDS = [
    ("anime", ("动漫", "国漫", "动画", "番剧")),
    ("variety", ("综艺",)),
    ("documentary", ("纪录片", "bbc")),
    ("music", ("音乐", "演唱会")),
    ("book", ("图书", "小说", "评书")),
    ("game", ("游戏",)),
    ("tv", ("剧", "tvb", "美剧", "英剧", "韩剧", "日剧", "泰剧", "短剧", "电视剧")),
    ("movie", ("电影", "港片", "漫威", "邵氏", "奥斯卡", "金棕榈", "票房", "top250")),
]

NAME_HEADS = ("名称", "名字", "标题", "影视名称", "片名", "剧名", "资源名", "影片",
              "电影名称", "影片名称", "资源名称", "影视名")
# 英文表头（如 高清影视之家 的 Title/Name 列）；必须整格等于才算，避免误伤含 name 的片名
NAME_HEADS_EN = ("title", "name", "movie", "film")
LINK_HEADS = ("链接", "转存", "地址", "下载")
RES_HEADS = ("分辨率", "清晰度", "画质", "规格")
SUB_HEADS = ("字幕", "语言", "中字")
SKIP_SHEETS = ("wpsreserved_cellimgl",)  # 腾讯文档内部表

# 片名里的「剧集」特征：第N季 / 全N集 / 共N集 / S01E02 / S01 / Season 1
_TV_TITLE_RE = re.compile(
    r"(第[一二三四五六七八九十\d]+季|全\s*\d+\s*集|共\s*\d+\s*集|"
    r"(?<![A-Za-z0-9])S\d{1,2}E\d{1,3}(?![0-9])|(?<![A-Za-z0-9])S\d{1,2}(?![0-9])|"
    r"Season\s*\d+)",
    re.I,
)

_QUALITY_4K = re.compile(r"(?<![A-Za-z0-9])(?:4k|2160p?|uhd)(?![A-Za-z0-9])", re.I)
_QUALITY_1080 = re.compile(r"(1080p|1080)", re.I)
_CN_SUB = re.compile(r"(中文|中字|国语|简中|繁中|简繁)", re.I)
_NO_CN = re.compile(r"无\s*(中文|中字|字幕)|无字幕", re.I)
_YEAR_RE = re.compile(r"[（(\[]((?:18|19|20|21)\d{2})[)）\]]")
_TMDB_HOSTS = {"themoviedb.org", "www.themoviedb.org", "tmdb.org", "www.tmdb.org"}


def classify_sheet(sheet_name: str) -> str:
    """按工作表名判断资源大类。"""
    n = (sheet_name or "").lower()
    # 动画电影仍然是电影；画质词完全不参与媒体类型识别。
    if "电影" in n and not any(k in n for k in ("电视剧", "电影剧集", "电影/剧", "电影、剧")):
        return "movie"
    for kind, keys in SHEET_KINDS:
        if any(k in n for k in keys):
            return kind
    return "other"


def is_skippable_sheet(sheet_name: str) -> bool:
    n = (sheet_name or "").lower()
    return any(s in n for s in SKIP_SHEETS)


def media_type_of(sheet_name: str, title: str = "") -> str:
    """返回 'movie'、'tv' 或 'unknown'。

    ⚠️ **片名特征优先于工作表名**：工作表名常常不可靠（例如「蚂蚁和 rb4k」这类复合表里
    既有电影也有剧集），只看表名会把「洛基 第二季[全6集]」判成电影。
    """
    t = title or ""
    if _TV_TITLE_RE.search(t):
        return "tv"
    kind = classify_sheet(sheet_name)
    if kind == "movie":
        return "movie"
    if kind in ("tv", "anime", "variety"):
        return "tv"
    return "unknown"


def is_name_head(text: str) -> bool:
    """判断一个单元格是否是「名称/标题」表头（含英文 Title/Name，需整格匹配）。"""
    t = (text or "").strip()
    if not t or len(t) > 8:
        return False
    return t in NAME_HEADS or t.lower() in NAME_HEADS_EN


# 「横幅行」：表头区/整表打包链接所在的行（尤其是单列「目录型」表）
BANNER_HINTS = ("打包链接", "大包链接", "点我返回", "点我直达", "点击直达", "点击这里",
                "点击进去", "复制资源", "资源列表", "目录", "快捷键")


def is_banner_row(row: List[str]) -> bool:
    txt = " ".join((c or "") for c in (row or []))
    return any(h in txt for h in BANNER_HINTS)


def _find_header(grid: List[List[str]], hrefs=None) -> Tuple[int, Optional[int]]:
    """在前 12 行里找表头 -> (表头行号, 名称列号)。找不到返回 (-1, None)。"""
    best = (-1, None, -1)
    for r in range(min(12, len(grid))):
        row = grid[r]
        non_empty = sum(1 for c in row if c.strip())
        name_col = None
        for ci, c in enumerate(row):
            if is_name_head(c):
                name_col = ci
                break
        # 没有明确名称表头时，不能把第一条数据误当成表头。
        if name_col is None:
            continue
        if any(extract_links(c or "") for c in row) or any(
                href and is_resource_link(classify_link(href)) for href in
                ((hrefs[r] if r < len(hrefs) else []) if hrefs else [])):
            continue
        score = non_empty + (10 if name_col is not None else 0)
        if score > best[2]:
            best = (r, name_col, score)
    return best[0], best[1]


def extract_year(title: str) -> str:
    """只识别发行年份标注，保留《1917》《2001：太空漫游》等片名中的数字。"""
    m = _YEAR_RE.search(title or "")
    if m:
        return m.group(1)
    # 裸结尾数字也可能属于片名，只有后接发布规格时才当作年份。
    m = re.search(r"(?:\s|[._-])((?:18|19|20|21)\d{2})(?=[\s._-]+[\[（(]?(?:4k|2160p?|1080p?|720p?|uhd|remux|bluray|web-dl|中字|中文字幕))",
                  title or "", re.I)
    return m.group(1) if m else ""


def _tmdb_value(value: str, numeric: bool = False) -> Tuple[str, str]:
    """解析 TMDB ID 或 TMDB 页面 URL；URL 同时携带 movie/tv 类型。"""
    text = (value or "").strip()
    if numeric and re.fullmatch(r"[1-9]\d*", text):
        return str(int(text)), ""
    for candidate in re.findall(r"https?://[^\s\"'<>，。；）]+", text, re.I):
        try:
            parsed = urlsplit(candidate)
            if (parsed.hostname or "").lower() not in _TMDB_HOSTS or parsed.username or parsed.password:
                continue
            m = re.match(r"^/(?:[A-Za-z]{2}(?:-[A-Za-z]{2})?/)?(movie|tv)/([1-9]\d*)(?:[-/]|$)", parsed.path)
            if m:
                return str(int(m.group(2))), m.group(1)
        except ValueError:
            continue
    return "", ""


def _title_cell(text: str) -> bool:
    t = (text or "").strip()
    if not t or t.isdecimal() or is_name_head(t) or is_banner_row([t]):
        return False
    if re.search(r"(?:https?://|magnet:|ed2k://)", t, re.I):
        return False
    if t.lower() in ("download", "link", "url", "点击转存", "点击下载", "转存", "链接", "下载"):
        return False
    # 不让纯画质、字幕、TMDB 编号列压过片名列。
    plain = re.sub(r"(?:4k|2160p?|1080p?|720p?|uhd|remux|bluray|blu-ray|web-dl|h\.?26[45]|"
                   r"中文|中字|国语|简中|繁中|简繁|字幕|无字幕|蓝光|原盘|杜比视界|简体|繁体|英语|中英)", "", t, flags=re.I)
    return bool(re.search(r"[A-Za-z\u3400-\u9fff]", plain))


def _infer_name_column(grid: List[List[str]], start: int) -> int:
    scores = []
    for ci in range(max((len(r) for r in grid), default=0)):
        values = [row[ci] for row in grid[start:start + 100] if ci < len(row) and _title_cell(row[ci])]
        score = sum(10 + min(len(value.strip()), 40) / 10 for value in values) - ci / 100
        scores.append((score, -ci))
    return -max(scores)[1] if scores else 0


def _collect_links(row: List[str], href_row: List[Optional[str]],
                   include_external: bool = False) -> List[Tuple[str, str]]:
    """收集一行里的资源链接：单元格文本 + 单元格超链接 -> [(kind, url)]。

    超链接里可能带错误的前缀（如 ``https://ed2k://...``），统一走 normalize_url。
    """
    raw: List[Tuple[str, str]] = []
    for c in (row or []):
        raw.extend(extract_links(c or "", include_other=include_external))
    for href in (href_row or []):
        if not href:
            continue
        u = normalize_url(href)
        k = classify_link(u)
        if k is None:
            continue
        if k == LINK_OTHER_HTTP and not include_external:
            continue
        raw.append((k, u.rstrip("#&")))
    return dedup_links(raw)


def parse_sheet(sheet_id: str, sheet_name: str,
                grid: List[List[str]], hrefs: List[List[Optional[str]]]) -> List[Dict[str, Any]]:
    """把一张工作表解析成资源记录列表。

    关键（真实文档踩坑）：
      * 链接**不一定在数据行里**——很多「合集/目录」表的表头挂着一个整表
        「打包链接」，数据行只有「序号 + 名称」。这类表要把表头链接**下放**到
        每一行，并标记 ``sheet_bundle=True``（整表打包，大包）。
      * 整表没有任何资源链接（只在表头挂了个外部文档链接，如 KDocs）的表：
        仍然保留记录用于**搜索**，标记 ``no_link=True``，并把外部链接作为参考展示。
    """
    if not grid:
        return []
    hdr_row, name_col = _find_header(grid, hrefs)
    start = hdr_row + 1 if hdr_row >= 0 else 0

    # 无表头时按非链接、非数字、非纯规格的文本列推断名称。
    if name_col is None:
        name_col = _infer_name_column(grid, start)

    tmdb_col = year_col = None
    res_col = sub_col = None
    if hdr_row >= 0:
        for ci, c in enumerate(grid[hdr_row]):
            t = (c or "").strip().lower()
            if "tmdb" in t:
                tmdb_col = ci
            elif t in ("年份", "年代", "上映年份", "year", "release year"):
                year_col = ci
            elif res_col is None and any(h in t for h in RES_HEADS):
                res_col = ci
            elif sub_col is None and any(h in t for h in SUB_HEADS):
                sub_col = ci

    def href_row(r: int) -> List[Optional[str]]:
        return hrefs[r] if r < len(hrefs) else []

    # 「表头区」= 表头行之前的行 + 顶部若干行里明显的横幅行。
    # 很多「合集/目录」表是**单列**结构、没有真正的表头行（如 老电影 / 动漫原盘），
    # 整表打包链接就挂在第 1~2 行的横幅里（"打包链接，点我直达"），必须把它们算作表头。
    top_end = min(8, len(grid))
    banner_rows = {r for r in range(top_end) if is_banner_row(grid[r])}
    header_area = set(range(0, start)) | banner_rows

    header_links: List[Tuple[str, str]] = []
    for r in sorted(header_area):
        header_links.extend(_collect_links(grid[r], href_row(r)))
    header_links = dedup_links(header_links)

    # 表头/横幅里的普通网页链接（如外部 KDocs 文档），用于「纯列表表」的参考展示
    header_http: List[str] = []
    for r in sorted(header_area):
        for href in href_row(r):
            if href and classify_link(normalize_url(href)) == LINK_OTHER_HTTP:
                header_http.append(normalize_url(href).rstrip("#&"))
    header_http = list(dict.fromkeys(header_http))

    # 第一遍：收集「数据行」及其自带链接；判断整表是否存在资源链接
    any_resource = any(is_resource_link(k) for k, _ in header_links)
    candidates: List[Tuple[int, str, List[Tuple[str, str]]]] = []
    for r in range(start, len(grid)):
        if r in header_area:
            continue
        row = grid[r]
        if not any((c or "").strip() for c in row):
            continue
        title = (row[name_col] if name_col < len(row) else "").strip()
        own = _collect_links(row, href_row(r))
        if (not title or is_name_head(title) and not own
                or re.match(r"^(?:https?://|magnet:|ed2k://)", title, re.I)):
            continue
        if any(is_resource_link(k) for k, _ in own):
            any_resource = True
        candidates.append((r, title, own))

    records: List[Dict[str, Any]] = []
    link_counter: Dict[str, int] = {}
    for r, title, own in candidates:
        if own:
            links, sheet_bundle = own, False
        elif header_links:
            links, sheet_bundle = header_links, True   # 整表打包链接 -> 下放到数据行
        elif any_resource:
            continue        # 有链接的表里，没链接的行视为标题/分隔行，跳过
        else:
            links, sheet_bundle = [], False            # 整表无资源链接：留空，稍后统一填外链

        row = grid[r]
        year = extract_year(title)
        if year_col is not None and year_col < len(row):
            ym = re.fullmatch(r"(?:18|19|20|21)\d{2}", (row[year_col] or "").strip())
            if ym:
                year = ym.group(0)
        tmdbid = ""
        tmdb_type = ""
        if tmdb_col is not None and tmdb_col < len(row):
            tmdbid, tmdb_type = _tmdb_value(row[tmdb_col], numeric=True)
        for value in list(row) + list(href_row(r)):
            tid, ttype = _tmdb_value(value or "")
            if tid and (not tmdbid or tid == tmdbid):
                tmdbid, tmdb_type = tid, ttype
                break

        spec = " ".join((c or "").strip() for c in row if c and c.strip() != title)

        # 规格文本：优先取「分辨率 / 字幕」两列，取不到再退回整行
        q_parts = []
        for ci in (res_col, sub_col):
            if ci is not None and ci < len(row) and (row[ci] or "").strip():
                q_parts.append(row[ci].strip())
        qtext = clean_display(" ".join(q_parts) or spec)

        for _, url in links:
            link_counter[url] = link_counter.get(url, 0) + 1

        records.append({
            "sheet_id": sheet_id,
            "sheet": sheet_name,
            "kind": classify_sheet(sheet_name),
            "row": r,
            "title": title,
            "year": year,
            "tmdbid": tmdbid,
            "media_type": tmdb_type or media_type_of(sheet_name, title),
            "spec": spec[:300],
            "qtext": qtext,
            "links": links,
            "sheet_bundle": sheet_bundle,
        })

    # 整表没有任何资源链接（如只在表头挂了外部文档链接的纯列表表）：仅搜索
    if records and not any_resource:
        ref = [(LINK_OTHER_HTTP, u) for u in header_http]
        for rec in records:
            rec["no_link"] = True
            rec["links"] = list(ref)

    # 标记「打包链接」：同一个链接被很多行共用（或整表共用表头打包链接）
    data_rows = max(1, len(records))
    for rec in records:
        if rec.get("sheet_bundle"):
            rec["bundle"] = True
            continue
        rec["bundle"] = any(link_counter.get(u, 0) >= 3 and link_counter.get(u, 0) >= 0.1 * data_rows
                            for _, u in rec["links"])
    return records


# ---------------------------------------------------------------------------
# 选片排序：4K + 中文 优先，其次 4K / 中文，都不满足取最新（行号最小）
# ---------------------------------------------------------------------------
_LINK_NOISE = re.compile(r"(https?://\S+|magnet:\S+|ed2k://\S+)")


def clean_display(text: str, limit: int = 90) -> str:
    """把整行文本整理成适合展示的「规格」：去掉链接、压缩空白、限长。"""
    t = _LINK_NOISE.sub(" ", text or "")
    t = re.sub(r"\s+", " ", t).strip(" -|,，、")
    return t[:limit]


def has_chinese(qtext: str) -> bool:
    """判断是否含中文字幕/语言；「无中字」要判为否。"""
    t = qtext or ""
    if _NO_CN.search(t):
        return False
    return bool(_CN_SUB.search(t))


def quality_score(rec: Dict[str, Any]) -> int:
    text = f"{rec.get('title','')} {rec.get('qtext') or rec.get('spec','')}"
    has_4k = bool(_QUALITY_4K.search(text))
    has_cn = has_chinese(text)
    if has_4k and has_cn:
        return 3
    if has_4k:
        return 2
    if has_cn:
        return 1
    return 0


def is_4k(rec: Dict[str, Any]) -> bool:
    return bool(_QUALITY_4K.search(f"{rec.get('title', '')} {rec.get('qtext') or rec.get('spec', '')}"))


def pick_best(records: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """在候选记录里选出最优的一条（4K+中文优先，其次取最靠前=最新）。"""
    if not records:
        return None
    return min(records, key=lambda r: (-quality_score(r), r.get("row", 0)))


def iter_links(rec: Dict[str, Any]):
    """统一遍历记录的链接，兼容两种形态：
      * 解析器原始形态：[(kind, url), ...]
      * 索引/接口形态：[{"kind":..., "url":...}, ...]
    """
    for item in (rec.get("links") or []):
        if isinstance(item, dict):
            yield item.get("kind"), item.get("url")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            yield item[0], item[1]


def search(records: List[Dict[str, Any]], keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
    """按关键词模糊匹配标题（去空格、忽略大小写）。"""
    kw = re.sub(r"\s+", "", (keyword or "")).lower()
    if not kw:
        return []
    hit = []
    for rec in records:
        t = re.sub(r"\s+", "", rec["title"]).lower()
        if kw in t:
            hit.append(rec)
    hit.sort(key=lambda r: (-quality_score(r), r.get("row", 0)))
    return hit[:limit]
