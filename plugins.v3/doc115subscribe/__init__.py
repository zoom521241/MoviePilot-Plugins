"""腾讯文档资源索引、电影订阅与可恢复的 115 转存任务。"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import re
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import MediaType

from . import doc_parser, subscribe_sync
from .doc_client import DocError, TencentDocsClient
from .doc_index import DocIndex
from .history import RecordStore, PendingStore, JsonListStore
from .link_router import LINK_115_SHARE, LINK_ED2K, LINK_MAGNET, classify_link
from .p115_transfer import P115Error, P115Transfer, extract_hash
from .qrlogin_browser import BrowserQrLogin, QrLoginError


class OfflineTaskError(P115Error):
    """Terminal task failure, as distinct from a temporary cloud lookup error."""


class Doc115Subscribe(_PluginBase):
    plugin_name = "115文档订阅与查询"
    plugin_desc = "腾讯文档跨表搜索、电影订阅与115分享/离线任务管理。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "0.9.2"
    plugin_author = "zoom521241"
    author_url = "https://github.com/zoom521241"
    plugin_config_prefix = "doc115subscribe_"
    plugin_order = 20
    auth_level = 1

    DEFAULTS = {
        "enabled": False, "doc_url": "https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo",
        "tencent_cookie": "", "p115_cookie": "",
        "movie_path": "/115-影视/115-downloads/电影",
        "tv_path": "/115-影视/115-downloads/电视剧",
        "magnet_staging_path": "/115-影视/115-downloads/磁力链接",
        "subscribe_enabled": True, "subscribe_cron": "0 21 * * *",
        "index_cron": "0 6 * * *", "create_subdir": True,
        "link_mode": "first", "upgrade_enabled": False,
    }
    _scheduler = None
    _index = None
    _qr = None
    _enabled = False
    _tencent_cookie = ""
    _p115_cookie = ""
    _P115_COOKIE_SOURCES = (("plugin.P115StrmHelper", "cookies"),
                           ("plugin.P115Disk", "cookie"),
                           ("plugin.P115StrgmSub", "cookies"))
    _runtime_lock = threading.Lock()
    QR_FRESH_SECONDS = 90

    def _ensure_runtime(self):
        with self._runtime_lock:
            if not hasattr(self, "_operation_lock"):
                self._operation_lock = threading.RLock()
                self._config_lock = threading.RLock()
                self._refresh_lock = threading.Lock()
                self._subscribe_lock = threading.Lock()
                self._offline_lock = threading.Lock()
                self._qr_lock = threading.RLock()
                self._generation = 0
                self._tr = None
                self._tr_cookie = ""
                self._mt_cache = {}
                self._qr_img = b""
                self._qr_ts = 0.0
                self._offline_next_ts = 0.0
                self._org_check_ts = 0.0
                self._last_refresh = {}
                self._last_subscribe = {}

    @classmethod
    def _validate_config(cls, config):
        conf = {k: config.get(k, v) for k, v in cls.DEFAULTS.items()}
        for k, default in cls.DEFAULTS.items():
            if isinstance(default, bool):
                if not isinstance(conf[k], bool):
                    raise ValueError(f"{k} 必须是布尔值")
            elif not isinstance(conf[k], str):
                raise ValueError(f"{k} 必须是文本")
            else:
                conf[k] = conf[k].strip()
        url = urllib.parse.urlparse(conf["doc_url"])
        if (url.scheme != "https" or url.hostname != "docs.qq.com" or url.username or url.password
                or url.port not in (None, 443)):
            raise ValueError("腾讯文档地址必须是 https://docs.qq.com/sheet/ 链接")
        TencentDocsClient.parse_doc_id(conf["doc_url"])
        for field in ("index_cron", "subscribe_cron"):
            CronTrigger.from_crontab(conf[field], timezone="Asia/Shanghai")
        for field in ("movie_path", "tv_path", "magnet_staging_path"):
            path = conf[field].replace("\\", "/")
            if not path.startswith("/") or path == "/" or any(p in (".", "..") for p in path.split("/")):
                raise ValueError(f"{field} 必须是非根目录的115绝对路径")
            if any(ord(c) < 32 for c in path):
                raise ValueError(f"{field} 含非法字符")
            conf[field] = path.rstrip("/")
        if conf["link_mode"] not in ("first", "all"):
            raise ValueError("链接策略必须是 first 或 all")
        return conf

    def init_plugin(self, config: dict = None):
        self._ensure_runtime()
        conf = self._validate_config({**self.DEFAULTS, **(config or {})})
        with self._config_lock, self._qr_lock, self._operation_lock:
            self.stop_service()
            self._generation += 1
            for key, val in conf.items():
                setattr(self, "_" + key, val)
            self._tr, self._tr_cookie = None, ""
            self._mt_cache = {}
            self._index = None
            self._load_index()
            if not self._enabled:
                return
            scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
            options = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 300}
            scheduler.add_job(self.refresh_index,
                trigger=CronTrigger.from_crontab(self._index_cron, timezone="Asia/Shanghai"),
                id="doc115-index", name="115文档刷新索引", **options)
            if self._subscribe_enabled:
                scheduler.add_job(self.run_subscribe,
                    trigger=CronTrigger.from_crontab(self._subscribe_cron, timezone="Asia/Shanghai"),
                    id="doc115-subscribe", name="115文档电影订阅", **options)
            scheduler.add_job(self.check_offline_tasks, trigger=IntervalTrigger(seconds=15),
                              id="doc115-offline", name="115文档离线搬运", **options)
            self._scheduler = scheduler
            try:
                scheduler.start()
            except Exception:
                self.stop_service()
                raise

    def stop_service(self):
        self._ensure_runtime()
        with self._config_lock, self._qr_lock, self._operation_lock:
            self._stop_service_locked()

    def _stop_service_locked(self):
        self._enabled = False
        scheduler, self._scheduler = self._scheduler, None
        if scheduler:
            scheduler.remove_all_jobs()
            if scheduler.running:
                scheduler.shutdown(wait=False)
        qr, self._qr = self._qr, None
        if qr:
            qr.close()
        self._qr_img = b""

    def get_state(self):
        return bool(self._enabled)

    def _current_config(self):
        return {key: getattr(self, "_" + key, default) for key, default in self.DEFAULTS.items()}

    def _public_config(self):
        conf = self._current_config()
        conf.update(tencent_cookie="", p115_cookie="",
                    tencent_cookie_ready=bool(self._tencent_cookie),
                    p115_cookie_ready=bool(self._p115_cookie),
                    p115_ready=bool(self.get_p115_cookie()))
        return conf

    def _error(self, exc):
        text = str(exc)
        for val in (self._tencent_cookie, self._p115_cookie, getattr(self, "_tr_cookie", "")):
            if val:
                text = text.replace(val, "[已隐藏]")
        return re.sub(r"([?&](?:token|apikey|password|receive_code)=)[^&\s]+", r"\1[已隐藏]", text)[:500]

    def get_p115_cookie(self):
        if self._p115_cookie:
            return self._p115_cookie
        try:
            from app.db.systemconfig_oper import SystemConfigOper
            for key, field in self._P115_COOKIE_SOURCES:
                cfg = SystemConfigOper().get(key) or {}
                if isinstance(cfg, dict) and isinstance(cfg.get(field), str) and cfg[field].strip():
                    return cfg[field].strip()
        except Exception:
            logger.debug("115文档：无法复用其它插件Cookie")
        return ""

    def get_data_path_local(self):
        return Path(self.get_data_path())

    @property
    def index_path(self):
        return self.get_data_path_local() / "doc_index.json"

    @property
    def pending_path(self):
        return self.get_data_path_local() / "pending_offline.json"

    @property
    def history_path(self):
        return self.get_data_path_local() / "history.json"

    def _pending(self):
        return PendingStore(self.pending_path)

    def _records(self):
        store = RecordStore(self.history_path)
        # 0.7.x inferred organization from absence; that was not proof of ingestion.
        def migrate(items):
            for rec in items:
                if rec.get("status") == "organized" and not rec.get("organization_confirmed"):
                    rec.update(status="unverified", message="旧记录整理状态未经入库证据确认，请核实媒体库")
                if not rec.get("resource_key") and rec.get("kind") and rec.get("url") and rec.get("final_path"):
                    rec["resource_key"] = hashlib.sha256(
                        f"{rec['kind']}|{rec['url']}|{rec['final_path']}".encode()).hexdigest()
        store.transaction(migrate)
        return store

    def _subscription_store(self):
        return JsonListStore(self.get_data_path_local() / "subscription_state.json")

    def _new_client(self):
        doc_id, _ = TencentDocsClient.parse_doc_id(self._doc_url)
        return TencentDocsClient(doc_id, self._tencent_cookie)

    def _load_index(self):
        client = self._new_client()
        self._index = DocIndex.load(self.index_path, client=client, expected_doc_id=client.doc_id)

    def _ensure_index(self):
        if self._index is None:
            self._load_index()
        return self._index

    def resolve_media_type(self, rec):
        explicit = rec.get("tmdb_type") or rec.get("media_type")
        hint = explicit if explicit in ("movie", "tv") else doc_parser.media_type_of(rec.get("sheet", ""), rec.get("title", ""))
        tmdbid = str(rec.get("tmdbid") or "")
        if not tmdbid.isdigit() or hint not in ("movie", "tv"):
            return hint
        key = ("themoviedb", tmdbid, hint)
        if key in self._mt_cache:
            return self._mt_cache[key]
        try:
            from app.chain.media import MediaChain
            chain = MediaChain()
            params = inspect.signature(chain.recognize_media).parameters
            mtype = MediaType.MOVIE if hint == "movie" else MediaType.TV
            if "media_id" in params:
                from app.schemas.types import MediaSource
                media = chain.recognize_media(media_source=MediaSource.TMDB, media_id=tmdbid, mtype=mtype)
            elif "tmdbid" in params:
                media = chain.recognize_media(tmdbid=int(tmdbid), mtype=mtype)
            else:
                return hint
            if media and media.type in (MediaType.MOVIE, MediaType.TV):
                result = "movie" if media.type == MediaType.MOVIE else "tv"
                self._mt_cache[key] = result
                return result
        except Exception as exc:
            logger.debug(f"115文档：媒体类型识别失败：{self._error(exc)}")
        return hint

    def refresh_index(self):
        self._ensure_runtime()
        if not self._tencent_cookie:
            return {"code": 1, "msg": "缺少腾讯文档Cookie"}
        if not self._refresh_lock.acquire(blocking=False):
            return {"code": 1, "msg": "索引正在刷新，请稍后"}
        generation = self._generation
        try:
            idx = DocIndex(self._new_client())
            summary = idx.build(previous=self._index)
            with self._operation_lock:
                if generation != self._generation:
                    return {"code": 1, "msg": "配置已变化，已丢弃旧刷新结果"}
                idx.save(self.index_path)
                self._index = idx
            partial = bool(summary.get("errors"))
            self._last_refresh = {"success": not partial, "at": time.time(),
                                  "msg": "部分工作表失败，已保留可用旧记录" if partial else "刷新完成"}
            return {"code": 0, "msg": self._last_refresh["msg"], "data": summary}
        except Exception as exc:
            self._last_refresh = {"success": False, "at": time.time(), "msg": self._error(exc)}
            logger.warning(f"115文档：索引刷新失败：{self._error(exc)}")
            return {"code": 1, "msg": self._error(exc)}
        finally:
            self._refresh_lock.release()

    def _transfers(self):
        cookie = self.get_p115_cookie()
        if not cookie:
            raise P115Error("未配置115 Cookie")
        if self._tr is None or self._tr_cookie != cookie:
            self._tr = P115Transfer(cookie)
            self._tr_cookie = cookie
        return self._tr

    def build_save_path(self, rec, target):
        base = self._movie_path if target == "movie" else self._tv_path
        if not self._create_subdir:
            return base
        title = (rec.get("title") or "").strip()
        year = str(rec.get("year") or "")
        name = title if not year or re.search(r"[（(]" + re.escape(year) + r"[)）]", title) else f"{title} ({year})"
        name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name).strip(" .")[:100]
        return f"{base}/{name}" if name else base

    @staticmethod
    def _fingerprint(rec):
        return hashlib.sha256(json.dumps(list(doc_parser.iter_links(rec)), sort_keys=True).encode()).hexdigest()

    def _set_subscription(self, key, **fields):
        if not key:
            return
        state = self._subscription_store()
        def change(items):
            item = next((x for x in items if x.get("key") == key), None)
            if item is None:
                item = {"key": key}
                items.append(item)
            if fields.get("status") == "failed" and item.get("completed_quality_score") is not None:
                fields.update(status="complete", quality_score=item["completed_quality_score"],
                              last_upgrade_fingerprint=fields.get("fingerprint", item.get("fingerprint")),
                              last_upgrade_error=fields.get("message") or "升级资源提交或搬运失败")
            item.update(fields, updated_at=time.time())
            if fields.get("status") == "complete" and not fields.get("last_upgrade_error"):
                item["completed_quality_score"] = max(item.get("completed_quality_score", 0),
                    item.get("target_quality_score", item.get("quality_score", 0)))
                item["quality_score"] = item["completed_quality_score"]
        state.transaction(change)

    def _complete_subscription_if_ready(self, key):
        if not key:
            return
        state = next((x for x in self._subscription_store().list() if x.get("key") == key), None)
        if not state or state.get("status") == "cancelled":
            return
        required = state.get("required_resources") or []
        if not required:
            return
        if set(required).issubset(set(state.get("completed_resources") or [])):
            self._set_subscription(key, status="complete")

    def _mark_resource_complete(self, key, resource_key):
        if not key or not resource_key:
            return
        def change(items):
            item = next((x for x in items if x.get("key") == key), None)
            if item is None:
                item = {"key": key}
                items.append(item)
            completed = set(item.get("completed_resources") or [])
            completed.add(resource_key)
            item.update(completed_resources=sorted(completed), updated_at=time.time())
        self._subscription_store().transaction(change)

    def do_transfer(self, rec, to="", force=False):
        self._ensure_runtime()
        with self._operation_lock:
            self._last_transfer_result = {"resource_keys": [], "required_resources": [], "uncertain": False}
            if not self._enabled:
                return False, "插件未启用"
            try:
                return self._do_transfer_inner(rec, to, force)
            except Exception as exc:
                logger.warning(f"115文档：转存失败：{self._error(exc)}")
                return False, self._error(exc)

    def _do_transfer_inner(self, rec, to="", force=False):
        if rec.get("sheet_bundle") or rec.get("bundle") or rec.get("no_link"):
            return False, "该条目为大包或没有独立资源，请点击链接查看"
        target = to or self.resolve_media_type(rec)
        if target not in ("movie", "tv"):
            return False, "请选择电影或电视剧目录"
        links = [(k, u) for k, u in doc_parser.iter_links(rec)
                 if k in (LINK_115_SHARE, LINK_MAGNET, LINK_ED2K) and classify_link(u) == k]
        # Tracker variants and hex/Base32 representations refer to one offline task.
        distinct, seen = [], set()
        for kind, url in links:
            identity = ("offline", extract_hash(url)) if kind != LINK_115_SHARE and extract_hash(url) else (kind, url)
            if identity not in seen:
                seen.add(identity)
                distinct.append((kind, url))
        links = distinct
        if not links:
            return False, "该条目没有有效资源链接"
        final = self.build_save_path(rec, target)
        tr, history, pending = self._transfers(), self._records(), self._pending()
        success, errors, successful_keys, uncertain = [], [], [], False
        self._last_transfer_result = {"resource_keys": [], "required_resources": [], "uncertain": False}
        required_keys = [hashlib.sha256(f"{k}|{u}|{final}".encode()).hexdigest() for k, u in links]
        for kind, url in links:
            resource_key = hashlib.sha256(f"{kind}|{url}|{final}".encode()).hexdigest()
            existing = next((r for r in history.list() if r.get("resource_key") == resource_key), None)
            if existing and existing.get("status") in ("submitting", "unverified") and not force:
                self._last_transfer_result["uncertain"] = True
                self._last_transfer_result["required_resources"] = [resource_key]
                return False, "上次提交结果尚未确认，请先核对任务，未重复转存"
            if existing and existing.get("status") in ("downloading", "awaiting_move", "moving") and not force:
                tracked = pending.get(existing.get("hash", ""))
                if not tracked or tracked.get("status") in ("failed", "missing", "cancelled"):
                    self._last_transfer_result["uncertain"] = True
                    self._last_transfer_result["required_resources"] = [resource_key]
                    return False, "历史任务缺少有效跟踪记录，请先核对115任务，未重复提交或标记完成"
            if existing and existing.get("status") in ("submitting", "downloading", "awaiting_move", "moving", "done", "organized", "unverified") and not force:
                success.append("该资源已提交，未重复下载")
                successful_keys.append(resource_key)
                if existing.get("status") in ("done", "organized", "unverified"):
                    self._mark_resource_complete(rec.get("_subscription_key"), resource_key)
                if self._link_mode == "first":
                    break
                continue
            h = extract_hash(url) if kind != LINK_115_SHARE else ""
            if kind != LINK_115_SHARE and not h:
                errors.append("无效或不支持的信息哈希，未提交下载")
                continue
            submission = self._magnet_staging_path if h else final
            context = {"title": rec.get("title"), "year": rec.get("year"), "type": target,
                       "kind": kind, "url": url, "hash": h, "resource_key": resource_key,
                       "staging_path": submission, "final_path": final,
                       "subscription_key": rec.get("_subscription_key", ""),
                       "fingerprint": self._fingerprint(rec), "quality_score": doc_parser.quality_score(rec)}
            item = history.add({**context, "status": "submitting", "message": "准备提交"})
            result = None
            try:
                if h:
                    active = pending.get(h)
                    if active and active.get("status", "downloading") not in ("failed", "missing", "cancelled"):
                        raise P115Error("相同离线任务已经在跟踪，请先查看转存记录")
                    if active:
                        pending.delete(h)
                    pending.upsert({**context, "record_id": item["id"], "status": "submitting",
                                    "created_ts": time.time(), "last_change_ts": time.time(), "attempts": 0})
                ok, msg = tr.add_resource(kind, url, submission)
                if not ok:
                    raise P115Error(msg)
                if h:
                    result = getattr(tr, "last_offline_result", None)
                    if result is not None and result.duplicate:
                        actual = result.actual_cid
                        expected = result.requested_cid
                        if actual and expected and str(actual) != str(expected):
                            raise P115Error("115已有同种子任务位于其它目录，未搬运或重下；请手动核对")
                    pending.update(h, status="downloading", task_file_id=getattr(result, "file_id", ""),
                                   actual_cid=getattr(result, "actual_cid", ""))
                    history.update(item["id"], status="downloading", message="已提交离线下载，等待落盘及搬运")
                else:
                    history.update(item["id"], status="done", progress=100,
                                   item_names=list(getattr(tr, "last_share_names", []) or []),
                                   message="已转存到下载目录，尚未确认整理入库", moved_at=time.time())
                    self._mark_resource_complete(context["subscription_key"], resource_key)
                success.append(msg)
                successful_keys.append(resource_key)
                if self._link_mode == "first":
                    break
            except Exception as exc:
                error = self._error(exc)
                errors.append(error)
                outcome = getattr(tr, "last_offline_result", None) if h else None
                share_result = getattr(tr, "last_share_result", {})
                uncertain = bool(outcome is not None and outcome.info_hash == h and outcome.uncertain) if h else bool(
                    share_result.get("uncertain") or share_result.get("partial"))
                history.update(item["id"], status="submitting" if uncertain else "failed", message=error)
                if h and pending.get(h) and pending.get(h).get("record_id") == item["id"]:
                    pending.update(h, status="submitting" if uncertain else "failed", message=error)
                if uncertain:
                    # Reconcile the task before attempting any other mirror.
                    successful_keys.append(resource_key)
                    break
        self._last_transfer_result = {"resource_keys": successful_keys,
            "required_resources": required_keys if self._link_mode == "all" else successful_keys,
            "uncertain": uncertain}
        if not success:
            return False, "；".join(errors) or "转存失败"
        if errors and self._link_mode == "all":
            return False, "部分资源已提交；失败资源可重试：" + "；".join(errors)
        return True, "；".join(success)

    @staticmethod
    def _update_record(store, task, **fields):
        rec = next((r for r in store.list() if r.get("id") == task.get("record_id")), None)
        if not rec:
            rec = store.find_by_hash(task.get("hash", ""))
        if rec:
            store.update(rec["id"], **fields)

    def _process_offline(self, tr, history):
        pending = self._pending()
        items = [x for x in pending.list() if x.get("status", "downloading") not in ("failed", "missing", "cancelled")]
        data = {"pending": len(items), "finished": 0, "moved": 0, "failed": 0, "maxpct": 0, "changed": False, "errors": []}
        if not items:
            return data
        tasks = {str(t.get("info_hash") or "").lower(): t for t in tr.list_tasks()}
        now = time.time()
        for item in items:
            h = item.get("hash", "")
            task = tasks.get(h)
            try:
                if not task:
                    since = item.get("missing_since") or now
                    terminal = now - since >= 3600
                    status = "missing" if terminal else "downloading"
                    message = "115任务已消失，请核对后重试" if terminal else "暂未查询到115任务，稍后重查"
                    pending.update(h, missing_since=since, status=status, message=message)
                    self._update_record(history, item, status=status, message=message)
                    if terminal:
                        data["failed"] += 1
                        self._set_subscription(item.get("subscription_key"), status="failed", message=message)
                    continue
                pct = max(0, min(100, int(float(task.get("percentDone") or 0))))
                if tr.task_failed(task):
                    raise OfflineTaskError("115离线任务失败，请核对后重试")
                changed = pct != item.get("last_pct")
                change_ts = now if changed else item.get("last_change_ts", item.get("created_ts", now))
                if now - float(change_ts) > 24 * 3600:
                    raise OfflineTaskError("离线任务超过24小时没有进度，已停止自动检查，可手动重试")
                pending.update(h, last_pct=pct, last_change_ts=change_ts, missing_since=0)
                data["changed"] |= changed
                data["maxpct"] = max(data["maxpct"], pct)
                if pct < 100:
                    self._update_record(history, item, status="downloading", progress=pct)
                    continue
                name = str(task.get("name") or "")
                if not name or name in (".", "..") or "/" in name or "\\" in name:
                    raise OfflineTaskError("115任务返回无效文件名，未执行搬运")
                staging, final = item["staging_path"], item["final_path"]
                file_id = str(task.get("file_id") or item.get("task_file_id") or "")
                if not file_id or not file_id.isdigit() or file_id == "0":
                    raise OfflineTaskError("115任务没有可验证的文件ID，未执行搬运；请核实任务后重试")
                pending.update(h, task_file_id=file_id)
                info = tr.get_file_info(file_id)
                if info and info.get("name"):
                    name = str(info["name"])
                    if name in (".", "..") or "/" in name or "\\" in name:
                        raise OfflineTaskError("115文件ID对应名称无效，未执行搬运")
                actual_cid = task.get("wp_path_id") or task.get("savepath") or item.get("actual_cid")
                if actual_cid and str(actual_cid).isdigit() and int(actual_cid) != tr.path_to_id(staging, mkdir=False):
                    raise OfflineTaskError("115任务保存目录与登记目录不同，未执行搬运")
                src = f"{staging}/{name}"
                if not tr.file_in_directory(file_id, staging):
                    # A previous move may have succeeded before a crash; verify exact target.
                    if tr.file_in_directory(file_id, final):
                        ok, error = True, ""
                    else:
                        since = item.get("completed_since") or now
                        if now - float(since) >= 3600:
                            raise OfflineTaskError("115显示完成但文件1小时未落盘，已停止检查，可核对后重试")
                        pending.update(h, completed_since=since, status="awaiting_move")
                        self._update_record(history, item, status="awaiting_move", progress=100,
                                            message="115显示完成，文件尚未落盘")
                        continue
                else:
                    if item.get("move_started") and now - float(item.get("move_requested_ts") or 0) < 300:
                        self._update_record(history, item, status="moving", message="等待115搬运结果，未重复发送请求")
                        continue
                    pending.update(h, status="moving", move_started=True, move_requested_ts=now)
                    self._update_record(history, item, status="moving", progress=100)
                    ok, error = tr.move_via_p115disk(src, final, file_id=file_id)
                if not ok:
                    attempts = int(item.get("attempts") or 0) + 1
                    pending.update(h, attempts=attempts)
                    if attempts >= 3:
                        raise OfflineTaskError(error or "搬运连续失败3次，可手动重试")
                    self._update_record(history, item, status="awaiting_move", message=error or "搬运失败，稍后重试")
                    continue
                if not tr.file_in_directory(file_id, final):
                    pending.update(h, status="moving", move_started=True)
                    self._update_record(history, item, status="moving", progress=100,
                                        message="115已接收搬运请求，等待按文件ID确认目标目录")
                    continue
                self._update_record(history, item, status="done", progress=100, item_name=name,
                                    moved_at=now, message="已搬入下载目录，尚未确认整理入库")
                self._mark_resource_complete(item.get("subscription_key"), item.get("resource_key"))
                pending.delete(h)
                data["moved"] += 1
                data["finished"] += 1
                self._complete_subscription_if_ready(item.get("subscription_key"))
            except OfflineTaskError as exc:
                pending.update(h, status="failed", message=self._error(exc))
                self._update_record(history, item, status="failed", message=self._error(exc))
                self._set_subscription(item.get("subscription_key"), status="failed", message=self._error(exc))
                data["failed"] += 1
            except P115Error as exc:
                # A failed query says nothing about whether the file exists.
                error = self._error(exc)
                pending.update(h, message=error)
                self._update_record(history, item, message="暂时无法查询115：" + error)
                data["errors"].append(error)
        data["pending"] = sum(x.get("status", "downloading") not in ("failed", "missing", "cancelled") for x in pending.list())
        return data

    def check_offline_tasks(self, force=False):
        self._ensure_runtime()
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        if not self._offline_lock.acquire(blocking=False):
            return {"code": 0, "data": {"skipped": 1}}
        try:
            with self._operation_lock:
                if not force and time.time() < self._offline_next_ts:
                    return {"code": 0, "data": {"skipped": 1}}
                if not any(x.get("status", "downloading") not in ("failed", "missing", "cancelled") for x in self._pending().list()):
                    return {"code": 0, "data": {"pending": 0, "finished": 0}}
                data = self._process_offline(self._transfers(), self._records())
                interval = 300 if data["errors"] else (15 if data["maxpct"] >= 99 else (90 if data["changed"] else 300))
                self._offline_next_ts = time.time() + interval if data["pending"] else 0
                return {"code": 0, "data": data}
        except Exception as exc:
            self._offline_next_ts = time.time() + 300
            return {"code": 1, "msg": self._error(exc)}
        finally:
            self._offline_lock.release()

    def records_view(self, refresh=False):
        # Reading history never triggers a cloud mutation.
        return {"code": 0, "data": self._records().list()}

    def delete_record(self, rec_id=""):
        store = self._records()
        if rec_id:
            return {"code": 0, "data": {"deleted": int(store.delete(rec_id))}}
        return {"code": 0, "data": {"deleted": store.clear(), "cleared": True}}

    def _mp_subscribes(self):
        from app.core.config import settings
        token = (getattr(settings, "API_TOKEN", "") or "").strip()
        if not token:
            raise RuntimeError("MP未配置API_TOKEN，无法读取订阅")
        ports = list(dict.fromkeys(int(p) for p in (getattr(settings, "PORT", 0), 5000, 5001, 3000) if str(p).isdigit() and int(p)))
        for port in ports:
            for endpoint, credential in (("list", "token"), ("", "apikey")):
                try:
                    rows, seen = [], set()
                    for page in range(1, 1001):
                        query = urllib.parse.urlencode({credential: token, "page": page, "count": 100})
                        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/v1/subscribe/{endpoint}?{query}",
                                                     headers={"User-Agent": "MoviePilot-Doc115Subscribe"})
                        with urllib.request.urlopen(req, timeout=10) as resp:
                            body = json.loads(resp.read().decode())
                        batch = body.get("data") if isinstance(body, dict) else body
                        if not isinstance(batch, list):
                            raise ValueError("MP订阅接口返回结构错误")
                        if not batch:
                            return rows
                        signature = hashlib.sha256(json.dumps(batch, sort_keys=True).encode()).hexdigest()
                        if signature in seen:
                            raise ValueError("MP订阅接口分页没有前进")
                        seen.add(signature)
                        rows.extend(batch)
                        if len(batch) < 100:
                            return rows
                    raise ValueError("订阅超过分页保护上限，未执行不完整同步")
                except Exception:
                    continue
        raise RuntimeError("读取MP订阅失败，请检查API_TOKEN、端口和接口版本")

    @staticmethod
    def _matches_rules(rec, sub):
        text = " ".join(str(rec.get(k) or "") for k in ("title", "qtext", "spec"))
        for field in ("include", "quality", "resolution", "effect"):
            if sub.get(field) and not re.search(str(sub[field]), text, re.I):
                return False
        return not (sub.get("exclude") and re.search(str(sub["exclude"]), text, re.I))

    def run_subscribe(self):
        self._ensure_runtime()
        if not self._enabled or not self._subscribe_enabled:
            return {"code": 1, "msg": "电影订阅同步未启用"}
        if not self._subscribe_lock.acquire(blocking=False):
            return {"code": 1, "msg": "订阅同步正在运行"}
        try:
            with self._operation_lock:
                index = self._ensure_index()
                if not index or not index.records:
                    raise ValueError("索引为空，请刷新索引")
                subs = []
                for raw in self._mp_subscribes():
                    if raw.get("type") != "电影":
                        continue
                    if raw.get("state") not in (None, "", "N", "R"):
                        continue
                    source = raw.get("media_source") or "themoviedb"
                    sub = {**raw, "title": raw.get("name") or raw.get("title") or "",
                           "tmdbid": str((raw.get("media_id") or raw.get("tmdbid") or "") if source == "themoviedb" else (raw.get("tmdbid") or "")),
                           "year": str(raw.get("year") or "")}
                    subs.append(sub)
                data = {"movie_subs": len(subs), "matched": 0, "transferred": 0, "skipped": 0, "failed": 0, "errors": []}
                records = subscribe_sync.SubscriptionMatcher(index.records)
                states = {x["key"]: x for x in self._subscription_store().list()}
                legacy_path = self.get_data_path_local() / "subscribed.json"
                legacy = set(json.loads(legacy_path.read_text(encoding="utf8"))) if legacy_path.exists() else set()
                for sub in subs:
                    if not self._enabled:
                        break
                    self._last_transfer_result = {"resource_keys": [], "required_resources": [], "uncertain": False}
                    candidates = subscribe_sync.subscription_candidates(records, sub)
                    if not candidates:
                        continue
                    key = subscribe_sync.transfer_key(sub, candidates[0])
                    state = states.get(key, {})
                    if state.get("status") == "cancelled":
                        data["skipped"] += 1
                        continue
                    if state.get("status") == "failed" and state.get("fingerprint") == self._fingerprint(candidates[0]):
                        data["skipped"] += 1
                        data["errors"].append(f"{sub['title']}：上次失败，等待手动重试或新资源")
                        continue
                    completed_score = state.get("completed_quality_score")
                    if completed_score is None and (state.get("status") == "complete" or key in legacy):
                        completed_score = state.get("quality_score", 3)
                        self._set_subscription(key, completed_quality_score=completed_score)
                    if completed_score is not None:
                        if not self._upgrade_enabled or doc_parser.quality_score(candidates[0]) <= completed_score:
                            data["skipped"] += 1
                            continue
                        candidates = [c for c in candidates if doc_parser.quality_score(c) > completed_score]
                        if state.get("last_upgrade_fingerprint") == self._fingerprint(candidates[0]):
                            data["skipped"] += 1
                            continue
                    if any(x.get("subscription_key") == key and x.get("status", "downloading") not in ("failed", "missing", "cancelled") for x in self._pending().list()):
                        data["skipped"] += 1
                        continue
                    data["matched"] += 1
                    if sub.get("filter") or sub.get("filter_groups"):
                        data["failed"] += 1
                        data["errors"].append(f"{sub['title']}：外部过滤规则组不能在文档记录中可靠校验，未自动下载")
                        continue
                    try:
                        for field in ("include", "exclude", "quality", "resolution", "effect"):
                            if sub.get(field):
                                re.compile(str(sub[field]), re.I)
                    except re.error as exc:
                        data["failed"] += 1
                        data["errors"].append(f"{sub['title']}：订阅正则规则无效：{self._error(exc)}")
                        continue
                    failures, accepted = [], None
                    for candidate in candidates:
                        if not self._matches_rules(candidate, sub):
                            continue
                        if self.resolve_media_type(candidate) != "movie":
                            continue
                        candidate = {**candidate, "_subscription_key": key}
                        ok, msg = self.do_transfer(candidate, to="movie")
                        if ok:
                            accepted = candidate
                            break
                        failures.append(msg)
                        if self._last_transfer_result.get("uncertain"):
                            break
                        if self._link_mode == "all" and any(x.get("subscription_key") == key for x in self._pending().list()):
                            break
                    if accepted:
                        data["transferred"] += 1
                        active = any(x.get("subscription_key") == key and x.get("status", "downloading") not in ("failed", "missing", "cancelled") for x in self._pending().list())
                        self._set_subscription(key, status="pending" if active else "complete",
                                               fingerprint=self._fingerprint(accepted), quality_score=doc_parser.quality_score(accepted),
                                               target_quality_score=doc_parser.quality_score(accepted),
                                               required_resources=self._last_transfer_result["required_resources"])
                    else:
                        data["failed"] += 1
                        data["errors"].append(f"{sub['title']}：" + ("；".join(failures) or "没有符合类型和订阅规则的可用资源"))
                        self._set_subscription(key, status="pending" if self._last_transfer_result.get("uncertain") else "failed",
                            fingerprint=self._fingerprint(candidates[0]),
                            target_quality_score=doc_parser.quality_score(candidates[0]),
                            required_resources=self._last_transfer_result.get("required_resources") or self._last_transfer_result.get("resource_keys", []))
                self._last_subscribe = {"success": not data["failed"], "at": time.time(), "msg": f"命中{data['matched']}，提交{data['transferred']}，失败{data['failed']}"}
                return {"code": 0, "msg": self._last_subscribe["msg"], "data": data}
        except Exception as exc:
            self._last_subscribe = {"success": False, "at": time.time(), "msg": self._error(exc)}
            return {"code": 1, "msg": self._error(exc)}
        finally:
            self._subscribe_lock.release()

    @staticmethod
    def get_render_mode():
        return "vue", "dist/assets"

    def get_form(self):
        return [], self._public_config()

    def get_page(self):
        return []

    def get_api(self):
        methods = [("status", self.api_status, "GET"), ("get_config", self.api_get_config, "GET"),
                   ("save_config", self.api_save_config, "POST"), ("refresh_index", self.refresh_index, "POST"),
                   ("search", self.api_search, "POST"), ("transfer", self.api_transfer, "POST"),
                   ("check_offline", self.api_check_offline, "POST"), ("records", self.api_records, "GET"),
                   ("records_delete", self.api_records_delete, "POST"), ("cancel_task", self.api_cancel_task, "POST"),
                   ("records_verify", self.api_records_verify, "POST"),
                   ("retry_task", self.api_retry_task, "POST"), ("run_subscribe", self.run_subscribe, "POST"),
                   ("qr_start", self.api_qr_start, "GET"), ("qr_status", self.api_qr_check, "GET")]
        return [{"path": "/" + name, "endpoint": endpoint, "auth": "bear", "methods": [method], "summary": name}
                for name, endpoint, method in methods]

    @staticmethod
    def _cookie_days_left(cookie: str) -> Optional[float]:
        """从腾讯文档 Cookie 的 uid_key 里解出登录凭证的过期时间，返回剩余天数。

        uid_key 的结构是「二进制前缀 + base64(含 JWT 的文本)」，所以要先整体 base64 解码，
        再从解出的文本里取 JWT（eyJ...），最后解 payload 里的 exp。
        """
        if not cookie:
            return None
        try:
            import base64 as _b64
            import json as _json
            import re as _re
            import urllib.parse as _up
            import time as _time

            kv = dict(p.split("=", 1) for p in cookie.split("; ") if "=" in p)
            uk = _up.unquote(kv.get("uid_key") or "")
            if not uk:
                return None
            # 去掉可能多出来的 '='
            uk = uk.rstrip("=")
            if len(uk) % 4 == 1:
                uk = uk[:-1]
            try:
                text = _b64.urlsafe_b64decode(uk + "=" * (-len(uk) % 4)).decode("utf-8", "ignore")
            except Exception:  # noqa: BLE001
                text = uk
            m = _re.search(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", text) or \
                _re.search(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", uk)
            if not m:
                return None
            seg = m.group(0).split(".")[1]
            seg += "=" * (-len(seg) % 4)
            info = _json.loads(_b64.urlsafe_b64decode(seg).decode("utf-8", "ignore"))
            exp = info.get("exp")
            if not exp:
                return None
            return (float(exp) - _time.time()) / 86400
        except Exception:  # noqa: BLE001
            return None

    def api_status(self):
        self._ensure_runtime()
        index = self._ensure_index()
        summary = index.summary() if index else {}
        return {"code": 0, "data": {"version": self.plugin_version, "enabled": self._enabled,
            "cookie_ready": bool(self._tencent_cookie), "p115_ready": bool(self.get_p115_cookie()),
            "cookie_days_left": self._cookie_days_left(self._tencent_cookie),
            "record_count": summary.get("record_count", 0), "sheet_count": summary.get("sheet_count", 0),
            "built_at_text": datetime.fromtimestamp(index.built_at).strftime("%Y-%m-%d %H:%M") if index and index.built_at else "尚未建立",
            "index_errors": summary.get("errors", []), "stale_sheets": summary.get("stale_sheets", []),
            "refreshing": self._refresh_lock.locked(), "last_refresh": self._last_refresh,
            "last_subscribe": self._last_subscribe}}

    def api_get_config(self):
        return {"code": 0, "data": self._public_config()}

    def api_save_config(self, payload: dict = None):
        self._ensure_runtime()
        if not isinstance(payload, dict) or not payload:
            return {"code": 1, "msg": "没有收到配置内容"}
        with self._config_lock:
            before = self._current_config()
            try:
                merged = {**before, **{k: v for k, v in payload.items() if k in self.DEFAULTS}}
                for field in ("tencent_cookie", "p115_cookie"):
                    if "clear_" + field in payload and not isinstance(payload["clear_" + field], bool):
                        raise ValueError("清除Cookie标记必须是布尔值")
                    if payload.get("clear_" + field) is True:
                        merged[field] = ""
                    elif not payload.get(field):
                        merged[field] = before[field]
                merged = self._validate_config(merged)
                self.init_plugin(merged)
                self.update_config(merged)
                return {"code": 0, "msg": "配置已保存", "data": self._public_config()}
            except Exception as exc:
                # Validation errors leave the old scheduler intact. Revert runtime if startup failed.
                if self._current_config() != before or (before["enabled"] and not self._scheduler):
                    try:
                        self.init_plugin(before)
                        self.update_config(before)
                    except Exception:
                        logger.error("115文档：旧配置恢复失败，请检查插件设置")
                return {"code": 1, "msg": "配置未生效：" + self._error(exc)}

    def api_search(self, payload: dict = None):
        body = payload or {}
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        try:
            index = self._ensure_index()
            if not index:
                raise ValueError("本地索引尚未建立，请刷新索引")
            kw = str(body.get("keyword") or "").strip()
            if not kw:
                raise ValueError("请输入影视名称")
            data = index.search_page(kw, media_type=body.get("media_type", "all"),
                quality=body.get("quality", "all"), link_kind=body.get("link_kind", "all"),
                page=int(body.get("page", 1)), page_size=int(body.get("page_size", 10)))
            return {"code": 0, "data": data}
        except Exception as exc:
            return {"code": 1, "msg": self._error(exc)}

    def api_transfer(self, payload: dict = None):
        body = payload or {}
        with self._operation_lock:
            index = self._ensure_index()
            if not index or body.get("index_version") != index.index_version:
                return {"code": 1, "msg": "索引已更新，请重新搜索再转存"}
            rec = index.get_record(str(body.get("record_id") or ""))
            if not rec:
                return {"code": 1, "msg": "资源已失效，请重新搜索"}
            target = body.get("to", "")
            if target not in ("movie", "tv"):
                return {"code": 1, "msg": "请选择电影或电视剧目录"}
            ok, msg = self.do_transfer(rec, target)
            return {"code": 0 if ok else 1, "msg": msg}

    def api_check_offline(self):
        return self.check_offline_tasks(force=True)

    def api_records(self, limit: int = 200, verify: str = ""):
        """转存记录。

        ``verify`` 传 1/true 时**强制**用 MP 整理记录核对一次（「刷新」按钮走这里）；
        不传则按 30 秒节流顺带核对（打开页面、定时轮询走这里）。
        """
        try:
            self.verify_organization(force=str(verify).strip().lower() in ("1", "true", "yes", "force"))
            return {"code": 0, "data": self._records().list()[:max(1, min(200, int(limit)))]}
        except Exception as exc:
            return {"code": 1, "msg": self._error(exc)}

    # ---- 整理结果核对（用 MoviePilot 的「整理记录」作证据）-------------------
    def _mp_api_json(self, path: str, params: Dict[str, Any]):
        """调用 MoviePilot 自身 API（本机回环，端口自动探测，带 UA）。"""
        from app.core.config import settings
        token = (getattr(settings, "API_TOKEN", "") or "").strip()
        if not token:
            raise RuntimeError("MP未配置API_TOKEN")
        ports = list(dict.fromkeys(int(p) for p in
                                   (getattr(settings, "PORT", 0), 5000, 5001, 3000)
                                   if str(p).isdigit() and int(p)))
        last: Optional[Exception] = None
        for port in ports:
            try:
                query = urllib.parse.urlencode({"apikey": token, **params})
                req = urllib.request.Request(f"http://127.0.0.1:{port}{path}?{query}",
                                             headers={"User-Agent": "MoviePilot-Doc115Subscribe"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode())
            except Exception as exc:  # noqa: BLE001
                last = exc
        raise RuntimeError(f"调用MP接口失败：{last}")

    @staticmethod
    def _org_search_key(title: str) -> str:
        """把文档标题截成"核心片名"，用于查 MP 整理记录（MP 入库后是「片名 (年份)」）。"""
        core = re.split(r"[\[（(]|第[一二三四五六七八九十\d]+季|(?<![A-Za-z0-9])S\d{1,2}|Season",
                        str(title or ""), maxsplit=1)[0]
        return core.strip(" .-·:：")[:24]

    def _mp_transfer_entries(self, title: str) -> List[Dict[str, Any]]:
        """按片名通配符查 MP 的「整理记录」，返回条目列表。"""
        key = self._org_search_key(title)
        if not key:
            return []
        body = self._mp_api_json("/api/v1/history/transfer",
                                 {"title": f"*{key}*", "page": 1, "count": 200})
        data = body.get("data") if isinstance(body, dict) else None
        if isinstance(data, dict):
            return list(data.get("list") or [])
        return list(data) if isinstance(data, list) else []

    @staticmethod
    def _norm_org_text(text: str) -> str:
        return re.sub(r"[\s\-_.·:：!！?？,，/\\|\[\]【】（）()]", "", str(text or "")).lower()

    @staticmethod
    def _entry_episodes(entry: Dict[str, Any]) -> Optional[Tuple[int, int]]:
        """从整理记录里取 (季, 集)。"""
        for raw in (f"{entry.get('seasons') or ''}{entry.get('episodes') or ''}",
                    str(entry.get("dest") or ""),
                    str((entry.get("dest_fileitem") or {}).get("path") or "")):
            m = re.search(r"[sS](\d{1,2})[eE](\d{1,3})", raw)
            if m:
                return int(m.group(1)), int(m.group(2))
        return None

    @staticmethod
    def _record_season(title: str) -> Optional[int]:
        """从记录标题里取季号（第N季 / Sxx / Season N），取不到返回 None。"""
        t = str(title or "")
        cn = "一二三四五六七八九十"
        m = re.search(r"第([一二三四五六七八九十]+|\d+)季", t)
        if m:
            raw = m.group(1)
            if raw.isdigit():
                return int(raw)
            return cn.index(raw) + 1 if raw in cn else None
        m = re.search(r"(?<![A-Za-z0-9])[sS](\d{1,2})(?![0-9])", t)
        if m:
            return int(m.group(1))
        m = re.search(r"Season\s*(\d{1,2})", t, re.I)
        return int(m.group(1)) if m else None

    def _org_entries_for(self, rec: Dict[str, Any], title: str) -> List[Dict[str, Any]]:
        """找出**本次转存/离线下载的那批文件**对应的 MP 整理记录。

        先按片名通配符查出该片的所有整理记录（标题严格相等、且季号一致，避免
        「飞驰人生」误配「飞驰人生3」）；若记录里知道 `item_name`，再用 MP 记录里的
        **源路径 `src`** 收窄到「本次这批文件」——这是判断"本次资源是否整理完成"的关键。
        """
        entries = self._mp_transfer_entries(title)
        mine = self._norm_org_text(self._org_search_key(title))
        if not mine:
            return []
        want_season = self._record_season(title)
        ours = []
        for e in entries:
            e_norm = self._norm_org_text(e.get("title") or "")
            e_norm_noyear = re.sub(r"(?:18|19|20|21)\d{2}$", "", e_norm)
            if not (e_norm == mine or e_norm_noyear == mine):
                continue
            ep = self._entry_episodes(e)
            if want_season is not None and ep and ep[0] != want_season:
                continue
            ours.append(e)
        # 用源路径锁定"本次这批文件"
        name = str(rec.get("item_name") or "").strip()
        final = str(rec.get("final_path") or "").strip()
        if name and final:
            prefix = f"{final.rstrip('/')}/{name}"
            narrowed = [e for e in ours
                        if str(e.get("src") or (e.get("src_fileitem") or {}).get("path") or "")
                        .startswith(prefix)]
            if narrowed:
                return narrowed
        return ours

    def verify_organization(self, force: bool = False) -> Dict[str, Any]:
        """核对「**本次转存/离线下载的资源**是否已经整理完成」——以 MP 的整理记录为证据。

        判定（只看"这批文件"本身是否已被整理，不判断剧集是否完整）：
          * 找到成功记录 → 「整理完成」，记下入库路径与已入库文件数，置 `organization_confirmed`；
          * 有成功也有失败 → 「部分整理失败」，带上失败原因；
          * 全部失败 → 「整理失败」，带上原因与阶段；
          * 查不到任何记录 → 保持原状（说明尚未被受理/仍在整理，或这本就是旧记录）。
        """
        store = self._records()
        now = time.time()
        if not force and now - self._org_check_ts < 30:
            return {"skipped": True}
        self._org_check_ts = now
        checked = confirmed = failed = partial = 0
        for rec in store.list():
            if rec.get("organization_confirmed") or rec.get("status") == "failed":
                continue
            if rec.get("status") not in ("done", "unverified", "organized", "partial",
                                         "awaiting_move", "moving", "missing"):
                continue
            if checked >= 10:
                break
            title = str(rec.get("title") or "").strip()
            if not title:
                continue
            checked += 1
            try:
                ours = self._org_entries_for(rec, title)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"115文档订阅与查询：读取MP整理记录失败：{exc}")
                break
            if not ours:
                continue                      # 本批资源还没有整理记录 → 保持"待确认"
            ok_entries = [e for e in ours if e.get("status") is True]
            bad_entries = [e for e in ours if e.get("status") is False]
            dest = str((ok_entries or ours)[0].get("dest") or "")[:140]
            tail = f"｜{dest}" if dest else ""
            if ok_entries:
                # 有成功记录 = 本次这批资源已经整理入库（个别文件失败只作备注，不影响"完成"结论）
                confirmed += 1
                note = ""
                if bad_entries:
                    partial += 1
                    note = f"（另有 {len(bad_entries)} 个文件整理失败：{str(bad_entries[0].get('errmsg') or '未知原因')[:60]}）"
                store.update(rec["id"], status="organized", organization_confirmed=True,
                             organized_at=now, organized_count=len(ok_entries),
                             organized_failed=len(bad_entries),
                             message=f"整理完成：本次资源已入库 {len(ok_entries)} 个文件{note}{tail}")
                logger.info(f"115文档订阅与查询：整理完成（MP整理记录确认）：{title}｜"
                            f"{len(ok_entries)} 个文件、失败 {len(bad_entries)} 个｜{dest}")
            else:
                failed += 1
                bad = bad_entries[0]
                reason = str(bad.get("errmsg") or "未知原因")
                stage = str(bad.get("failure_stage") or "-")
                store.update(rec["id"], status="failed",
                             message=f"整理失败：{reason[:100]}（阶段 {stage}，"
                                     f"重试 {bad.get('retry_count') or 0} 次）")
        if checked:
            logger.info(f"115文档订阅与查询：整理核对：检查 {checked} 条，完成 {confirmed} 条，"
                        f"部分失败 {partial} 条，失败 {failed} 条")
        return {"checked": checked, "confirmed": confirmed, "partial": partial, "failed": failed}

    def api_records_verify(self):
        with self._operation_lock:
            try:
                return {"code": 0, "data": self.verify_organization(force=True)}
            except Exception as exc:
                return {"code": 1, "msg": self._error(exc)}

    def api_records_delete(self, payload: dict = None):
        with self._operation_lock:
            try:
                return self.delete_record(str((payload or {}).get("id") or ""))
            except Exception as exc:
                return {"code": 1, "msg": self._error(exc)}

    def api_cancel_task(self, payload: dict = None):
        with self._operation_lock:
            rec_id = str((payload or {}).get("id") or "")
            task = next((x for x in self._pending().list() if x.get("record_id") == rec_id), None)
            if not task:
                return {"code": 1, "msg": "没有正在跟踪的任务"}
            self._pending().delete(task["hash"])
            self._records().update(rec_id, status="cancelled", message="已停止自动搬运；115下载与文件不受影响")
            self._set_subscription(task.get("subscription_key"), status="cancelled")
            return {"code": 0, "msg": "已停止跟踪，未取消115下载或删除文件"}

    def api_retry_task(self, payload: dict = None):
        with self._operation_lock:
            rec = next((x for x in self._records().list() if x.get("id") == (payload or {}).get("id")), None)
            if not rec or rec.get("status") not in ("failed", "missing", "cancelled"):
                return {"code": 1, "msg": "该记录不需要重试"}
            candidate = {**rec, "links": [(rec["kind"], rec["url"])], "_subscription_key": rec.get("subscription_key", "")}
            ok, msg = self.do_transfer(candidate, rec.get("type", "movie"), force=True)
            if ok and candidate["_subscription_key"]:
                self._set_subscription(candidate["_subscription_key"], status="pending")
                self._complete_subscription_if_ready(candidate["_subscription_key"])
            return {"code": 0 if ok else 1, "msg": msg}

    def api_qr_start(self, force: bool = False):
        self._ensure_runtime()
        with self._config_lock, self._qr_lock:
            if not force and self._qr and self._qr_img and time.time() - self._qr_ts < self.QR_FRESH_SECONDS:
                return {"code": 0, "data": {"qr_base64": "data:image/png;base64," + base64.b64encode(self._qr_img).decode(),
                                               "session_id": self._qr.session_id, "cached": True}}
            qr = None
            try:
                if self._qr:
                    self._qr.close()
                self._qr, self._qr_img = None, b""
                qr = BrowserQrLogin(self._doc_url)
                shot, already, cost = qr.start()
                self._qr = qr
                if already:
                    return self._finish_qr(qr.check())
                self._qr_img, self._qr_ts = shot, time.time()
                return {"code": 0, "data": {"qr_base64": "data:image/png;base64," + base64.b64encode(shot).decode(),
                                               "session_id": qr.session_id, "cost": round(cost, 1)}}
            except Exception as exc:
                failed_qr = self._qr or qr
                if failed_qr:
                    failed_qr.close()
                self._qr, self._qr_img = None, b""
                return {"code": 1, "msg": self._error(exc)}

    def _finish_qr(self, state):
        cookie = state.get("cookie") or ""
        if not cookie:
            return {"code": 1, "msg": "没有获取到有效登录Cookie，请重试"}
        with self._config_lock:
            self._tencent_cookie = cookie
            self.update_config(self._current_config())
        self._qr.close()
        self._qr, self._qr_img = None, b""
        threading.Thread(target=self.refresh_index, daemon=True, name="doc115-index-after-login").start()
        return {"code": 0, "data": {"state": "confirmed", "cookie_saved": True, "index_refreshing": True}}

    def api_qr_check(self, session_id: str = ""):
        self._ensure_runtime()
        with self._config_lock, self._qr_lock:
            if not self._qr or session_id != self._qr.session_id:
                return {"code": 1, "msg": "扫码会话已变化，请重新获取二维码", "data": {"state": "expired"}}
            state = self._qr.check() or {}
            if state.get("state") == "confirmed":
                return self._finish_qr(state)
            data = {k: v for k, v in state.items() if k != "cookie"}
            return {"code": 1 if data.get("state") == "error" else 0, "msg": data.get("msg", ""), "data": data}
