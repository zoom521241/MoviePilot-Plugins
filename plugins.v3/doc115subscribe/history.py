"""转存 / 离线下载记录（详情页「转存记录」页的数据源）。

只记录本插件发起的操作，最多保留最近 ``MAX_RECORDS`` 条。
状态机：
  * ``submitted``   115 分享已转存（文件直接落到最终目录，等 115 生活事件触发整理）
  * ``downloading`` 磁力/ed2k 已提交离线下载（文件先落暂存目录）
  * ``moving``      离线完成，正在从暂存目录搬到最终目录（走 115网盘Plus）
  * ``done``        已搬到最终目录（等 115 生活事件触发整理）
  * ``failed``      失败
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

MAX_RECORDS = 200


class RecordStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()

    # -- 底层读写 -----------------------------------------------------------
    def _load(self) -> List[Dict[str, Any]]:
        with self._lock:
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, list) else []
            except Exception:
                return []

    def _save(self, items: List[Dict[str, Any]]) -> None:
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(items[-MAX_RECORDS:], ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
            except Exception:
                pass

    # -- 对外接口 -----------------------------------------------------------
    def add(self, item: Dict[str, Any]) -> Dict[str, Any]:
        items = self._load()
        now = time.time()
        rec = {
            "id": f"{int(now * 1000)}-{len(items) % 1000}",
            "status": "submitted",
            "progress": 0,
            "message": "",
            "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            "updated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
            **item,
        }
        items.append(rec)
        self._save(items)
        return rec

    def update(self, rec_id: str, **fields: Any) -> None:
        items = self._load()
        hit = False
        for it in items:
            if it.get("id") == rec_id:
                it.update(fields)
                it["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                hit = True
                break
        if hit:
            self._save(items)

    def list(self, limit: int = MAX_RECORDS) -> List[Dict[str, Any]]:
        return list(reversed(self._load()))[:limit]

    def find_by_hash(self, info_hash: str) -> Optional[Dict[str, Any]]:
        h = (info_hash or "").lower()
        if not h:
            return None
        for it in reversed(self._load()):
            if (it.get("hash") or "").lower() == h:
                return it
        return None

    def clear(self) -> int:
        items = self._load()
        self._save([])
        return len(items)
