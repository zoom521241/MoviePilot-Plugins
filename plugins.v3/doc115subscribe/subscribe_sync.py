"""电影订阅的严格身份匹配及可转存候选排序；不依赖 MoviePilot。"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Tuple

try:
    from . import doc_parser
    from .link_router import classify_link, is_resource_link
except ImportError:
    import doc_parser
    from link_router import classify_link, is_resource_link

MOVIE_SHEET_HINT = ("最新电影",)
_RELEASE_SUFFIX = re.compile(
    r"(?:\s|[._-])(?:4k|2160p?|1080p?|720p?|uhd|remux|bluray|blu-ray|web-dl|"
    r"中字|中文字幕|中文|国语|简中|繁中|简繁)(?:\b|(?=[\s\u3400-\u9fff]))[\s\S]*$", re.I)


def _norm_title(title: str, year_hint: str = "") -> str:
    s = title or ""
    def strip_metadata(match):
        inner = match.group(1).strip()
        if (re.fullmatch(r"(?:18|19|20|21)\d{2}", inner)
                or re.search(r"(?:4k|2160p?|1080p?|720p?|uhd|remux|bluray|blu-ray|web-dl|"
                             r"字幕|中字|简中|繁中|国语|杜比|发布组|导演剪辑|加长版|未删减|"
                             r"directors?\s*cut|extended\s*cut)", inner, re.I)):
            return " "
        # 括号也可能是续集或副标题，不能无条件删除。
        return " " + inner + " "
    s = re.sub(r"[【\[（(「『](.*?)[】\]）)」』]", strip_metadata, s)
    # 仅清除发行信息后缀，绝不把续作或任意前缀当作同一片名。
    s = _RELEASE_SUFFIX.sub("", s)
    if re.fullmatch(r"(?:18|19|20|21)\d{2}", str(year_hint)):
        s = re.sub(r"(?:\s|[._-])" + re.escape(str(year_hint)) + r"$", "", s.strip())
    return re.sub(r"[\s\-_.·:：!！?？,，/\\|]", "", s).lower()


def is_movie_sheet(sheet_name: str) -> bool:
    return any(h in (sheet_name or "") for h in MOVIE_SHEET_HINT)


def _media_type(record: Dict[str, Any]) -> str:
    if doc_parser._TV_TITLE_RE.search(record.get("title", "")):
        return "tv"
    return record.get("media_type") or doc_parser.media_type_of(record.get("sheet", ""), record.get("title", ""))


def movie_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """标题剧集特征、明确媒体类型优先，画质表不再冒充电影表。"""
    return [r for r in records if _media_type(r) == "movie"]


def _year(value: Dict[str, Any]) -> str:
    return str(value.get("year") or doc_parser.extract_year(value.get("title", "")) or "").strip()


def _tmdb(value: Dict[str, Any]) -> str:
    text = str(value.get("tmdbid") or "").strip()
    return str(int(text)) if re.fullmatch(r"[1-9]\d*", text) else ""


def _usable(record: Dict[str, Any]) -> bool:
    if any(record.get(flag) for flag in ("bundle", "sheet_bundle", "no_link")):
        return False
    # 不信任缓存里声明的 kind，重新校验链接真实主机和协议。
    return any(url and is_resource_link(classify_link(url)) for _, url in doc_parser.iter_links(record))


class SubscriptionMatcher:
    """一次同步只建立一次身份索引，避免每个订阅都重新扫描数十万行。"""
    def __init__(self, records: Iterable[Dict[str, Any]]):
        self.records = [rec for rec in records if _media_type(rec) == "movie" and _usable(rec)]
        self.by_tmdb: Dict[str, List[Dict[str, Any]]] = {}
        self.by_title: Dict[str, List[Dict[str, Any]]] = {}
        for rec in self.records:
            tmdb = _tmdb(rec)
            if tmdb:
                self.by_tmdb.setdefault(tmdb, []).append(rec)
            title = rec.get("title", "")
            keys = {_norm_title(title), _norm_title(title, _year(rec))}
            bare = re.search(r"(?:\s|[._-])((?:18|19|20|21)\d{2})$", title.strip())
            if bare:
                # 索引同时保留发行年别名；最终匹配仍须订阅年份一致，不能据此误配。
                keys.add(_norm_title(title, bare.group(1)))
            for key in keys:
                self.by_title.setdefault(key, []).append(rec)

    def __iter__(self):
        return iter(self.records)

    def candidates_for(self, sub: Dict[str, Any]) -> List[Dict[str, Any]]:
        candidates = (self.by_tmdb.get(_tmdb(sub), [])
                      + self.by_title.get(_norm_title(sub.get("title", "")), [])
                      + self.by_title.get(_norm_title(sub.get("title", ""), _year(sub)), []))
        seen, result = set(), []
        for rec in candidates:
            if id(rec) not in seen:
                seen.add(id(rec))
                result.append(rec)
        return result


def subscription_candidates(records: Iterable[Dict[str, Any]], sub: Dict[str, Any]) -> List[Dict[str, Any]]:
    """返回按身份可信度、4K/中文及行号排序的可转存电影候选。

    双方都有的 TMDB、年份或类型一旦冲突就排除。只有身份缺失时才按完整标题
    兜底；不会为了获得命中恢复已排除的候选，也不会把续作当作片名前缀匹配。
    """
    sub_type = str(sub.get("media_type") or sub.get("type") or "movie").lower()
    if sub_type not in ("movie", "电影", "电影订阅"):
        return []
    st, sy = _tmdb(sub), _year(sub)
    sn = _norm_title(sub.get("title", ""), sy)
    out = []
    for rec in records.candidates_for(sub) if isinstance(records, SubscriptionMatcher) else records:
        if _media_type(rec) != "movie":
            continue
        rt = _tmdb(rec)
        if st and rt and st != rt:
            continue
        ry = _year(rec)
        if sy and ry and sy != ry:
            continue
        exact_id = bool(st and rt and st == rt)
        if not exact_id and (not sn or _norm_title(rec.get("title", ""), ry or sy) != sn):
            continue
        if not _usable(rec):
            continue
        out.append((0 if exact_id else 1, rec))
    out.sort(key=lambda item: (item[0], -doc_parser.quality_score(item[1]),
                               item[1].get("row", 0), item[1].get("sheet_id", "")))
    return [rec for _, rec in out]


def match_subscription_candidates(records: Iterable[Dict[str, Any]], subscribes: Iterable[Dict[str, Any]]
                                  ) -> List[Tuple[Dict[str, Any], List[Dict[str, Any]]]]:
    records = SubscriptionMatcher(records)
    return [(sub, candidates) for sub in subscribes
            if (candidates := subscription_candidates(records, sub))]


def match_subscriptions(records: Iterable[Dict[str, Any]], subscribes: Iterable[Dict[str, Any]]
                        ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """兼容旧调用方：每个订阅仅返回优先级最高的可用候选。"""
    return [(sub, candidates[0]) for sub, candidates in match_subscription_candidates(records, subscribes)]


def transfer_key(sub: Dict[str, Any], rec: Dict[str, Any]) -> str:
    """保留既有电影去重键，避免升级后重复转存历史影片。"""
    tm = _tmdb(rec) or _tmdb(sub)
    if tm:
        return f"tmdb:{tm}"
    year = _year(rec) or _year(sub)
    return f"title:{_norm_title(rec.get('title', ''), year)}:{year}"
