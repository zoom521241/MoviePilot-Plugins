"""表格解析：把「单元格网格」变成可用的资源记录。

表格结构在不同工作表之间并不统一（列名、列数、链接是文本还是超链接都不一样），
所以这里采用**宽容解析**：
  * 先在前若干行里找表头（含「名称/标题/片名…」），定位名称列；
  * 链接不依赖固定列，**扫描整行的文本与超链接**，再用 link_router 过滤出资源链接；
  * 分辨率/字幕等规格信息按关键字从整行文本里提取，用于选片排序。
"""
from __future__ import annotations

import functools
import re
import unicodedata
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
_QUALITY_1080 = re.compile(r"(?<![A-Za-z0-9])1080[pi]?(?![0-9])", re.I)
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
# 只在「名称列为空或没识别到名称列」时生效，避免把链接文字恰好是「点击这里」之类的数据行丢掉。
BANNER_HINTS = ("打包链接", "大包链接", "点我返回", "点我直达", "点击直达",
                "点击进去", "复制资源", "资源列表", "目录", "快捷键")


def is_banner_row(row: List[str], name_col: Optional[int] = None) -> bool:
    """横幅行判断；给出名称列且该列有片名时，一律不是横幅。"""
    row = row or []
    if name_col is not None and name_col < len(row) and (row[name_col] or "").strip():
        title = row[name_col].strip()
        # 名称列本身就是横幅文字（单列目录表）时仍按横幅处理
        if not any(h in title for h in BANNER_HINTS):
            return False
    txt = " ".join((c or "") for c in row)
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
                is_resource_link(classify_link(href)) for href in
                _flat_hrefs((hrefs[r] if r < len(hrefs) else []) if hrefs else [])):
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


