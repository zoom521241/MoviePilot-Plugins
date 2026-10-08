"""115文档订阅与查询（MoviePilot V3 插件）

功能
----
1. **订阅下载（仅电影）**：定时读取腾讯文档「最新电影（持续更新）」表，与 MP 订阅比对，
   命中后把资源转存到 115 网盘的电影下载目录。
2. **查找**：插件页搜索框，跨文档所有工作表搜索片名，展示结果并标注电影/电视剧，
   选中后一键转存（可手动指定电影/电视剧目录）。
3. 文档地址可配置；115 Cookie 复用「115网盘Plus」(P115Disk) 插件；
   插件页提供**微信扫码登录**，扫码后自动固定保存腾讯文档 Cookie。

链接分派：115 分享链接 -> 115 转存；磁力 / ed2k -> 115 离线下载。
文档不允许导出，本插件改用文档前端自身的 dop-api 接口直读（见 doc_client）。
"""
from __future__ import annotations

import base64
import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import MediaType

try:
    from app.schemas.types import MessageType as _MsgType
except ImportError:  # V2 回退
    from app.schemas.types import NotificationType as _MsgType

try:
    from . import doc_parser, subscribe_sync
    from .doc_client import DocError, TencentDocsClient
    from .doc_index import DocIndex
    from .history import RecordStore
    from .link_router import LINK_115_SHARE, LINK_ED2K, LINK_MAGNET
    from .p115_transfer import P115Error, P115Transfer, extract_hash
    from .qrlogin_browser import BrowserQrLogin, QrLoginError
except ImportError:
    import doc_parser
    import subscribe_sync
    from doc_client import DocError, TencentDocsClient
    from doc_index import DocIndex
    from history import RecordStore
    from link_router import LINK_115_SHARE, LINK_ED2K, LINK_MAGNET
    from p115_transfer import P115Error, P115Transfer, extract_hash
    from qrlogin_browser import BrowserQrLogin, QrLoginError


