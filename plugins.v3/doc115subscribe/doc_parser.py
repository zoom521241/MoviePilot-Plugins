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

try:  # 作为包的一部分加载（MoviePilot 运行时）
    from .link_router import (LINK_115_SHARE, LINK_ED2K, LINK_MAGNET,
                              classify_link, dedup_links, extract_links)
except ImportError:  # 直接作为顶层模块加载（脚本/单测）
    from link_router import (LINK_115_SHARE, LINK_ED2K, LINK_MAGNET,
                             classify_link, dedup_links, extract_links)

# 工作表 -> 资源大类
SHEET_KINDS = [
    ("movie", ("电影", "原盘", "remux", "蓝光", "blu", "1080p", "4k", "uhd", "港片", "漫威", "邵氏",
               "奥斯卡", "金棕榈", "票房", "top250", "高清影视", "ed2k")),
    ("tv", ("剧", "tvb", "美剧", "英剧", "韩剧", "日剧", "泰剧", "短剧", "电视剧")),
    ("anime", ("动漫", "国漫", "动画", "番剧")),
    ("variety", ("综艺",)),
    ("documentary", ("纪录片", "bbc")),
    ("music", ("音乐", "演唱会")),
    ("book", ("图书", "小说", "评书")),
    ("game", ("游戏",)),
]

NAME_HEADS = ("名称", "名字", "标题", "影视名称", "片名", "剧名", "资源名", "影片")
LINK_HEADS = ("链接", "转存", "地址", "下载")
RES_HEADS = ("分辨率", "清晰度", "画质", "规格")
SUB_HEADS = ("字幕", "语言", "中字")
SKIP_SHEETS = ("wpsreserved_cellimgl",)  # 腾讯文档内部表

_QUALITY_4K = re.compile(r"(4k|2160|uhd|杜比视界|dolby\s*vision)", re.I)
_QUALITY_1080 = re.compile(r"(1080p|1080)", re.I)
_CN_SUB = re.compile(r"(中文|中字|国语|简中|繁中|简繁)", re.I)
_NO_CN = re.compile(r"无\s*(中文|中字|字幕)|无字幕", re.I)
_YEAR_RE = re.compile(r"[（(](\d{4})[)）]")
_TMDBID_RE = re.compile(r"\b(\d{4,9})\b")


def classify_sheet(sheet_name: str) -> str:
    """按工作表名判断资源大类。"""
    n = (sheet_name or "").lower()
    for kind, keys in SHEET_KINDS:
        if any(k in n for k in keys):
            return kind
    return "other"


def is_skippable_sheet(sheet_name: str) -> bool:
    n = (sheet_name or "").lower()
    return any(s in n for s in SKIP_SHEETS)


def media_type_of(sheet_name: str, title: str = "") -> str:
    """返回 'movie' 或 'tv'：先看工作表名，再看片名特征。"""
    kind = classify_sheet(sheet_name)
    if kind == "movie":
        return "movie"
    if kind in ("tv", "anime", "variety"):
        return "tv"
    # 名称特征兜底
    t = (title or "")
    if re.search(r"(第[一二三四五六七八九十\d]+季|S\d{1,2}E\d|第\d+集|全\d+集|Season\s*\d)", t, re.I):
        return "tv"
    return "movie"


def _find_header(grid: List[List[str]]) -> Tuple[int, Optional[int]]:
    """在前 12 行里找表头 -> (表头行号, 名称列号)。找不到返回 (-1, None)。"""
    best = (-1, None, -1)
    for r in range(min(12, len(grid))):
        row = grid[r]
        non_empty = sum(1 for c in row if c.strip())
        if non_empty < 2:
            continue
        name_col = None
        for ci, c in enumerate(row):
            txt = (c or "").strip()
            if any(h in txt for h in NAME_HEADS) and len(txt) <= 8:
                name_col = ci
                break
        score = non_empty + (10 if name_col is not None else 0)
        if score > best[2]:
            best = (r, name_col, score)
    return best[0], best[1]


def parse_sheet(sheet_id: str, sheet_name: str,
                grid: List[List[str]], hrefs: List[List[Optional[str]]]) -> List[Dict[str, Any]]:
    """把一张工作表解析成资源记录列表。"""
    if not grid:
        return []
    hdr_row, name_col = _find_header(grid)
    start = hdr_row + 1 if hdr_row >= 0 else 0

    # 标题列兜底：取平均文本最长的列
    if name_col is None:
        best_len, best_col = 0, 0
        for ci in range(len(grid[0])):
            avg = sum(len(grid[r][ci]) for r in range(start, len(grid))) / max(1, len(grid) - start)
            if avg > best_len:
                best_len, best_col = avg, ci
        name_col = best_col

    tmdb_col = None
    res_col = sub_col = None
    if hdr_row >= 0:
        for ci, c in enumerate(grid[hdr_row]):
            t = (c or "").strip().lower()
            if "tmdb" in t:
                tmdb_col = ci
            elif res_col is None and any(h in t for h in RES_HEADS):
                res_col = ci
            elif sub_col is None and any(h in t for h in SUB_HEADS):
                sub_col = ci

    records: List[Dict[str, Any]] = []
    link_counter: Dict[str, int] = {}

    for r in range(start, len(grid)):
        row = grid[r]
        if not any((c or "").strip() for c in row):
            continue
        title = (row[name_col] if name_col < len(row) else "").strip()
        if not title or any(h in title for h in NAME_HEADS):
            continue

        # 收集整行的资源链接：单元格文本 + 单元格超链接
        raw_links: List[Tuple[str, str]] = []
        for ci, c in enumerate(row):
            raw_links.extend(extract_links(c or ""))
        for ci, href in enumerate(hrefs[r] if r < len(hrefs) else []):
            if href:
                k = classify_link(href)
                if k and k != "http":
                    raw_links.append((k, href.rstrip("#&")))
        links = dedup_links(raw_links)
        if not links:
            continue

        year = ""
        m = _YEAR_RE.search(title)
        if m:
            year = m.group(1)
        tmdbid = ""
        if tmdb_col is not None and tmdb_col < len(row):
            mm = re.search(r"\d{4,9}", row[tmdb_col] or "")
            if mm:
                tmdbid = mm.group(0)

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
            "spec": spec[:300],
            "qtext": qtext,
            "links": links,
        })

    # 标记「打包链接」：同一个链接被很多行共用
    data_rows = max(1, len(records))
    for rec in records:
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