def year_from_cell(value: Any) -> str:
    """年份列 -> 年份：2019 / 2019.0 / 2019年 / 2019-05-01 / 2019/5/1 / 日期序列号 43586。"""
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    m = re.fullmatch(r"((?:18|19|20|21)\d{2})(?:\.0+)?\s*年?", text)
    if m:
        return m.group(1)
    m = re.match(r"((?:18|19|20|21)\d{2})\s*[-/.年]\s*\d{1,2}(?:\s*[-/.月]\s*\d{1,2}\s*日?)?", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d{5}(?:\.\d+)?", text):
        # 表格日期序列号（1899-12-30 起的天数；5 位数即 1927~2173 年）
        number = float(text)
        if number < 73051:
            import datetime
            year = (datetime.date(1899, 12, 30) + datetime.timedelta(days=int(number))).year
            return str(year) if 1900 <= year <= 2100 else ""
    return ""


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
    if not t or t.isdecimal() or is_name_head(t) or is_banner_row([t]) or t in ("点击这里", "点我", "点击"):
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


def _flat_hrefs(href_row) -> List[str]:
    """一行超链接 -> 扁平列表；单元格可能是 None / 字符串 / 多个链接的列表。"""
    out: List[str] = []
    for cell in (href_row or []):
        if not cell:
            continue
        if isinstance(cell, (list, tuple)):
            out.extend(str(u) for u in cell if u)
        else:
            out.append(str(cell))
    return out


def _collect_links(row: List[str], href_row: List[Optional[str]],
                   include_external: bool = False) -> List[Tuple[str, str]]:
    """收集一行里的资源链接：单元格文本 + 单元格超链接 -> [(kind, url)]。

    超链接里可能带错误的前缀（如 ``https://ed2k://...``），统一走 normalize_url。
    """
    raw: List[Tuple[str, str]] = []
    for c in (row or []):
        raw.extend(extract_links(c or "", include_other=include_external))
    for href in _flat_hrefs(href_row):
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
    # 有明确表头时，名称列有片名的行一定是数据行；无表头时名称列是推断的，横幅仍按整行判断。
    banner_col = name_col if hdr_row >= 0 else None
    banner_rows = {r for r in range(top_end) if is_banner_row(grid[r], banner_col)}
    header_area = set(range(0, start)) | banner_rows

    header_links: List[Tuple[str, str]] = []
    for r in sorted(header_area):
        header_links.extend(_collect_links(grid[r], href_row(r)))
    header_links = dedup_links(header_links)

    # 表头/横幅里的普通网页链接（如外部 KDocs 文档），用于「纯列表表」的参考展示
    header_http: List[str] = []
    for r in sorted(header_area):
        for href in _flat_hrefs(href_row(r)):
            if classify_link(normalize_url(href)) == LINK_OTHER_HTTP:
                header_http.append(normalize_url(href).rstrip("#&"))
    header_http = list(dict.fromkeys(header_http))

    # 第一遍：收集「数据行」及其自带链接；判断整表是否存在资源链接
    any_resource = any(is_resource_link(k) for k, _ in header_links)
    candidates: List[Tuple[int, str, List[Tuple[str, str]]]] = []
    inherited_rows = set()
    prev_title, prev_row = "", -2
    for r in range(start, len(grid)):
        if r in header_area:
            continue
        row = grid[r]
        if not any((c or "").strip() for c in row):
            prev_title = ""          # 空行打断合并单元格的继承
            continue
        title = (row[name_col] if name_col < len(row) else "").strip()
        own = _collect_links(row, href_row(r))
        if not title and prev_title and prev_row == r - 1 and any(is_resource_link(k) for k, _ in own):
            # 合并单元格：标题只写在首行，相邻下一行的链接继承上一行标题
            title = prev_title
            inherited_rows.add(r)
        if (not title or is_name_head(title) and not own
                or re.match(r"^(?:https?://|magnet:|ed2k://)", title, re.I)):
            continue
        prev_title, prev_row = title, r
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
            year = year_from_cell(row[year_col]) or year
        tmdbid = ""
        tmdb_type = ""
        if tmdb_col is not None and tmdb_col < len(row):
            tmdbid, tmdb_type = _tmdb_value(row[tmdb_col], numeric=True)
        for value in list(row) + _flat_hrefs(href_row(r)):
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
        if r in inherited_rows:
            records[-1]["title_inherited"] = True

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


def link_kinds_of(rec: Dict[str, Any]) -> List[str]:
    """记录里出现的链接类型集合（去重排序）：115_share / magnet / ed2k / other。"""
    return sorted({str(k) for k, _ in iter_links(rec) if k})


def matches_link_kind(rec: Dict[str, Any], want: str) -> bool:
    """按链接类型筛选一条记录。

    ``want`` 取值：
      * ``all``    不限
      * ``share``  含 115 分享链接（可直接转存）
      * ``magnet`` 含磁力链接
      * ``ed2k``   含 ed2k 链接
      * ``doc``    **没有任何可用资源链接**（纯列表/只在外部文档里，插件不能转存）
    """
    kinds = set(link_kinds_of(rec))
    if want in ("", "all"):
        return True
    if want == "share":
        return LINK_115_SHARE in kinds
    if want == "magnet":
        return LINK_MAGNET in kinds
    if want == "ed2k":
        return LINK_ED2K in kinds
    if want == "doc":
        return not (kinds & {LINK_115_SHARE, LINK_MAGNET, LINK_ED2K})
    return True


# ---------------------------------------------------------------------------
# 搜索归一化与打分
# ---------------------------------------------------------------------------
try:  # 可选繁简转换：环境里有 opencc 就用，没有就跳过（不新增依赖）
    import opencc as _opencc  # type: ignore
    try:
        _T2S = _opencc.OpenCC("t2s")
    except Exception:  # noqa: BLE001
        _T2S = _opencc.OpenCC("t2s.json")
except Exception:  # noqa: BLE001
    _T2S = None

_CN_DIGITS = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
              "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_SERIES_RE = re.compile(
    r"第\s*([0-9零〇一二两三四五六七八九十百]+)\s*(季|部|集|期|章|篇)"
    r"|(?<![a-z0-9])(?:season\s*|s)0*(\d{1,2})(?![0-9])")
_SPEC_WORDS = re.compile(
    r"(?<![a-z0-9])(?:4k|2160p?|1080p?|720p?|uhd|hdr10?|hdr|remux|bluray|blu-ray|web-?dl|h\.?26[45]|x26[45]|hevc)"
    r"(?![a-z0-9])|中文字幕|中字|国语|简中|繁中|简繁|蓝光原盘|原盘|杜比视界", re.I)


def _cn_number(text: str) -> Optional[int]:
    if text.isdigit():
        return int(text)
    if any(ch not in _CN_DIGITS and ch not in "十百" for ch in text):
        return None
    total, current = 0, 0
    for ch in text:
        if ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        else:
            current = current * 10 + _CN_DIGITS[ch] if current else _CN_DIGITS[ch]
    return total + current


