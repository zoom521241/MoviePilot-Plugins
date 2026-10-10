"""腾讯文档「微信扫码登录」——浏览器实现（常驻浏览器 + 可预热）。

速度优化：
1. **浏览器常驻**：playwright 与 Chromium 首次启动后复用（playwright 同步 API 有线程亲和性，
   因此所有浏览器操作都收敛到唯一一个后台线程）；
2. **二维码预热**：详情页打开时（/status）后台就开始生成二维码，用户点「获取登录二维码」时直接返回，
   等于秒出；
3. **截图尺寸自校验**：真二维码约 18KB、占位图约 5.5KB，截到小图就继续等，避免拿到空白页。

「刷新二维码」的语义
--------------------
* 轮询 ``check`` 时，距上次截图超过 ``QR_REFRESH_SECONDS`` 会重新截一次 iframe（微信页面
  自身可能已换码），返回 ``refreshed=True`` 与新图；
* 若二维码已过期（截图超过 ``QR_EXPIRE_SECONDS``，或页面出现「已失效/已过期」提示），
  则在同一会话里**重新加载登录页**取一张全新的二维码，同样以 ``refreshed=True`` 返回；
* 用户主动点「换一张」时，调用方应 ``force`` 新建会话（旧会话随之结束）。

为什么必须用浏览器：`bind-wx-quick-login.html` 不发任何网络请求，只把 code 通过 postMessage
交给父页面，真正的登录交换由文档页完成 —— 纯 HTTP 请求 redirect_uri 拿不到 Cookie。
"""
from __future__ import annotations

import base64
import glob
import os
import queue
import re
import threading
import time
import uuid
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlparse

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CHROME_CANDIDATES = [
    "/moviepilot/.cloakbrowser/chromium-146.0.7680.177.5/chrome-linux/chrome",
    "/moviepilot/.cloakbrowser/chromium-1179/chrome-linux/chrome",
]
QR_REFRESH_SECONDS = 100
QR_EXPIRE_SECONDS = 240       # 微信网页扫码二维码有效期约 4~5 分钟，过期后重新加载登录页
WORKER_START_TIMEOUT = 90
_EXPIRED_HINTS = ("二维码已失效", "二维码已过期", "已失效", "已过期", "刷新二维码")
SESSION_TIMEOUT = 15 * 60
MIN_QR_BYTES = 10000          # 占位图约 5.5KB，真二维码约 18KB


class QrLoginError(RuntimeError):
    pass


def _find_chromium() -> Optional[str]:
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    hits = sorted(glob.glob("/moviepilot/.cloakbrowser/*/chrome-linux/chrome"))
    return hits[0] if hits else None


