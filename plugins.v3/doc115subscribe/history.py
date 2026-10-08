"""Transactional JSON storage for history and pending offline tasks.

All instances for one file share a lock. Mutations reread inside that lock and
atomically replace the file. Invalid data and disk failures reach the caller.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, TypeVar

MAX_RECORDS = 200
_T = TypeVar("_T")
_LOCKS: Dict[str, Any] = {}
_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path):
    identity = os.path.normcase(str(path.resolve()))
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(identity, threading.RLock())


class JsonListStore:
    """One process-wide transaction boundary per JSON file path."""

    def __init__(self, path: Path, key: str = "id", max_records: Optional[int] = None):
        self.path = Path(path)
        self.key = key
        self.max_records = max_records
        self._lock = _path_lock(self.path)

    def _read_unlocked(self) -> List[Dict[str, Any]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        if not isinstance(data, list) or any(not isinstance(it, dict) for it in data):
            raise ValueError(f"记录文件格式错误：{self.path.name}")
        return data

    def _write_unlocked(self, items: List[Dict[str, Any]]) -> None:
        if self.max_records is not None:
            items = items[-self.max_records:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=self.path.parent,
                prefix=f".{self.path.name}.", suffix=".tmp", delete=False,
            ) as stream:
                temp_name = stream.name
                json.dump(items, stream, ensure_ascii=False, indent=1, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, self.path)
            temp_name = None
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name)
                except FileNotFoundError:
                    pass

    def transaction(self, mutator: Callable[[List[Dict[str, Any]]], _T]) -> _T:
        """Mutate the latest rows in place, commit once, and return a snapshot."""
        with self._lock:
            items = self._read_unlocked()
            before = copy.deepcopy(items)
            result = mutator(items)
            if items != before:
                self._write_unlocked(items)
            return copy.deepcopy(result)

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            return self._read_unlocked()

    def get(self, value: Any, *, key: Optional[str] = None) -> Optional[Dict[str, Any]]:
        field = key or self.key
        with self._lock:
            return next((it for it in self._read_unlocked() if it.get(field) == value), None)

    def upsert(self, item: Dict[str, Any], *, key: Optional[str] = None) -> Dict[str, Any]:
        """Insert or fill missing fields; existing progress and timestamps win.

        Use ``update`` for deliberate changes to an existing row.
        """
        field = key or self.key
        value = item.get(field)
        if value in (None, ""):
            raise ValueError(f"记录缺少唯一标识：{field}")

        def mutate(items):
            for row in items:
                if row.get(field) == value:
                    for name, data in item.items():
                        row.setdefault(name, copy.deepcopy(data))
                    return row
            row = copy.deepcopy(item)
            items.append(row)
            return row

        return self.transaction(mutate)

    def update(self, value: Any, *, key: Optional[str] = None, **fields: Any) -> bool:
        field = key or self.key

        def mutate(items):
            for row in items:
                if row.get(field) == value:
                    row.update(copy.deepcopy(fields))
                    return True
            return False

        return self.transaction(mutate)

    def delete(self, value: Any, *, key: Optional[str] = None) -> bool:
        field = key or self.key

        def mutate(items):
            keep = [it for it in items if it.get(field) != value]
            removed = len(keep) != len(items)
            items[:] = keep
            return removed

        return self.transaction(mutate)

    def clear(self) -> int:
        def mutate(items):
            count = len(items)
            items.clear()
            return count

        return self.transaction(mutate)


class PendingStore(JsonListStore):
    """Unbounded offline queue, keyed by canonical info hash."""

    def __init__(self, path: Path):
        super().__init__(path, key="hash")


class RecordStore(JsonListStore):
    """Recent plugin activity; preserves the existing JSON history format."""

    def __init__(self, path: Path):
        super().__init__(path, key="id", max_records=MAX_RECORDS)

    def _load(self) -> List[Dict[str, Any]]:
        return super().list()

    def add(self, item: Dict[str, Any]) -> Dict[str, Any]:
        now = time.time()
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        rec = {
            "status": "submitted", "progress": 0, "message": "",
            "submitted_at": timestamp, "updated_at": timestamp,
            **copy.deepcopy(item),
        }
        rec["id"] = f"{int(now * 1000)}-{uuid.uuid4().hex[:12]}"

        def mutate(items):
            items.append(rec)
            return rec

        return self.transaction(mutate)

    def update(self, rec_id: str, **fields: Any) -> bool:
        fields["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        return super().update(rec_id, **fields)

    def list(self, limit: int = MAX_RECORDS) -> List[Dict[str, Any]]:
        return list(reversed(super().list()))[:max(0, int(limit))]

    def find_by_hash(self, info_hash: str) -> Optional[Dict[str, Any]]:
        wanted = (info_hash or "").lower()
        if wanted:
            for item in self.list():
                if str(item.get("hash") or "").lower() == wanted:
                    return item
        return None
