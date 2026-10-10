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
from .runtime import TaskRuntime
from .permissions import protect_endpoint
from .doc_client import DocError, TencentDocsClient
from .doc_index import DocIndex
from .history import RecordStore, PendingStore, JsonListStore
from .link_router import LINK_115_SHARE, LINK_ED2K, LINK_MAGNET, classify_link
from .p115_transfer import P115Error, P115Transfer, extract_hash
from .qrlogin_browser import BrowserQrLogin, QrLoginError


def _transfer_event(name):
    try:
        try:
            from app.sdk.events import eventmanager
        except ImportError:
            from app.core.event import eventmanager
        from app.schemas.types import EventType
        return eventmanager.register(getattr(EventType, name))
    except (ImportError, AttributeError):
        return lambda callback: callback


class Doc115Subscribe(TaskRuntime, _PluginBase):
    plugin_name = "115文档订阅与查询"
    plugin_desc = "腾讯文档跨表搜索、电影订阅与115分享/离线任务管理。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "0.11.0"
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
        "subscribe_enabled": False, "subscribe_cron": "0 21 * * *",
        "index_cron": "0 6 * * *", "create_subdir": True,
        "link_mode": "first", "upgrade_enabled": False,
        "min_media_size_mb": 10,
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

    @_transfer_event("TransferComplete")
    @_transfer_event("TransferFailed")
    def on_transfer_result(self, event):
        self._receive_event(event)

    def _ensure_runtime(self):
        with self._runtime_lock:
            if not hasattr(self, "_operation_lock"):
                self._operation_lock = threading.RLock()
                self._transfer_local = threading.local()
                self._config_lock = threading.RLock()
                self._refresh_lock = threading.Lock()
                self._subscribe_lock = threading.Lock()
                self._offline_lock = threading.Lock()
                self._org_lock = threading.Lock()
                self._ledger_instance = None
                self._mp_instance = None
                self._subscriptions_cache = None
                self._subscriptions_cursor = None
                self._qr_lock = threading.RLock()
                self._generation = 0
                self._tr = None
                self._tr_cookie = ""
                self._mt_cache = {}
                self._qr_img = b""
                self._qr_ts = 0.0
                self._last_refresh = {}
                self._last_subscribe = {}

    @classmethod
    def _validate_config(cls, config):
        conf = {k: config.get(k, v) for k, v in cls.DEFAULTS.items()}
        for k, default in cls.DEFAULTS.items():
            if isinstance(default, bool):
                if not isinstance(conf[k], bool):
                    raise ValueError(f"{k} 必须是布尔值")
            elif isinstance(default, int):
                if isinstance(conf[k], bool) or not isinstance(conf[k], int) or not 0 <= conf[k] <= 1024:
                    raise ValueError(f"{k} 必须是 0 到 1024 的整数")
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
        staging = conf["magnet_staging_path"]
        for field, label in (("movie_path", "电影下载目录"), ("tv_path", "电视剧下载目录")):
            other = conf[field]
            if staging == other or staging.startswith(other + "/") or other.startswith(staging + "/"):
                raise ValueError(f"磁力暂存目录不能与{label}相同或互相嵌套（MP 会把暂存中的文件当成待整理文件）")
        if conf["link_mode"] not in ("first", "all"):
            raise ValueError("链接策略必须是 first 或 all")
        return conf

    def init_plugin(self, config: dict = None):
        self._ensure_runtime()
        conf = self._validate_config({**self.DEFAULTS, **(config or {})})
        with self._config_lock, self._qr_lock:
            self.stop_service()
            self._generation += 1
            for key, val in conf.items():
                setattr(self, "_" + key, val)
            self._tr, self._tr_cookie = None, ""
            self._mt_cache = {}
            self._mp_instance = None
            self._subscriptions_cache = None
            self._subscriptions_cursor = None
            self._directories_cache = None
            self._directories_next_ts = 0
            self._directories_error = ""
            self._index = None
            self._load_index()
            self._refresh_event_paths(force=True)
            # 启动迁移/清理：旧版本写坏的事件直接 ack、旧 inbox 行与超量证据清理（不删除任务批次）
            self._maintain_ledger(force=True)
            if not self._enabled:
                return
            scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
            options = {"max_instances": 1, "coalesce": True, "misfire_grace_time": 300}
            scheduler.add_job(self.refresh_index,
                trigger=CronTrigger.from_crontab(self._index_cron, timezone="Asia/Shanghai"),
                id="doc115-index", name="115文档刷新索引", **options)
            if self._subscribe_enabled:
                # cron 只排队，由离线 worker 执行（失败有退避重试，不会因 MP 读取锁冲突直接失败）
                scheduler.add_job(self.queue_subscribe_job,
                    trigger=CronTrigger.from_crontab(self._subscribe_cron, timezone="Asia/Shanghai"),
                    id="doc115-subscribe", name="115文档电影订阅", **options)
            scheduler.add_job(self.check_offline_tasks, trigger=IntervalTrigger(seconds=2),
                              id="doc115-offline", name="115文档离线搬运", **options)
            # 后台自动核对「本次资源是否已整理入库」：只调本机 MP 的整理记录接口，不访问 115。
            scheduler.add_job(self.check_organization, trigger=IntervalTrigger(seconds=20),
                              id="doc115-organize", name="115文档整理核对", **options)
            self._scheduler = scheduler
            try:
                scheduler.start()
            except Exception:
                self.stop_service()
                raise

    def stop_service(self):
        self._ensure_runtime()
        with self._config_lock, self._qr_lock:
            self._stop_service_locked()

    def _stop_service_locked(self):
        self._enabled = False
        self._generation += 1
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
        """迁移前旧版待搬运 JSON（只读兼容/测试用）；业务逻辑一律查 SQLite 账本。"""
        return PendingStore(self.pending_path)


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
        self._tr.attach_state(self.get_data_path_local() / ("115-budget-" + self._account_key()[:16] + ".json"))
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
        generation = self._generation
        try:
            with self._mp().work_slice(cancelled=lambda: not self._live(generation)):
                index = self._ensure_index()
                if not index or not index.records:
                    raise ValueError("索引为空，请刷新索引")
                subs = []
                for raw in self._mp_subscribes():
                    if raw.get("type") != "电影":
                        continue
                    if raw.get("state") not in (None, "", "N", "R"):
                        continue
                    sub = self._normalise_subscription(raw)
                    subs.append(sub)
                data = {"movie_subs": len(subs), "matched": 0, "transferred": 0, "skipped": 0, "failed": 0, "errors": []}
                records = subscribe_sync.SubscriptionMatcher(index.records)
                states = {x["key"]: x for x in self._subscription_store().list()}
                legacy_path = self.get_data_path_local() / "subscribed.json"
                legacy = set(json.loads(legacy_path.read_text(encoding="utf8"))) if legacy_path.exists() else set()
                for sub in subs:
                    if not self._live(generation):
                        break
                    self._last_transfer_result = {"resource_keys": [], "required_resources": [], "uncertain": False}
                    plan = self._subscription_plan(records, sub, states, legacy)
                    candidates, key, state = plan["candidates"], plan["key"], plan["state"]
                    if not candidates:
                        continue
                    if plan.get("completed_score") is not None and state.get("completed_quality_score") is None:
                        self._set_subscription(key, completed_quality_score=plan["completed_score"])
                    if plan["status"] == "skipped":
                        data["skipped"] += 1
                        if state.get("status") == "failed":
                            data["errors"].append(f"{sub['title']}：{plan['reason']}")
                        continue
                    data["matched"] += 1
                    if plan["status"] == "blocked":
                        data["failed"] += 1
                        data["errors"].append(f"{sub['title']}：{plan['reason']}")
                        if plan["reason"] == "没有符合类型和订阅规则的可用资源":
                            self._set_subscription(key, status="failed", fingerprint=self._fingerprint(candidates[0]),
                                                   target_quality_score=doc_parser.quality_score(candidates[0]), required_resources=[])
                        continue
                    eligible = plan["eligible"]
                    failures, accepted = [], None
                    for candidate_pos, candidate in enumerate(eligible):
                        if not self._matches_rules(candidate, sub):
                            continue
                        if (candidate.get("media_type") or doc_parser.media_type_of(candidate.get("sheet", ""), candidate.get("title", ""))) != "movie":
                            continue
                        candidate = {**candidate, "_subscription_key": key, "_fallback_candidates": eligible[candidate_pos + 1:]}
                        ok, msg = self.do_transfer(candidate, to="movie")
                        if ok:
                            accepted = self._last_transfer_result.get("actual_candidate") or candidate
                            break
                        failures.append(msg)
                        if self._last_transfer_result.get("uncertain"):
                            break
                        if self._link_mode == "all" and any(x.get("subscription_key") == key and self._is_tracking(x)
                                                            for x in self._records().tracked()):
                            break
                    if accepted:
                        data["transferred"] += 1
                        active = any(x.get("subscription_key") == key and x.get("acquisition_status") not in ("failed", "saved", "success") and x.get("tracking_enabled", True) for x in self._records().list(limit=None, include_hidden=True))
                        self._set_subscription(key, status="pending" if active else "complete",
                                               fingerprint=self._fingerprint(accepted), quality_score=self._last_transfer_result.get("quality_score", doc_parser.quality_score(accepted)),
                                               target_quality_score=self._last_transfer_result.get("quality_score", doc_parser.quality_score(accepted)),
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
                   ("save_config", self.api_save_config, "POST"), ("refresh_index", self.api_refresh_index, "POST"),
                   ("search", self.api_search, "POST"), ("transfer", self.api_transfer, "POST"),
                   ("records", self.api_records, "GET"),
                   ("records_delete", self.api_records_delete, "POST"), ("records_bulk", self.api_records_bulk, "POST"),
                   ("records_verify", self.api_records_verify, "POST"), ("run_subscribe", self.api_run_subscribe, "POST"),
                   ("subscriptions_preview", self.api_subscriptions_preview, "GET"),
                   ("diagnostics", self.api_diagnostics, "GET"), ("directories", self.api_directories, "GET"),
                   ("task_action", self.api_task_action, "POST"),
                   ("qr_start", self.api_qr_start, "GET"), ("qr_status", self.api_qr_check, "GET")]
        return [{"path": "/" + name, "endpoint": protect_endpoint(endpoint), "auth": "bear", "methods": [method], "summary": name}
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
            "subscribe_enabled": self._subscribe_enabled, "movie_path": self._movie_path, "tv_path": self._tv_path,
            "cookie_ready": bool(self._tencent_cookie), "p115_ready": bool(self.get_p115_cookie()),
            "cookie_days_left": self._cookie_days_left(self._tencent_cookie),
            "record_count": summary.get("record_count", 0), "sheet_count": summary.get("sheet_count", 0),
            "built_at_text": datetime.fromtimestamp(index.built_at).strftime("%Y-%m-%d %H:%M") if index and index.built_at else "尚未建立",
            "index_errors": summary.get("errors", []), "stale_sheets": summary.get("stale_sheets", []),
            "refreshing": self._refresh_lock.locked(), "last_refresh": self._last_refresh,
            "last_subscribe": self._last_subscribe, "stats": self.records_stats(), "jobs": self.jobs_view()}}

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
            sort = str(body.get("sort") or "relevance")
            if sort not in ("relevance", "year_desc", "year_asc", "quality"):
                raise ValueError("排序方式无效")
            options = dict(media_type=body.get("media_type", "all"),
                quality=body.get("quality", "all"), subtitle=body.get("subtitle", "all"), link_kind=body.get("link_kind", "all"),
                page=int(body.get("page", 1)), page_size=int(body.get("page_size", 10)))
            try:
                data = index.search_page(kw, sort=sort, **options)
            except TypeError:
                # 兼容尚未支持 sort 参数的 DocIndex.search_page
                data = index.search_page(kw, **options)
            return {"code": 0, "data": data}
        except Exception as exc:
            return {"code": 1, "msg": self._error(exc)}


    # ---- 整理结果核对（用 MoviePilot 的「整理记录」作证据）-------------------


    def api_qr_start(self, force: bool = False):
        self._ensure_runtime()
        with self._config_lock, self._qr_lock:
            if not force and self._qr and self._qr_img and time.time() - self._qr_ts < self.QR_FRESH_SECONDS:
                return {"code": 0, "data": {"qr_base64": "data:image/png;base64," + base64.b64encode(self._qr_img).decode(),
                                               "session_id": self._qr.session_id, "cached": True}}
            old, self._qr, self._qr_img = self._qr, None, b""
            doc_url, generation = self._doc_url, self._generation
            attempt = self._qr_attempt = getattr(self, "_qr_attempt", 0) + 1
        # 浏览器启动/出码最长约 180 秒：等待期间不持有任何插件锁，避免阻塞配置与其它接口。
        if old:
            old.close()
        qr = None
        try:
            qr = BrowserQrLogin(doc_url)
            shot, already, cost = qr.start()
        except Exception as exc:
            if qr:
                qr.close()
            return {"code": 1, "msg": self._error(exc)}
        with self._config_lock, self._qr_lock:
            if attempt == self._qr_attempt and generation == self._generation:
                self._qr = qr
                if already:
                    return self._finish_qr(qr.check())
                self._qr_img, self._qr_ts = shot, time.time()
                return {"code": 0, "data": {"qr_base64": "data:image/png;base64," + base64.b64encode(shot).decode(),
                                               "session_id": qr.session_id, "cost": round(cost, 1)}}
        qr.close()
        return {"code": 1, "msg": "扫码会话已被新的请求或配置更新替换，请重新获取二维码"}

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
