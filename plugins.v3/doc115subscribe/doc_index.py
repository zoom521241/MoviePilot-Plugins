"""按文档来源隔离的本地资源索引；支持原子持久化与部分刷新保留。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from . import doc_parser
    from .doc_client import DocError, TencentDocsClient
except ImportError:
    import doc_parser
    from doc_client import DocError, TencentDocsClient

INDEX_VERSION = 3
# 刷新失败、沿用旧数据的工作表超过该天数视为过期
STALE_MAX_DAYS = 14
SORTS = ("relevance", "year_desc", "year_asc", "quality")
# 同一索引版本内缓存最近几个关键词的命中列表：切换筛选/排序/翻页不再重扫全量
HIT_CACHE_SIZE = 8


def _kind_ok(kinds, want: str) -> bool:
    """与 doc_parser.matches_link_kind 同义，但用预计算的链接类型集合。"""
    if want == "share":
        return doc_parser.LINK_115_SHARE in kinds
    if want == "magnet":
        return doc_parser.LINK_MAGNET in kinds
    if want == "ed2k":
        return doc_parser.LINK_ED2K in kinds
    if want == "doc":
        return not (kinds & {doc_parser.LINK_115_SHARE, doc_parser.LINK_MAGNET, doc_parser.LINK_ED2K})
    return True


def _legitimately_empty(data: Dict[str, Any]) -> bool:
    """接口成功返回、表头仍在但没有任何数据行：合法变空，应清空旧数据。

    整张网格都为空（可能是接口异常/数据块缺失）不算，仍保留旧数据并标记 stale。
    """
    grid = data.get("grid") or []
    rows = [row for row in grid if any(str(c or "").strip() for c in row)]
    hrefs = [cell for row in (data.get("hrefs") or []) for cell in (row or []) if cell]
    return (len(rows) == 1 and not hrefs
            and any(doc_parser.is_name_head(str(c or "")) for c in rows[0]))


class DocIndex:
    def __init__(self, client: Optional[TencentDocsClient], max_sheets: int = 0):
        self.client = client
        self.source_doc_id = str(getattr(client, "doc_id", "") or "")
        self.max_sheets = max_sheets
        self.records: List[Dict[str, Any]] = []
        self.sheets: List[Dict[str, Any]] = []
        self.built_at: float = 0.0
        self.errors: List[str] = []
        self._index_version = uuid.uuid4().hex
        self._by_id: Dict[str, Dict[str, Any]] = {}
        self._search_lock = threading.Lock()
        self._search_meta: Optional[List[tuple]] = None
        self._hit_cache: "OrderedDict[str, List[tuple]]" = OrderedDict()

    @property
    def index_version(self) -> str:
        """每次成功刷新产生新的版本，防止搜索后索引切换导致误选。"""
        return self._index_version

    def _identify(self, record: Dict[str, Any]) -> str:
        identity = {key: record.get(key) for key in
                    ("sheet_id", "title", "year", "tmdbid", "media_type", "qtext", "spec",
                     "bundle", "sheet_bundle", "no_link")}
        identity["source_doc_id"] = self.source_doc_id
        identity["links"] = sorted((kind or "", url or "") for kind, url in doc_parser.iter_links(record))
        return hashlib.sha256(json.dumps(identity, ensure_ascii=False, sort_keys=True,
                                         separators=(",", ":")).encode("utf-8")).hexdigest()

    def _set_records(self, records: List[Dict[str, Any]]) -> None:
        with self._search_lock:
            self._search_meta = None
            self._hit_cache.clear()
        self._by_id = {}
        self.records = records
        for rec in records:
            rec["links"] = list(doc_parser.iter_links(rec))
            rec["record_id"] = self._identify(rec)
            self._by_id.setdefault(rec["record_id"], rec)

    def build(self, progress=None, previous: Optional["DocIndex"] = None) -> Dict[str, Any]:
        """先构建完整新快照；失败工作表保留同来源的上次有效数据。"""
        if not self.client:
            raise DocError("没有配置文档客户端")
        previous = previous or (self if self.built_at else None)
        if previous and previous.source_doc_id != self.source_doc_id:
            previous = None
        old_sheets = {sh["id"]: sh for sh in (previous.sheets if previous else [])}
        old_records: Dict[str, List[Dict[str, Any]]] = {}
        for rec in previous.records if previous else []:
            old_records.setdefault(rec["sheet_id"], []).append(rec)
        sheet_list = self.client.fetch_sheet_list()
        if self.max_sheets:
            sheet_list = sheet_list[:self.max_sheets]
        records, sheets, errors = [], [], []
        total, succeeded = len(sheet_list), 0
        now = time.time()
        for i, sh in enumerate(sheet_list, 1):
            sid, name = sh["id"], sh["name"]
            if doc_parser.is_skippable_sheet(name):
                continue
            try:
                data = self.client.fetch_sheet(sid)
                recs = doc_parser.parse_sheet(sid, name, data["grid"], data.get("hrefs") or [])
                if not recs and old_records.get(sid) and not _legitimately_empty(data):
                    # 表里还有内容却一条都没解析出来：更可能是解析/接口问题，保留旧数据
                    raise DocError("本次解析结果为空，已保留上次有效数据")
                succeeded += bool(recs)
                records.extend(recs)
                sheets.append({"id": sid, "name": name, "kind": doc_parser.classify_sheet(name),
                               "count": len(recs), "stale": False, "last_success_at": now})
            except Exception as exc:  # 文档接口和解析失败均不能覆盖上次有效表。
                message = f"{name}: {exc}"
                errors.append(message)
                if sid in old_sheets:
                    cached = dict(old_sheets[sid])
                    last_ok = float(cached.get("last_success_at") or previous.built_at or 0)
                    cached.update({"stale": True, "error": message, "last_success_at": last_ok,
                                   "stale_days": round(max(0.0, now - last_ok) / 86400, 1) if last_ok else None,
                                   "expired": not last_ok or now - last_ok > STALE_MAX_DAYS * 86400})
                    sheets.append(cached)
                    records.extend(dict(rec) for rec in old_records.get(sid, []))
            finally:
                if progress:
                    progress(i, total, name)
        # 全部失败或全表退化为空时，调用方应继续使用旧索引，绝不保存空快照。
        if not succeeded or not records:
            raise DocError("索引刷新失败，未覆盖有效缓存：" + ("；".join(errors) or "未解析到任何资源"))
        self.sheets, self.errors, self.built_at = sheets, errors, now
        self._index_version = uuid.uuid4().hex
        self._set_records(records)
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        return {"built_at": self.built_at, "sheet_count": len(self.sheets),
                "record_count": len(self.records), "errors": list(self.errors),
                "source_doc_id": self.source_doc_id, "doc_id": self.source_doc_id,
                "index_version": self.index_version,
                "stale_sheets": [dict(sh) for sh in self.sheets if sh.get("stale")],
                "stale_sheet_count": sum(bool(sh.get("stale")) for sh in self.sheets),
                "expired_sheets": [dict(sh) for sh in self.sheets if sh.get("stale") and sh.get("expired")],
                "expired_sheet_count": sum(bool(sh.get("stale") and sh.get("expired")) for sh in self.sheets),
                "stale_max_days": STALE_MAX_DAYS}

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        return self._by_id.get(record_id)

    def _public_record(self, rec: Dict[str, Any]) -> Dict[str, Any]:
        result = {key: rec.get(key, "") for key in
                  ("sheet_id", "sheet", "row", "title", "year", "tmdbid", "qtext", "record_id")}
        result.update({"media_type": rec.get("media_type") or doc_parser.media_type_of(rec.get("sheet", ""), rec.get("title", "")),
                       "quality_score": doc_parser.quality_score(rec),
                       "bundle": bool(rec.get("bundle")), "sheet_bundle": bool(rec.get("sheet_bundle")),
                       "no_link": bool(rec.get("no_link")),
                       "link_kinds": doc_parser.link_kinds_of(rec),
                       "index_version": self.index_version, "source_doc_id": self.source_doc_id,
                       "links": [{"kind": kind, "url": url} for kind, url in doc_parser.iter_links(rec)]})
        return result

    def search_page(self, keyword: str, media_type: str = "all", quality: str = "all",
                    link_kind: str = "all", page: int = 1, page_size: int = 10, subtitle: str = "all",
                    sort: str = "relevance") -> Dict[str, Any]:
        """归一化标题匹配 + 筛选 + 排序 + 分页。

        sort: relevance（相关度>画质>行号，默认）| year_desc | year_asc | quality。
        每条记录带 ``match``（命中的原标题片段，供高亮；可能为空）与 ``score``。
        page 收敛到 [1, total_pages]。
        """
        if subtitle not in ("all", "cn"):
            raise ValueError("字幕筛选条件无效")
        if media_type not in ("all", "movie", "tv", "unknown") or quality not in ("all", "4k", "cn", "4k_cn", "1080p"):
            raise ValueError("搜索筛选条件无效")
        if link_kind not in ("all", "share", "magnet", "ed2k", "doc"):
            raise ValueError("链接类型筛选条件无效")
        sort = sort or "relevance"
        if sort not in SORTS:
            raise ValueError("排序方式无效")
        page_size = max(1, min(100, int(page_size)))
        filtered = []
        for score, rec, meta in self._hits(keyword):
            mtype, is4k, is1080, cn, kinds, _, _ = meta
            if media_type != "all" and media_type != mtype:
                continue
            if link_kind != "all" and not _kind_ok(kinds, link_kind):
                continue
            if subtitle == "cn" and not cn:
                continue
            if (quality == "4k" and not is4k or quality == "cn" and not cn
                    or quality == "4k_cn" and not (is4k and cn)
                    or quality == "1080p" and not is1080):
                continue
            filtered.append((score, rec, meta))
        if sort != "relevance":
            if sort == "quality":
                filtered.sort(key=lambda h: (-h[2][5], -h[0], h[1].get("row", 0)))
            else:
                sign = -1 if sort == "year_desc" else 1
                # 无年份的排在最后；同年按相关度
                filtered.sort(key=lambda h: (h[2][6] is None, sign * (h[2][6] or 0), -h[0],
                                             -h[2][5], h[1].get("row", 0)))
        total = len(filtered)
        total_pages = max(1, -(-total // page_size))
        try:
            page = int(page)
        except (TypeError, ValueError):
            page = 1
        page = max(1, min(total_pages, page))
        start = (page - 1) * page_size
        out = []
        for score, rec, _ in filtered[start:start + page_size]:
            public = self._public_record(rec)
            # 高亮片段只为当前页计算（全量计算需要逐条做原文映射，非常慢）
            public.update({"match": doc_parser.score_title(rec, keyword)[1], "score": score})
            out.append(public)
        return {"records": out, "total": total, "page": page, "page_size": page_size,
                "total_pages": total_pages, "sort": sort,
                "index_version": self.index_version, "source_doc_id": self.source_doc_id}

    def _meta(self) -> List[tuple]:
        """每条记录的搜索元数据，随索引版本惰性构建一次：
        [(search_key, (media_type, is_4k, is_1080, has_cn, link_kinds, quality_score, year_int))]。"""
        meta = self._search_meta
        if meta is not None:
            return meta
        with self._search_lock:
            if self._search_meta is None:
                built = []
                for rec in self.records:
                    text = f"{rec.get('title', '')} {rec.get('qtext') or rec.get('spec', '')}"
                    key = doc_parser.search_key(rec)
                    year = key[2]
                    built.append((key, (
                        rec.get("media_type") or doc_parser.media_type_of(rec.get("sheet", ""), rec.get("title", "")),
                        doc_parser.is_4k(rec), doc_parser.is_1080(rec), doc_parser.has_chinese(text),
                        frozenset(doc_parser.link_kinds_of(rec)), doc_parser.quality_score(rec),
                        int(year) if year.isdigit() else None)))
                self._search_meta = built
            return self._search_meta

    def warm_search(self) -> None:
        """后台预热搜索元数据（加载/刷新索引后调用），首次搜索不再承担构建开销。"""
        self._meta()

    def _hits(self, keyword: str) -> List[tuple]:
        """关键词全部命中 [(score, rec, meta)]，按相关度>画质>行号排序；按 (索引版本, 关键词) 缓存。"""
        cache_key = (keyword or "").strip()
        with self._search_lock:
            cached = self._hit_cache.get(cache_key)
            if cached is not None:
                self._hit_cache.move_to_end(cache_key)
                return cached
        query = doc_parser.prepare_query(cache_key)
        hits = []
        if query is not None:
            records = self.records
            for i, (key, meta) in enumerate(self._meta()):
                score = doc_parser.score_key(key, query)
                if score:
                    hits.append((score, records[i], meta))
            hits.sort(key=lambda h: (-h[0], -h[2][5], h[1].get("row", 0)))
        with self._search_lock:
            self._hit_cache[cache_key] = hits
            while len(self._hit_cache) > HIT_CACHE_SIZE:
                self._hit_cache.popitem(last=False)
        return hits

    def search(self, keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
        return [self._public_record(rec) for rec in doc_parser.search(self.records, keyword, limit=limit)]

    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"version": INDEX_VERSION, "source_doc_id": self.source_doc_id,
                   "index_version": self.index_version, "built_at": self.built_at,
                   "sheets": self.sheets, "records": self.records, "errors": self.errors}
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                             prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
                temp_path = Path(stream.name)
                json.dump(payload, stream, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path and temp_path.exists():
                temp_path.unlink()

    @classmethod
    def load(cls, path: Path, client: Optional[TencentDocsClient] = None,
             expected_doc_id: Optional[str] = None) -> Optional["DocIndex"]:
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            source = payload.get("source_doc_id")
            expected = expected_doc_id if expected_doc_id is not None else getattr(client, "doc_id", None)
            if (payload.get("version") != INDEX_VERSION or not source or expected and source != expected
                    or not isinstance(payload.get("records"), list) or not payload["records"]
                    or not all(isinstance(rec, dict) for rec in payload["records"])
                    or not isinstance(payload.get("sheets"), list) or not payload.get("index_version")):
                return None
            idx = cls(client)
            idx.source_doc_id = source
            idx.sheets = payload["sheets"]
            idx.built_at = float(payload.get("built_at") or 0)
            idx.errors = payload.get("errors") or []
            idx._index_version = str(payload["index_version"])
            idx._set_records(payload["records"])
            return idx
        except (OSError, ValueError, TypeError, KeyError, AttributeError):
            return None

    @property
    def age_hours(self) -> float:
        return (time.time() - self.built_at) / 3600.0 if self.built_at else float("inf")
