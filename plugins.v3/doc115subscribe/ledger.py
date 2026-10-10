"""Plugin-private SQLite tasks, submission intents and resource protection.

Transactions contain only local persistence. Every sent attempt keeps its
receipt even after configuration changes or stop; a lease expiry is never proof
that a request was not submitted. Hiding history never removes resource holds.
"""
from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .organization import match_history, prepare_manifest, summarize, timestamp


def _encode(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class TaskLedger:
    SCHEMA_VERSION = 1
    MAX_PENDING_EVENTS = 2000
    MAX_ACKNOWLEDGED_EVENTS = 1000
    MAX_EVIDENCE_PER_BATCH = 500
    ACK_RETENTION_SECONDS = 7 * 86400   # maintenance() 的兜底清理；_prune_events 仍按 1 天/条数上限更积极地清理

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as db:
            metadata_exists = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='metadata'").fetchone()
            if metadata_exists:
                version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
                if version and int(version[0]) != self.SCHEMA_VERSION:
                    raise ValueError("不支持的插件账本版本；已暂停以保护既有提交证据")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS batches (
                    batch_id TEXT PRIMARY KEY, resource_key TEXT,
                    created_ts REAL NOT NULL, updated_ts REAL NOT NULL,
                    hidden INTEGER NOT NULL DEFAULT 0, revision INTEGER NOT NULL DEFAULT 1,
                    config_generation INTEGER NOT NULL DEFAULT 0, payload TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS batches_resource ON batches(resource_key);
                CREATE TABLE IF NOT EXISTS resource_holds (
                    resource_key TEXT PRIMARY KEY, batch_id TEXT NOT NULL,
                    state TEXT NOT NULL, updated_ts REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY, batch_id TEXT NOT NULL,
                    phase TEXT NOT NULL, generation INTEGER NOT NULL,
                    created_ts REAL NOT NULL, outcome TEXT NOT NULL,
                    intent TEXT NOT NULL, receipt TEXT, received_ts REAL);
                CREATE INDEX IF NOT EXISTS attempts_batch ON attempts(batch_id);
                CREATE TABLE IF NOT EXISTS evidence (
                    batch_id TEXT NOT NULL, evidence_key TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(batch_id, evidence_key));
                CREATE TABLE IF NOT EXISTS event_inbox (
                    event_id TEXT PRIMARY KEY, created_ts REAL NOT NULL,
                    payload TEXT NOT NULL, acknowledged INTEGER NOT NULL DEFAULT 0,
                    touched_revision INTEGER NOT NULL DEFAULT 0);
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(event_inbox)")}
            if "touched_revision" not in columns:
                db.execute("ALTER TABLE event_inbox ADD COLUMN touched_revision INTEGER NOT NULL DEFAULT 0")
            db.execute("CREATE INDEX IF NOT EXISTS event_inbox_due ON event_inbox(acknowledged,touched_revision,created_ts)")
            version = db.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()
            if version and int(version[0]) != self.SCHEMA_VERSION:
                raise ValueError("不支持的插件账本版本；已暂停以保护既有提交证据")
            db.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES('schema_version',?)", (str(self.SCHEMA_VERSION),))
        self._migrate_index_columns()

    # 0.11.0：把高频调度要用的字段冗余成列，2 秒/20 秒的 tick 只取到期/活跃的行，不再全表反序列化。
    INDEX_COLUMNS = (("acquisition_status", "TEXT NOT NULL DEFAULT ''"), ("organization_status", "TEXT NOT NULL DEFAULT ''"),
                     ("move_status", "TEXT NOT NULL DEFAULT ''"), ("next_check_at", "REAL NOT NULL DEFAULT 0"),
                     ("org_next_ts", "REAL NOT NULL DEFAULT 0"), ("tracking_enabled", "INTEGER NOT NULL DEFAULT 1"),
                     ("org_giveup", "INTEGER NOT NULL DEFAULT 0"), ("org_requested", "INTEGER NOT NULL DEFAULT 0"),
                     ("media_type", "TEXT NOT NULL DEFAULT ''"))

    @staticmethod
    def _number(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    @classmethod
    def _index_values(cls, item: Dict[str, Any]) -> tuple:
        kind = str(item.get("type") or item.get("target_type") or item.get("media_type") or "").strip().lower()
        media = "tv" if kind in ("tv", "电视剧", "剧集") else "movie" if kind in ("movie", "电影") else ""
        return (str(item.get("acquisition_status") or ""), str(item.get("organization_status") or ""),
                str(item.get("move_status") or ""), cls._number(item.get("next_check_at")),
                cls._number(item.get("org_next_ts")), int(bool(item.get("tracking_enabled", True))),
                int(bool(item.get("org_giveup"))), int(bool(item.get("org_requested"))), media)

    def _write_index(self, db, batch_id: str, item: Dict[str, Any]) -> None:
        names = ",".join(f"{name}=?" for name, _ in self.INDEX_COLUMNS)
        db.execute(f"UPDATE batches SET {names} WHERE batch_id=?", (*self._index_values(item), batch_id))

    def _migrate_index_columns(self) -> None:
        with self._connection(write=True) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(batches)")}
            added = False
            for name, kind in self.INDEX_COLUMNS:
                if name not in columns:
                    db.execute(f"ALTER TABLE batches ADD COLUMN {name} {kind}")
                    added = True
            done = db.execute("SELECT 1 FROM metadata WHERE key='index_columns_v1'").fetchone()
            if added or not done:
                for row in list(db.execute("SELECT batch_id,payload FROM batches")):
                    self._write_index(db, row[0], json.loads(row[1]))
                db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('index_columns_v1',?)", (str(time.time()),))
            db.execute("CREATE INDEX IF NOT EXISTS batches_acquire_due ON batches(tracking_enabled,acquisition_status,next_check_at)")
            db.execute("CREATE INDEX IF NOT EXISTS batches_org_due ON batches(tracking_enabled,org_giveup,org_next_ts)")

    @contextmanager
    def _connection(self, write: bool = False):
        db = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA busy_timeout=10000")
        db.execute("PRAGMA foreign_keys=ON")
        try:
            if write:
                db.execute("BEGIN IMMEDIATE")
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _row(row) -> Optional[Dict[str, Any]]:
        if row is None:
            return None
        payload = json.loads(row["payload"])
        payload.update(id=row["batch_id"], batch_id=row["batch_id"], revision=row["revision"],
                       config_generation=row["config_generation"], hidden=bool(row["hidden"]),
                       created_ts=row["created_ts"], updated_ts=row["updated_ts"])
        return payload

    def _get(self, db, batch_id: str) -> Optional[Dict[str, Any]]:
        return self._row(db.execute("SELECT * FROM batches WHERE batch_id=?", (str(batch_id),)).fetchone())

    def get(self, batch_id: str) -> Optional[Dict[str, Any]]:
        with self._connection() as db:
            return self._get(db, batch_id)

    def list(self, limit: Optional[int] = 200, include_hidden: bool = False, offset: int = 0) -> List[Dict[str, Any]]:
        with self._connection() as db:
            query = "SELECT * FROM batches" + ("" if include_hidden else " WHERE hidden=0") + " ORDER BY created_ts DESC,batch_id DESC LIMIT ?"
            query += " OFFSET ?"
            return [self._row(row) for row in db.execute(query, (-1 if limit is None else max(0, int(limit)), max(0, int(offset))))]

    def find_by_resource(self, resource_key: str) -> Optional[Dict[str, Any]]:
        with self._connection() as db:
            hold = db.execute("SELECT batch_id FROM resource_holds WHERE resource_key=?", (str(resource_key),)).fetchone()
            return self._get(db, hold[0]) if hold else None

    def find_by_hash(self, info_hash: str) -> Optional[Dict[str, Any]]:
        wanted = str(info_hash or "").lower()
        if not wanted:
            return None
        with self._connection() as db:
            for row in db.execute("SELECT * FROM batches ORDER BY created_ts DESC"):
                item = self._row(row)
                if str(item.get("hash") or "").lower() == wanted:
                    return item
        return None

    def _insert(self, db, context: Dict[str, Any], resource_key: str = "", generation: int = 0) -> Dict[str, Any]:
        now = time.time()
        batch_id = str(context.get("batch_id") or context.get("id") or uuid.uuid4().hex)
        item = {"status": "submitting", "acquisition_status": "submitting", "organization_status": "unknown",
                "manifest_complete": False, "tracking_enabled": True, "message": "准备提交",
                "progress": 0, "submitted_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now)),
                **copy.deepcopy(context), "id": batch_id, "batch_id": batch_id,
                "resource_key": resource_key or str(context.get("resource_key") or "")}
        generation = int(item.get("config_generation", generation))
        created = float(item.get("created_ts") or now)
        db.execute("INSERT INTO batches(batch_id,resource_key,created_ts,updated_ts,config_generation,payload) VALUES(?,?,?,?,?,?)",
                   (batch_id, item["resource_key"], created, now, generation, _encode(item)))
        self._write_index(db, batch_id, item)
        return self._get(db, batch_id)

    def add(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility insertion; network submitters must use claim_resource."""
        context = copy.deepcopy(context)
        if "acquisition_status" not in context:
            state = str(context.get("status") or "submitting")
            context["acquisition_status"] = "saved" if state in ("done", "organized") else state if state in ("queued", "submitting", "downloading", "awaiting_move", "moving", "failed") else "uncertain"
        with self._connection(write=True) as db:
            item = self._insert(db, context)
            if item.get("resource_key"):
                db.execute("INSERT OR IGNORE INTO resource_holds VALUES(?,?,?,?)", (item["resource_key"], item["id"], "held", time.time()))
            return item

    def claim_resource(self, resource_key: str, context: Dict[str, Any], generation: int = 0) -> Dict[str, Any]:
        if not resource_key:
            raise ValueError("提交必须具有稳定资源标识")
        with self._connection(write=True) as db:
            old = db.execute("SELECT batch_id FROM resource_holds WHERE resource_key=?", (str(resource_key),)).fetchone()
            if old:
                return {"claimed": False, "batch": self._get(db, old[0]), "attempt": None}
            legacy = self._legacy_equivalent(db, context)
            if legacy:
                db.execute("INSERT INTO resource_holds VALUES(?,?,?,?)", (resource_key, legacy["id"], "uncertain", time.time()))
                return {"claimed": False, "batch": legacy, "attempt": None}
            item = self._insert(db, context, str(resource_key), generation)
            db.execute("INSERT INTO resource_holds VALUES(?,?,?,?)", (resource_key, item["id"], "held", time.time()))
            attempt = self._new_attempt(db, item, "acquire", generation)
            self._update(db, item["id"], {"evidence_started_at": attempt["created_ts"]})
            item = self._get(db, item["id"])
            return {"claimed": True, "batch": item, "attempt": attempt}

    def prepare_resource(self, resource_key: str, context: Dict[str, Any], generation: int = 0) -> Dict[str, Any]:
        """Reserve a persistent queue entry without implying a sent request."""
        if not resource_key:
            raise ValueError("提交必须具有稳定资源标识")
        with self._connection(write=True) as db:
            old = db.execute("SELECT batch_id FROM resource_holds WHERE resource_key=?", (str(resource_key),)).fetchone()
            if old:
                return {"claimed": False, "batch": self._get(db, old[0])}
            legacy = self._legacy_equivalent(db, context)
            if legacy:
                db.execute("INSERT INTO resource_holds VALUES(?,?,?,?)", (resource_key, legacy["id"], "uncertain", time.time()))
                return {"claimed": False, "batch": legacy}
            item = self._insert(db, {**context, "status": "queued", "acquisition_status": "queued"}, str(resource_key), generation)
            db.execute("INSERT INTO resource_holds VALUES(?,?,?,?)", (resource_key, item["id"], "queued", time.time()))
            return {"claimed": True, "batch": item}

    def _legacy_equivalent(self, db, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Old key schemas/unknown accounts must not silently allow resubmits."""
        info_hash = str(context.get("hash") or "").lower()
        url = str(context.get("url") or "")
        if not info_hash and not url:
            return None
        for row in db.execute("SELECT * FROM batches"):
            old = self._row(row)
            if not old.get("legacy_snapshot") or not old.get("dedupe_hold"):
                continue
            same = info_hash == str(old.get("hash") or "").lower() if info_hash else url == str(old.get("url") or "") and context.get("kind") == old.get("kind")
            if not same:
                continue
            if context.get("final_path") and old.get("final_path") and str(context["final_path"]).rstrip("/") != str(old["final_path"]).rstrip("/"):
                continue
            if context.get("account_key") and old.get("account_key") and context["account_key"] != old["account_key"]:
                continue
            return old
        return None

    @staticmethod
    def _new_attempt(db, batch: Dict[str, Any], phase: str, generation: int, intent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        attempt = {"attempt_id": uuid.uuid4().hex, "batch_id": batch["id"], "phase": phase,
                   "kind": "submit" if phase == "acquire" else phase,
                   "generation": int(generation), "created_ts": time.time(), "outcome": "intent", "intent": copy.deepcopy(intent if intent is not None else batch)}
        db.execute("INSERT INTO attempts(attempt_id,batch_id,phase,generation,created_ts,outcome,intent) VALUES(?,?,?,?,?,?,?)",
                   (attempt["attempt_id"], attempt["batch_id"], phase, int(generation), attempt["created_ts"], "intent", _encode(attempt["intent"])))
        return attempt

    def begin_attempt(self, batch_id: str, phase: str = "acquire", generation: int = 0,
                      kind: Optional[str] = None, intent: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Claim an existing phase. Unresolved intents cannot be blindly reissued."""
        phase = "acquire" if (kind or phase) == "submit" else str(kind or phase)
        with self._connection(write=True) as db:
            batch = self._get(db, batch_id)
            if not batch:
                raise KeyError(batch_id)
            if not batch.get("tracking_enabled", True) or batch["config_generation"] != int(generation):
                raise ValueError("任务已停止或配置已变更")
            existing = db.execute("SELECT * FROM attempts WHERE batch_id=? AND phase=? AND outcome IN ('intent','uncertain','accepted') ORDER BY created_ts DESC LIMIT 1", (batch_id, phase)).fetchone()
            if existing:
                raise ValueError("本阶段已有待核实提交，不能再次发送")
            if phase in ("acquire", "share_receive") and batch.get("acquisition_status") in ("saved", "success", "downloading", "awaiting_move", "moving"):
                raise ValueError("资源已获取或正在获取，不能作为整理重试再次提交")
            if phase == "move" and batch.get("move_status") == "success":
                raise ValueError("本批次已经搬运成功，仅允许核对结果")
            attempt = self._new_attempt(db, batch, str(phase), int(generation), intent)
            if phase in ("acquire", "share_receive"):
                fields = {"status": "submitting", "acquisition_status": "submitting", "active_attempt_id": attempt["attempt_id"]}
                if not batch.get("evidence_started_at"):
                    fields["evidence_started_at"] = attempt["created_ts"]
                self._update(db, batch_id, fields)
            elif phase == "move":
                self._update(db, batch_id, {"status": "moving", "acquisition_status": "moving", "move_status": "moving", "active_attempt_id": attempt["attempt_id"]})
            return attempt

    def attempts(self, batch_id: str) -> List[Dict[str, Any]]:
        with self._connection() as db:
            rows = []
            for row in db.execute("SELECT * FROM attempts WHERE batch_id=? ORDER BY created_ts", (batch_id,)):
                result = dict(row)
                result["kind"] = "submit" if result["phase"] == "acquire" else result["phase"]
                result["intent"] = json.loads(result["intent"])
                result["receipt"] = json.loads(result["receipt"]) if result["receipt"] else None
                rows.append(result)
            return rows

    def _update(self, db, batch_id: str, fields: Dict[str, Any], expected_revision: Optional[int] = None) -> bool:
        item = self._get(db, batch_id)
        if item is None or (expected_revision is not None and item["revision"] != int(expected_revision)):
            return False
        for key in ("id", "batch_id", "created_ts", "revision"):
            fields.pop(key, None)
        item.update(copy.deepcopy(fields))
        generation = int(item.get("config_generation") or 0)
        now = time.time()
        item["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        db.execute("UPDATE batches SET payload=?,updated_ts=?,revision=revision+1,config_generation=?,hidden=? WHERE batch_id=?",
                   (_encode(item), now, generation, int(bool(item.get("hidden"))), batch_id))
        self._write_index(db, batch_id, item)
        if item.get("resource_key") and item.get("acquisition_status") in ("saved", "success"):
            db.execute("UPDATE resource_holds SET state='acquired',updated_ts=? WHERE resource_key=?", (now, item["resource_key"]))
        return True

    def update(self, batch_id: str, **fields: Any) -> bool:
        expected_revision = fields.pop("expected_revision", None)
        with self._connection(write=True) as db:
            return self._update(db, str(batch_id), fields, expected_revision)

    def update_merged(self, batch_id: str, fields: Dict[str, Any],
                      merge: Callable[[Dict[str, Any], Dict[str, Any]], Optional[Dict[str, Any]]]) -> bool:
        """在同一写事务内读最新记录再合并，避免后台用旧快照覆盖用户刚做的修改。

        ``merge(current, fields)`` 返回实际要写入的字段；返回 None 表示放弃本次写入。
        """
        with self._connection(write=True) as db:
            current = self._get(db, str(batch_id))
            if current is None:
                return False
            merged = merge(current, copy.deepcopy(fields))
            if merged is None:
                return False
            return self._update(db, str(batch_id), merged)

    # ---- 按索引列取行（高频 tick 用，不做全表反序列化）--------------------
    ACTIVE_ACQUISITION = ("queued", "submitting", "uncertain", "downloading", "awaiting_move", "moving")

    def due_acquisitions(self, now: float, limit: int = 1) -> Dict[str, Any]:
        """跟踪中、获取未终结且已到期的批次：按 (next_check_at, created_ts) 取最早的若干条，并给出到期总数。"""
        marks = ",".join("?" * len(self.ACTIVE_ACQUISITION))
        where = f"tracking_enabled=1 AND acquisition_status IN ({marks}) AND next_check_at<=?"
        params = (*self.ACTIVE_ACQUISITION, float(now))
        with self._connection() as db:
            count = db.execute(f"SELECT COUNT(*) FROM batches WHERE {where}", params).fetchone()[0]
            rows = [self._row(r) for r in db.execute(
                f"SELECT * FROM batches WHERE {where} ORDER BY next_check_at,created_ts LIMIT ?", (*params, max(0, int(limit))))]
            return {"rows": rows, "count": int(count)}

    def due_organization(self, now: float, record_id: str = "", extra_acquisition: Iterable[str] = ()) -> List[Dict[str, Any]]:
        """跟踪中、未放弃、到期且（未成功或被手动请求）的批次；其余细节条件由调用方再判断。"""
        statuses = ("saved", "success", *tuple(extra_acquisition))
        marks = ",".join("?" * len(statuses))
        where = (f"tracking_enabled=1 AND org_giveup=0 AND org_next_ts<=? AND (acquisition_status IN ({marks}) "
                 "OR move_status IN ('moving','uncertain')) AND (organization_status!='success' OR org_requested=1)")
        params: List[Any] = [float(now), *statuses]
        if record_id:
            where += " AND batch_id=?"
            params.append(str(record_id))
        with self._connection() as db:
            return [self._row(r) for r in db.execute(
                f"SELECT * FROM batches WHERE {where} ORDER BY org_next_ts,created_ts", params)]

    def tracked(self) -> List[Dict[str, Any]]:
        with self._connection() as db:
            return [self._row(r) for r in db.execute("SELECT * FROM batches WHERE tracking_enabled=1 ORDER BY created_ts DESC,batch_id DESC")]

    def change_token(self) -> tuple:
        """任意批次增删改都会改变该值（revision 单调递增），用于判断是否需要重建本地缓存。"""
        with self._connection() as db:
            row = db.execute("SELECT COUNT(*),COALESCE(SUM(revision),0),COALESCE(MAX(updated_ts),0) FROM batches").fetchone()
            return (str(self.path), int(row[0]), int(row[1]), float(row[2]))

    def save_receipt(self, attempt_id: str, outcome: str, receipt: Dict[str, Any], generation: Optional[int] = None) -> Dict[str, Any]:
        if outcome not in ("success", "failure", "uncertain", "accepted"):
            raise ValueError("未知外部回执结果")
        with self._connection(write=True) as db:
            attempt = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if not attempt:
                raise KeyError(attempt_id)
            previous = attempt["outcome"]
            # A duplicated/late callback cannot downgrade a completed write.
            if previous == "success" and outcome != "success":
                return {"saved": True, "current_generation": False, "batch": self._get(db, attempt["batch_id"])}
            db.execute("UPDATE attempts SET outcome=?,receipt=?,received_ts=? WHERE attempt_id=?", (outcome, _encode(receipt), time.time(), attempt_id))
            batch = self._get(db, attempt["batch_id"])
            actual_generation = int(generation) if generation is not None else int(attempt["generation"])
            current = batch["config_generation"] == actual_generation == int(attempt["generation"]) and batch.get("tracking_enabled", True)
            facts = {"last_attempt_id": attempt_id, "last_receipt_outcome": outcome}
            if attempt["phase"] == "acquire":
                acquired = batch.get("acquisition_status") in ("saved", "success")
                status = receipt.get("acquisition_status") or ({"success": "saved", "accepted": "downloading", "uncertain": "uncertain", "failure": "failed"}[outcome])
                if not acquired:
                    facts["acquisition_status"] = status
                    if current:
                        facts["status"] = {"saved": "done", "success": "done", "uncertain": "unverified"}.get(status, status)
            elif attempt["phase"] == "share_receive":
                state = copy.deepcopy(receipt.get("share_state") or {})
                previous_state = batch.get("share_state") or {}
                if int(state.get("received") or 0) < int(previous_state.get("received") or 0):
                    state = copy.deepcopy(previous_state)
                if state:
                    facts["share_state"] = state
                done = bool(receipt.get("done") or state.get("done"))
                already_saved = batch.get("acquisition_status") in ("saved", "success")
                if not already_saved:
                    status = "saved" if outcome == "success" and done else "queued" if outcome == "success" else "uncertain" if outcome in ("accepted", "uncertain") else "failed"
                    facts["acquisition_status"] = status
                    if status == "saved":
                        facts["moved_at"] = time.time()
                    if current:
                        facts["status"] = {"saved": "done", "uncertain": "unverified"}.get(status, status)
                        if status == "saved":
                            facts["progress"] = 100
            elif attempt["phase"] == "move":
                facts["move_status"] = {"success": "success", "accepted": "moving", "uncertain": "uncertain", "failure": "failed"}[outcome]
                if outcome == "success":
                    facts.update(acquisition_status="saved", moved_at=time.time())
                    if current:
                        facts.update(status="done", progress=100)
            # Whitelisted factual identity is useful even after stop. Scheduling,
            # presentation messages and configuration are never copied blindly.
            for key in ("task_file_id", "file_id", "task_id", "actual_cid", "item_name", "item_names", "quality_score", "fingerprint", "actual_candidate"):
                if key in receipt:
                    facts[key] = copy.deepcopy(receipt[key])
            for key in ("source_manifest", "source_manifest_ready", "manifest_snapshot_ready"):
                if key in receipt:
                    facts[key] = copy.deepcopy(receipt[key])
            if current:
                for key in ("next_check_at", "message", "progress"):
                    if key in receipt:
                        facts[key] = receipt[key]
            self._update(db, batch["id"], facts)
            hold_state = "acquired" if facts.get("acquisition_status") == "saved" or batch.get("acquisition_status") in ("saved", "success") else "uncertain" if outcome in ("accepted", "uncertain") else "failed_safe" if outcome == "failure" else "held"
            if batch.get("resource_key"):
                db.execute("UPDATE resource_holds SET state=?,updated_ts=? WHERE resource_key=?", (hold_state, time.time(), batch["resource_key"]))
            return {"saved": True, "current_generation": bool(current), "batch": self._get(db, batch["id"])}

    def delete(self, batch_id: str) -> bool:
        return self.update(batch_id, hidden=True)

    hide = delete

    def clear(self) -> int:
        with self._connection(write=True) as db:
            rows = [row[0] for row in db.execute("SELECT batch_id FROM batches WHERE hidden=0")]
            for batch_id in rows:
                self._update(db, batch_id, {"hidden": True})
            return len(rows)

    def stop_tracking(self, batch_id: str) -> bool:
        return self.update(batch_id, tracking_enabled=False, next_check_at=0, organization_status="paused")

    def set_manifest(self, batch_id: str, items: Iterable[Dict[str, Any]], complete: bool = False, reason: str = "") -> Dict[str, Any]:
        with self._connection(write=True) as db:
            batch = self._get(db, batch_id)
            if not batch:
                raise KeyError(batch_id)
            incoming = prepare_manifest(items)
            # Immutable expected units are enriched by exact path/storage. A
            # received share's new target ID fills an empty ID; it is never
            # treated as a second episode or as the original source-share ID.
            old = batch.get("manifest") or []
            merged = {u["unit_key"]: copy.deepcopy(u) for u in old}
            by_path = {(u.get("storage"), u.get("source_path")): u["unit_key"] for u in old}
            conflicts = copy.deepcopy(batch.get("manifest_conflicts") or [])
            for unit in incoming["items"]:
                key = by_path.get((unit.get("storage"), unit.get("source_path")))
                if key:
                    previous = merged[key]
                    if previous.get("file_id") and unit.get("file_id") and previous["file_id"] != unit["file_id"]:
                        conflict = {"source_path": unit["source_path"], "storage": unit["storage"],
                                    "registered_file_id": previous["file_id"], "observed_file_id": unit["file_id"]}
                        if conflict not in conflicts:
                            conflicts.append(conflict)
                        continue
                    enriched = {**previous, **unit, "unit_key": key,
                                "file_id": unit.get("file_id") or previous.get("file_id") or "",
                                "required": bool(previous.get("required") or unit.get("required"))}
                    merged[key] = enriched
                else:
                    merged[unit["unit_key"]] = unit
                    by_path[(unit.get("storage"), unit.get("source_path"))] = unit["unit_key"]
            result = prepare_manifest(merged.values(), complete or batch.get("manifest_complete", False), batch.get("expected_episodes"))
            incoming_reason = incoming["reason"]
            # Empty later scans cannot erase the original nonempty expectation.
            if incoming_reason == "empty_required_manifest" and old:
                incoming_reason = ""
            if incoming_reason:
                result["complete"] = False
                result["reason"] = ",".join(filter(None, (result["reason"], incoming_reason)))
            if conflicts:
                result["complete"] = False
                result["reason"] = ",".join(filter(None, (result["reason"], "manifest_file_identity_conflict")))
            expected_count = batch.get("expected_episode_count")
            if expected_count is not None:
                actual_episodes = {int(e) for unit in result["items"] if unit.get("required") for e in (unit.get("episodes") or [])}
                if len(actual_episodes) < int(expected_count):
                    result["complete"] = False
                    result["reason"] = ",".join(filter(None, (result["reason"], "expected_episode_missing")))
            self._update(db, batch_id, {"manifest": result["items"], "manifest_complete": result["complete"],
                                      "manifest_reason": reason or result["reason"], "manifest_conflicts": conflicts})
            return self._get(db, batch_id)

    append_manifest = set_manifest

    def get_manifest(self, batch_id: str) -> Dict[str, Any]:
        batch = self.get(batch_id)
        if not batch:
            raise KeyError(batch_id)
        return {"items": batch.get("manifest") or [], "complete": bool(batch.get("manifest_complete")), "reason": batch.get("manifest_reason") or ""}

    def get_evidence(self, batch_id: str) -> List[Dict[str, Any]]:
        with self._connection() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM evidence WHERE batch_id=?", (batch_id,))]

    def record_evidence(self, batch_id: str, entries: Iterable[Dict[str, Any]], pagination_complete: bool = False) -> Dict[str, Any]:
        with self._connection(write=True) as db:
            batch = self._get(db, batch_id)
            if not batch:
                raise KeyError(batch_id)
            for entry in match_history(batch, entries):
                old = db.execute("SELECT payload FROM evidence WHERE batch_id=? AND evidence_key=?", (batch_id, entry["evidence_key"])).fetchone()
                if old:
                    old_entry = json.loads(old[0])
                    if old_entry.get("status") is True and entry.get("status") is False and entry.get("time_is_observed"):
                        continue
                    old_rank = (timestamp(old_entry.get("evidence_at")) or 0, old_entry.get("status") is True)
                    new_rank = (timestamp(entry.get("evidence_at")) or 0, entry.get("status") is True)
                    recovering_observed_failure = old_entry.get("status") is False and old_entry.get("time_is_observed") and entry.get("status") is True
                    if old_rank > new_rank and not recovering_observed_failure:
                        continue
                db.execute("INSERT OR REPLACE INTO evidence(batch_id,evidence_key,payload) VALUES(?,?,?)", (batch_id, entry["evidence_key"], _encode(entry)))
            evidence = [json.loads(row[0]) for row in db.execute("SELECT payload FROM evidence WHERE batch_id=?", (batch_id,))]
            # Reassociate saved candidates after manifest enrichment. Early
            # evidence remains useful but cannot confirm an unknown package.
            evidence = match_history(batch, evidence)
            projection = summarize(batch.get("manifest") or [], evidence, batch.get("manifest_complete", False), pagination_complete)
            self._trim_evidence(db, batch_id, projection.get("organization_evidence") or [])
            self._update(db, batch_id, projection)
            return self._get(db, batch_id)

    def _trim_evidence(self, db, batch_id: str, keep: Iterable[Dict[str, Any]]) -> int:
        """每个批次最多保留 MAX_EVIDENCE_PER_BATCH 条证据：逐文件最新证据必留，其余按证据时间保留最新的。"""
        rows = [(row[0], json.loads(row[1])) for row in db.execute(
            "SELECT evidence_key,payload FROM evidence WHERE batch_id=?", (batch_id,))]
        if len(rows) <= self.MAX_EVIDENCE_PER_BATCH:
            return 0
        pinned = {str(e.get("evidence_key")) for e in keep if e.get("evidence_key") is not None}
        rest = sorted((r for r in rows if r[0] not in pinned),
                      key=lambda r: (timestamp(r[1].get("evidence_at")) or 0, r[0]), reverse=True)
        room = max(0, self.MAX_EVIDENCE_PER_BATCH - len(pinned))
        drop = [key for key, _ in rest[room:]]
        for key in drop:
            db.execute("DELETE FROM evidence WHERE batch_id=? AND evidence_key=?", (batch_id, key))
        return len(drop)

    def maintenance(self) -> Dict[str, int]:
        """启动/定期本地清理（不删除 batches，不动 attempts）：

        - 0.10.x 把 MediaInfo 的 repr 字符串写进了事件 payload，这些事件永远无法处理，直接 ack；
        - 删除已 ack 且超过 ACK_RETENTION_SECONDS 的 inbox 行；
        - 每个批次的 evidence 超出上限的旧条目裁掉。
        """
        result = {"legacy_events_acked": 0, "inbox_deleted": 0, "evidence_trimmed": 0}
        with self._connection(write=True) as db:
            for row in list(db.execute("SELECT event_id,payload FROM event_inbox WHERE acknowledged=0")):
                try:
                    payload = json.loads(row[1])
                except ValueError:
                    payload = None
                broken = not isinstance(payload, dict) or isinstance(payload.get("mediainfo"), str) \
                    or isinstance(payload.get("transferinfo"), str) or isinstance(payload.get("meta"), str)
                if broken:
                    db.execute("UPDATE event_inbox SET acknowledged=1 WHERE event_id=?", (row[0],))
                    result["legacy_events_acked"] += 1
            result["inbox_deleted"] = db.execute("DELETE FROM event_inbox WHERE acknowledged=1 AND created_ts<?",
                                                 (time.time() - self.ACK_RETENTION_SECONDS,)).rowcount
            crowded = [row[0] for row in db.execute(
                "SELECT batch_id FROM evidence GROUP BY batch_id HAVING COUNT(*)>?", (self.MAX_EVIDENCE_PER_BATCH,))]
            for batch_id in crowded:
                batch = self._get(db, batch_id)
                keep = (batch or {}).get("organization_evidence") or []
                result["evidence_trimmed"] += self._trim_evidence(db, batch_id, keep)
        return result

    def enqueue_event(self, event_id: str, payload: Dict[str, Any]) -> bool:
        if not event_id:
            event_id = hashlib.sha256(_encode(payload).encode()).hexdigest()
        with self._connection(write=True) as db:
            self._prune_events(db)
            if db.execute("SELECT 1 FROM event_inbox WHERE event_id=?", (str(event_id),)).fetchone():
                return False
            pending = db.execute("SELECT COUNT(*) FROM event_inbox WHERE acknowledged=0").fetchone()[0]
            if pending >= self.MAX_PENDING_EVENTS:
                dropped = db.execute("SELECT value FROM metadata WHERE key='event_overflow_count'").fetchone()
                db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('event_overflow_count',?)", (str((int(dropped[0]) if dropped else 0) + 1),))
                return False
            cursor = db.execute("INSERT OR IGNORE INTO event_inbox(event_id,created_ts,payload) VALUES(?,?,?)", (str(event_id), time.time(), _encode(payload)))
            return cursor.rowcount == 1

    def drain_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fair snapshot: unassociated early clues cannot starve later events."""
        with self._connection(write=True) as db:
            self._prune_events(db)
            rows = list(db.execute("SELECT event_id,created_ts,payload FROM event_inbox WHERE acknowledged=0 ORDER BY touched_revision,created_ts,event_id LIMIT ?", (max(0, int(limit)),)))
            revision_row = db.execute("SELECT value FROM metadata WHERE key='event_drain_revision'").fetchone()
            revision = (int(revision_row[0]) if revision_row else 0) + 1
            db.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('event_drain_revision',?)", (str(revision),))
            for row in rows:
                db.execute("UPDATE event_inbox SET touched_revision=? WHERE event_id=?", (revision, row[0]))
            return [{"event_id": row[0], "created_ts": row[1], "payload": json.loads(row[2])} for row in rows]

    def ack_event(self, event_id: str) -> bool:
        with self._connection(write=True) as db:
            result = db.execute("UPDATE event_inbox SET acknowledged=1 WHERE event_id=?", (event_id,)).rowcount == 1
            self._prune_events(db)
            return result

    def _prune_events(self, db) -> None:
        db.execute("DELETE FROM event_inbox WHERE acknowledged=1 AND created_ts<?", (time.time() - 86400,))
        db.execute("DELETE FROM event_inbox WHERE acknowledged=1 AND event_id NOT IN (SELECT event_id FROM event_inbox WHERE acknowledged=1 ORDER BY created_ts DESC,event_id DESC LIMIT ?)", (self.MAX_ACKNOWLEDGED_EVENTS,))

    def event_counts(self) -> Dict[str, int]:
        with self._connection() as db:
            overflow = db.execute("SELECT value FROM metadata WHERE key='event_overflow_count'").fetchone()
            return {"pending": db.execute("SELECT COUNT(*) FROM event_inbox WHERE acknowledged=0").fetchone()[0],
                    "acknowledged": db.execute("SELECT COUNT(*) FROM event_inbox WHERE acknowledged=1").fetchone()[0],
                    "overflow": int(overflow[0]) if overflow else 0}

    def migrate_json(self, records_path: Path, pending_path: Optional[Path] = None) -> Dict[str, Any]:
        """One local transaction; original JSON remains an untouched backup."""
        paths = [Path(records_path)] + ([Path(pending_path)] if pending_path else [])
        snapshots = []
        for path in paths:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                value = []
            if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
                raise ValueError("旧记录文件格式错误，停止迁移")
            snapshots.append(value)
        migration_key = "json_v1:" + hashlib.sha256(str(paths[0].resolve()).encode()).hexdigest()
        with self._connection(write=True) as db:
            if db.execute("SELECT 1 FROM metadata WHERE key=?", (migration_key,)).fetchone():
                return {"imported": 0, "pending": 0, "already_migrated": True}
            rows = copy.deepcopy(snapshots[0])
            pending = snapshots[1] if len(snapshots) > 1 else []
            pending_by_id = {str(row.get("record_id")): row for row in pending if row.get("record_id")}
            for index, row in enumerate(rows):
                task = pending_by_id.get(str(row.get("id")))
                if not task:
                    continue
                # The old visible history lacked the exact offline file IDs.
                # Preserve its facts and enrich missing fields from its paired
                # active task; a stopped pending task must remain stopped.
                enriched = {**copy.deepcopy(task), **row, "legacy_pending_snapshot": copy.deepcopy(task)}
                if task.get("status") == "cancelled":
                    enriched["tracking_enabled"] = False
                if row.get("status") not in ("done", "organized") and not row.get("moved_at") and task.get("status") in ("downloading", "awaiting_move", "moving"):
                    enriched["status"] = task["status"]
                rows[index] = enriched
            represented = {str(row.get("id")) for row in rows}
            rows += [{**row, "id": str(row.get("record_id") or "legacy-pending-" + str(row.get("hash") or index)), "legacy_pending": True} for index, row in enumerate(pending) if str(row.get("record_id")) not in represented]
            imported = 0
            for index, row in enumerate(rows):
                original = copy.deepcopy(row)
                batch_id = str(row.get("id") or "legacy-" + hashlib.sha256(_encode(row).encode()).hexdigest())
                if self._get(db, batch_id):
                    continue
                status = str(row.get("status") or "unverified")
                strong_acquired = status in ("done", "organized") or bool(row.get("moved_at"))
                acquisition = "saved" if strong_acquired else "downloading" if status in ("downloading", "awaiting_move", "moving") else "uncertain"
                key = str(row.get("resource_key") or "legacy:" + hashlib.sha256(f"{row.get('account_key','')}|{row.get('kind','')}|{row.get('hash') or row.get('url','')}|{row.get('final_path','')}".encode()).hexdigest())
                item = {**row, "id": batch_id, "resource_key": key, "legacy_snapshot": original,
                        "acquisition_status": acquisition, "status": "done" if strong_acquired else status,
                        "organization_status": "unknown", "organization_confirmed": False,
                        "manifest_complete": False, "dedupe_hold": True,
                        "tracking_enabled": row.get("tracking_enabled", status != "cancelled"), "actual_quality_verified": False}
                self._insert(db, item, key, int(row.get("config_generation") or 0))
                db.execute("INSERT OR IGNORE INTO resource_holds VALUES(?,?,?,?)", (key, batch_id, "acquired" if strong_acquired else "uncertain", time.time()))
                imported += 1
            db.execute("INSERT INTO metadata(key,value) VALUES(?,?)", (migration_key, str(time.time())))
            return {"imported": imported, "pending": len(pending), "already_migrated": False}

    def backup(self, path: Path) -> None:
        """SQLite's consistent snapshot API, including concurrent transactions."""
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source:
            target = sqlite3.connect(str(destination))
            try:
                source.backup(target)
            finally:
                target.close()


LedgerRecordStore = TaskLedger
