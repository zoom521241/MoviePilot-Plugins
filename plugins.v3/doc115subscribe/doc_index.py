"""本地索引：把整份文档抓一遍并缓存解析结果，供搜索秒开。

为什么不实时搜：文档有 90 个工作表、单表上千行，实时逐表抓取要很久。
改为「每天刷新一次本地索引 + 搜索走缓存」，搜索延迟从分钟级降到毫秒级。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # 作为包的一部分加载（MoviePilot 运行时）
    from . import doc_parser
    from .doc_client import DocError, TencentDocsClient
except ImportError:  # 直接作为顶层模块加载（脚本/单测）
    import doc_parser
    from doc_client import DocError, TencentDocsClient

INDEX_VERSION = 1


class DocIndex:
    def __init__(self, client: TencentDocsClient, max_sheets: int = 0):
        self.client = client
        self.max_sheets = max_sheets  # 0 = 全部
        self.records: List[Dict[str, Any]] = []
        self.sheets: List[Dict[str, Any]] = []
        self.built_at: float = 0.0
        self.errors: List[str] = []

    # -- 构建 ---------------------------------------------------------------
    def build(self, progress=None) -> Dict[str, Any]:
        self.records = []
        self.sheets = []
        self.errors = []
        sheet_list = self.client.fetch_sheet_list()
        if self.max_sheets:
            sheet_list = sheet_list[: self.max_sheets]
        total = len(sheet_list)
        for i, sh in enumerate(sheet_list, 1):
            name, sid = sh["name"], sh["id"]
            if doc_parser.is_skippable_sheet(name):
                continue
            try:
                data = self.client.fetch_sheet(sid)
                recs = doc_parser.parse_sheet(sid, name, data["grid"], data["hrefs"])
            except DocError as exc:
                self.errors.append(f"{name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001
                self.errors.append(f"{name}: {exc}")
                continue
            self.records.extend(recs)
            self.sheets.append({"id": sid, "name": name,
                                "kind": doc_parser.classify_sheet(name),
                                "count": len(recs)})
            if progress:
                progress(i, total, name)
        self.built_at = time.time()
        return self.summary()

    def summary(self) -> Dict[str, Any]:
        return {
            "built_at": self.built_at,
            "sheet_count": len(self.sheets),
            "record_count": len(self.records),
            "errors": self.errors,
        }

    # -- 搜索 ---------------------------------------------------------------
    def search(self, keyword: str, limit: int = 50) -> List[Dict[str, Any]]:
        out = []
        for rec in doc_parser.search(self.records, keyword, limit=limit):
            links = [{"kind": k, "url": u} for k, u in rec["links"]]
            out.append({
                "sheet_id": rec["sheet_id"],
                "sheet": rec["sheet"],
                "row": rec["row"],
                "title": rec["title"],
                "year": rec["year"],
                "tmdbid": rec["tmdbid"],
                "media_type": doc_parser.media_type_of(rec["sheet"], rec["title"]),
                "quality_score": doc_parser.quality_score(rec),
                "qtext": rec.get("qtext", ""),
                "bundle": rec.get("bundle", False),
                "links": links,
            })
        return out

    # -- 持久化 -------------------------------------------------------------
    def save(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": INDEX_VERSION,
            "built_at": self.built_at,
            "sheets": self.sheets,
            "records": self.records,
            "errors": self.errors,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    @classmethod
    def load(cls, path: Path, client: Optional[TencentDocsClient] = None) -> Optional["DocIndex"]:
        path = Path(path)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return None
        if payload.get("version") != INDEX_VERSION:
            return None
        idx = cls(client)  # type: ignore[arg-type]
        idx.records = payload.get("records") or []
        idx.sheets = payload.get("sheets") or []
        idx.built_at = payload.get("built_at") or 0
        idx.errors = payload.get("errors") or []
        return idx

    @property
    def age_hours(self) -> float:
        if not self.built_at:
            return float("inf")
        return (time.time() - self.built_at) / 3600.0
