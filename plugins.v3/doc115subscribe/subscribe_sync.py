"""订阅同步（仅电影）：把文档里的资源与 MP 订阅比对，挑出该转存的条目。

纯逻辑模块，不依赖 MoviePilot，便于离线测试。
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# MoviePilot V3 以「包」的形式加载插件（app.plugins.<插件id>），插件目录不在 sys.path 上，
# 因此插件内部模块必须用相对导入；绝对导入仅在脚本/单测场景下兜底。
try:
    from . import doc_parser
except ImportError:  # 直接作为顶层模块加载（脚本/单测）
    import doc_parser

# 用户只要求电影参与订阅
MOVIE_SHEET_HINT = ("最新电影",)


def _norm_title(t: str) -> str:
    """归一化片名：去空格、去括号内容、统一小写。"""
    s = re.sub(r"[（(].*?[)）]", "", t or "")
    s = re.sub(r"[\s\-_.·:：!！?？,，/\\|]", "", s)
    return s.lower()


def is_movie_sheet(sheet_name: str) -> bool:
    return any(h in (sheet_name or "") for h in MOVIE_SHEET_HINT)


def movie_records(records: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """只保留电影类工作表里的记录。"""
    out = []
    for r in records:
        if is_movie_sheet(r.get("sheet", "")) or r.get("kind") == "movie":
            out.append(r)
    return out


def match_subscriptions(records: Iterable[Dict[str, Any]],
                        subscribes: Iterable[Dict[str, Any]]
                        ) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """把订阅与文档记录配对，返回 [(订阅, 选中的记录)]。

    匹配优先级：**TMDBID 相等** > 「片名(+年份)」相同。
    同一订阅命中多条时，用 doc_parser.pick_best 选最优（4K+中文优先，其次最新）。
    """
    by_tmdb: Dict[str, List[Dict[str, Any]]] = {}
    by_title: Dict[str, List[Dict[str, Any]]] = {}
    for r in records:
        tm = str(r.get("tmdbid") or "").strip()
        if tm:
            by_tmdb.setdefault(tm, []).append(r)
        by_title.setdefault(_norm_title(r.get("title", "")), []).append(r)

    pairs: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for sub in subscribes:
        cands: List[Dict[str, Any]] = []
        tm = str(sub.get("tmdbid") or "").strip()
        if tm and tm in by_tmdb:
            cands = list(by_tmdb[tm])
        else:
            cands = list(by_title.get(_norm_title(sub.get("title", "")), []))
            # 年份不一致时降权（不排除，文档年份可能缺失）
            year = str(sub.get("year") or "").strip()
            if year:
                cands = [c for c in cands if not c.get("year") or c["year"] == year] or cands
        if not cands:
            continue
        best = doc_parser.pick_best(cands)
        if best:
            pairs.append((sub, best))
    return pairs


def transfer_key(sub: Dict[str, Any], rec: Dict[str, Any]) -> str:
    """去重键：优先 tmdbid，其次片名+年份。"""
    tm = str(rec.get("tmdbid") or sub.get("tmdbid") or "").strip()
    if tm:
        return f"tmdb:{tm}"
    return f"title:{_norm_title(rec.get('title', ''))}:{rec.get('year') or sub.get('year') or ''}"
