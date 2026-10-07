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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

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
    from .p115_transfer import P115Error, P115Transfer
    from .qrlogin import QrLoginError, TencentDocsQrLogin
except ImportError:
    import doc_parser
    import subscribe_sync
    from doc_client import DocError, TencentDocsClient
    from doc_index import DocIndex
    from p115_transfer import P115Error, P115Transfer
    from qrlogin import QrLoginError, TencentDocsQrLogin


class Doc115Subscribe(_PluginBase):
    # ---- 插件元信息 ---------------------------------------------------------
    plugin_name = "115文档订阅与查询"
    plugin_desc = "从腾讯文档追更表读取资源：定时为电影订阅转存到115，并支持插件内跨表搜索转存。"
    plugin_icon = "https://raw.githubusercontent.com/jxxghp/MoviePilot-Plugins/main/icons/cloud.png"
    plugin_version = "0.2.0"
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
    _subscribe_enabled = True
    _subscribe_cron = "0 21 * * *"
    _index_cron = "0 6 * * *"
    _use_agent = True

    _scheduler: Optional[BackgroundScheduler] = None
    _index: Optional[DocIndex] = None
    _qr: Optional[TencentDocsQrLogin] = None
    _qr_img: str = ""
    _search_results: List[Dict[str, Any]] = []
    _page_msg: str = ""
    _mt_cache: Dict[str, str] = {}

    # ---------------------------------------------------------------------
    def init_plugin(self, config: dict = None):
        self._enabled = False
        self._scheduler = None
        self._index = None
        self._qr = None
        self._qr_img = ""
        self._search_results = []
        self._page_msg = ""
        if config:
            self._enabled = bool(config.get("enabled", False))
            self._doc_url = config.get("doc_url") or self.__class__._doc_url
            self._tencent_cookie = config.get("tencent_cookie") or ""
            self._p115_cookie = config.get("p115_cookie") or ""
            self._movie_path = config.get("movie_path") or self.__class__._movie_path
            self._tv_path = config.get("tv_path") or self.__class__._tv_path
            self._subscribe_enabled = bool(config.get("subscribe_enabled", True))
            self._subscribe_cron = config.get("subscribe_cron") or self.__class__._subscribe_cron
            self._index_cron = config.get("index_cron") or self.__class__._index_cron
            self._use_agent = bool(config.get("use_agent", True))

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
                        logger.info(f"115文档订阅与查询：复用 {key}.{field} 的 115 Cookie")
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
            "subscribe_enabled": self._subscribe_enabled,
            "subscribe_cron": self._subscribe_cron,
            "index_cron": self._index_cron,
            "use_agent": self._use_agent,
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
        cookie = self.get_p115_cookie()
        if not cookie:
            return None
        try:
            return P115Transfer(cookie)
        except P115Error as exc:
            logger.error(f"115文档订阅与查询：初始化 115 客户端失败：{exc}")
            return None

    def do_transfer(self, rec: Dict[str, Any], to: str = "") -> Tuple[bool, str]:
        """把一条记录转存到 115：to = movie / tv（留空按识别结果）。"""
        links = [(k, u) for k, u in doc_parser.iter_links(rec) if k and u]
        if not links:
            return False, "该条目没有可用链接"
        target = to or self.resolve_media_type(rec)
        save_path = self._movie_path if target == "movie" else self._tv_path
        tr = self._transfers()
        if not tr:
            return False, "未配置 115 Cookie（可在插件配置填写，或先装好115网盘Plus）"
        ok_msgs, errs = [], []
        for kind, url in links:
            try:
                ok, msg = tr.add_resource(kind, url, save_path)
                if ok:
                    ok_msgs.append(msg)
            except P115Error as exc:
                errs.append(str(exc))
        if ok_msgs:
            return True, f"{rec.get('title')} -> {save_path}（{'；'.join(ok_msgs)}）"
        return False, f"{rec.get('title')} 转存失败：{'；'.join(errs) or '未知错误'}"

    # ---- 订阅同步（仅电影） ------------------------------------------------
    def _get_movie_subscribes(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        try:
            from app.db.subscribe_oper import SubscribeOper
            for sub in SubscribeOper().list() or []:
                stype = str(getattr(sub, "type", "") or "")
                is_movie = ("MOVIE" in stype.upper()) or (stype in ("电影", "movie"))
                if not is_movie:
                    continue
                out.append({
                    "tmdbid": getattr(sub, "tmdbid", None),
                    "title": getattr(sub, "name", "") or "",
                    "year": str(getattr(sub, "year", "") or ""),
                })
        except Exception as exc:  # noqa: BLE001
            logger.error(f"115文档订阅与查询：读取 MP 订阅失败：{exc}")
        return out

    def run_subscribe(self) -> Dict[str, Any]:
        if not self._tencent_cookie:
            return {"code": 1, "msg": "缺少腾讯文档 Cookie"}
        if not self._index:
            self._load_index()
        if not self._index:
            return {"code": 1, "msg": "本地索引为空，请先刷新索引"}

        subs = self._get_movie_subscribes()
        if not subs:
            logger.info("115文档订阅与查询：没有电影订阅，跳过")
            return {"code": 0, "data": {"matched": 0, "transferred": 0}}

        records = subscribe_sync.movie_records(self._index.records)
        pairs = subscribe_sync.match_subscriptions(records, subs)
        logger.info(f"115文档订阅与查询：订阅 {len(subs)} 条，文档命中 {len(pairs)} 条")

        history: List[Dict[str, Any]] = self.get_data("history") or []
        done_keys = {h.get("key") for h in history}
        added = 0
        for sub, rec in pairs:
            key = subscribe_sync.transfer_key(sub, rec)
            if key in done_keys:
                continue
            ok, msg = self.do_transfer(rec, to="movie")
            if ok:
                added += 1
                done_keys.add(key)
                history.append({"key": key, "title": rec.get("title"),
                                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")})
                logger.info(f"115文档订阅与查询：{msg}")
            else:
                logger.warning(f"115文档订阅与查询：{msg}")
        self.save_data("history", history[-500:])
        if added:
            self.post_message(mtype=_MsgType.Plugin, title="【115文档订阅与查询】",
                              text=f"本轮为 {added} 部电影订阅完成转存")
        return {"code": 0, "data": {"matched": len(pairs), "transferred": added}}

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
            {"path": "/run_subscribe", "endpoint": self.api_run_subscribe,
             "auth": "bear", "methods": ["POST"], "summary": "手动同步电影订阅"},
            {"path": "/qr_start", "endpoint": self.api_qr_start,
             "auth": "bear", "methods": ["GET"], "summary": "生成扫码登录二维码"},
            {"path": "/qr_status", "endpoint": self.api_qr_check,
             "auth": "bear", "methods": ["GET"], "summary": "查询扫码状态"},
        ]

    # --- API 实现 -----------------------------------------------------------
    def api_status(self) -> Dict[str, Any]:
        s = self._index.summary() if self._index else {"record_count": 0, "sheet_count": 0}
        built = "尚未建立"
        if self._index and self._index.built_at:
            built = datetime.fromtimestamp(self._index.built_at).strftime("%Y-%m-%d %H:%M")
        return {"code": 0, "data": {
            "enabled": self._enabled,
            "cookie_ready": bool(self._tencent_cookie),
            "p115_ready": bool(self.get_p115_cookie()),
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
        if not self._index:
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
        if not self._index:
            return {"code": 1, "msg": "本地索引尚未建立"}
        if not kw:
            return {"code": 1, "msg": "缺少搜索关键词"}
        hits = self._index.search(kw, limit=30)
        if idx < 0 or idx >= len(hits):
            return {"code": 1, "msg": "结果已失效，请重新搜索"}
        ok, msg = self.do_transfer(hits[idx], to=target)
        return {"code": 0 if ok else 1, "msg": msg}

    def api_run_subscribe(self) -> Dict[str, Any]:
        return self.run_subscribe()

    def api_qr_start(self) -> Dict[str, Any]:
        try:
            self._qr = TencentDocsQrLogin()
            info = self._qr.start()
            img = self._qr.qr_image()
        except QrLoginError as exc:
            return {"code": 1, "msg": str(exc)}
        return {"code": 0, "data": {
            "uuid": info["uuid"],
            "qr_base64": "data:image/jpeg;base64," + base64.b64encode(img).decode()}}

    def api_qr_check(self) -> Dict[str, Any]:
        if not self._qr:
            return {"code": 1, "msg": "请先点「获取登录二维码」"}
        try:
            st = self._qr.poll()
        except QrLoginError as exc:
            return {"code": 1, "msg": str(exc)}
        if st["state"] != "confirmed" or not st.get("code"):
            return {"code": 0, "data": {"state": st["state"]}}
        try:
            cookie = self._qr.finish(st["code"])
        except QrLoginError as exc:
            return {"code": 1, "msg": f"换取 Cookie 失败：{exc}"}
        self._tencent_cookie = cookie
        self.update_config(self._current_config())
        self._qr = None
        self.refresh_index()
        return {"code": 0, "data": {"state": "confirmed", "cookie_saved": True}}

    def stop_service(self):
        if self._scheduler:
            try:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._scheduler.shutdown()
            except Exception:  # noqa: BLE001
                pass
            self._scheduler = None