def png_data_url(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


def _validate_doc_url(doc_url: str) -> str:
    """Only a Tencent document URL may be opened by the login browser."""
    try:
        parsed = urlparse(str(doc_url or "").strip())
        valid = (parsed.scheme == "https" and parsed.hostname == "docs.qq.com"
                 and not parsed.username and not parsed.password and parsed.port in (None, 443)
                 and re.fullmatch(r"/sheet/[A-Za-z0-9_-]+/?", parsed.path))
    except ValueError:
        valid = False
    if not valid:
        raise QrLoginError("扫码登录仅支持 https://docs.qq.com/sheet/ 文档链接")
    return parsed.geturl()


def _tencent_cookie(cookie: Dict[str, Any]) -> bool:
    domain = str(cookie.get("domain", "")).lstrip(".").lower()
    return domain == "qq.com" or domain.endswith(".qq.com")


class _Worker:
    """唯一的浏览器工作线程：playwright + Chromium 常驻，按指令服务。"""

    _qr_born = 0.0
    _page = None
    _doc_url = ""

    def __init__(self):
        self.q: "queue.Queue" = queue.Queue()
        self.ready = threading.Event()
        self.error: Optional[str] = None
        self._ctx = None
        self._page = None
        self._last_shot = 0.0
        self._qr_born = 0.0
        self._session_id = None
        self._doc_url = ""
        self._thread = threading.Thread(target=self._run, daemon=True, name="doc115-browser")
        self._thread.start()
        if not self.ready.wait(timeout=WORKER_START_TIMEOUT):
            # 不返回一个不可用的 worker：标记错误，并让线程在启动完成后自行退出。
            self.error = "浏览器启动超时，请稍后重试"
            self.q.put(("quit", None, queue.Queue()))
            raise QrLoginError(self.error)
        if self.error:
            raise QrLoginError(self.error)

    def submit(self, cmd: str, payload: Any = None, timeout: float = 180) -> Any:
        if self.error:
            raise QrLoginError(self.error)
        box: "queue.Queue" = queue.Queue()
        self.q.put((cmd, payload, box))
        try:
            ok, data = box.get(timeout=timeout)
        except queue.Empty as exc:
            raise QrLoginError(f"浏览器操作超时（{cmd}）") from exc
        if not ok:
            raise QrLoginError(str(data))
        return data

    # ---- 线程主体 ---------------------------------------------------------
    def _run(self):
        exe = _find_chromium()
        if not exe:
            self.error = "容器内未找到 Chromium（/moviepilot/.cloakbrowser）"
            self.ready.set()
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self.error = "未安装 playwright，无法使用扫码登录"
            self.ready.set()
            return
        try:
            pw = sync_playwright().start()
            browser = pw.chromium.launch(
                executable_path=exe, headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"])
        except Exception as exc:  # noqa: BLE001
            self.error = f"启动浏览器失败：{exc}"
            self.ready.set()
            return
        self._browser = browser
        self.ready.set()
        try:
            while True:
                cmd, payload, box = self.q.get()
                if cmd == "quit":
                    box.put((True, None))
                    break
                try:
                    if cmd == "start":
                        box.put((True, self._start(payload["doc_url"], payload["session_id"])))
                    elif cmd == "check":
                        box.put((True, self._check(payload)))
                    elif cmd == "end_session":
                        self._end_session(payload)
                        box.put((True, None))
                    else:
                        box.put((False, f"未知指令 {cmd}"))
                except Exception as exc:  # noqa: BLE001
                    box.put((False, str(exc)))
        finally:
            try:
                browser.close()
                pw.stop()
            except Exception:  # noqa: BLE001
                pass

    # ---- 会话 -------------------------------------------------------------
    def _end_session(self, session_id: Optional[str] = None):
        if session_id is not None and session_id != self._session_id:
            return
        if self._ctx is not None:
            try:
                self._ctx.close()
            except Exception:  # noqa: BLE001
                pass
        self._ctx = None
        self._page = None
        self._session_id = None
        self._doc_url = ""

    def _start(self, doc_url: str, session_id: str) -> Tuple[bytes, bool]:
        doc_url = _validate_doc_url(doc_url)
        self._end_session()
        self._session_id = session_id
        self._doc_url = doc_url
        self._ctx = self._browser.new_context(
            user_agent=UA, viewport={"width": 1280, "height": 900}, locale="zh-CN")
        self._page = self._ctx.new_page()
        return self._open_login()

    def _open_login(self) -> Tuple[bytes, bool]:
        """（重新）加载文档页并打开微信扫码弹窗，返回 (二维码PNG, 是否已登录)。"""
        page = self._page
        page.goto(self._doc_url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(2500)          # 页面初始化（太短会导致弹窗不完整、二维码不渲染）
        if self._has_uid(self._ctx):
            return b"", True
        btn = page.locator("text=立即登录").first
        try:
            btn.click(timeout=8000)
        except Exception:  # noqa: BLE001
            try:
                btn.dispatch_event("click")
            except Exception:  # noqa: BLE001
                pass
        page.wait_for_timeout(1800)
        try:  # 协议勾选（必须点，勾了才会出码；不做幂等判断，避免误判导致跳过）
            page.locator("text=我已阅读并接受").first.click(timeout=5000, force=True)
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(2000)
        shot = self._shoot_qr()
        self._qr_born = time.time()
        return shot, False

    def _qr_expired(self) -> bool:
        if self._qr_born and time.time() - self._qr_born > QR_EXPIRE_SECONDS:
            return True
        try:
            for frame in self._page.frames:
                if urlparse(frame.url).hostname in ("open.weixin.qq.com", "open.wechat.com"):
                    text = frame.locator("body").first.inner_text(timeout=1000)
                    return any(hint in text for hint in _EXPIRED_HINTS)
        except Exception:  # noqa: BLE001
            return False
        return False

    def _shoot_qr(self) -> bytes:
        page = self._page
        frame = None
        deadline = time.time() + 20
        while time.time() < deadline:
            frame = next((f for f in page.frames
                          if urlparse(f.url).hostname in ("open.weixin.qq.com", "open.wechat.com")
                          and "qrconnect" in urlparse(f.url).path), None)
            if frame:
                break
            page.wait_for_timeout(150)
        if not frame:
            raise QrLoginError("未找到二维码 iframe（腾讯页面可能已改版）")
        best = b""
        for _ in range(20):
            try:
                best = frame.locator("body").first.screenshot()
            except Exception:  # noqa: BLE001
                page.wait_for_timeout(300)
                continue
            if len(best) >= MIN_QR_BYTES:
                self._last_shot = time.time()
                return best
            page.wait_for_timeout(300)
        self._last_shot = time.time()
        raise QrLoginError(f"二维码未渲染完成（截图仅 {len(best)} 字节，疑似占位图），请点「换一张二维码」重试")

    def _has_uid(self, ctx) -> bool:
        try:
            return any(c.get("name") == "uid" and _tencent_cookie(c) for c in ctx.cookies())
        except Exception:  # noqa: BLE001
            return False

    def _check(self, session_id: str) -> Dict[str, Any]:
        ctx = self._ctx
        if ctx is None or session_id != self._session_id:
            return {"state": "expired", "session_id": session_id}
        cookies = ctx.cookies()
        cookies = [c for c in cookies if _tencent_cookie(c)]
        names = {c.get("name") for c in cookies}
        if "uid" in names:
            parts = [f"{c['name']}={c['value']}" for c in cookies]
            return {"state": "confirmed", "session_id": session_id, "cookie": "; ".join(parts), "count": len(parts)}
        if self._qr_expired():
            # 过期：同一会话内重新加载登录页拿新码
            try:
                shot, already = self._open_login()
            except Exception:  # noqa: BLE001
                return {"state": "wait"}
            if already:
                return self._check(session_id)
            return {"state": "wait", "qr_base64": png_data_url(shot), "refreshed": True, "reloaded": True}
        if time.time() - self._last_shot > QR_REFRESH_SECONDS:
            try:
                shot = self._shoot_qr()
                return {"state": "wait", "qr_base64": png_data_url(shot), "refreshed": True}
            except Exception:  # noqa: BLE001
                return {"state": "wait"}
        return {"state": "wait"}


_WORKER_LOCK = threading.Lock()
_WORKER: Optional[_Worker] = None


def _get_worker() -> _Worker:
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None or _WORKER.error or not _WORKER._thread.is_alive():
            _WORKER = _Worker()
        return _WORKER


class BrowserQrLogin:
    """一次登录会话的句柄；底层浏览器常驻复用。"""

    def __init__(self, doc_url: str):
        self.doc_url = _validate_doc_url(doc_url)
        self.session_id = uuid.uuid4().hex
        self._started_at = 0.0
        self._worker: Optional[_Worker] = None
        self._closed = False

    def start(self) -> Tuple[bytes, bool, float]:
        """返回 (二维码PNG, 是否已登录, 耗时秒)。"""
        if self._closed:
            raise QrLoginError("登录会话已关闭，请重新获取二维码")
        t0 = time.time()
        self._worker = _get_worker()
        shot, already = self._worker.submit("start", {
            "doc_url": self.doc_url, "session_id": self.session_id,
        }, timeout=180)
        self._started_at = time.time()
        return shot, already, time.time() - t0

    def check(self) -> Dict[str, Any]:
        if self._closed or not self._started_at or self._worker is None:
            return {"state": "expired", "session_id": self.session_id}
        if time.time() - self._started_at > SESSION_TIMEOUT:
            self.close()
            return {"state": "expired"}
        try:
            return self._worker.submit("check", self.session_id, timeout=120)
        except QrLoginError as exc:
            return {"state": "wait"} if "超时" in str(exc) else {"state": "error", "msg": str(exc)}

    def close(self):
        if self._closed:
            return
        self._closed = True
        worker = self._worker
        if worker is None:
            return
        try:
            worker.submit("end_session", self.session_id, timeout=40)
        except Exception:  # noqa: BLE001
            pass
