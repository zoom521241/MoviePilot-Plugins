# -*- coding: utf-8 -*-
"""夸克网盘搬家插件。

把夸克网盘指定目录中的影片搬迁到 115 网盘指定目录。

设计要点：

* 夸克凭证走官方扫码登录，cookie 保存在插件数据中，失效即暂停任务；
* 115 侧复用 MoviePilot 已授权的存储实例，不重复要求用户授权；
* 全程串行单任务，并受统一限流闸门约束，宁慢勿封。
"""

import base64
import io
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.plugins import _PluginBase
from app.sdk.logging import logger

from .quark_auth import QuarkAuth
from .quark_client import QuarkClient

try:
    from app.modules.filemanager.storages.u115 import U115Pan
except Exception:  # pragma: no cover - 宿主未启用 115 存储时降级
    U115Pan = None

# 视频后缀，用于「只搬视频」模式
VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".ts",
    ".rmvb", ".webm", ".m2ts", ".iso",
}


class QuarkTo115(_PluginBase):
    """夸克网盘搬家插件。"""

    plugin_name = "夸克网盘搬家"
    plugin_desc = "把夸克网盘指定目录中的影片搬迁到 115 网盘指定目录。"
    plugin_icon = "Quark.png"
    plugin_version = "0.1.0"
    plugin_author = "zoom521241"
    author_url = "https://github.com/zoom521241"
    plugin_config_prefix = "quarkto115_"
    plugin_order = 100
    auth_level = 1

    # 私有状态
    _enabled = False
    _src_dir = "/"
    _dst_dir = "/夸克搬家"
    _cron = "0 3 * * *"
    _only_video = True
    _qps = 1.0
    _max_files = 20
    _max_depth = 3
    _notify = True

    _client: Optional[QuarkClient] = None
    _auth: Optional[QuarkAuth] = None
    _login_state: Dict[str, Any] = {}
    _last_result: Dict[str, Any] = {}
    _running = False

    # ------------------------------------------------------------------ #
    # 生命周期
    # ------------------------------------------------------------------ #
    def init_plugin(self, config: dict = None) -> None:
        """根据插件配置初始化运行状态。"""
        self.stop_service()
        self._enabled = False
        if not config:
            return
        self._enabled = bool(config.get("enabled"))
        # 源目录不默认根目录：误填 / 会把整个网盘翻一遍
        self._src_dir = str(config.get("src_dir") or "").strip().rstrip("/")
        self._dst_dir = str(config.get("dst_dir") or "/夸克搬家").strip() or "/"
        self._cron = str(config.get("cron") or "0 3 * * *").strip()
        self._only_video = bool(config.get("only_video", True))
        self._notify = bool(config.get("notify", True))
        try:
            self._qps = float(config.get("qps") or 1.0)
        except (TypeError, ValueError):
            self._qps = 1.0
        try:
            self._max_files = max(1, int(config.get("max_files") or 20))
        except (TypeError, ValueError):
            self._max_files = 20
        try:
            self._max_depth = max(1, int(config.get("max_depth") or 3))
        except (TypeError, ValueError):
            self._max_depth = 3

        self._auth = QuarkAuth()
        self._login_state = {}
        self._running = False

    def get_state(self) -> bool:
        """获取插件启用状态。"""
        return self._enabled

    def stop_service(self) -> None:
        """停止插件后台服务并释放资源。"""
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._client = None
        if self._auth:
            try:
                self._auth.close()
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # 凭证
    # ------------------------------------------------------------------ #
    def __get_cookie(self) -> str:
        """读取已保存的夸克 cookie。"""
        try:
            return str(self.get_data("cookie") or "").strip()
        except Exception:
            return ""

    def __save_cookie(self, cookie: str) -> None:
        """保存夸克 cookie 到插件数据。"""
        try:
            self.save_data("cookie", cookie)
        except Exception as err:
            logger.error(f"【夸克搬家】保存 cookie 失败：{err}")

    def __ensure_client(self) -> bool:
        """确保夸克客户端可用。

        cookie 无效时返回 False，调用方应停止任务而不是继续重试。
        """
        if self._client:
            return True
        cookie = self.__get_cookie()
        if not cookie:
            logger.warning("【夸克搬家】尚未扫码登录，请先完成夸克扫码")
            return False
        if not self._auth:
            self._auth = QuarkAuth()
        if not self._auth.validate(cookie):
            logger.warning("【夸克搬家】夸克 cookie 已失效，请重新扫码")
            return False
        self._client = QuarkClient(cookie, qps=self._qps)
        return True

    # ------------------------------------------------------------------ #
    # 扫码登录页面
    # ------------------------------------------------------------------ #
    def __qrcode_page(self) -> Any:
        """返回扫码登录页面。

        页面每 3 秒自动刷新：未扫码时展示二维码，扫码成功后自动写入 cookie。
        """
        from fastapi.responses import HTMLResponse

        if not self._auth:
            self._auth = QuarkAuth()

        token = self._login_state.get("token")
        # token 不存在或已判定过期时重新申请
        if not token or self._login_state.get("state") == "expired":
            token = self._auth.fetch_login_token()
            self._login_state = {"token": token, "state": "pending"}

        message = "请使用夸克 APP 扫码"
        if token:
            state, payload = self._auth.poll_once(token)
            if state == "success":
                self.__save_cookie(payload)
                self._login_state["state"] = "success"
                self._client = None
                return HTMLResponse(
                    "<html><head><meta charset='utf-8'><title>扫码成功</title></head>"
                    "<body style='font-family:sans-serif;padding:40px'>"
                    "<h2>夸克扫码登录成功</h2>"
                    "<p>cookie 已保存，可以关闭本页。</p></body></html>"
                )
            if state == "expired":
                self._login_state["state"] = "expired"
                message = "二维码已过期，正在刷新，请稍候"
            elif state == "error":
                message = f"登录异常：{payload}"

        img_tag = ""
        if token and self._login_state.get("state") != "expired":
            try:
                import qrcode

                qr = qrcode.make(self._auth.build_qrcode_url(token))
                buf = io.BytesIO()
                qr.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode()
                img_tag = f"<img src='data:image/png;base64,{b64}' width='260'/>"
            except Exception as err:
                img_tag = f"<p style='color:#c00'>二维码生成失败：{err}</p>"

        html = (
            "<html><head><meta charset='utf-8'>"
            "<meta http-equiv='refresh' content='3'>"
            "<title>夸克扫码登录</title></head>"
            "<body style='font-family:sans-serif;padding:40px;text-align:center'>"
            f"<h2>{message}</h2>{img_tag}"
            "<p style='color:#888'>页面每 3 秒自动刷新</p>"
            "</body></html>"
        )
        return HTMLResponse(html)

    def __qrcode_status(self) -> Dict[str, Any]:
        """返回当前登录状态，供外部轮询。"""
        cookie = self.__get_cookie()
        valid = bool(cookie) and bool(self._auth and self._auth.validate(cookie))
        return {"success": True, "logged_in": valid, "state": self._login_state.get("state", "idle")}

    def get_api(self) -> List[Dict[str, Any]]:
        """返回插件 API 列表。"""
        return [
            {
                "path": "/qrcode",
                "endpoint": self.__qrcode_page,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "夸克扫码登录页",
            },
            {
                "path": "/qrstatus",
                "endpoint": self.__qrcode_status,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "扫码登录状态",
            },
            {
                "path": "/scan",
                "endpoint": self.__scan_api,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "扫描待搬清单（不传输）",
            },
            {
                "path": "/run",
                "endpoint": self.__run_api,
                "methods": ["GET"],
                "auth": "apikey",
                "summary": "立即执行一次搬家",
            },
        ]

    def __scan_api(self, dir: str = "", depth: int = 0,
                   limit: int = 0) -> Dict[str, Any]:
        """扫描待搬清单，不执行任何传输。

        :param dir: 临时指定源目录，为空时使用插件配置
        :param depth: 临时指定遍历深度，为空时使用插件配置
        :param limit: 临时指定返回条数上限，为空时使用插件配置
        """
        result = self.scan(src_dir=dir or None, depth=depth or None,
                           max_files=limit or None)
        return {
            "success": bool(result.get("success")),
            "message": result.get("message") or "",
            "total": len(result.get("items") or []),
            "items": result.get("items") or [],
        }

    def __run_api(self) -> Dict[str, Any]:
        """立即执行一次搬家任务。"""
        result = self.transfer(dry_run=False)
        return {
            "success": bool(result.get("success")),
            "message": result.get("message") or "",
        }

    # ------------------------------------------------------------------ #
    # 命令
    # ------------------------------------------------------------------ #
    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """返回插件远程命令列表。"""
        return [
            {
                "cmd": "/q2p115_scan",
                "event": "QuarkTo115Scan",
                "desc": "扫描夸克源目录（只列清单，不传输）",
                "category": "网盘",
                "data": {},
            },
            {
                "cmd": "/q2p115_run",
                "event": "QuarkTo115Run",
                "desc": "立即执行一次夸克到 115 的搬家",
                "category": "网盘",
                "data": {},
            },
        ]

    def get_service(self) -> List[Dict[str, Any]]:
        """返回插件定时服务。"""
        if not self._enabled:
            return []
        return [
            {
                "id": "QuarkTo115",
                "name": "夸克网盘搬家",
                "trigger": "cron",
                "func": self.__scheduled_transfer,
                "kwargs": {},
            }
        ]

    def __scheduled_transfer(self) -> None:
        """定时执行的搬家任务。"""
        self.transfer(dry_run=False)

    # ------------------------------------------------------------------ #
    # 115 侧
    # ------------------------------------------------------------------ #
    def __get_u115(self) -> Optional[Any]:
        """获取宿主的 115 存储实例。

        未启用或未授权时返回 None，由调用方给出明确提示。
        """
        if U115Pan is None:
            logger.error("【夸克搬家】当前 MoviePilot 未启用 115 存储模块")
            return None
        try:
            pan = U115Pan()
            if not pan.check():
                logger.error("【夸克搬家】115 网盘未授权，请先在「设置 - 存储」中完成 115 授权")
                return None
            return pan
        except Exception as err:
            logger.error(f"【夸克搬家】初始化 115 存储失败：{err}")
            return None

    def __ensure_target_dir(self, pan: Any) -> Optional[Any]:
        """确保 115 目标目录存在并返回其 FileItem。"""
        from app.schemas import FileItem

        path = Path(self._dst_dir)
        item = pan.get_folder(path)
        if item:
            return item
        # 逐级创建
        parent = pan.get_folder(Path("/"))
        if not parent:
            root = FileItem(storage="u115", path="/", type="dir", name="/", basename="/")
            parent = root
        for part in [p for p in self._dst_dir.split("/") if p]:
            item = pan.get_folder(Path(str(path)))
            found = None
            try:
                for child in pan.list(parent) or []:
                    if child.type == "dir" and child.name == part:
                        found = child
                        break
            except Exception:
                found = None
            if not found:
                found = pan.create_folder(parent, part)
            if not found:
                logger.error(f"【夸克搬家】115 目录创建失败：{part}")
                return None
            parent = found
        return parent

    # ------------------------------------------------------------------ #
    # 核心流程
    # ------------------------------------------------------------------ #
    def scan(self, src_dir: str = None, depth: int = None,
             max_files: int = None) -> Dict[str, Any]:
        """扫描夸克源目录，返回待搬清单。

        :param src_dir: 覆盖配置中的源目录，为空时回退配置值
        :param depth: 覆盖配置中的遍历深度
        :param max_files: 覆盖配置中的单轮上限
        :return: 含 success / items / message 的结果字典
        """
        if not self.__ensure_client():
            return {"success": False, "items": [], "message": "夸克未登录或 cookie 已失效"}

        target_dir = (src_dir or "").strip().rstrip("/") or self._src_dir
        if not target_dir:
            return {
                "success": False,
                "items": [],
                "message": "未配置夸克源目录，请先在插件配置填写要搬家的目录",
            }
        if target_dir == "/":
            return {
                "success": False,
                "items": [],
                "message": "源目录不能是网盘根目录，请填写具体目录（如 /影视/电影）",
            }

        fid = self._client.resolve_path(target_dir)
        if not fid:
            return {"success": False, "items": [], "message": f"夸克源目录不存在：{target_dir}"}

        try:
            max_depth = max(1, int(depth)) if depth else self._max_depth
        except (TypeError, ValueError):
            max_depth = self._max_depth
        try:
            limit = max(1, int(max_files)) if max_files else self._max_files
        except (TypeError, ValueError):
            limit = self._max_files

        items: List[Dict[str, Any]] = []
        scanned = 0
        for item in self._client.walk(fid, max_depth=max_depth, max_nodes=500):
            scanned += 1
            if item.get("dir"):
                continue
            name = item.get("file_name") or ""
            if self._only_video and Path(name).suffix.lower() not in VIDEO_EXTENSIONS:
                continue
            items.append(
                {
                    "fid": item.get("fid"),
                    "name": name,
                    "path": item.get("path"),
                    "size": item.get("size") or 0,
                }
            )
            if len(items) >= limit:
                break
        return {
            "success": True,
            "items": items,
            "message": f"源目录 {target_dir} 扫描 {scanned} 个对象，"
                       f"发现 {len(items)} 个待搬文件（深度上限 {max_depth}）",
        }

    def transfer(self, dry_run: bool = True) -> Dict[str, Any]:
        """执行一次搬家任务。

        :param dry_run: 为 True 时只扫描不传输
        :return: 任务结果字典
        """
        if self._running:
            return {"success": False, "message": "上一轮任务尚未结束"}
        self._running = True
        try:
            result = self.scan()
            self._last_result = {
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "dry_run": dry_run,
                "total": len(result.get("items") or []),
                "success": 0,
                "failed": 0,
            }
            if not result.get("success"):
                self._last_result["message"] = result.get("message")
                return result
            if dry_run:
                self._last_result["message"] = f"扫描完成（未传输）：{result.get('message')}"
                logger.info(f"【夸克搬家】{self._last_result['message']}")
                return result

            pan = self.__get_u115()
            if not pan:
                msg = "115 网盘不可用，请先在「设置 - 存储」完成授权"
                self._last_result["message"] = msg
                return {"success": False, "message": msg}
            target = self.__ensure_target_dir(pan)
            if not target:
                msg = f"115 目标目录不可用：{self._dst_dir}"
                self._last_result["message"] = msg
                return {"success": False, "message": msg}

            temp_dir = Path(self.get_data_path()) / "temp"
            temp_dir.mkdir(parents=True, exist_ok=True)

            for entry in result.get("items") or []:
                local_path = temp_dir / entry["name"]
                try:
                    if not self._client.download_file(entry["fid"], str(local_path)):
                        logger.error(f"【夸克搬家】下载失败：{entry['name']}")
                        self._last_result["failed"] += 1
                        continue
                    uploaded = pan.upload(target, local_path, new_name=entry["name"])
                    if uploaded:
                        self._last_result["success"] += 1
                        logger.info(f"【夸克搬家】已搬迁：{entry['name']}")
                    else:
                        self._last_result["failed"] += 1
                        logger.error(f"【夸克搬家】上传失败：{entry['name']}")
                except Exception as err:
                    self._last_result["failed"] += 1
                    logger.error(f"【夸克搬家】处理异常 {entry['name']}：{err}")
                finally:
                    try:
                        if local_path.exists():
                            local_path.unlink()
                    except Exception:
                        pass
                    # 文件间随机等待，避免形成机器特征
                    time.sleep(2)

            summary = (
                f"搬家完成：成功 {self._last_result['success']} 个，"
                f"失败 {self._last_result['failed']} 个"
            )
            self._last_result["message"] = summary
            if self._notify:
                self.post_message(
                    mtype=None,
                    title="夸克网盘搬家",
                    text=summary,
                )
            return {"success": True, "message": summary}
        finally:
            self._running = False

    # ------------------------------------------------------------------ #
    # 配置表单与页面
    # ------------------------------------------------------------------ #
    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回插件配置表单与默认配置。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "enabled", "label": "启用插件"},
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "only_video", "label": "只处理视频文件"},
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "src_dir",
                                            "label": "夸克源目录",
                                            "placeholder": "/影视/电影",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "dst_dir",
                                            "label": "115 目标目录",
                                            "placeholder": "/夸克搬家",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "cron",
                                            "label": "定时表达式",
                                            "placeholder": "0 3 * * *",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "qps",
                                            "label": "接口限流（次/秒）",
                                            "placeholder": "1.0",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 4},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "max_files",
                                            "label": "单轮最大文件数",
                                            "placeholder": "20",
                                        },
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VTextField",
                                        "props": {
                                            "model": "max_depth",
                                            "label": "目录遍历深度",
                                            "placeholder": "3",
                                        },
                                    }
                                ],
                            },
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {"model": "notify", "label": "完成后发送通知"},
                                    }
                                ],
                            },
                        ],
                    },
                    {
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "首次使用请访问插件的扫码登录页完成夸克授权；"
                            "115 需在「设置 - 存储」中完成授权。夸克源目录必须填写具体目录，"
                            "不允许填根目录 /，插件严格串行运行并限速，避免触发风控。",
                        },
                    },
                ],
            }
        ], {
            "enabled": False,
            "only_video": True,
            "src_dir": "",
            "dst_dir": "/夸克搬家",
            "cron": "0 3 * * *",
            "qps": 1.0,
            "max_files": 20,
            "max_depth": 3,
            "notify": True,
        }

    def get_page(self) -> Optional[List[dict]]:
        """返回插件详情页面。"""
        cookie = self.__get_cookie()
        logged = bool(cookie)
        last = self._last_result or {}
        rows = [
            f"夸克登录状态：{'已登录' if logged else '未登录，请扫码'}",
            f"源目录：{self._src_dir}",
            f"目标目录：{self._dst_dir}",
            f"上次运行：{last.get('time') or '尚未运行'}",
            f"上次结果：{last.get('message') or '-'}",
        ]
        return [
            {"component": "VAlert", "props": {"type": "info", "variant": "tonal", "text": "\n".join(rows)}},
        ]