class Doc115Subscribe(_PluginBase):
    # ---- 插件元信息 ---------------------------------------------------------
    plugin_name = "115文档订阅与查询"
    plugin_desc = "从腾讯文档追更表读取资源：定时为电影订阅转存到115，并支持插件内跨表搜索转存。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "0.7.1"
    plugin_author = "zoom521241"
    author_url = "https://github.com/zoom521241"
    plugin_config_prefix = "doc115subscribe_"
    plugin_order = 20
    auth_level = 1

    # ---- 默认配置 ----------------------------------------------------------
    _enabled = False
    _doc_url = "https://docs.qq.com/sheet/DZWtEeFFGZW9XUkJo"
    _tencent_cookie = ""
    _p115_cookie = ""
    _movie_path = "/115-影视/115-downloads/电影"
    _tv_path = "/115-影视/115-downloads/电视剧"
    # 磁力/ed2k 先落这个暂存目录，下载完成后再由插件搬到上面的电影/电视剧目录
    _magnet_staging_path = "/115-影视/115-downloads/磁力链接"
    _subscribe_enabled = True
    _subscribe_cron = "0 21 * * *"
    _index_cron = "0 6 * * *"
    _use_agent = True
    _create_subdir = True      # 转存时按「片名 (年份)」建子目录

    _scheduler: Optional[BackgroundScheduler] = None
    _index: Optional[DocIndex] = None
    _qr: Optional[BrowserQrLogin] = None
    _qr_img: bytes = b""          # 预热好的二维码（PNG）
    _qr_ts: float = 0.0            # 预热时间
    _qr_lock: Any = None
    _qr_img: str = ""
    _search_results: List[Dict[str, Any]] = []
    _page_msg: str = ""
    _mt_cache: Dict[str, str] = {}
    _tr: Any = None            # 缓存的 115 操作句柄
    _tr_cookie: str = ""       # 缓存对应的 Cookie
    _offline_next_ts: float = 0.0    # 下一次允许检查离线任务的时间戳（节流）
    _offline_change_ts: float = 0.0  # 上次进度发生变化的时间戳（用于死种退避）

    # ---------------------------------------------------------------------
    def init_plugin(self, config: dict = None):
        self._enabled = False
        self._scheduler = None
        self._index = None
        self._qr = None
        self._qr_img = b""
        self._qr_ts = 0.0
        self._qr_lock = threading.Lock()
        self._search_results = []
        self._page_msg = ""
        self._tr = None
        self._tr_cookie = ""
        self._offline_next_ts = 0.0
        self._offline_change_ts = 0.0
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._doc_url = config.get("doc_url") or self.__class__._doc_url
            self._tencent_cookie = config.get("tencent_cookie") or ""
            self._p115_cookie = config.get("p115_cookie") or ""
            self._movie_path = config.get("movie_path") or self.__class__._movie_path
            self._tv_path = config.get("tv_path") or self.__class__._tv_path
            self._magnet_staging_path = (
                config.get("magnet_staging_path") or self.__class__._magnet_staging_path
            )
            self._subscribe_enabled = bool(config.get("subscribe_enabled", True))
            self._subscribe_cron = config.get("subscribe_cron") or self.__class__._subscribe_cron
            self._index_cron = config.get("index_cron") or self.__class__._index_cron
            self._use_agent = bool(config.get("use_agent", True))
            self._create_subdir = bool(config.get("create_subdir", True))

        self.stop_service()
        self._load_index()

        if not self._enabled:
            logger.info("115文档订阅与查询：插件未启用")
            return

        self._scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
        self._scheduler.add_job(
            self.refresh_index,
            trigger=CronTrigger.from_crontab(self._index_cron, timezone="Asia/Shanghai"),
            name="115文档订阅与查询-刷新索引",
        )
        if self._subscribe_enabled:
            self._scheduler.add_job(
                self.run_subscribe,
                trigger=CronTrigger.from_crontab(self._subscribe_cron, timezone="Asia/Shanghai"),
                name="115文档订阅与查询-订阅同步",
            )
        self._scheduler.add_job(
            self.check_offline_tasks,
            trigger=IntervalTrigger(seconds=15),
            name="115文档订阅与查询-离线任务整理",
        )
        self._scheduler.start()
        logger.info("115文档订阅与查询：已启用，定时任务已注册")

    # ---- 基础 --------------------------------------------------------------
    def get_state(self) -> bool:
        return bool(self._enabled and self._tencent_cookie)

    # 本插件未单独填 115 Cookie 时，按顺序复用其它 115 插件的已保存 Cookie
    _P115_COOKIE_SOURCES = (
        ("plugin.P115StrmHelper", "cookies"),   # 115网盘STRM助手
        ("plugin.P115Disk", "cookie"),          # 115网盘储存（115网盘Plus）
        ("plugin.P115StrgmSub", "cookies"),     # 115网盘订阅追更
    )

    def get_p115_cookie(self) -> str:
        """115 Cookie：本插件配置优先，否则复用其它 115 插件已保存的 Cookie。"""
        if self._p115_cookie:
            return self._p115_cookie
        try:
            from app.db.systemconfig_oper import SystemConfigOper
            oper = SystemConfigOper()
            for key, field in self._P115_COOKIE_SOURCES:
                cfg = oper.get(key) or {}
                if isinstance(cfg, dict):
                    val = (cfg.get(field) or "").strip()
                    if val:
                        logger.debug(f"115文档订阅与查询：复用 {key}.{field} 的 115 Cookie")
                        return val
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"115文档订阅与查询：读取其它插件 115 Cookie 失败：{exc}")
        return ""

    def _current_config(self) -> Dict[str, Any]:
        return {
            "enabled": self._enabled,
            "doc_url": self._doc_url,
            "tencent_cookie": self._tencent_cookie,
            "p115_cookie": self._p115_cookie,
            "movie_path": self._movie_path,
            "tv_path": self._tv_path,
            "magnet_staging_path": self._magnet_staging_path,
            "subscribe_enabled": self._subscribe_enabled,
            "subscribe_cron": self._subscribe_cron,
            "index_cron": self._index_cron,
            "use_agent": self._use_agent,
            "create_subdir": self._create_subdir,
        }

    def resolve_media_type(self, rec: Dict[str, Any]) -> str:
        """判定电影/电视剧：**TMDBID 精准识别** > 工作表名 > 片名特征。"""
        tmdbid = str(rec.get("tmdbid") or "").strip()
        if tmdbid.isdigit():
            if tmdbid in self._mt_cache:
                return self._mt_cache[tmdbid]
            try:
                from app.chain.media import MediaChain
                media = MediaChain().recognize_media(tmdbid=int(tmdbid))
                if media and media.type:
                    mt = "movie" if media.type == MediaType.MOVIE else "tv"
                    self._mt_cache[tmdbid] = mt
                    return mt
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"115文档订阅与查询：TMDBID {tmdbid} 识别失败：{exc}")
        return doc_parser.media_type_of(rec.get("sheet", ""), rec.get("title", ""))

    def get_data_path_local(self) -> Path:
        return Path(self.get_data_path())

    @property
    def index_path(self) -> Path:
        return self.get_data_path_local() / "doc_index.json"

    def _new_client(self) -> TencentDocsClient:
        doc_id, _ = TencentDocsClient.parse_doc_id(self._doc_url)
        return TencentDocsClient(doc_id, self._tencent_cookie)

    def _load_index(self):
        self._index = DocIndex.load(self.index_path)
        if self._index and not self._index.client:
            self._index.client = self._new_client()
        if self._index:
            logger.info(f"115文档订阅与查询：已加载本地索引 {self._index.summary()}")

    # ---- 索引 --------------------------------------------------------------
    @property
    def pending_path(self):
        return self.get_data_path_local() / "pending_offline.json"

    def _load_pending(self) -> List[Dict[str, Any]]:
        try:
            p = self.pending_path
            if p.exists():
                return json.loads(p.read_text(encoding="utf-8")) or []
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"115文档订阅与查询：读取待整理离线任务失败：{exc}")
        return []

    def _save_pending(self, items: List[Dict[str, Any]]) -> None:
        try:
            self.pending_path.parent.mkdir(parents=True, exist_ok=True)
            self.pending_path.write_text(
                json.dumps(items, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"115文档订阅与查询：保存待整理离线任务失败：{exc}")

    # ---- 转存/离线记录（详情页「转存记录」页）------------------------------
    @property
    def history_path(self):
        return self.get_data_path_local() / "history.json"

    def _records(self) -> RecordStore:
        return RecordStore(self.history_path)

    def add_pending_offline(self, rec: Dict[str, Any], target: str,
                            submit_path: str, final_path: str, url: str) -> Optional[str]:
        """登记离线任务：磁力/ed2k 先落暂存目录，下载完成后再搬到最终目录。"""
        h = extract_hash(url)
        if not h:
            return None
        items = self._load_pending()
        if not any(i.get("hash") == h for i in items):
            items.append({
                "hash": h,
                "title": rec.get("title"),
                "year": rec.get("year"),
                "type": "movie" if target == "movie" else "tv",
                "staging_path": submit_path,   # 实际提交/落盘目录
                "final_path": final_path,      # 下载完成后要搬到的目录
                "url": url,
                "added_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            self._save_pending(items)
        # 有新任务 → 让检查立刻开始（不受节流影响）
        self._offline_next_ts = 0.0
        self._offline_change_ts = 0.0
        logger.info(f"115文档订阅与查询：已登记离线任务（先落 {submit_path}，"
                    f"完成后搬到 {final_path}）：{rec.get('title')} [{h[:12]}]")
        return h

    def _process_offline(self, tr, store: RecordStore) -> Dict[str, Any]:
        """检查离线任务：**已下完且已落盘**的，从暂存目录搬到最终目录。

        返回 ``{"pending", "finished", "moved", "maxpct", "changed"}``。
        整理由 115 生活事件驱动（搬到 电影/电视剧 目录这个动作本身就是事件），本插件不写 MP 下载历史。
        """
        items = self._load_pending()
        if not items:
            return {"pending": 0, "finished": 0, "moved": 0, "maxpct": 0, "changed": False}
        tasks = tr.list_tasks()
        by_hash: Dict[str, Dict[str, Any]] = {}
        for t in tasks:
            h = str(t.get("info_hash") or "").lower()
            if h:
                by_hash[h] = t

        moved, finished, remain = 0, 0, []
        maxpct, changed = 0, False
        for it in items:
            h = str(it.get("hash") or "").lower()
            t = by_hash.get(h) or {}
            try:
                pct = int(float(t.get("percentDone") or 0))
            except (TypeError, ValueError):
                pct = 0
            maxpct = max(maxpct, pct)
            if pct != it.get("last_pct"):
                changed = True
                it["last_pct"] = pct
            name = str(t.get("name") or "")
            staging = str(it.get("staging_path") or "")
            final = str(it.get("final_path") or "")

            if pct < 100:
                self._update_record(store, h, status="downloading", progress=pct)
                remain.append(it)
                continue

            # 100% —— 必须校验文件**真的落盘**到暂存目录（115 偶发"任务完成但文件未落盘"）
            src = f"{staging}/{name}" if (staging and name) else ""
            if not src or not tr.path_exists(src):
                self._update_record(
                    store, h, status="downloading", progress=100,
                    message="离线任务显示已完成，但文件未出现在暂存目录："
                            "若是重复提交同一种子，115 会去重且不会重新下载，文件不会再产生")
                remain.append(it)
                continue

            self._update_record(store, h, status="moving", progress=100)
            ok, err = tr.move_via_p115disk(src, final)
            if ok:
                moved += 1
                finished += 1
                self._update_record(store, h, status="done", progress=100,
                                    message=f"已搬到 {final}，等待 115 整理",
                                    item_name=name, moved_at=time.time())
                logger.info(f"115文档订阅与查询：离线下载完成并已搬到最终目录（等待 115 整理）："
                            f"{it.get('title')} -> {final}")
            else:
                self._update_record(store, h, status="failed", progress=100, message=err)
                logger.warning(f"115文档订阅与查询：离线文件搬运失败 {it.get('title')}：{err}")
                remain.append(it)
        if moved or finished or changed:
            self._save_pending(remain)
        return {"pending": len(remain), "finished": finished, "moved": moved,
                "maxpct": maxpct, "changed": changed}

    def check_offline_tasks(self, force: bool = False) -> Dict[str, Any]:
        """检查离线任务并按需搬运（**自适应节流**，避免频繁访问 115）。

        * 没有待搬运任务时：直接返回，**一次 115 请求都不发**；
        * 有任务时按进度自适应间隔：下载中 90s、接近完成(≥99%) 15s、进度 10 分钟没变化 300s；
        * ``force=True``（按钮 / 刚提交转存）忽略节流立即检查。
        """
        now = time.time()
        if not force and now < self._offline_next_ts:
            return {"code": 0, "data": {"skipped": 1}}
        tr = self._transfers()
        if not tr:
            return {"code": 1, "msg": "未配置 115 Cookie"}
        try:
            data = self._process_offline(tr, self._records())
        except Exception as exc:  # noqa: BLE001
            self._offline_next_ts = now + 300          # 出错退避 5 分钟
            return {"code": 1, "msg": f"查询 115 离线任务失败：{exc}"}

        if not data.get("pending"):
            # 搬完就停：没有待处理任务 → 不再设置下一次检查（也就不会再请求 115）
            self._offline_next_ts = 0
            self._offline_change_ts = 0
        else:
            if data.get("changed"):
                self._offline_change_ts = now
            elif not self._offline_change_ts:
                self._offline_change_ts = now
            stalled = self._offline_change_ts and (now - self._offline_change_ts) > 600
            if stalled:
                interval = 300                          # 10 分钟没动静 → 死种退避，5 分钟一问
            elif data.get("maxpct", 0) >= 99:
                interval = 15                           # 快下完了 → 加密，下完立刻搬
            else:
                interval = 90                           # 下载中 → 90 秒一问
            self._offline_next_ts = now + interval
            logger.debug(f"115文档订阅与查询：离线检查下一次将于 {interval}s 后（"
                         f"pending={data['pending']} maxpct={data['maxpct']} stalled={bool(stalled)}）")
        return {"code": 0, "data": data}

    @staticmethod
    def _update_record(store: RecordStore, info_hash: str, **fields: Any) -> None:
        rec = store.find_by_hash(info_hash)
        if rec:
            store.update(rec["id"], **fields)

    def _refresh_organized(self, store: RecordStore) -> None:
        """回填「已整理」状态：已搬到最终目录的条目，若文件已不在下载目录 → 说明 115 整理完成。

        只在**打开记录页**时跑（用户主动看），不改后台"搬完即停"的节流策略；
        只检查最近 6 小时内搬过去的、且知道文件名的条目。
        """
        tr = self._transfers()
        if not tr:
            return
        now = time.time()
        checked = 0
        for r in store.list():
            if r.get("status") != "done":
                continue
            name = str(r.get("item_name") or "")
            final = str(r.get("final_path") or "")
            moved_at = float(r.get("moved_at") or 0)
            if not name or not final or not moved_at:
                continue                      # 115 分享转存拿不到文件名，跳过
            if now - moved_at > 6 * 3600:
                continue                      # 超过 6 小时就不再追问
            if checked >= 5:
                break
            checked += 1
            try:
                if not tr.path_exists(f"{final}/{name}"):
                    store.update(r["id"], status="organized",
                                 message=f"已整理完成（文件已移出 {final}）")
                    logger.info(f"115文档订阅与查询：检测到已整理：{r.get('title')}")
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"115文档订阅与查询：检查整理状态失败：{exc}")

    def records_view(self, refresh: bool = True) -> Dict[str, Any]:
        """详情页「转存记录」页数据：历史记录 + 离线任务实时进度。

        ``refresh=True`` 时按**节流规则**顺带跑一次离线检查（不会因此额外增加 115 请求频率）；
        想强制立即检查请用按钮（``/check_offline``）。
        """
        store = self._records()
        if refresh:
            try:
                self.check_offline_tasks(force=False)
                self._refresh_organized(store)
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"115文档订阅与查询：刷新离线进度/搬运失败：{exc}")
        return {"code": 0, "data": store.list()}

    def delete_record(self, rec_id: str = "") -> Dict[str, Any]:
        """删除一条（或不传 id 则清空）转存记录；同时清掉对应的待处理离线任务。"""
        store = self._records()
        if not rec_id:
            n = store.clear()
            self._save_pending([])
            return {"code": 0, "data": {"deleted": n, "cleared": True}}
        rec = None
        for r in store.list():
            if r.get("id") == rec_id:
                rec = r
                break
        if not rec:
            return {"code": 1, "msg": "记录不存在"}
        ok = store.delete(rec_id)
        h = str(rec.get("hash") or "").lower()
        if h:
            items = self._load_pending()
            keep = [i for i in items if str(i.get("hash") or "").lower() != h]
            if len(keep) != len(items):
                self._save_pending(keep)
        return {"code": 0, "data": {"deleted": 1 if ok else 0}}

    # ---- 订阅同步（仅电影）--------------------------------------------------
    @property
    def subscribed_path(self):
        return self.get_data_path_local() / "subscribed.json"

    def _load_subscribed(self) -> set:
        """已按订阅转存过的去重键（tmdb:xxx / title:xxx）。"""
        try:
            data = json.loads(self.subscribed_path.read_text(encoding="utf-8"))
            return set(data) if isinstance(data, list) else set()
        except Exception:
            return set()

    def _save_subscribed(self, keys) -> None:
        try:
            self.subscribed_path.parent.mkdir(parents=True, exist_ok=True)
            self.subscribed_path.write_text(
                json.dumps(sorted(keys), ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"115文档订阅与查询：保存订阅去重记录失败：{exc}")

    def _mp_subscribes(self) -> List[Dict[str, Any]]:
        """读取 MP 订阅列表。

        走 MoviePilot 自己的 API（``/api/v1/subscribe/``）而不是内部应用层服务——
        V3 的订阅链重构频繁，公开 API 反而是最稳定的契约。
        """
        import urllib.request

        try:
            from app.core.config import settings
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"115文档订阅与查询：读取 MP 配置失败，无法同步订阅：{exc}")
            return []
        token = (getattr(settings, "API_TOKEN", "") or "").strip()
        ports: List[int] = []
        for p in (getattr(settings, "PORT", None), 5000, 5001, 3000):
            try:
                p = int(p)
            except (TypeError, ValueError):
                continue
            if p and p not in ports:
                ports.append(p)
        for port in ports:
            try:
                out: List[Dict[str, Any]] = []
                for page in range(1, 6):          # 每页 100 条（MP 对 count 有上限，传大会 422）
                    url = (f"http://127.0.0.1:{port}/api/v1/subscribe/"
                           f"?apikey={token}&page={page}&count=100")
                    # ⚠️ 必须带 User-Agent：MP 的 API 会拒绝 urllib 默认 UA 的请求
                    req = urllib.request.Request(
                        url, headers={"User-Agent": "MoviePilot-Doc115Subscribe"})
                    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                        data = json.loads(resp.read().decode("utf-8"))
                    rows = data.get("data") if isinstance(data, dict) else data
                    if not isinstance(rows, list):
                        break
                    out.extend(rows)
                    if len(rows) < 100:
                        break
                if out:
                    return out
            except Exception:  # noqa: BLE001
                continue
        logger.warning("115文档订阅与查询：读取 MP 订阅列表失败（API_TOKEN / 端口不一致）")
        return []

    def run_subscribe(self) -> Dict[str, Any]:
        """按 MP 的**电影**订阅，去「最新电影」工作表找资源并转存到 115。"""
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        self._ensure_index()
        if not self._index or not self._index.records:
            return {"code": 1, "msg": "本地索引为空，请先刷新索引"}
        subs: List[Dict[str, Any]] = []
        for s in self._mp_subscribes():
            if str(s.get("type") or "") != "电影":
                continue
            source = str(s.get("media_source") or "")
            if source in ("", "themoviedb"):
                tmdbid = str(s.get("media_id") or s.get("tmdbid") or "").strip()
            else:
                tmdbid = str(s.get("tmdbid") or "").strip()
            title = str(s.get("name") or s.get("title") or "").strip()
            if not title and not tmdbid:
                continue
            subs.append({"title": title, "year": str(s.get("year") or "").strip(),
                         "tmdbid": tmdbid})
        if not subs:
            return {"code": 0, "data": {"movie_subs": 0, "matched": 0, "transferred": 0}}
        pairs = subscribe_sync.match_subscriptions(
            subscribe_sync.movie_records(self._index.records), subs)
        done = self._load_subscribed()
        matched = transferred = skipped = failed = 0
        for sub, rec in pairs:
            key = subscribe_sync.transfer_key(sub, rec)
            if key in done:
                skipped += 1
                continue
            matched += 1
            try:
                ok, msg = self.do_transfer(rec)
            except Exception as exc:  # noqa: BLE001
                ok, msg = False, f"{type(exc).__name__}: {exc}"
            if ok:
                transferred += 1
                done.add(key)
                self._save_subscribed(done)
                logger.info(f"115文档订阅与查询：订阅命中并转存 {rec.get('title')}（{msg}）")
            else:
                failed += 1
                logger.warning(f"115文档订阅与查询：订运转存失败 {rec.get('title')}：{msg}")
        logger.info(f"115文档订阅与查询：订阅同步完成：电影订阅 {len(subs)} 个，"
                    f"本次新命中 {matched} 条，转存 {transferred} 条，跳过 {skipped} 条，失败 {failed} 条")
        return {"code": 0, "data": {"movie_subs": len(subs), "matched": matched,
                                    "transferred": transferred, "skipped": skipped,
                                    "failed": failed}}

    def _ensure_index(self):
        """内存里没有索引时，从磁盘已保存的文件加载（避免重启/重载后又要重建）。"""
        if self._index is None:
            try:
                self._load_index()
            except Exception as exc:  # noqa: BLE001
                logger.error(f"115文档订阅与查询：加载本地索引失败：{exc}")
        return self._index

    def refresh_index(self) -> Dict[str, Any]:
        if not self._tencent_cookie:
            logger.error("115文档订阅与查询：缺少腾讯文档 Cookie，跳过索引刷新")
            return {"code": 1, "msg": "缺少腾讯文档 Cookie"}
        logger.info("115文档订阅与查询：开始刷新本地索引…")
        try:
            idx = DocIndex(self._new_client())
            idx.build(progress=lambda i, t, n: logger.info(
                f"115文档订阅与查询：索引 [{i}/{t}] {n}"))
            idx.save(self.index_path)
            self._index = idx
            summary = idx.summary()
            logger.info(f"115文档订阅与查询：索引刷新完成 {summary}")
            if summary["errors"]:
                logger.warning(f"115文档订阅与查询：部分工作表未解析：{summary['errors'][:5]}")
            return {"code": 0, "data": summary}
        except DocError as exc:
            logger.error(f"115文档订阅与查询：索引刷新失败 {exc}")
            return {"code": 1, "msg": str(exc)}

    # ---- 115 操作 ----------------------------------------------------------
    def _transfers(self) -> Optional[P115Transfer]:
        """115 操作句柄（按 Cookie 缓存，避免每次都新建并刷日志）。"""
        cookie = self.get_p115_cookie()
        if not cookie:
            return None
        if self._tr is not None and self._tr_cookie == cookie:
            return self._tr
        try:
            self._tr = P115Transfer(cookie)
            self._tr_cookie = cookie
            return self._tr
        except P115Error as exc:
            logger.error(f"115文档订阅与查询：初始化 115 客户端失败：{exc}")
            return None

    def build_save_path(self, rec: Dict[str, Any], target: str) -> str:
        """转存目标目录：默认按「片名 (年份)」建子目录，便于 MP 整理识别。"""
        base = self._movie_path if target == "movie" else self._tv_path
        if not self._create_subdir:
            return base
        title = (rec.get("title") or "").strip()
        year = str(rec.get("year") or "").strip()
        if not title:
            return base
        name = f"{title} ({year})" if year else title
        # 去掉 115 不允许的字符
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return f"{base}/{name[:80]}"

    def do_transfer(self, rec: Dict[str, Any], to: str = "") -> Tuple[bool, str]:
        try:
            return self._do_transfer_inner(rec, to)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"115文档订阅与查询：转存异常 {rec.get('title')} -> "
                         f"{type(exc).__name__}: {exc}", exc_info=True)
            return False, f"{rec.get('title')} 转存异常：{type(exc).__name__}: {exc}"

    def _do_transfer_inner(self, rec: Dict[str, Any], to: str = "") -> Tuple[bool, str]:
        """把一条记录转存到 115：115 分享走转存、磁力/ed2k 走离线下载。

        115 分享直接落到最终目录；磁力/ed2k 先落到「磁力暂存目录」，下载完成后
        再由本插件搬到最终目录。整理由 115 生活事件驱动，**不再写 MP 下载历史**。
        """
        links = [(k, u) for k, u in doc_parser.iter_links(rec) if k and u]
        if not links:
            return False, "该条目没有可用链接"
        # 「大包」（整表打包链接 / 多行共用同一链接 / 纯列表无链接）条目：只做搜索，
        # 不做一键转存（避免误转整包），由用户点结果里的链接自行查看/转存。
        if rec.get("sheet_bundle") or rec.get("bundle") or rec.get("no_link"):
            return False, (f"{rec.get('title')}：该条目是打包链接（大包），已关闭一键转存；"
                           f"请点击结果里的 115/磁力 链接自行查看或转存")
        target = to or self.resolve_media_type(rec)
        final_path = self.build_save_path(rec, target)
        staging_path = self._magnet_staging_path or final_path
        tr = self._transfers()
        if not tr:
            return False, "未配置 115 Cookie（可在插件配置填写，或先装好 115 网盘相关插件）"
        store = self._records()
        ok_msgs, errs, first_url = [], [], ""
        offline_added = []
        for kind, url in links:
            try:
                # 磁力/ed2k 先落「磁力暂存目录」，完成后再由插件搬到最终目录；
                # 115 分享是直接落到最终目录的。
                submit_path = staging_path if kind in (LINK_MAGNET, LINK_ED2K) else final_path
                ok, msg = tr.add_resource(kind, url, submit_path)
                if ok:
                    ok_msgs.append(msg)
                    first_url = first_url or url
                    if kind in (LINK_MAGNET, LINK_ED2K):
                        h = self.add_pending_offline(rec, target, submit_path, final_path, url)
                        offline_added.append(kind)
                        store.add({
                            "title": rec.get("title"), "year": rec.get("year"),
                            "type": "movie" if target == "movie" else "tv",
                            "kind": kind, "url": url, "hash": h or "",
                            "staging_path": submit_path, "final_path": final_path,
                            "status": "downloading", "progress": 0,
                            "message": f"已提交离线下载，先落 {submit_path}",
                        })
                    else:
                        store.add({
                            "title": rec.get("title"), "year": rec.get("year"),
                            "type": "movie" if target == "movie" else "tv",
                            "kind": kind, "url": url, "hash": "",
                            "staging_path": final_path, "final_path": final_path,
                            "status": "done",
                            "message": f"已转存到 {final_path}；整理由 115 助手接管",
                        })
            except Exception as exc:  # noqa: BLE001
                errs.append(str(exc))
                logger.warning(
                    f"115文档订阅与查询：链接处理失败 {rec.get('title')} [{kind}] {url} -> "
                    f"{type(exc).__name__}: {exc}", exc_info=True)
        if not ok_msgs:
            reason = "；".join(errs) or "未知错误"
            if any("失效" in e or "取消" in e or "过期" in e for e in errs):
                reason += "。文档里的这条分享已被分享者取消或过期，请换一条链接"
            return False, f"{rec.get('title')} 转存失败：{reason}"
        is_offline_only = bool(offline_added) and all(m == "已提交离线下载" for m in ok_msgs)
        if is_offline_only:
            return True, (f"{rec.get('title')} -> 先落 {staging_path}（{'；'.join(ok_msgs)}）"
                          f"，下载完成后会搬到 {final_path}，再由 115 整理")
        return True, (f"{rec.get('title')} -> {final_path}（{'；'.join(ok_msgs)}），"
                      f"已转存，等待 115 整理")

    # ---- 表单 / 页面（Vue 联邦模式） --------------------------------------
    @staticmethod
    def get_render_mode():
        """声明本插件使用 Vue 联邦组件渲染（Vuetify 页面无法把输入框的值传给接口）。"""
        return "vue", "dist/assets"

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """Vue 模式下配置表单由前端组件渲染，这里只返回默认配置模型。"""
        return [], self._current_config()

    def get_page(self) -> Optional[List[dict]]:
        """Vue 模式下详情页由前端组件渲染。"""
        return []

    # ---- API ---------------------------------------------------------------
    def get_api(self) -> List[Dict[str, Any]]:
        return [
            {"path": "/status", "endpoint": self.api_status,
             "auth": "bear", "methods": ["GET"], "summary": "插件状态"},
            {"path": "/get_config", "endpoint": self.api_get_config,
             "auth": "bear", "methods": ["GET"], "summary": "读取配置"},
            {"path": "/save_config", "endpoint": self.api_save_config,
             "auth": "bear", "methods": ["POST"], "summary": "保存配置"},
            {"path": "/refresh_index", "endpoint": self.api_refresh_index,
             "auth": "bear", "methods": ["POST"], "summary": "刷新本地索引"},
            {"path": "/search", "endpoint": self.api_search,
             "auth": "bear", "methods": ["POST"], "summary": "搜索文档资源"},
            {"path": "/transfer", "endpoint": self.api_transfer,
             "auth": "bear", "methods": ["POST"], "summary": "转存到 115"},
            {"path": "/check_offline", "endpoint": self.api_check_offline,
             "auth": "bear", "methods": ["POST"], "summary": "检查离线下载并搬运到最终目录"},
            {"path": "/records", "endpoint": self.api_records,
             "auth": "bear", "methods": ["GET"], "summary": "转存/离线记录与进度"},
            {"path": "/records_delete", "endpoint": self.api_records_delete,
             "auth": "bear", "methods": ["POST"], "summary": "删除转存记录（不传 id 则清空）"},
            {"path": "/run_subscribe", "endpoint": self.api_run_subscribe,
             "auth": "bear", "methods": ["POST"], "summary": "手动同步电影订阅"},
            {"path": "/qr_start", "endpoint": self.api_qr_start,
             "auth": "bear", "methods": ["GET"], "summary": "生成扫码登录二维码"},
            {"path": "/qr_status", "endpoint": self.api_qr_check,
             "auth": "bear", "methods": ["GET"], "summary": "查询扫码状态"},
        ]

    # --- API 实现 -----------------------------------------------------------

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

    def api_status(self) -> Dict[str, Any]:
        if self._enabled and not self._tencent_cookie:
            try:
                self.prewarm_qr()          # 页面打开即在后台备好二维码
            except Exception:  # noqa: BLE001
                pass
        idx = self._ensure_index()
        s = idx.summary() if idx else {"record_count": 0, "sheet_count": 0}
        built = "尚未建立"
        if idx and idx.built_at:
            built = datetime.fromtimestamp(idx.built_at).strftime("%Y-%m-%d %H:%M")
        return {"code": 0, "data": {
            "version": self.plugin_version,
            "enabled": self._enabled,
            "cookie_ready": bool(self._tencent_cookie),
            "p115_ready": bool(self.get_p115_cookie()),
            "cookie_days_left": self._cookie_days_left(self._tencent_cookie),
            "record_count": s.get("record_count", 0),
            "sheet_count": s.get("sheet_count", 0),
            "built_at_text": built,
        }}

    def api_get_config(self) -> Dict[str, Any]:
        return {"code": 0, "data": self._current_config()}

    def api_save_config(self, payload: dict = None) -> Dict[str, Any]:
        conf = dict(payload or {})
        if not conf:
            return {"code": 1, "msg": "没有收到配置内容"}
        merged = self._current_config()
        merged.update(conf)
        self.update_config(merged)
        # 让新配置立即生效（与 MP 的 init 流程一致）
        try:
            self.init_plugin(merged)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"115文档订阅与查询：重新初始化失败：{exc}")
        return {"code": 0, "msg": "配置已保存", "data": self._current_config()}

    def api_refresh_index(self) -> Dict[str, Any]:
        return self.refresh_index()

    def api_search(self, keyword: str = "", payload: dict = None) -> Dict[str, Any]:
        kw = (keyword or (payload or {}).get("keyword") or "").strip()
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        if not self._ensure_index():
            return {"code": 1, "msg": "本地索引尚未建立，请先点「刷新索引」"}
        if not kw:
            return {"code": 1, "msg": "请输入影视名称"}
        results = self._index.search(kw, limit=30)
        for r in results:
            r["media_type"] = self.resolve_media_type(r)
        return {"code": 0, "data": results}

    def api_transfer(self, payload: dict = None, index: int = -1, to: str = "",
                     keyword: str = "") -> Dict[str, Any]:
        """前端传 {keyword, index, to}：后端按同样的关键词重跑一次搜索再取下标对应的记录。"""
        body = payload or {}
        kw = (body.get("keyword") or keyword or "").strip()
        target = body.get("to") or to or ""
        raw_idx = body.get("index", index)
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            idx = -1
        if not self._enabled:
            return {"code": 1, "msg": "插件未启用"}
        if not self._ensure_index():
            return {"code": 1, "msg": "本地索引尚未建立"}
        if not kw:
            return {"code": 1, "msg": "缺少搜索关键词"}
        hits = self._index.search(kw, limit=30)
        if idx < 0 or idx >= len(hits):
            return {"code": 1, "msg": "结果已失效，请重新搜索"}
        ok, msg = self.do_transfer(hits[idx], to=target)
        return {"code": 0 if ok else 1, "msg": msg}

    def api_check_offline(self) -> Dict[str, Any]:
        """按钮/手动触发：忽略节流，立即检查一次。"""
        return self.check_offline_tasks(force=True)

    def api_records(self, limit: int = 200) -> Dict[str, Any]:
        """详情页「转存记录」页：历史转存/离线记录 + 实时进度。"""
        data = self.records_view(refresh=True).get("data") or []
        try:
            n = int(limit)
        except (TypeError, ValueError):
            n = 200
        return {"code": 0, "data": data[:max(1, n)]}

    def api_records_delete(self, payload: dict = None) -> Dict[str, Any]:
        """前端传 {id} 删除单条；不传 id（或 id 为空）则清空全部。"""
        body = payload or {}
        return self.delete_record(str(body.get("id") or ""))

    def api_run_subscribe(self) -> Dict[str, Any]:
        return self.run_subscribe()

    QR_FRESH_SECONDS = 90

    def api_qr_start(self) -> Dict[str, Any]:
        """返回二维码。若页面打开时已预热好，则**秒出**；否则现生成（约 7 秒）。"""
        # 预热命中
        with self._qr_lock:
            if self._qr and self._qr_img and (time.time() - self._qr_ts) < self.QR_FRESH_SECONDS:
                return {"code": 0, "data": {
                    "qr_base64": "data:image/png;base64," + base64.b64encode(self._qr_img).decode(),
                    "cached": True}}
        return self._start_qr_now()

    def _start_qr_now(self) -> Dict[str, Any]:
        try:
            if self._qr:
                self._qr.close()
            qr = BrowserQrLogin(self._doc_url)
            shot, already, cost = qr.start()
        except QrLoginError as exc:
            return {"code": 1, "msg": f"获取二维码失败：{exc}"}
        if already:
            self._qr = qr
            return self.page_qr_collect()
        if not shot:
            return {"code": 1, "msg": "未截取到二维码，请重试"}
        with self._qr_lock:
            self._qr = qr
            self._qr_img = shot
            self._qr_ts = time.time()
        logger.info(f"115文档订阅与查询：二维码生成完成，耗时 {cost:.1f}s")
        return {"code": 0, "data": {
            "qr_base64": "data:image/png;base64," + base64.b64encode(shot).decode(),
            "cost": round(cost, 1)}}

    def prewarm_qr(self):
        """后台预热二维码：详情页打开时调用，用户点按钮即可秒出。"""
        with self._qr_lock:
            if self._qr and self._qr_img and (time.time() - self._qr_ts) < self.QR_FRESH_SECONDS:
                return
            if getattr(self, "_qr_warming", False):
                return
            self._qr_warming = True

        def _run():
            try:
                self._start_qr_now()
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"115文档订阅与查询：二维码预热失败：{exc}")
            finally:
                self._qr_warming = False

        threading.Thread(target=_run, daemon=True, name="doc115-qrprewarm").start()

    def page_qr_collect(self) -> Dict[str, Any]:
        """会话已是登录态时，直接收集 Cookie 并保存。"""
        st = self._qr.check() if self._qr else {}
        cookie = (st or {}).get("cookie")
        if not cookie:
            return {"code": 1, "msg": "已是登录态但未取到 Cookie，请重试"}
        self._tencent_cookie = cookie
        self.update_config(self._current_config())
        if self._qr:
            self._qr.close()
        self._qr = None
        with self._qr_lock:
            self._qr_img = b""
        self.refresh_index()
        return {"code": 0, "data": {"state": "confirmed", "cookie_saved": True}}

    def api_qr_check(self) -> Dict[str, Any]:
        """查询扫码状态；确认后自动保存 Cookie。二维码过期会自动附上新码。"""
        if not self._qr:
            return {"code": 1, "msg": "请先点「获取登录二维码」"}
        st = self._qr.check() or {}
        state = st.get("state")
        if state == "confirmed":
            cookie = st.get("cookie") or ""
            if not cookie:
                return {"code": 1, "msg": "登录成功但未取到 Cookie，请重新获取二维码"}
            self._tencent_cookie = cookie
            self.update_config(self._current_config())
            self._qr.close()
            self._qr = None
            with self._qr_lock:
                self._qr_img = b""
            # 索引构建约 4~5 分钟，放后台跑，避免这次请求超时
            threading.Thread(target=self.refresh_index, daemon=True,
                             name="doc115-index-after-login").start()
            return {"code": 0, "data": {"state": "confirmed", "cookie_saved": True,
                                        "count": st.get("count"), "index_refreshing": True}}
        data: Dict[str, Any] = {"state": state or "wait"}
        if st.get("qr_base64"):
            data["qr_base64"] = st["qr_base64"]
        if state == "error":
            data["msg"] = st.get("msg")
            return {"code": 1, "msg": st.get("msg") or "检查失败", "data": data}
        return {"code": 0, "data": data}

    def stop_service(self):
        if self._scheduler:
            try:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._scheduler = None