def _drop_char(ch: str) -> bool:
    cat = unicodedata.category(ch)
    return cat[0] in ("P", "Z", "C") or ch.isspace() or ch in "·・‧—–~～|｜`^"


def _normalize_map(text: str) -> Tuple[str, Tuple[Tuple[int, int], ...]]:
    """归一化文本，并给出每个归一化字符对应的原文区间 (start, end)。"""
    raw = text or ""
    if _T2S is not None:
        try:
            converted = _T2S.convert(raw)
            if len(converted) == len(raw):  # 只接受逐字转换，保证能映射回原文
                raw = converted
        except Exception:  # noqa: BLE001
            pass
    chars: List[str] = []
    origin: List[int] = []
    for i, ch in enumerate(raw):
        for folded in unicodedata.normalize("NFKC", ch).lower():
            chars.append(folded)
            origin.append(i)
    folded = "".join(chars)
    out: List[str] = []
    spans: List[Tuple[int, int]] = []
    pos = 0
    for m in _SERIES_RE.finditer(folded):
        for j in range(pos, m.start()):
            if not _drop_char(folded[j]):
                out.append(folded[j])
                spans.append((origin[j], origin[j] + 1))
        if m.group(3) is not None:
            replacement = f"s{int(m.group(3))}"
        else:
            number = _cn_number(m.group(1))
            if number is None:
                replacement = m.group(0)
            else:
                replacement = {"季": f"s{number}", "集": f"e{number}", "期": f"e{number}"}.get(m.group(2), str(number))
        span = (origin[m.start()], origin[m.end() - 1] + 1)
        for ch in replacement:
            if not _drop_char(ch):
                out.append(ch)
                spans.append(span)
        pos = m.end()
    for j in range(pos, len(folded)):
        if not _drop_char(folded[j]):
            out.append(folded[j])
            spans.append((origin[j], origin[j] + 1))
    return "".join(out), tuple(spans)


def normalize_title(text: str) -> str:
    """搜索用归一化：全角转半角、小写、去空白与标点、「第二季」→s2「第2部」→2、可选繁转简。"""
    return _normalize_map(text)[0]


def core_title(title: str) -> str:
    """去掉发行年份标注与画质/字幕规格，只留片名主体（用于相关度匹配）。"""
    t = _YEAR_RE.sub(" ", title or "")
    year = extract_year(t)
    if year:
        t = re.sub(r"(?:(?<=\s)|(?<=[._-]))" + year + r"(?=[\s._-])", " ", t, count=1)
    t = _SPEC_WORDS.sub(" ", t)
    return t.strip() or (title or "")


@functools.lru_cache(maxsize=65536)
def _title_key(title: str) -> Tuple[str, Tuple[Tuple[int, int], ...], str]:
    core = core_title(title)
    norm, spans = _normalize_map(core)
    return norm, spans, core


def _split_keyword(keyword: str) -> Tuple[str, str]:
    """关键词 -> (去掉年份后的关键词, 年份)。只剩年份时保留原样（如《1917》）。"""
    text = (keyword or "").strip()
    m = re.search(r"(?:^|[\s(（\[])((?:18|19|20|21)\d{2})(?:[)）\]]|\s|$)", text)
    if m:
        rest = (text[:m.start(1)] + " " + text[m.end(1):]).strip(" ()（）[]")
        if normalize_title(rest):
            return rest, m.group(1)
    return text, ""


def _find_bounded(haystack: str, needle: str) -> int:
    """包含匹配，但关键词以数字开头/结尾时不与相邻数字粘连（沙丘2 不命中 沙丘21）。"""
    start = haystack.find(needle)
    while start >= 0:
        end = start + len(needle)
        ok_left = not (needle[0].isdigit() and start > 0 and haystack[start - 1].isdigit())
        ok_right = not (needle[-1].isdigit() and end < len(haystack) and haystack[end].isdigit())
        if ok_left and ok_right:
            return start
        start = haystack.find(needle, start + 1)
    return -1


