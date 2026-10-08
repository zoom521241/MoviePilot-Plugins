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
    """归一化片名：去掉发布组/合集等各类括号内容，再去空格与标点，统一小写。"""
    s = t or ""
    s = re.sub(r"[【\[（(「『].*?[】\]）)」』]", "", s)
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

    匹配优先级：
      1. **TMDBID 相等**（最准）
      2. 「片名(+年份)」归一化后**完全相同**
      3. 归一化后**订阅名是文档标题的前缀**（文档标题常带「发布组/合集/字幕/英文名」等后缀），
         要求订阅名 ≥4 个字符且年份不冲突 —— 避免「八仙」误配「八仙饭店」这类短名误判。

    同一订阅命中多条时，用 doc_parser.pick_best 选最优（4K+中文优先，其次最新）。
    """
    records = list(records)
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
            # 兜底：订阅名是文档标题的前缀（文档标题常带发布组/合集/字幕后缀）
            nsub = _norm_title(sub.get("title", ""))
            year = str(sub.get("year") or "").strip()
            if len(nsub) >= 4:
                for r in records:
                    if not _norm_title(r.get("title", "")).startswith(nsub):
                        continue
                    ry = str(r.get("year") or "").strip()
                    if year and ry and year != ry:
                        continue
                    cands.append(r)
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
