"""Persistent plugin task orchestration; network never runs in HTTP actions."""
from __future__ import annotations

import copy
import hashlib
import json
import re
import time
import traceback
from typing import Any, Dict
from urllib.parse import urlsplit
from contextlib import nullcontext
from pathlib import PurePosixPath

try:                                    # MP 运行时的日志器（写入 config/logs/plugins/）
    from app.log import logger
except Exception:                       # 脱离 MP 运行时的降级（单测等）
    import logging
    logger = logging.getLogger("doc115subscribe")

from . import doc_parser, subscribe_sync
from .ledger import TaskLedger
from .link_router import LINK_115_SHARE, LINK_MAGNET, LINK_ED2K, classify_link
from .mp_adapter import MPAdapter, MPDeferred
from .organization import (classify_optional_media, core_title, legacy_identity, match_history,
                           path_is_within)
from .p115_transfer import P115Error, extract_hash


class TaskRuntime:
    ORG_BACKOFF_BASE = 20          # 查不到整理证据时的退避：第 1/2/3 次后分别等 40 → 80 → 160 秒（_delay = base·2^次数）
    ORG_BACKOFF_MAX = 900
    ORG_MAX_PER_RUN = 5
    ORG_GIVEUP_ATTEMPTS = 4        # 连续 4 次仍无任何整理证据 → 判「未找到整理记录」并移出自动核对（约 5 分钟，按 20 秒 tick 取整）
    EVENT_GIVEUP_ATTEMPTS = 3      # 同一条事件连续处理失败 3 次后跳过，避免毒事件拖死整轮核对
    ORG_PENDING_STATES = ("done", "unverified", "organized", "partial", "missing", "unfound")

    @property
    def _last_transfer_result(self):
        return getattr(self._transfer_local, "result", {})

    @_last_transfer_result.setter
    def _last_transfer_result(self, value):
        self._transfer_local.result = value

    def _records(self):
        self._ensure_runtime()
        if getattr(self, "_ledger_instance", None) is None:
            ledger = TaskLedger(self.get_data_path_local() / "tasks.sqlite3")
            ledger.migrate_json(self.history_path, self.pending_path)
            self._ledger_instance = ledger
        return self._ledger_instance

    def _account_key(self):
        cookie = self.get_p115_cookie()
        uid = re.search(r"(?:^|;)\s*UID=([^;]+)", cookie, re.I)
        value = uid.group(1).split("_")[0] if uid else cookie
        return hashlib.sha256(value.encode()).hexdigest()

    def _live(self, generation, batch_id=""):
        if not self._enabled or generation != self._generation:
            return False
        if batch_id:
            item = self._records().get(batch_id)
            return bool(item and item.get("tracking_enabled", True))
        return True

    ORG_REQUEST_FIELDS = ("org_requested", "org_giveup", "org_next_ts", "org_page", "org_attempts", "org_stale_count")
    IN_FLIGHT_STATES = ("queued", "submitting", "uncertain", "downloading", "awaiting_move", "moving", "unverified")

    @classmethod
    def _merge_latest(cls, current, fields, snapshot_ts=None):
        """后台写回前与最新记录合并，避免旧快照覆盖用户刚做的操作（并发覆盖保护）。

        - 用户在本轮核对开始之后又点了「核对」（org_request_ts 更新）：保留其排队请求，不覆盖调度字段；
        - 记录已经是 saved/success（例如用户「确认已转存」或事件证实搬运）：不允许被降级回进行中状态。
        """
        if not current.get("tracking_enabled", True):
            return None
        fields = dict(fields)
        if snapshot_ts is not None and float(current.get("org_request_ts") or 0) > float(snapshot_ts):
            for key in cls.ORG_REQUEST_FIELDS:
                fields.pop(key, None)
        if current.get("acquisition_status") in ("saved", "success"):
            if fields.get("acquisition_status") in cls.IN_FLIGHT_STATES:
                fields.pop("acquisition_status", None)
            if fields.get("status") in cls.IN_FLIGHT_STATES:
                fields.pop("status", None)
            if current.get("move_status") == "success" and fields.get("move_status") in ("moving", "uncertain"):
                fields.pop("move_status", None)
        return fields

    def _update_live(self, batch_id, generation, _snapshot_ts=None, **fields):
        if not self._live(generation, batch_id):
            return False
        store = self._records()
        if not hasattr(store, "update_merged"):
            return store.update(batch_id, **fields)
        return store.update_merged(batch_id, fields, lambda current, f: self._merge_latest(current, f, _snapshot_ts))

    def do_transfer(self, rec, to="", force=False):
        """Reserve an asynchronous resource plan, never force a cloud resubmit."""
        self._ensure_runtime()
        self._last_transfer_result = {"resource_keys": [], "required_resources": [], "uncertain": False}
        if not self._enabled:
            return False, "插件未启用"
        if force:
            return False, "不能通过强制转存重试整理；请核对原任务"
        if rec.get("sheet_bundle") or rec.get("bundle") or rec.get("no_link"):
            return False, "该条目为大包或无独立链接，请查看文档"
        target = to or doc_parser.media_type_of(rec.get("sheet", ""), rec.get("title", ""))
        if target not in ("movie", "tv"):
            return False, "请选择电影或电视剧目录"
        links, seen = [], set()
        for kind, url in doc_parser.iter_links(rec):
            if kind not in (LINK_115_SHARE, LINK_MAGNET, LINK_ED2K) or classify_link(url) != kind:
                continue
            h = extract_hash(url) if kind != LINK_115_SHARE else ""
            if kind != LINK_115_SHARE and not h:
                continue
            identity = ("offline", h) if h else (kind, urlsplit(url).path.rstrip("/").split("/")[-1])
            if identity not in seen:
                seen.add(identity)
                links.append((kind, url))
        if not links:
            return False, "没有可安全跟踪的有效链接"
        final, generation = self.build_save_path(rec, target), self._generation
        explicit = bool(rec.get("_explicit_source"))
        plan = links if self._link_mode == "all" and not explicit else links[:1]
        store = self._records()
        account = self._account_key()

        def lookup(kind, url):
            h = extract_hash(url) if kind != LINK_115_SHARE else ""
            identity = "offline:" + h if h else kind + ":" + urlsplit(url).path.rstrip("/").split("/")[-1]
            key = hashlib.sha256(f"{account}|{identity}|{final}".encode()).hexdigest()
            # Old JSON keys did not include the account; retain their protective hold.
            legacy = hashlib.sha256(f"{kind}|{url}|{final}".encode()).hexdigest()
            raw_key = hashlib.sha256(f"{account}|{kind}:{url}|{final}".encode()).hexdigest()
            old = store.find_by_resource(key) or store.find_by_resource(raw_key) or store.find_by_resource(legacy)
            if not old and not h:
                code = urlsplit(url).path.rstrip("/").split("/")[-1]
                old = next((x for x in store.list(limit=None, include_hidden=True)
                            if x.get("kind") == LINK_115_SHARE and x.get("final_path") == final and
                            x.get("account_key", account) == account and
                            urlsplit(x.get("url") or "").path.rstrip("/").split("/")[-1] == code), None)
            if h:
                tracked = store.find_by_hash(h)
                if tracked and tracked.get("acquisition_status") not in ("failed",) and tracked.get("account_key", account) == account:
                    old = old or tracked
            return h, key, old

        # 先整体检查：任一资源上次明确失败就整体拒绝，避免多链接循环中途 return 留下已排队的残余预约。
        found = [(kind, url, *lookup(kind, url)) for kind, url in plan]
        if any(old and old.get("acquisition_status") == "failed" for *_, old in found):
            return False, "上次获取失败，请处理原因后使用该任务的获取重试"
        actual_items = []
        for kind, url, h, key, old in found:
            media_type = rec.get("media_type") or doc_parser.media_type_of(rec.get("sheet", ""), rec.get("title", ""))
            context = {"title": rec.get("title"), "year": rec.get("year"), "type": media_type,
                "target_type": target,
                "tmdbid": str(rec.get("tmdbid") or ""), "kind": kind, "url": url, "hash": h,
                "account_key": account, "source_storage": "115网盘Plus", "final_storage": "115网盘Plus",
                "final_path": final, "staging_path": self._magnet_staging_path if h else final,
                "subscription_key": rec.get("_subscription_key", ""), "quality_score": doc_parser.quality_score(rec),
                "fingerprint": self._fingerprint(rec), "actual_candidate": copy.deepcopy(rec),
                "config_generation": generation, "next_check_at": time.time(), "message": "已排队，等待获取",
                "fallback_links": links[1:] if not explicit and self._link_mode == "first" else [],
                "fallback_candidates": copy.deepcopy(rec.get("_fallback_candidates") or []),
                "expected_episodes": rec.get("expected_episodes") or [],
                "expected_episode_count": rec.get("expected_episode_count"), "automatic": bool(rec.get("_subscription_key"))}
            context["min_media_size_mb"] = self._min_media_size_mb
            prepared = {"claimed": False, "batch": old} if old else store.prepare_resource(key, context, generation)
            item = prepared["batch"]
            actual_items.append(item)
            self._last_transfer_result["resource_keys"].append(item["resource_key"])
            self._last_transfer_result["required_resources"].append(item["resource_key"])
            if item.get("acquisition_status") in ("saved", "success"):
                self._mark_resource_complete(item.get("subscription_key"), item["resource_key"])
            if item.get("acquisition_status") == "uncertain":
                self._last_transfer_result["uncertain"] = True
        actual = min(actual_items, key=lambda x: int(x.get("quality_score") or 0))
        self._refresh_event_paths()
        self._last_transfer_result.update(state="queued", actual_candidate=copy.deepcopy(actual.get("actual_candidate") or rec),
                                         quality_score=actual.get("quality_score", doc_parser.quality_score(rec)))
        return True, "已排队；已有任务会继续跟踪，不重复获取"

    def api_transfer(self, payload: dict = None):
        body = payload or {}
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        with self._operation_lock:
            index = self._ensure_index()
            if not index or body.get("index_version") != index.index_version:
                return {"code": 1, "msg": "索引已更新，请重新搜索"}
            rec = index.get_record(str(body.get("record_id") or ""))
            if not rec:
                return {"code": 1, "msg": "资源已失效，请重新搜索"}
            target = body.get("to", "")
            if target not in ("movie", "tv"):
                return {"code": 1, "msg": "请选择电影或电视剧目录"}
            rec = copy.deepcopy(rec)
            if "link_index" in body or "link_kind" in body:
                try:
                    pos = int(body["link_index"])
                    if isinstance(body["link_index"], bool) or pos < 0:
                        raise ValueError()
                    links = list(doc_parser.iter_links(rec))
                    kind, url = links[pos]
                    if body.get("link_kind") != kind or kind not in (LINK_115_SHARE, LINK_MAGNET, LINK_ED2K):
                        raise ValueError()
                    rec.update(links=[(kind, url)], _explicit_source=True)
                except (KeyError, ValueError, IndexError, TypeError):
                    return {"code": 1, "msg": "所选来源无效，请重新搜索"}
            ok, msg = self.do_transfer(rec, target)
            return {"code": 0 if ok else 1, "msg": msg, "data": dict(self._last_transfer_result)}

    @staticmethod
    def _delay(attempt, base=30, cap=300):
        return min(cap, base * 2 ** min(max(0, int(attempt)), 5))

    def _defer_task(self, rec, generation, exc):
        if getattr(exc, "reason", "") in ("capability", "target_changed", "account_changed", "local_state"):
            self._update_live(rec["id"], generation, tracking_enabled=False, next_check_at=0,
                              query_error=self._error(exc), last_error=self._error(exc), message="需要处理：" + self._error(exc))
            return
        count = int(rec.get("query_errors") or 0)
        retry = float(getattr(exc, "retry_at", 0) or 0)
        self._update_live(rec["id"], generation, next_check_at=max(time.time() + 2, retry or time.time() + self._delay(count)),
                          last_error=self._error(exc), query_errors=count + 1,
                          query_error=self._error(exc), message="等待核实或请求额度：" + self._error(exc))

    def _submit_step(self, rec, tr, generation):
        store, attempt = self._records(), None
        state = rec.get("share_state") or {}

        def begin(intent):
            nonlocal attempt
            if not self._live(generation, rec["id"]):
                raise P115Error("任务已停止，未发送提交")
            phase = "share_receive" if rec["kind"] == LINK_115_SHARE else "acquire"
            attempt = store.begin_attempt(rec["id"], phase=phase, generation=generation, intent=intent)

        try:
            if rec["kind"] == LINK_115_SHARE:
                tr.last_share_result = {}
                state = tr.prepare_share(rec["url"], rec["final_path"], state=state)
                self._update_live(rec["id"], generation, share_state=state)
                if not state.get("complete"):
                    self._update_live(rec["id"], generation, next_check_at=time.time() + 2)
                    return
                if not rec.get("source_manifest_ready"):
                    manifest = tr.share_manifest_slice(rec["url"], cursor=rec.get("source_manifest_cursor"))
                    entries = list(manifest["items"])
                    self._update_live(rec["id"], generation, source_manifest=entries,
                                      source_manifest_cursor=manifest.get("cursor"), source_manifest_ready=manifest["complete"])
                    unsupported = bool(manifest.get("error")) and any(x in manifest["error"] for x in ("需进一步识别", "超过扫描上限", "目录数量超过"))
                    if not manifest["complete"] and not unsupported:
                        self._update_live(rec["id"], generation, next_check_at=time.time() + (900 if manifest.get("error") else 2),
                            manifest_reason=manifest.get("error") or "原始清单分段读取中",
                            message="原始清单待核实，尚未转存" if manifest.get("error") else "读取本批次原始清单中")
                        return
                    mapped = [{**unit, "source_path": rec["final_path"].rstrip("/") + "/" + unit["relative_path"],
                               "file_id": "", "episodes": [int(x[1]) if isinstance(x, (list, tuple)) else int(x) for x in unit.get("episodes", [])],
                               "storage": "115网盘Plus"} for unit in entries if not unit.get("is_dir")]
                    mapped = classify_optional_media(mapped, rec.get("min_media_size_mb", 0))
                    store.set_manifest(rec["id"], mapped, complete=manifest["complete"], reason=manifest.get("error") or "")
                    self._update_live(rec["id"], generation, source_manifest_ready=True)
                    self._refresh_event_paths()
                state = tr.receive_prepared(rec["url"], rec["final_path"], state, before_submit=begin)
                if attempt:
                    store.save_receipt(attempt["attempt_id"], "success", {"received": state.get("received", 0),
                        "share_state": state, "done": bool(state.get("done"))}, self._generation)
                self._update_live(rec["id"], generation, share_state=state)
                if state.get("done"):
                    self._update_live(rec["id"], generation, status="done", acquisition_status="saved", progress=100,
                        item_names=[x["name"] for x in state.get("items", []) if x.get("name")], moved_at=time.time(),
                        message="已转存到下载目录，MP整理待核实", org_next_ts=time.time() + 60,
                        next_check_at=0, last_error="", query_error="")
                    self._mark_resource_complete(rec.get("subscription_key"), rec["resource_key"])
                    self._complete_subscription_if_ready(rec.get("subscription_key"))
                else:
                    self._update_live(rec["id"], generation, status="queued", acquisition_status="queued", next_check_at=time.time() + 2)
            else:
                tr.last_offline_result = None
                result = tr.offline_add(rec["url"], rec["staging_path"], before_submit=begin)
                receipt = {"task_file_id": getattr(result, "file_id", ""), "actual_cid": getattr(result, "actual_cid", ""),
                           "message": "115已接受离线任务，等待落盘", "next_check_at": time.time() + 5}
                if attempt:
                    store.save_receipt(attempt["attempt_id"], "accepted", receipt, self._generation)
                else:
                    self._update_live(rec["id"], generation, acquisition_status="downloading", status="downloading", **receipt)
                self._update_live(rec["id"], generation, submitted_ts=time.time(), fast_checks=0, progress=0)
        except Exception as exc:
            if getattr(exc, "reconcile_only", False):
                recovery = getattr(exc, "state", None) or {}
                receipt = {"task_file_id": recovery.get("file_id") or "", "actual_cid": recovery.get("actual_cid") or ""}
                if attempt:
                    store.save_receipt(attempt["attempt_id"], "accepted", receipt, self._generation)
                self._update_live(rec["id"], generation, acquisition_status="downloading", status="downloading",
                    offline_cursor=recovery.get("recovery_cursor"), duplicate_recovery_pending=True,
                    message="已有离线任务，等待只读核实，未重复提交")
                self._defer_task(rec, generation, exc)
                return
            if getattr(exc, "state", None) and rec["kind"] == LINK_115_SHARE:
                state = exc.state
                if "queue" in state:
                    self._update_live(rec["id"], generation, source_manifest_cursor=state)
                else:
                    self._update_live(rec["id"], generation, share_state=state)
            receipt = getattr(tr, "last_share_result", {}) if rec["kind"] == LINK_115_SHARE else getattr(tr, "last_offline_result", None)
            uncertain = bool(getattr(exc, "uncertain", False)) or bool(receipt.get("uncertain") if isinstance(receipt, dict) else getattr(receipt, "uncertain", False))
            if not attempt and getattr(exc, "not_sent", False):
                uncertain = False
            partial = bool(rec["kind"] == LINK_115_SHARE and int(state.get("received") or 0) > 0)
            if attempt:
                store.save_receipt(attempt["attempt_id"], "uncertain" if uncertain else "failure",
                                   {"message": self._error(exc), **({"share_state": state} if rec["kind"] == LINK_115_SHARE else {})}, self._generation)
            if uncertain:
                self._update_live(rec["id"], generation, acquisition_status="uncertain", status="unverified",
                    next_check_at=time.time() + 30, message="提交结果待核实，未重复获取", last_error=self._error(exc))
            elif hasattr(exc, "retry_at"):
                if partial and getattr(exc, "not_sent", False):
                    self._update_live(rec["id"], generation, acquisition_status="queued", status="queued", share_state=state)
                self._defer_task(rec, generation, exc)
            elif partial:
                self._update_live(rec["id"], generation, acquisition_status="uncertain", status="unverified",
                                  next_check_at=time.time() + 900, message="部分已转存，剩余部分明确失败，请核对原资源")
            else:
                self._update_live(rec["id"], generation, acquisition_status="failed", status="failed",
                                  next_check_at=0, last_error=self._error(exc), message="获取失败：" + self._error(exc))
                self._fallback_after_failure(rec, generation)

    def _fallback_after_failure(self, rec, generation):
        if not self._live(generation, rec["id"]):
            return
        # This path is only called for an explicit, definitive acquire failure.
        candidates = list(rec.get("fallback_candidates") or [])
        links = list(rec.get("fallback_links") or [])
        original = copy.deepcopy(rec.get("actual_candidate") or {})
        if links:
            candidate = {**original, "links": links, "_explicit_source": False, "_fallback_candidates": candidates}
        elif candidates:
            candidate = {**candidates[0], "_fallback_candidates": candidates[1:], "_subscription_key": rec.get("subscription_key", "")}
        else:
            self._set_subscription(rec.get("subscription_key"), status="failed", message=rec.get("last_error") or "候选获取失败")
            return
        candidate["_subscription_key"] = rec.get("subscription_key", "")
        ok, _ = self.do_transfer(candidate, rec.get("target_type") or rec.get("type", "movie"))
        if not ok:
            return
        key = rec.get("subscription_key")
        if key:
            state = next((x for x in self._subscription_store().list() if x.get("key") == key), {})
            required = [x for x in state.get("required_resources", []) if x != rec["resource_key"]]
            required += self._last_transfer_result["required_resources"]
            self._set_subscription(key, status="pending", required_resources=list(dict.fromkeys(required)),
                target_quality_score=doc_parser.quality_score(candidate), fingerprint=self._fingerprint(candidate))
        self._update_live(rec["id"], generation, fallback_batch_keys=self._last_transfer_result["resource_keys"],
                          message="该来源明确失败，备用来源已排队")

    def _mark_resource_complete(self, key, resource_key):
        if not key or not resource_key:
            return
        acquired = self._records().find_by_resource(resource_key)
        if not acquired or acquired.get("acquisition_status") not in ("saved", "success"):
            return
        def change(items):
            item = next((x for x in items if x.get("key") == key), None)
            if item is None:
                item = {"key": key}
                items.append(item)
            completed = set(item.get("completed_resources") or [])
            completed.add(resource_key)
            needed = item.get("required_resources") or [resource_key]
            acquired_items = [self._records().find_by_resource(k) for k in needed]
            scores = [int(x.get("quality_score") or 0) for x in acquired_items if x and x.get("acquisition_status") in ("saved", "success")]
            score = min(scores) if scores else int(acquired.get("quality_score") or 0)
            item.update(completed_resources=sorted(completed), updated_at=time.time(),
                        target_quality_score=score,
                        actual_quality_score=score,
                        fingerprint=acquired.get("fingerprint"))
        self._subscription_store().transaction(change)

    def _offline_wait(self, rec, generation, *, progress=None):
        fast = int(rec.get("fast_checks") or 0)
        count = int(rec.get("wait_checks") or 0)
        now = time.time()
        next_at = max(now + 2, float(rec.get("submitted_ts") or now) + 15) if fast < 1 else now + self._delay(count)
        fields = {"next_check_at": next_at, "fast_checks": fast + 1, "wait_checks": count + (fast >= 1)}
        if progress is not None:
            fields["progress"] = progress
        self._update_live(rec["id"], generation, **fields)

    def _offline_step(self, rec, tr, generation):
        store = self._records()
        if self._confirm_move_from_evidence(rec, generation):
            return
        fid = str(rec.get("task_file_id") or "")
        # Registered file identity is checked before interpreting a vanished task.
        info = tr.get_file_info(fid) if fid else None
        final_cid = None
        if info:
            try:
                final_cid = tr.path_to_id(rec["final_path"], mkdir=False)
            except Exception as exc:
                from .p115_transfer import P115NotFound
                if not isinstance(exc, P115NotFound):
                    raise
        if info and str(info["parent_id"]) == str(final_cid):
            for attempt in store.attempts(rec["id"]):
                if attempt["phase"] == "move" and attempt["outcome"] in ("intent", "accepted", "uncertain"):
                    store.save_receipt(attempt["attempt_id"], "success", {"task_file_id": fid, "item_name": info["name"]}, self._generation)
            self._update_live(rec["id"], generation, status="done", acquisition_status="saved", move_status="success",
                              progress=100, moved_at=rec.get("moved_at") or time.time(), next_check_at=0,
                              item_name=info["name"], message="已在下载目录，MP整理待核实", org_next_ts=time.time() + 60)
            self._mark_resource_complete(rec.get("subscription_key"), rec["resource_key"])
            self._complete_subscription_if_ready(rec.get("subscription_key"))
            return
        if rec.get("status") in ("moving", "awaiting_move") and fid:
            staging_cid = tr.path_to_id(rec["staging_path"], mkdir=False)
            if info and str(info["parent_id"]) == str(staging_cid):
                self._move_step(rec, tr, generation, info)
                return
        try:
            result = tr.list_tasks_slice(cursor=rec.get("offline_cursor"))
        except Exception as exc:
            if getattr(exc, "state", None):
                self._update_live(rec["id"], generation, offline_cursor=exc.state)
            raise
        matcher = getattr(tr, "match_task", None)
        claimed = {str(x.get("task_file_id")) for x in self._records().list(limit=None, include_hidden=True)
                   if x.get("id") != rec["id"] and x.get("task_file_id")}
        task = next((x for x in result["items"]
                     if str(x.get("file_id") or x.get("fid") or "") not in claimed
                     and (matcher(x, rec.get("url") or "", rec.get("hash") or "") if callable(matcher)
                          else str(x.get("info_hash") or "").lower() == str(rec.get("hash") or "").lower())), None)
        if not task:
            self._update_live(rec["id"], generation, offline_cursor=result.get("cursor"))
            if not result["complete"]:
                self._update_live(rec["id"], generation, next_check_at=time.time() + 2)
                return
            self._offline_wait(rec, generation)
            self._update_live(rec["id"], generation, message="未看到对应离线任务，保留已有提交证据", offline_cursor=None)
            return
        if tr.task_failed(task):
            self._update_live(rec["id"], generation, acquisition_status="failed", status="failed", next_check_at=0,
                              message="115离线任务失败，请前往115处理")
            self._set_subscription(rec.get("subscription_key"), status="failed", message="115离线任务失败")
            return
        pct = max(0, min(100, int(float(task.get("percentDone") or task.get("percent_done") or 0))))
        fid = str(task.get("file_id") or task.get("fid") or fid)
        moving = rec.get("move_status") in ("moving", "uncertain")
        self._update_live(rec["id"], generation, task_file_id=fid, offline_cursor=None,
                          acquisition_status="moving" if moving else "downloading",
                          status="moving" if moving else "downloading", progress=pct, query_error="", query_errors=0)
        if pct < 100 or not fid:
            self._offline_wait(rec, generation, progress=pct)
            return
        info = tr.get_file_info(fid)
        if not info:
            self._offline_wait(rec, generation, progress=100)
            self._update_live(rec["id"], generation, message="115显示100%，等待文件落盘")
            return
        staging_cid = tr.path_to_id(rec["staging_path"], mkdir=False)
        if str(info["parent_id"]) != str(staging_cid):
            self._offline_wait(rec, generation, progress=100)
            self._update_live(rec["id"], generation, message="文件位置尚未确认，未搬运其它目录资源")
            return
        fresh = store.get(rec["id"])
        self._update_live(rec["id"], generation, status="awaiting_move", acquisition_status="awaiting_move",
                          item_name=info["name"], next_check_at=time.time() + 2)
        fresh.update(task_file_id=fid, item_name=info["name"])
        self._move_step(fresh, tr, generation, info)

    def _confirm_move_from_evidence(self, rec, generation):
        """A complete batch seen by MP proves it passed the final directory."""
        if rec.get("move_status") not in ("moving", "uncertain"):
            return False
        store = self._records()
        attempts = [x for x in store.attempts(rec["id"]) if x["phase"] == "move" and x["outcome"] in ("intent", "accepted", "uncertain")]
        if not attempts:
            return False
        complete_proof = rec.get("organization_status") == "success" and rec.get("manifest_complete")
        # A positive atomic root-move receipt plus an exact final-path MP proof
        # confirms the move, even if a different episode was deleted afterwards.
        accepted_proof = any(x["outcome"] == "accepted" for x in attempts) and (
            int(rec.get("organized_count") or 0) + int(rec.get("organized_failed") or 0) > 0)
        if not (complete_proof or accepted_proof):
            return False
        for attempt in attempts:
            store.save_receipt(attempt["attempt_id"], "success", {"task_file_id": rec.get("task_file_id") or ""}, self._generation)
        self._update_live(rec["id"], generation, acquisition_status="saved", status="done", move_status="success",
                          progress=100, next_check_at=0, org_next_ts=0, query_error="", last_error="",
                          message="已凭本批次搬运回执与MP下载目录证据确认搬运，整理按逐文件证据显示")
        self._mark_resource_complete(rec.get("subscription_key"), rec["resource_key"])
        self._complete_subscription_if_ready(rec.get("subscription_key"))
        return True

    def _move_step(self, rec, tr, generation, info):
        store, fid = self._records(), str(rec.get("task_file_id") or info["id"])
        name = str(info.get("name") or rec.get("item_name") or "")
        if not name or name in (".", "..") or "/" in name or "\\" in name:
            raise P115Error("文件身份或名称无效，未搬运")
        src = rec["staging_path"].rstrip("/") + "/" + name
        # Capture the batch before exposing it to MP's monitor; later deletion
        # cannot shrink this original list to whatever remains in the directory.
        if not rec.get("manifest_snapshot_ready"):
            try:
                result = tr.manifest_slice(src, cursor=rec.get("manifest_cursor"), file_id=fid)
            except Exception as exc:
                if getattr(exc, "state", None):
                    self._update_live(rec["id"], generation, manifest_cursor=exc.state)
                raise
            mapped = []
            for unit in result["items"]:
                if unit.get("is_dir"):
                    continue
                relative = str(PurePosixPath(unit["path"]).relative_to(src))
                suffix = "" if relative == "." else "/" + relative
                mapped.append({**unit, "source_path": rec["final_path"].rstrip("/") + "/" + name + suffix,
                    "file_id": str(unit.get("id") or unit.get("file_id") or ""), "storage": "115网盘Plus",
                    "episodes": [int(x[1]) if isinstance(x, (list, tuple)) else int(x) for x in unit.get("episodes", [])]})
            # 方案 A：源清单枚举完整即视为「本批完整」，与 115 分享路径一致；
            # 不再要求文档声明集数（expected_episodes 目前没有任何代码产出，旧逻辑会让整季包永远判不了成功）。
            known = True
            mapped = classify_optional_media(mapped, rec.get("min_media_size_mb", 0))
            store.append_manifest(rec["id"], mapped, complete=result["complete"] and known,
                                  reason=result.get("error") or ("离线原始必要清单未获证实" if not known else ""))
            self._refresh_event_paths()
            unsupported = bool(result.get("error")) and any(x in result["error"] for x in ("需进一步识别", "超过本批次扫描上限"))
            self._update_live(rec["id"], generation, manifest_cursor=result.get("cursor"),
                              manifest_snapshot_ready=result["complete"] or unsupported, next_check_at=time.time() + (900 if result.get("error") else 2))
            if not result["complete"] and not unsupported:
                return
        if rec.get("move_status") in ("uncertain", "moving"):
            self._offline_wait(rec, generation)
            self._update_live(rec["id"], generation, message="搬运回执待核实，未重复发送")
            return
        attempt = store.begin_attempt(rec["id"], phase="move", generation=generation, intent={"file_id": fid, "src": src, "dest": rec["final_path"]})
        try:
            ok, error = tr.move_via_p115disk(src, rec["final_path"], file_id=fid)
            if not ok:
                store.save_receipt(attempt["attempt_id"], "uncertain", {"message": error}, self._generation)
                self._update_live(rec["id"], generation, status="moving", next_check_at=time.time() + 30, message="搬运结果待核实：" + str(error))
                return
            store.save_receipt(attempt["attempt_id"], "accepted", {"task_file_id": fid, "item_name": name}, self._generation)
            self._update_live(rec["id"], generation, status="moving", acquisition_status="moving", next_check_at=time.time() + 2,
                              message="已提交整包搬运，等待确认目录")
            # The next stage verifies file ID/parent; no second write.
        except Exception as exc:
            not_sent = bool(getattr(exc, "not_sent", False))
            store.save_receipt(attempt["attempt_id"], "failure" if not_sent else "uncertain", {"message": self._error(exc)}, self._generation)
            if not_sent:
                self._defer_task(rec, generation, exc)
            else:
                self._update_live(rec["id"], generation, status="moving", next_check_at=time.time() + 30, message="搬运结果待核实")

    def _note_offline_tick(self, state, **extra):
        self._last_offline_tick = {"at": time.time(), "state": state, **extra}

    def check_offline_tasks(self, force=False):
        self._ensure_runtime()
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        if not self._offline_lock.acquire(blocking=False):
            return {"code": 0, "data": {"skipped": True}}
        generation, rec = self._generation, None
        try:
            store, now = self._records(), time.time()
            self._maintain_ledger(now)
            if self._run_requested_job(generation):
                self._note_offline_tick("ok", background_job=True)
                return {"code": 0, "data": {"background_job": True}}
            due = store.due_acquisitions(now, limit=1)
            if not due["rows"]:
                return {"code": 0, "data": {"pending": 0, "skipped": True}}
            rec, pending = due["rows"][0], due["count"]
            if rec.get("account_key") and rec["account_key"] != self._account_key():
                store.update(rec["id"], tracking_enabled=False, query_error="该任务属于其它115账号，未使用新账号处理",
                             message="账号变化，原任务已暂停", next_check_at=0)
                return {"code": 0, "data": {"paused": 1, "reason": "account_changed"}}
            if rec.get("config_generation") != generation:
                store.update(rec["id"], config_generation=generation)
                rec = store.get(rec["id"])
            if rec.get("status") == "submitting" and any(x["outcome"] in ("intent", "uncertain") for x in store.attempts(rec["id"])):
                # Restart after an unresolved intent must reconcile, never resend.
                store.update(rec["id"], status="unverified", acquisition_status="uncertain")
                rec = store.get(rec["id"])
            reconcile = bool(rec.get("reconcile_requested"))
            if rec["kind"] == LINK_115_SHARE and rec.get("acquisition_status") == "uncertain" and not reconcile:
                self._update_live(rec["id"], generation, next_check_at=now + 900, message="分享提交结果待核实，自动重发已暂停")
                return {"code": 0, "data": {"pending": pending, "paused": 1}}
            tr = self._transfers()
            context = tr.work_slice(cancelled=lambda: not self._live(generation, rec["id"])) if hasattr(tr, "work_slice") else nullcontext()
            with context:
                if not self._live(generation, rec["id"]):
                    return {"code": 0, "data": {"skipped": True}}
                if reconcile and rec["kind"] == LINK_115_SHARE:
                    self._reconcile_step(rec, tr, generation)
                elif rec.get("acquisition_status") == "queued":
                    self._submit_step(rec, tr, generation)
                else:
                    if reconcile:
                        self._update_live(rec["id"], generation, reconcile_requested=False)
                    self._offline_step(rec, tr, generation)
            self._note_offline_tick("ok", processed=rec["id"], pending=pending)
            return {"code": 0, "data": {"pending": pending, "processed": 1}}
        except Exception as exc:
            if rec:
                try:
                    self._defer_task(rec, generation, exc)
                except Exception:  # noqa: BLE001
                    pass
            self._note_offline_tick("error", error=self._error(exc)[:300], record_id=(rec or {}).get("id", ""))
            # 每 2 秒一次的 worker：异常 5 分钟最多记一次 warning（含堆栈），其余降为 debug，避免刷屏也不再静默。
            if time.time() - float(getattr(self, "_last_offline_error_log", 0) or 0) > 300:
                self._last_offline_error_log = time.time()
                logger.warning("115文档订阅与查询：离线/转存后台任务失败：" + self._error(exc)
                               + "\n" + traceback.format_exc())
            else:
                logger.debug("115文档订阅与查询：离线/转存后台任务失败：" + self._error(exc))
            return {"code": 1, "msg": self._error(exc)}
        finally:
            self._offline_lock.release()

    LEDGER_MAINTENANCE_INTERVAL = 6 * 3600

    def _maintain_ledger(self, now=None, force=False):
        """启动时与每 6 小时一次的本地账本清理（坏事件 ack、旧 inbox、证据上限）；失败只记日志。"""
        now = time.time() if now is None else now
        if not force and now < float(getattr(self, "_ledger_maintenance_next", 0) or 0):
            return None
        self._ledger_maintenance_next = now + self.LEDGER_MAINTENANCE_INTERVAL
        try:
            result = self._records().maintenance()
        except Exception as exc:  # noqa: BLE001
            logger.warning("115文档订阅与查询：本地账本清理失败：" + self._error(exc))
            return None
        self._last_maintenance = {"at": now, **result}
        if result.get("legacy_events_acked"):
            logger.info(f"115文档订阅与查询：已清理 {result['legacy_events_acked']} 条旧版本写入的无效整理事件")
        return result

    TERMINAL_ACQUISITION = ("saved", "success", "failed")

    @classmethod
    def _is_tracking(cls, item):
        """仍在后台处理：自动跟踪开启且获取未终结（saved/success/failed 以外）。"""
        return bool(item.get("tracking_enabled", True)) and item.get("acquisition_status") not in cls.TERMINAL_ACQUISITION

    def _record_view(self, item):
        item = {k: v for k, v in item.items() if k not in ("url", "source_manifest", "share_state", "actual_candidate", "fallback_links", "account_key")}
        acquisition = item.get("acquisition_status", "unknown")
        actions = ["verify"] if acquisition in ("saved", "success") else []
        if item.get("tracking_enabled", True) and acquisition not in ("saved", "success", "failed"):
            actions += (["check_download"] if item.get("hash") else []) + ["stop_tracking"]
        if item.get("move_status") == "failed":
            actions.append("retry_move")
        if acquisition == "failed" and not item.get("hash"):
            actions.append("retry_submit")
        if acquisition == "failed" and item.get("hash"):
            actions.append("check_download")
        if acquisition == "uncertain" or item.get("status") == "unverified":
            # 分享提交结果不明时自动重发已暂停；给出两条出路：只读核对 / 用户人工确认已转存
            actions.append("reconcile")
            if item.get("kind") == LINK_115_SHARE:
                # 磁力/ed2k 的文件可能仍在暂存目录，人工确认会跳过搬运，因此只对分享开放
                actions.append("confirm_saved")
        # 「确认已整理」：已转存且整理状态为 unfound（MP 历史记录查不到）时显示，供用户人工标记已整理
        if acquisition in ("saved", "success") and item.get("organization_status") == "unfound":
            actions.append("confirm_organized")
        item["allowed_actions"] = list(dict.fromkeys(actions))
        item["hidden"] = bool(item.get("hidden"))
        item["tracking"] = self._is_tracking(item)
        if acquisition in ("saved", "success"):
            item["next_check_at"] = item.get("org_next_ts") or 0
        if not item.get("tracking_enabled", True):
            item["pause_reason"] = item.get("last_error") or item.get("message") or "自动跟踪已暂停"
        item["organization"] = {"confirmed": item.get("organized_count", 0), "expected": item.get("organized_total"),
            "failed": item.get("organized_failed", 0), "missing": item.get("organized_missing", 0),
            "manifest_complete": bool(item.get("manifest_complete"))}
        evidence = {}
        for entry in item.get("organization_evidence") or []:
            for unit_key in entry.get("unit_keys") or []:
                evidence[unit_key] = entry
        files = []
        for unit in item.get("manifest") or []:
            if not unit.get("required"):
                continue
            proof = evidence.get(unit.get("unit_key"))
            state = "success" if proof and proof.get("status") is True else "failed" if proof and proof.get("status") is False else "unverified"
            files.append({"id": unit.get("unit_key"), "name": unit.get("name") or PurePosixPath(unit.get("source_path") or "").name,
                          "path": unit.get("source_path"), "status": state,
                          "message": "MP整理成功" if state == "success" else str(proof.get("errmsg") or "MP整理失败") if state == "failed" else "尚无本批次整理证据"})
        item["files"] = files
        item["ignored_files"] = [{"name": u.get("name") or PurePosixPath(u.get("source_path") or "").name,
                                  "reason": u["ignored_reason"], "size": u.get("size")}
                                 for u in item.get("manifest") or [] if u.get("ignored_reason") and not u.get("required")]
        return item

    @classmethod
    def _needs_attention(cls, x):
        return bool(x.get("query_error") or x.get("organization_status") in ("partial", "failed", "paused", "unfound")
                    or x.get("acquisition_status") in ("uncertain", "failed")
                    or (x.get("acquisition_status") in ("saved", "success") and x.get("org_giveup")
                        and x.get("organization_status") != "success"))

    @classmethod
    def _is_active(cls, x):
        return bool(x.get("tracking_enabled", True) and
                    (x.get("acquisition_status") in ("queued", "submitting", "uncertain", "downloading", "awaiting_move", "moving")
                     or x.get("acquisition_status") in ("saved", "success") and x.get("organization_status") not in ("success", "paused", "failed")
                     and not x.get("org_giveup")))

    @staticmethod
    def _title_query(value):
        return re.sub(r"\s+", "", str(value or "")).casefold()

    def api_records(self, limit: int = 200, page: int = 1, page_size: int = 20, filter: str = "all",
                    q: str = "", media: str = "all"):
        # limit 仅为兼容旧前端签名保留，不再使用；分页由 page/page_size 决定。
        try:
            if filter not in ("all", "active", "needs_attention", "completed", "hidden"):
                raise ValueError("无效的任务筛选")
            if media not in ("all", "movie", "tv"):
                raise ValueError("无效的类型筛选")
            everything = self._records().list(limit=None, include_hidden=True)
            visible = [x for x in everything if not x.get("hidden")]
            rows = [x for x in everything if x.get("hidden")] if filter == "hidden" else visible
            if filter == "active":
                rows = [x for x in rows if self._is_active(x)]
            elif filter == "needs_attention":
                rows = [x for x in rows if self._needs_attention(x)]
            elif filter == "completed":
                rows = [x for x in rows if x.get("organization_status") == "success"]
            if media != "all":
                rows = [x for x in rows if self._media_bucket(x) == media]
            needle = self._title_query(q)
            if needle:
                rows = [x for x in rows if needle in self._title_query(x.get("title"))]
            size = max(1, min(100, int(page_size)))
            pages = max(1, (len(rows) + size - 1) // size)
            page = min(max(1, int(page)), pages)
            return {"code": 0, "data": {"records": [self._record_view(x) for x in rows[(page - 1)*size:page*size]],
                "total": len(rows), "page": page, "page_size": size, "stats": self._record_stats(visible)}}
        except Exception as exc:
            return {"code": 1, "msg": self._error(exc)}

    @staticmethod
    def _media_bucket(row):
        kind = str(row.get("type") or row.get("target_type") or row.get("media_type") or "").strip().lower()
        return "tv" if kind in ("tv", "电视剧", "剧集") else "movie" if kind in ("movie", "电影") else ""

    @classmethod
    def _record_stats(cls, rows) -> Dict[str, Any]:
        """全部未隐藏记录的统计（不受筛选影响）：电影/电视剧任务数与已整理入库数、进行中与需处理数。"""
        stats = {"movie": {"total": 0, "organized": 0}, "tv": {"total": 0, "organized": 0},
                 "total": 0, "organized": 0, "active": 0, "attention": 0}
        for row in rows:
            if row.get("hidden"):
                continue
            bucket = cls._media_bucket(row)
            organized = str(row.get("organization_status") or "") == "success"
            stats["total"] += 1
            stats["organized"] += organized
            stats["active"] += cls._is_active(row)
            stats["attention"] += cls._needs_attention(row)
            if bucket:
                stats[bucket]["total"] += 1
                stats[bucket]["organized"] += organized
        return stats

    def records_stats(self):
        return self._record_stats(self._records().list(limit=None))

    TRACKING_DELETE_MSG = "任务仍在后台处理，请先停止自动跟踪再删除"

    def delete_record(self, rec_id=""):
        store = self._records()
        if rec_id:
            rec = store.get(rec_id)
            if not rec:
                return {"code": 1, "msg": "任务不存在"}
            if self._is_tracking(rec):
                return {"code": 1, "msg": self.TRACKING_DELETE_MSG}
            return {"code": 0, "data": {"deleted": int(store.delete(rec_id))},
                    "msg": "已隐藏展示记录，获取证据保留"}
        hidden = skipped = 0
        for rec in store.list(limit=None):
            if self._is_tracking(rec):
                skipped += 1
            elif store.delete(rec["id"]):
                hidden += 1
        return {"code": 0, "data": {"hidden": hidden, "skipped": skipped},
                "msg": f"已隐藏 {hidden} 条" + (f"，{skipped} 条仍在后台处理未隐藏" if skipped else "") + "；获取证据保留"}

    def api_records_delete(self, payload: dict = None):
        return self.delete_record(str((payload or {}).get("id") or ""))

    def api_records_bulk(self, payload: dict = None):
        body = payload or {}
        ids, action = body.get("ids"), str(body.get("action") or "")
        if not isinstance(ids, list) or not ids or len(ids) > 500:
            return {"code": 1, "msg": "请选择 1 到 500 条记录"}
        if action not in ("verify", "hide", "unhide", "stop_tracking"):
            return {"code": 1, "msg": "不支持的批量操作"}
        store, done, skipped = self._records(), 0, 0
        for rid in dict.fromkeys(str(x) for x in ids if x):
            rec = store.get(rid)
            if not rec:
                skipped += 1
                continue
            if action == "hide":
                ok = not self._is_tracking(rec) and not rec.get("hidden") and store.delete(rid)
            elif action == "unhide":
                ok = bool(rec.get("hidden")) and store.update(rid, hidden=False)
            elif action == "stop_tracking":
                ok = bool(rec.get("tracking_enabled", True)) and self._stop_tracking(rec)
            else:
                ok = rec.get("acquisition_status") in ("saved", "success") and \
                    self.api_records_verify({"id": rid})["data"]["queued"] > 0
            done += bool(ok)
            skipped += not ok
        names = {"verify": "已排队核对", "hide": "已隐藏", "unhide": "已恢复显示", "stop_tracking": "已停止跟踪"}
        return {"code": 0, "data": {"done": done, "skipped": skipped},
                "msg": f"{names[action]} {done} 条" + (f"，跳过 {skipped} 条" if skipped else "")}

    def _stop_tracking(self, rec):
        ok = self._records().stop_tracking(rec["id"])
        self._set_subscription(rec.get("subscription_key"), status="cancelled")
        return ok

    def api_cancel_task(self, payload: dict = None):
        rid = str((payload or {}).get("id") or "")
        rec = self._records().get(rid)
        if not rec:
            return {"code": 1, "msg": "任务不存在"}
        self._stop_tracking(rec)
        return {"code": 0, "msg": "已停止跟踪，115下载与文件保留"}

    def api_retry_task(self, payload: dict = None):
        rid = str((payload or {}).get("id") or "")
        rec = self._records().get(rid)
        if not rec:
            return {"code": 1, "msg": "任务不存在"}
        if (payload or {}).get("action") == "retry_submit":
            attempts = self._records().attempts(rid)
            if rec.get("acquisition_status") != "failed" or any(x["outcome"] in ("intent", "uncertain", "accepted", "success") for x in attempts):
                return {"code": 1, "msg": "已有成功或未确认提交，不能重新获取"}
            self._records().update(rid, tracking_enabled=True, acquisition_status="queued", status="queued",
                next_check_at=time.time(), config_generation=self._generation, query_error="", last_error="")
            return {"code": 0, "msg": "已排队重试明确失败的获取", "data": {"state": "queued"}}
        # Retry means reconcile/move only. It is never a second acquire request.
        if rec.get("acquisition_status") in ("saved", "success"):
            return self.api_records_verify({"id": rid})
        if not rec.get("hash"):
            return {"code": 1, "msg": "原提交需要核实，未再次转存"}
        self._records().update(rid, tracking_enabled=True, config_generation=self._generation,
            acquisition_status="downloading" if rec.get("acquisition_status") == "failed" else rec.get("acquisition_status"),
            status="downloading" if rec.get("acquisition_status") == "failed" else rec.get("status"),
            # 用户手动点「重查下载状态」：立即排队（仍受 115 请求额度约束），不再沿用自动退避的下次时间
            next_check_at=time.time() if (payload or {}).get("action") == "check_download" else max(time.time(), float(rec.get("next_check_at") or 0)),
            message="已恢复原任务核对，未重新下载")
        self._set_subscription(rec.get("subscription_key"), status="pending")
        return {"code": 0, "msg": "已排队核对原任务，遵守冷却和请求额度"}

    def api_task_action(self, payload: dict = None):
        body = payload or {}
        rec = self._records().get(str(body.get("id") or ""))
        action = str(body.get("action") or "")
        if not rec or action not in self._record_view(rec)["allowed_actions"]:
            return {"code": 1, "msg": "该任务当前不允许此操作，请刷新状态"}
        if action == "verify":
            return self.api_records_verify({"id": rec["id"]})
        if action == "stop_tracking":
            return self.api_cancel_task({"id": rec["id"]})
        if action in ("retry_move", "retry_submit", "check_download"):
            return self.api_retry_task({"id": rec["id"], "action": action})
        if action == "reconcile":
            return self._request_reconcile(rec)
        if action == "confirm_saved":
            return self._confirm_saved(rec)
        if action == "confirm_organized":
            return self._confirm_organized(rec)
        return {"code": 1, "msg": "不支持的任务操作"}

    def _request_reconcile(self, rec):
        """只读核对：排队一次后台检查（不重发提交）。后台由 _reconcile_step 执行。"""
        self._records().update(rec["id"], tracking_enabled=True, config_generation=self._generation,
                               reconcile_requested=True, next_check_at=time.time(), query_error="",
                               message="已排队只读核对：检查目标目录中是否已有本批条目，不会重新转存")
        return {"code": 0, "msg": "已排队只读核对，不会重新转存", "data": {"state": "queued"}}

    def _confirm_saved(self, rec):
        """用户在 115 原生界面确认已转存：置为 saved，进入整理核对；不发送任何云端请求。"""
        now = time.time()
        self._records().update(rec["id"], tracking_enabled=True, acquisition_status="saved", status="done",
                               progress=100, moved_at=rec.get("moved_at") or now, next_check_at=0,
                               reconcile_requested=False, manual_confirmed_at=now, query_error="", last_error="",
                               org_next_ts=now, org_requested=True, org_request_ts=now, org_giveup=False, org_page=1,
                               org_attempts=0, org_stale_count=0, message="已人工确认转存，等待MP整理核对")
        self._mark_resource_complete(rec.get("subscription_key"), rec.get("resource_key"))
        self._complete_subscription_if_ready(rec.get("subscription_key"))
        self._refresh_event_paths(force=True)
        return {"code": 0, "msg": "已标记为已转存，进入整理核对", "data": {"state": "saved"}}

    def _confirm_organized(self, rec):
        """用户人工确认已整理：直接标记为整理成功，不查询 MP；用于 MP 历史记录查不到但用户已确认入库的批次。"""
        store = self._records()
        batch = store.get(rec["id"])
        if not batch:
            return {"code": 1, "msg": "任务不存在"}
        manifest = batch.get("manifest") or []
        required = [u for u in manifest if u.get("required")]
        if not required and not batch.get("manifest_complete"):
            return {"code": 1, "msg": "该任务没有文件清单或清单不完整，无法标记为已整理"}
        now = time.time()
        store.update(rec["id"], tracking_enabled=True, organization_status="success",
                     organized_count=len(required) or 1, organized_total=len(required) or 1,
                     manifest_complete=True, organization_confirmed=True, org_giveup=False, org_requested=False,
                     org_last_check=now, query_error="", message="已人工确认整理成功")
        self._mark_resource_complete(rec.get("subscription_key"), rec.get("resource_key"))
        self._complete_subscription_if_ready(rec.get("subscription_key"))
        return {"code": 0, "msg": "已标记为整理成功", "data": {"state": "success"}}

    def _reconcile_step(self, rec, tr, generation):
        """只读核对 uncertain/unverified 分享批次：列 final_path 目录，看清单条目名是否都在。

        只调用 p115_transfer 现成的只读接口 list_names（内部 path_to_id(mkdir=False) + 分页列目录），
        从不提交/重发。找到全部顶层条目 → 判已转存（saved）；否则保持待核实并说明，交由用户人工处理。
        若传输客户端没有 list_names（兼容旧版本），只标记 org_requested，交给整理核对用 MP 整理记录判定。
        """
        now = time.time()
        expected = [x.get("name") for x in (rec.get("share_state") or {}).get("items", []) if x.get("name")]
        if not expected:
            expected = sorted({str(u.get("relative_path") or "").split("/")[0]
                               for u in rec.get("source_manifest") or [] if u.get("relative_path")} - {""})
        if not hasattr(tr, "list_names") or not expected:
            self._update_live(rec["id"], generation, reconcile_requested=False, org_requested=True,
                              org_request_ts=now, org_next_ts=now, next_check_at=now + 900,
                              message="无法只读列目录，已交由整理核对按 MP 整理记录判定")
            return
        try:
            names = set(tr.list_names(rec["final_path"]))
        except Exception as exc:
            from .p115_transfer import P115NotFound
            if not isinstance(exc, P115NotFound):
                raise
            names = set()
        missing = [n for n in expected if n not in names]
        if not missing:
            self._update_live(rec["id"], generation, acquisition_status="saved", status="done", progress=100,
                              item_names=expected, moved_at=rec.get("moved_at") or now, next_check_at=0,
                              reconcile_requested=False, query_error="", last_error="",
                              org_next_ts=now + 60, message="只读核对：目标目录已有本批全部条目，MP整理待核实")
            self._mark_resource_complete(rec.get("subscription_key"), rec["resource_key"])
            self._complete_subscription_if_ready(rec.get("subscription_key"))
            self._refresh_event_paths(force=True)
        else:
            self._update_live(rec["id"], generation, reconcile_requested=False, next_check_at=now + 900,
                              message=f"只读核对：目标目录缺少 {len(missing)}/{len(expected)} 个条目，未重新转存；"
                                      "请到 115 核实后选择「确认已转存」或停止跟踪")

    def _mp(self):
        if getattr(self, "_mp_instance", None) is None:
            from app.core.config import settings
            self._mp_instance = MPAdapter(settings)
        return self._mp_instance

    def _mp_api_json(self, path, params):
        return self._mp().get(path, params)

    @staticmethod
    def _org_search_key(title):
        """MP 整理记录的模糊查询词：先去掉括号标签（[] 【】 （） ()），再截到季号/年份前，再截到第一个英文句点前（避免 MP 模糊搜索匹配失败）。

        只用于发现候选，身份由 match_history 全量比较；为空时调用方跳过查询（绝不用 "**" 全量扫描）。
        """
        raw = re.sub(r"[\[【（(][^\]】）)]*[\]】）)]", " ", str(title or ""))
        raw = re.split(r"第[零一二三四五六七八九十两\d]+季|(?<![a-z0-9])s\d{1,2}(?!\d)|\bseason\s*\d+|[\[【（(]",
                       raw, maxsplit=1, flags=re.I)[0]
        # MP 的模糊搜索（title=*kw*）遇到 . 匹配失败，截到第一个 . 前（通常是中英文分隔点）
        raw = re.split(r"\.", raw, maxsplit=1)[0]
        return re.sub(r"\s+", " ", raw).strip(" .-·:：_")[:24].strip()

    @staticmethod
    def _org_due(rec, now):
        return now >= float(rec.get("org_next_ts") or 0)

    ORG_STALE_ATTEMPTS = 6         # partial / failed 连续 6 次完整核对结果都没变化 → 停止自动核对（保留手动核对）
    ORG_FINAL_STATES = ("success", "partial", "failed")

    def _log_org_change(self, before_rec, before_status, batch):
        """仅在整理结论变化时打印「整理成功/部分/失败」，返回是否变化。"""
        status = (batch or {}).get("organization_status")
        if status == before_status or status not in self.ORG_FINAL_STATES:
            return False
        title = core_title((batch or {}).get("title") or before_rec.get("title"))
        total = batch.get("organized_total") or batch.get("organized_count") or 0
        if status == "success":
            logger.info(f"115文档订阅与查询：整理成功：{title}｜已入库 {batch.get('organized_count')}/{total} 个")
        elif status == "partial":
            logger.info(f"115文档订阅与查询：整理部分成功：{title}｜已入库 {batch.get('organized_count')}"
                        + (f"/{batch.get('organized_total')}" if batch.get("organized_total") else "") + " 个")
        else:
            logger.info(f"115文档订阅与查询：整理失败：{title}｜失败 {batch.get('organized_failed')} 个")
        return True

    def verify_organization(self, force=False, record_id=""):
        store, now, generation = self._records(), time.time(), self._generation
        rows = store.due_organization(now, record_id=record_id)
        counts = {"checked": 0, "confirmed": 0, "partial": 0, "failed": 0, "unfound": 0, "changed": 0}
        cache = {}
        for rec in rows[:self.ORG_MAX_PER_RUN]:
            if not self._live(generation, rec["id"]):
                break
            key = (self._org_search_key(rec.get("title")), int(rec.get("org_page") or 1))
            before = rec.get("organization_status")
            try:
                if key not in cache:
                    if not key[0]:
                        cache[key] = ([], 0)          # 标题只剩标签：不查询，按「无证据」走退避/放弃
                    else:
                        try:
                            body = self._mp_api_json("/api/v1/history/transfer", {"title": "*" + key[0] + "*", "page": key[1], "count": 100})
                            cache[key] = self._mp().page(body)
                        except Exception as exc:
                            cache[key] = exc
                if isinstance(cache[key], Exception):
                    raise cache[key]
                entries, total = cache[key]
                complete = key[1] * 100 >= total if total is not None else len(entries) < 100
                if not (rec.get("manifest") or []):
                    # 旧版本（0.9.x）记录没有"本批文件清单"，无法做逐文件映射：
                    # 退回「标题/类型/季号」身份匹配，只认成功证据，且明确告知依据（不虚报整批完整）。
                    counts["checked"] += 1
                    legacy_ok = [e for e in entries if e.get("status") is True and legacy_identity(rec, e)]
                    if legacy_ok:
                        counts["confirmed"] += 1
                        if before != "success":
                            counts["changed"] += 1
                            logger.info(f"115文档订阅与查询：旧记录按标题匹配判成功：{core_title(rec.get('title'))}"
                                        f"｜{len(legacy_ok)} 个文件")
                        self._update_live(rec["id"], generation, _snapshot_ts=now, org_attempts=0, org_last_check=now,
                            org_error_count=0, query_error="", org_giveup=False, org_requested=False,
                            org_next_ts=0, org_page=1, organization_status="success", organization_confirmed=True,
                            organized_count=len(legacy_ok), organized_failed=0,
                            message=f"整理成功：依据 MoviePilot 整理记录按标题/季号核对到 {len(legacy_ok)} 个已整理文件"
                                    f"（该记录由旧版本写入，没有本批文件清单）")
                    elif not complete:
                        # 旧记录也逐页查完再下结论，翻页期间不计等待次数
                        self._update_live(rec["id"], generation, _snapshot_ts=now, org_page=key[1] + 1,
                                          org_next_ts=now + 2, org_last_check=now, org_error_count=0, query_error="")
                    else:
                        waits = int(rec.get("org_attempts") or 0) + 1
                        giveup = waits >= self.ORG_GIVEUP_ATTEMPTS
                        if giveup:
                            counts["unfound"] += 1
                            counts["changed"] += 1
                        fields = dict(org_attempts=waits, org_last_check=now, org_error_count=0, query_error="",
                                      org_giveup=giveup, org_requested=False, org_page=1,
                                      org_next_ts=0 if giveup else now + self._delay(waits,
                                          base=self.ORG_BACKOFF_BASE, cap=self.ORG_BACKOFF_MAX),
                                      organization_status="unfound" if giveup else "unknown")
                        if giveup:
                            fields["message"] = ("未找到整理证据（旧版本记录没有本批文件清单，只能按标题/季号核对），"
                                                 "已停止自动核对")
                            logger.info(f"115文档订阅与查询：旧记录未匹配到整理证据，停止自动核对："
                                        f"{core_title(rec.get('title'))}")
                        self._update_live(rec["id"], generation, _snapshot_ts=now, **fields)
                    continue
                batch = store.record_evidence(rec["id"], entries, pagination_complete=complete)
                self._confirm_move_from_evidence(batch, generation)
                counts["checked"] += 1
                status = batch.get("organization_status")
                counts[{"success": "confirmed", "partial": "partial", "failed": "failed"}.get(status, "unfound")] += 1
                if self._log_org_change(rec, before, batch):
                    counts["changed"] += 1
                if status == "success":
                    # 已逐文件证实：不再翻后续分页，页码复位，结束本次（含手动）核对
                    total = batch.get("organized_total") or batch.get("organized_count") or 0
                    self._update_live(rec["id"], generation, _snapshot_ts=now, org_page=1, org_next_ts=0,
                        org_attempts=0, org_stale_count=0, org_last_check=now, org_error_count=0, query_error="",
                        org_giveup=False, org_requested=False, organization_status="success",
                        message=f"整理成功：本批 {batch.get('organized_count')}/{total} 个文件已入库")
                    continue
                if not complete:
                    # 翻页中：结论未定，不计等待/停滞次数
                    self._update_live(rec["id"], generation, _snapshot_ts=now, org_page=key[1] + 1, org_next_ts=now + 2,
                                      org_last_check=now, org_error_count=0, query_error="", organization_status=status)
                    continue
                waits = int(rec.get("org_attempts") or 0) + 1
                signature = [status, batch.get("organized_count"), batch.get("organized_failed"), batch.get("organized_missing")]
                stale = int(rec.get("org_stale_count") or 0) + 1 if signature == rec.get("org_signature") else 0
                # 连续 ORG_GIVEUP_ATTEMPTS 次仍然「一点证据都没有」→ 判未找到并移出自动核对池
                giveup_unknown = status == "unknown" and waits >= self.ORG_GIVEUP_ATTEMPTS
                # partial / failed 长期无变化 → 停止自动核对，等用户手动核对
                giveup_stale = status in ("partial", "failed") and stale + 1 >= self.ORG_STALE_ATTEMPTS
                giveup = giveup_unknown or giveup_stale
                fields = dict(org_page=1, org_next_ts=0 if giveup else now + self._delay(
                                  waits, base=self.ORG_BACKOFF_BASE, cap=self.ORG_BACKOFF_MAX),
                              org_attempts=waits, org_stale_count=stale, org_signature=signature,
                              org_last_check=now, org_error_count=0, query_error="",
                              org_giveup=giveup, org_requested=False,
                              organization_status="unfound" if giveup_unknown else status)
                if giveup_unknown:
                    counts["changed"] += 1
                    fields["message"] = ("未找到本批次的整理证据（可能已手动删除或尚未整理），已停止自动核对；"
                                         "可点该任务的「核对」重新检查")
                    logger.info(f"115文档订阅与查询：连续 {waits} 次无整理证据，停止自动核对：{core_title(rec.get('title'))}")
                elif status == "partial":
                    fields["message"] = (f"部分成功：已入库 {batch.get('organized_count')} 个"
                                          + (f"（共 {batch.get('organized_total')} 个）" if batch.get("organized_total") else ""))
                elif status == "failed":
                    fields["message"] = f"整理失败：{batch.get('organized_failed')} 个文件 MP 整理失败"
                if giveup_stale:
                    fields["message"] += f"；连续 {stale + 1} 次核对无变化，已停止自动核对，可手动「核对」"
                    logger.info(f"115文档订阅与查询：整理结果连续 {stale + 1} 次无变化，停止自动核对："
                                f"{core_title(rec.get('title'))}")
                self._update_live(rec["id"], generation, _snapshot_ts=now, **fields)
            except Exception as exc:
                errors = int(rec.get("org_error_count") or 0)
                self._update_live(rec["id"], generation, org_error_count=errors + 1,
                    org_next_ts=max(now + self._delay(errors, base=30, cap=900), float(getattr(exc, "retry_at", 0) or 0)),
                    query_error=self._error(exc), org_last_check=now)
                if isinstance(exc, MPDeferred):
                    break
        return counts

    def check_organization(self):
        """每 20 秒的整理核对（后台任务）。

        0.10.1 起：任何失败都会留痕（含堆栈，5 分钟最多记一次）并把最近一次执行结果写进 diagnostics，
        不再像 0.10.0 那样静默 return——静默会让"任务其实没在跑"这件事完全无法被发现。
        """
        self._ensure_runtime()
        if not self._enabled:
            self._last_org_tick = {"at": time.time(), "state": "disabled"}
            return {"code": 1, "msg": "插件未启用"}
        if not self._org_lock.acquire(blocking=False):
            self._last_org_tick = {"at": time.time(), "state": "busy"}
            return {"code": 0, "data": {"skipped": True}}
        generation = self._generation
        try:
            try:                                # 账本变化时才真正重建；失败不影响本轮核对
                self._refresh_event_paths()
            except Exception as exc:  # noqa: BLE001
                logger.debug("115文档订阅与查询：事件路径缓存刷新失败：" + self._error(exc))
            events = self._drain_events()
            with self._mp().work_slice(cancelled=lambda: not self._live(generation)):
                result = self.verify_organization()
                if not result["checked"] and getattr(self, "_directories_requested", False):
                    self._refresh_directories_snapshot(generation)
                self._last_org_tick = {"at": time.time(), "state": "ok", "checked": result.get("checked"),
                                       "confirmed": result.get("confirmed"), "changed": result.get("changed"), "events": events}
                if result.get("checked"):
                    # 只有整理结论有变化时才 info；否则（例如翻页、无变化的复查）降为 debug，避免每页刷屏
                    log = logger.info if result.get("changed") else logger.debug
                    log(f"115文档订阅与查询：整理核对完成：检查 {result.get('checked')} 条，"
                        f"成功 {result.get('confirmed')}，部分 {result.get('partial')}，"
                        f"失败 {result.get('failed')}，未找到 {result.get('unfound')}")
                return {"code": 0, "data": result}
        except Exception as exc:
            self._last_org_tick = {"at": time.time(), "state": "error", "error": self._error(exc)[:300]}
            if time.time() - float(getattr(self, "_last_org_error_log", 0) or 0) > 300:
                self._last_org_error_log = time.time()
                logger.warning("115文档订阅与查询：整理核对执行失败：" + self._error(exc)
                               + "\n" + traceback.format_exc())
            return {"code": 1, "msg": self._error(exc)}
        finally:
            self._org_lock.release()

    def api_records_verify(self, payload: dict = None):
        """手动核对整理证据（不重新获取）。

        带 id：只重开这一条（含已成功/已放弃）；不带 id：只重开「未成功、需要处理」的记录，
        已整理成功的不动，也不批量清空所有放弃标记以外的东西。
        """
        rid = str((payload or {}).get("id") or "")
        store = self._records()
        rows = [store.get(rid)] if rid else store.list(limit=None)
        queued, now = 0, time.time()
        for rec in rows:
            if not rec or rec.get("acquisition_status") not in ("saved", "success"):
                continue
            if not rid and rec.get("organization_status") == "success":
                continue
            # Reopen a completed/giveup projection, but don't bypass error cooldown.
            next_at = max(now, float(rec.get("org_next_ts") or 0)) if rec.get("query_error") else now
            store.update(rec["id"], tracking_enabled=True, org_giveup=False, org_next_ts=next_at, org_requested=True,
                         org_request_ts=now, org_page=1)
            # org_attempts / org_stale_count 不清零：已放弃的记录手动核对一次仍无变化会再次停止，不会重新进入长时间自动核对
            queued += 1
        return {"code": 0, "msg": "已排队核对整理证据，未重新获取", "data": {"state": "queued", "queued": queued}}

    def _mp_subscribes(self):
        mp, now = self._mp(), time.time()
        cached = getattr(self, "_subscriptions_cache", None)
        if cached and now - cached[0] < 300:
            return copy.deepcopy(cached[1])
        rows, page = [], 1
        cursor = getattr(self, "_subscriptions_cursor", None) or {"rows": [], "page": 1}
        rows, page = list(cursor["rows"]), int(cursor["page"])
        while True:
            body = self._mp_api_json("/api/v1/subscribe/", {"page": page, "count": 100})
            items, total = mp.page(body)
            known = {x.get("id") for x in rows}
            rows += [x for x in items if x.get("id") not in known or x.get("id") is None]
            if (page * 100 >= total if total is not None else len(items) < 100):
                self._subscriptions_cache = (now, rows)
                self._subscriptions_cursor = None
                return copy.deepcopy(rows)
            if not items:
                raise ValueError("MP订阅分页不完整")
            page += 1
            self._subscriptions_cursor = {"rows": rows, "page": page}

    def api_subscriptions_fetch(self, payload: dict = None):
        """只读拉取 MP 订阅列表并刷新本地缓存（不匹配提交、不转存），之后「预演」即可看到最新订阅。"""
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        mp = self._mp()
        try:
            context = mp.work_slice() if hasattr(mp, "work_slice") else nullcontext()
            with context:
                self._subscriptions_cache = None
                self._subscriptions_cursor = None
                rows = self._mp_subscribes()
        except MPDeferred as exc:
            return {"code": 1, "msg": f"暂时无法读取 MP 订阅：{exc}"}
        except Exception as exc:  # noqa: BLE001
            return {"code": 1, "msg": "读取 MP 订阅失败：" + self._error(exc)}
        movies = sum(1 for x in rows if x.get("type") == "电影")
        return {"code": 0, "msg": f"已读取 MP 订阅 {len(rows)} 个（电影 {movies} 个），未提交任何资源",
                "data": {"total": len(rows), "movies": movies}}

    def api_subscriptions_preview(self):
        index = self._ensure_index()
        cached = getattr(self, "_subscriptions_cache", None)
        rows = cached[1] if cached else []
        matcher = subscribe_sync.SubscriptionMatcher(index.records if index else [])
        states = {x["key"]: x for x in self._subscription_store().list()}
        legacy_path = self.get_data_path_local() / "subscribed.json"
        legacy = set(json.loads(legacy_path.read_text(encoding="utf8"))) if legacy_path.exists() else set()
        preview = []
        for raw in rows:
            if raw.get("type") != "电影":
                continue
            sub = self._normalise_subscription(raw)
            plan = self._subscription_plan(matcher, sub, states, legacy)
            best = (plan["eligible"] or plan["candidates"] or [{}])[0]
            preview.append({"id": raw.get("id"), "title": sub["title"], "year": sub.get("year") or "",
                            "matched": len(plan["eligible"]), "state": plan["status"], "reason": plan["reason"],
                            "qtext": str(best.get("qtext") or best.get("spec") or ""),
                            "next_check_at": self._subscribe_next_check_at()})
        return {"code": 0, "data": {"records": preview, "cached_at": cached[0] if cached else 0,
                                    "cache_empty": not bool(cached), "msg": "本地预演，不提交资源"}}

    def _subscribe_next_check_at(self):
        """下次订阅同步时间：已排队的后台任务优先，否则取调度器里订阅 cron 的下次触发时间。"""
        job = self._job_store().get("subscribe") or {}
        if job.get("state") in ("queued", "running"):
            return float(job.get("next_check_at") or 0)
        scheduler = getattr(self, "_scheduler", None)
        try:
            item = scheduler.get_job("doc115-subscribe") if scheduler and hasattr(scheduler, "get_job") else None
            when = getattr(item, "next_run_time", None)
            return when.timestamp() if when else 0
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _normalise_subscription(raw):
        source = raw.get("media_source") or "themoviedb"
        return {**raw, "title": raw.get("name") or raw.get("title") or "",
                "tmdbid": str((raw.get("media_id") or raw.get("tmdbid") or "") if source == "themoviedb" else (raw.get("tmdbid") or "")),
                "year": str(raw.get("year") or "")}

    def _subscription_plan(self, matcher, sub, states, legacy):
        """Shared, read-only rule evaluation for preview and automatic work."""
        candidates = subscribe_sync.subscription_candidates(matcher, sub)
        plan = {"candidates": candidates, "eligible": [], "key": "", "state": {}, "status": "skipped", "reason": "本地文档没有匹配资源"}
        if sub.get("state") not in (None, "", "N", "R"):
            plan["reason"] = "MP订阅当前未启用"
            return plan
        if not candidates:
            return plan
        key = subscribe_sync.transfer_key(sub, candidates[0])
        state = states.get(key, {})
        plan.update(key=key, state=state)
        if state.get("status") == "cancelled":
            plan["reason"] = "已停止本插件订阅跟踪"
            return plan
        if state.get("status") == "failed" and state.get("fingerprint") == self._fingerprint(candidates[0]):
            plan["reason"] = "上次失败，等待手动重试或新资源"
            return plan
        completed = state.get("completed_quality_score")
        if completed is None and (state.get("status") == "complete" or key in legacy):
            completed = state.get("quality_score", 3)
        plan["completed_score"] = completed
        if completed is not None:
            if not self._upgrade_enabled or doc_parser.quality_score(candidates[0]) <= completed:
                plan["reason"] = "已完成获取，无需重复获取或升级"
                return plan
            candidates = [c for c in candidates if doc_parser.quality_score(c) > completed]
            if state.get("last_upgrade_fingerprint") == self._fingerprint(candidates[0]):
                plan["reason"] = "该升级资源已处理，等待新资源"
                return plan
        if any(x.get("subscription_key") == key and x.get("acquisition_status") not in ("failed", "saved", "success") and x.get("tracking_enabled", True)
               for x in self._records().list(limit=None, include_hidden=True)):
            plan["reason"] = "原获取任务正在跟踪"
            return plan
        plan["status"] = "blocked"
        if sub.get("filter") or sub.get("filter_groups"):
            plan["reason"] = "外部过滤规则组不能在文档记录中可靠校验，未自动下载"
            return plan
        try:
            for field in ("include", "exclude", "quality", "resolution", "effect"):
                if sub.get(field):
                    re.compile(str(sub[field]), re.I)
        except re.error as exc:
            plan["reason"] = "订阅正则规则无效：" + self._error(exc)
            return plan
        eligible = [c for c in candidates if self._matches_rules(c, sub) and
                    (c.get("media_type") or doc_parser.media_type_of(c.get("sheet", ""), c.get("title", ""))) == "movie"]
        plan.update(candidates=candidates, eligible=eligible,
                    status="ready" if eligible else "blocked", reason="符合订阅规则，可排队获取" if eligible else "没有符合类型和订阅规则的可用资源")
        return plan

    def _job_store(self):
        from .history import JsonListStore
        return JsonListStore(self.get_data_path_local() / "local_jobs.json")

    def _queue_job(self, name):
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        jobs, now = self._job_store(), time.time()
        old = jobs.get(name)
        if old and old.get("state") in ("queued", "running"):
            return {"code": 0, "msg": "任务已排队", "data": {"state": "queued"}}
        fields = {"state": "queued", "next_check_at": now, "generation": self._generation, "queued_at": now,
                  "failures": 0, "msg": ""}
        if old:
            jobs.update(name, **fields)
        else:
            jobs.upsert({"id": name, **fields})
        return {"code": 0, "msg": "已排队后台处理", "data": {"state": "queued"}}

    def queue_subscribe_job(self):
        """订阅 cron 回调：只排队，由离线 worker 执行（有失败重试，避免与 MP 读取锁冲突直接失败）。"""
        if self._subscribe_enabled:
            self._queue_job("subscribe")

    def jobs_view(self):
        """GET /status 的 jobs：index / subscribe 后台任务状态。"""
        result = {}
        rows = {x.get("id"): x for x in self._job_store().list()}
        for name in ("index", "subscribe"):
            job = rows.get(name) or {}
            state = job.get("state") or "idle"
            if state == "done":
                state = "idle"
            elif state == "queued" and int(job.get("failures") or 0) > 0:
                # 失败后会自动退避重试（不是终态）：标成 retrying，前端继续显示进行中并给出失败原因
                state = "retrying"
            result[name] = {"state": state if state in ("idle", "queued", "running", "retrying", "failed") else "idle",
                            "failures": int(job.get("failures") or 0),
                            "next_at": float(job.get("next_check_at") or 0) if state == "retrying" else 0,
                            "msg": str(job.get("msg") or ""), "at": float(job.get("finished_at") or job.get("queued_at") or 0)}
        if result["index"]["state"] == "idle" and getattr(self, "_refresh_lock", None) and self._refresh_lock.locked():
            result["index"]["state"] = "running"
        return result

    def api_run_subscribe(self):
        if not self._subscribe_enabled:
            return {"code": 1, "msg": "电影订阅同步未启用"}
        return self._queue_job("subscribe")

    def api_refresh_index(self):
        return self._queue_job("index")

    def _run_requested_job(self, generation):
        jobs, now = self._job_store(), time.time()
        due = [x for x in jobs.list() if x.get("state") in ("queued", "running") and float(x.get("next_check_at") or 0) <= now]
        if not due:
            return False
        job = min(due, key=lambda x: float(x.get("next_check_at") or 0))
        if not self._live(generation):
            return False
        if job["id"] == "subscribe" and not getattr(self, "_subscribe_enabled", False):
            jobs.update(job["id"], state="done", next_check_at=0, msg="电影订阅同步未启用", finished_at=now)
            return True
        jobs.update(job["id"], state="running", started_at=now)
        try:
            result = self.run_subscribe() if job["id"] == "subscribe" else self.refresh_index()
        except Exception as exc:  # noqa: BLE001
            result = {"code": 1, "msg": self._error(exc)}
        if self._live(generation):
            done = time.time()
            if result.get("code") == 0:
                jobs.update(job["id"], state="done", next_check_at=0, failures=0, msg=str(result.get("msg") or ""), finished_at=done)
            else:
                failures = int(job.get("failures") or 0)
                jobs.update(job["id"], state="queued", next_check_at=now + self._delay(failures, cap=900), failures=failures+1,
                            msg=str(result.get("msg") or "执行失败"), finished_at=done)
                if failures + 1 >= 5:
                    logger.warning(f"115文档订阅与查询：后台任务 {job['id']} 连续 {failures + 1} 次失败：{result.get('msg')}")
        return True

    def api_directories(self):
        # Directory selection reads only a previous bounded MP snapshot.
        cached = getattr(self, "_directories_cache", None)
        self._directories_requested = True
        return {"code": 0, "data": {"records": cached[1] if cached else [],
                "cached_at": cached[0] if cached else 0, "monitor_confirmed": False,
                "error": getattr(self, "_directories_error", "")}}

    def _refresh_directories_snapshot(self, generation):
        now = time.time()
        if not self._live(generation) or now < getattr(self, "_directories_next_ts", 0):
            return
        try:
            body = self._mp_api_json("/api/v1/storage/directories", {"directory_type": "download", "storage_type": "remote"})
            rows, _ = self._mp().page(body)
            allowed = ("name", "storage", "download_path", "media_type", "monitor_type", "monitor_mode")
            records = [{**{k: row.get(k) for k in allowed}, "path": row["download_path"], "monitored": None,
                        "media_type": {"电影": "movie", "电视剧": "tv"}.get(row.get("media_type"), row.get("media_type"))}
                       for row in rows if row.get("storage") in ("115网盘Plus", "u115", "115") and row.get("download_path")]
            if self._live(generation):
                self._directories_cache = (now, records)
                self._directories_error = ""
                self._directories_errors = 0
                self._directories_next_ts = now + 300
                self._directories_requested = False
        except Exception as exc:
            if self._live(generation):
                errors = getattr(self, "_directories_errors", 0)
                self._directories_errors = errors + 1
                self._directories_error = self._error(exc)
                self._directories_next_ts = max(now + self._delay(errors, base=60, cap=900), float(getattr(exc, "retry_at", 0) or 0))

    def api_diagnostics(self):
        tr, mp = getattr(self, "_tr", None), getattr(self, "_mp_instance", None)
        store = self._records()
        return {"code": 0, "data": {"version": self.plugin_version, "enabled": self._enabled,
            "cloud": tr.budget_state if tr and hasattr(tr, "budget_state") else {"state": "未验证"},
            "mp": mp.diagnostics() if mp else {"state": "未验证"},
            "active_tasks": sum(self._is_tracking(x) for x in store.tracked()),
            "offline": {"last_tick": getattr(self, "_last_offline_tick", None) or {"state": "尚未执行"}},
            "organization": {"last_tick": getattr(self, "_last_org_tick", None) or {"state": "尚未执行"},
                             "last_event_stats": getattr(self, "_last_event_stats", None),
                             "last_event_error": getattr(self, "_last_event_error", None),
                             "events": store.event_counts()},
            "maintenance": getattr(self, "_last_maintenance", None),
            "jobs": self.jobs_view(),
            "scope": "仅本插件；只读本地状态，未请求115或MP"}}

    def _refresh_event_paths(self, force=False):
        """Build local membership outside MP's event callback; no common-dir root.

        只在账本有变化（批次数/revision 合计/最近更新时间）时重建，避免每次 tick 全表反序列化。
        """
        store = self._records()
        token = store.change_token() if hasattr(store, "change_token") else None
        if not force and token is not None and token == getattr(self, "_event_paths_token", None):
            return
        paths = {}
        for rec in (store.tracked() if hasattr(store, "tracked") else store.list(limit=None, include_hidden=True)):
            if not rec.get("tracking_enabled", True):
                continue
            names = set(rec.get("item_names") or [])
            if rec.get("item_name"):
                names.add(rec["item_name"])
            roots = [rec["final_path"].rstrip("/") + "/" + n for n in names if n and "/" not in n and "\\" not in n]
            roots += [unit.get("source_path") for unit in rec.get("manifest") or [] if unit.get("source_path")]
            # A newly queued share can receive events while the response is in
            # flight; the source manifest is registered before its first write.
            for path in roots:
                paths.setdefault(path, set()).add(rec["id"])
        self._event_paths = {path: tuple(ids) for path, ids in paths.items()}
        self._event_paths_token = token

    def _event_batches(self, source_path):
        ids = set()
        for path, batch_ids in getattr(self, "_event_paths", {}).items():
            if path_is_within(source_path, path):
                ids.update(batch_ids)
        return ids

    # MediaInfo 只保留身份字段：整个对象（含海报/简介/演员等）既无用又可能不可序列化。
    EVENT_MEDIA_FIELDS = ("title", "original_title", "en_title", "year", "type", "tmdb_id", "tmdbid", "tvdb_id",
                          "douban_id", "imdb_id", "season", "seasons", "episode", "episodes", "category")
    EVENT_FILE_FIELDS = ("storage", "path", "name", "type", "fileid", "file_id", "parent_fileid", "size")
    EVENT_TRANSFER_FIELDS = ("success", "message", "transfer_type", "file_count", "target_item", "target_diritem",
                             "target_fileitem", "fail_list", "date")
    EVENT_PAYLOAD_KEYS = ("fileitem", "src_fileitem", "mediainfo", "meta", "transferinfo",
                          "history_id", "message", "date", "timestamp")

    @staticmethod
    def _plain(value, depth=0, max_depth=6):
        """把 MP 事件里的 pydantic / dataclass / 普通对象 / Enum 转成可 JSON 序列化的基础类型。"""
        import dataclasses
        import datetime
        import enum
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, enum.Enum):
            return TaskRuntime._plain(value.value, depth, max_depth)
        if isinstance(value, (datetime.datetime, datetime.date)):
            return value.isoformat()
        if depth >= max_depth:
            return None
        nxt = depth + 1
        if isinstance(value, dict):
            return {str(k): TaskRuntime._plain(v, nxt, max_depth) for k, v in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            items = sorted(value, key=str) if isinstance(value, (set, frozenset)) else value
            return [TaskRuntime._plain(x, nxt, max_depth) for x in items]
        if isinstance(value, (bytes, bytearray)):
            return None
        if hasattr(value, "model_dump"):
            try:
                return TaskRuntime._plain(value.model_dump(), depth, max_depth)
            except Exception:  # noqa: BLE001
                pass
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return {f.name: TaskRuntime._plain(getattr(value, f.name, None), nxt, max_depth)
                    for f in dataclasses.fields(value)}
        if hasattr(value, "__dict__") and not isinstance(value, type):
            return {str(k): TaskRuntime._plain(v, nxt, max_depth)
                    for k, v in vars(value).items() if not str(k).startswith("_") and not callable(v)}
        return None

    @classmethod
    def _pick(cls, value, fields):
        """只取需要的字段；对象/字典都适用，结果一定是 dict。"""
        if value is None:
            return {}
        if not isinstance(value, dict):
            raw = {}
            for name in fields:
                try:
                    attr = getattr(value, name, None)
                except Exception:  # noqa: BLE001
                    attr = None
                if attr is not None and not callable(attr):
                    raw[name] = attr
            if not raw:
                dumped = cls._plain(value, max_depth=2)
                raw = dumped if isinstance(dumped, dict) else {}
            value = raw
        return {k: cls._plain(value[k], 1) for k in fields if k in value and value[k] is not None}

    def _event_clue(self, payload):
        """事件 payload → 只含白名单字段的纯数据线索。"""
        clue = {}
        for key in self.EVENT_PAYLOAD_KEYS:
            if key not in payload or payload[key] is None:
                continue
            value = payload[key]
            if key in ("fileitem", "src_fileitem"):
                clue[key] = self._pick(value, self.EVENT_FILE_FIELDS)
            elif key == "mediainfo":
                media = self._pick(value, self.EVENT_MEDIA_FIELDS)
                if "tmdbid" not in media and media.get("tmdb_id") is not None:
                    media["tmdbid"] = str(media["tmdb_id"])
                clue[key] = media
            elif key == "meta":
                clue[key] = self._pick(value, ("name", "title", "year", "type", "begin_season", "season",
                                              "begin_episode", "end_episode", "tmdbid"))
            elif key == "transferinfo":
                info = self._pick(value, self.EVENT_TRANSFER_FIELDS)
                for item in ("target_item", "target_diritem", "target_fileitem"):
                    if isinstance(info.get(item), dict):
                        info[item] = {k: info[item][k] for k in self.EVENT_FILE_FIELDS if k in info[item]}
                if isinstance(info.get("fail_list"), list):
                    info["fail_list"] = info["fail_list"][:50]
                clue[key] = info
            else:
                clue[key] = self._plain(value, 1)
        return clue

    def _receive_event(self, event):
        """MP callbacks persist clues only; no cloud lookup or host mutation."""
        if not self._enabled:
            return
        payload = getattr(event, "event_data", None) or {}
        if not isinstance(payload, dict):
            return
        clue = self._event_clue(payload)
        source = clue.get("fileitem") or clue.get("src_fileitem") or {}
        path = source.get("path") if isinstance(source, dict) else ""
        # Filter unrelated host events using cached batch paths, not cloud calls.
        batch_ids = self._event_batches(path)
        if not batch_ids:
            return
        kind = getattr(event, "event_type", "")
        clue["_event_type"] = str(getattr(kind, "value", kind) or "")
        clue["_batch_ids"] = sorted(batch_ids)
        # 去重哈希不含接收时间：MP 重复投递同一事件只入库一次。
        event_id = hashlib.sha256(json.dumps(clue, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
        clue["_received_ts"] = time.time()
        self._records().enqueue_event(event_id, clue)

    def _apply_queued_event(self, store, queued):
        """处理单条 115 生活事件（供 _drain_events 调用，异常由调用方隔离）。"""
        clue = queued.get("payload") or queued.get("data") or {}
        if not isinstance(clue, dict):
            store.ack_event(queued["event_id"])
            return

        def mapping(value):
            return value if isinstance(value, dict) else {}
        source = mapping(clue.get("fileitem")) or mapping(clue.get("src_fileitem"))
        media = mapping(clue.get("mediainfo"))
        transfer = mapping(clue.get("transferinfo"))
        dest = mapping(transfer.get("target_item")) or mapping(transfer.get("target_diritem")) or mapping(transfer.get("target_fileitem"))
        received = float(clue.get("_received_ts") or queued.get("created_ts") or 0)
        stated = clue.get("date") or clue.get("timestamp") or transfer.get("date")
        if isinstance(transfer.get("success"), bool):
            status = transfer["success"]
        else:
            status = "fail" not in str(clue.get("_event_type", "")).lower()
        entry = {**media, "src_fileitem": source, "src": source.get("path"), "src_storage": source.get("storage"),
            "date": stated or received or None,
            "time_is_observed": not bool(stated),
            "evidence_source": "event", "title": media.get("title"), "type": media.get("type"),
            "status": status, "id": clue.get("history_id"), "dest_fileitem": dest,
            "errmsg": clue.get("message") or transfer.get("message") or ""}
        associated = False
        for rid in clue.get("_batch_ids") or self._event_batches(source.get("path")):
            rec = store.get(rid)
            if not rec or not rec.get("tracking_enabled", True):
                continue
            if match_history(rec, [entry]):
                before = rec.get("organization_status")
                batch = store.record_evidence(rec["id"], [entry])
                self._confirm_move_from_evidence(batch, self._generation)
                self._log_org_change(rec, before, batch)
                associated = True
        # Candidate clues get finite local retries, so unrelated/obsolete
        # inbox rows cannot pin the first page and starve newer events.
        if associated or time.time() - received > 900:
            store.ack_event(queued["event_id"])

    def _drain_events(self):
        """排空 115 生活事件；**单条事件异常不再拖死整轮核对**。

        0.10.0 的失效点：事件处理里任何异常都会冒泡到 check_organization 的 except，
        被静默吞掉 → 每 20 秒都失败一次、既不更新记录也不留任何日志（本次线上故障即此）。
        """
        store = self._records()
        failures = getattr(self, "_event_failures", None)
        if not isinstance(failures, dict):
            failures = self._event_failures = {}
        handled = errors = 0
        for queued in store.drain_events(limit=50):
            event_id = str(queued.get("event_id") or "")
            try:
                self._apply_queued_event(store, queued)
                handled += 1
                failures.pop(event_id, None)
            except Exception as exc:  # noqa: BLE001
                errors += 1
                count = int(failures.get(event_id) or 0) + 1
                failures[event_id] = count
                self._last_event_error = {"at": time.time(), "event_id": event_id, "error": self._error(exc)[:300]}
                if count >= self.EVENT_GIVEUP_ATTEMPTS:
                    try:
                        store.ack_event(event_id)
                    except Exception:  # noqa: BLE001
                        pass
                    failures.pop(event_id, None)
                    logger.warning(f"115文档订阅与查询：事件连续 {count} 次处理失败，已跳过该事件：{event_id}｜"
                                   + self._error(exc) + "\n" + traceback.format_exc())
                else:
                    logger.warning(f"115文档订阅与查询：事件处理失败（第 {count} 次）：{event_id}｜" + self._error(exc))
        self._last_event_stats = {"at": time.time(), "handled": handled, "errors": errors,
                                  "pending": len(failures)}
        return {"handled": handled, "errors": errors}