def score_title(rec: Dict[str, Any], keyword: str) -> Tuple[int, str]:
    """相关度：完全相等 > 前缀 > 包含；年份匹配加分。返回 (分数, 命中的原标题片段)，0 表示不命中。"""
    kw, kw_year = _split_keyword(keyword)
    stripped = _SPEC_WORDS.sub(" ", kw)
    if normalize_title(stripped):
        kw = stripped          # 关键词里的画质/字幕词不参与片名匹配
    needle = normalize_title(kw)
    if not needle:
        return 0, ""
    title = str(rec.get("title") or "")
    norm, spans, source = _title_key(title)
    pos = _find_bounded(norm, needle)
    penalty = 0
    if pos < 0 and kw_year:
        # 关键词里的年份也可能就是片名的一部分（如「银翼杀手 2049」）
        full = normalize_title(keyword)
        pos = _find_bounded(norm, full)
        if pos >= 0:
            needle, kw_year = full, ""
    if pos < 0:
        # 回退：在完整标题（含年份/规格）里找，相关度最低
        norm, spans = _normalize_map(title)
        source = title
        full = normalize_title(keyword)
        pos = _find_bounded(norm, full)
        if pos < 0:
            return 0, ""
        needle, kw_year, penalty = full, "", 20
    score = 100 if pos == 0 and len(needle) == len(norm) else 60 if pos == 0 else 30
    score -= penalty
    rec_year = str(rec.get("year") or extract_year(title) or "")
    if kw_year:
        if rec_year == kw_year:
            score += 20
        elif rec_year:
            score -= 25
    a, b = spans[pos][0], spans[pos + len(needle) - 1][1]
    fragment = source[a:b].strip()
    if fragment and fragment not in title:
        fragment = ""
    return max(score, 1), fragment


def is_1080(rec: Dict[str, Any]) -> bool:
    return bool(_QUALITY_1080.search(f"{rec.get('title', '')} {rec.get('qtext') or rec.get('spec', '')}"))


def search_key(rec: Dict[str, Any]) -> Tuple[str, str, str]:
    """预计算的搜索键：(去规格后的归一化片名, 完整标题归一化, 年份)。随索引版本缓存，避免每次搜索重算 23 万条。"""
    title = str(rec.get("title") or "")
    core_norm = _normalize_map(core_title(title))[0]
    full_norm = _normalize_map(title)[0]
    year = str(rec.get("year") or extract_year(title) or "")
    return core_norm, (full_norm if full_norm != core_norm else ""), year


def prepare_query(keyword: str) -> Optional[Dict[str, Any]]:
    """把关键词预处理成 score_key 需要的形式；无有效片名时返回 None。"""
    kw, kw_year = _split_keyword(keyword)
    stripped = _SPEC_WORDS.sub(" ", kw)
    if normalize_title(stripped):
        kw = stripped
    needle = normalize_title(kw)
    if not needle:
        return None
    return {"needle": needle, "year": kw_year, "full": normalize_title(keyword)}


def score_key(key: Tuple[str, str, str], query: Dict[str, Any]) -> int:
    """与 score_title 同一套打分规则，但只用预计算键，不生成高亮片段。0 表示不命中。"""
    norm, full_norm, rec_year = key
    needle, kw_year, full = query["needle"], query["year"], query["full"]
    pos = _find_bounded(norm, needle)
    penalty = 0
    if pos < 0 and kw_year:
        pos = _find_bounded(norm, full)
        if pos >= 0:
            needle, kw_year = full, ""
    if pos < 0:
        target = full_norm or norm
        pos = _find_bounded(target, full)
        if pos < 0:
            return 0
        norm, needle, kw_year, penalty = target, full, "", 20
    score = 100 if pos == 0 and len(needle) == len(norm) else 60 if pos == 0 else 30
    score -= penalty
    if kw_year:
        if rec_year == kw_year:
            score += 20
        elif rec_year:
            score -= 25
    return max(score, 1)


def search_scored(records: List[Dict[str, Any]], keyword: str) -> List[Tuple[int, Dict[str, Any], str]]:
    """[(分数, 记录, 命中片段)]，按相关度、画质、行号排序。"""
    hits = []
    for rec in records:
        score, fragment = score_title(rec, keyword)
        if score:
            hits.append((score, rec, fragment))
    hits.sort(key=lambda h: (-h[0], -quality_score(h[1]), h[1].get("row", 0)))
    return hits


def search(records: List[Dict[str, Any]], keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
    """按归一化后的标题匹配并按相关度排序（画质为次级排序）。"""
    return [rec for _, rec, _ in search_scored(records, keyword)[:limit]]
