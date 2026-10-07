"""腾讯文档「微信扫码登录」——浏览器实现（使用容器内自带 Chromium）。

为什么不用纯 HTTP：观察 `bind-wx-quick-login.html` 的脚本可知，那个页面**不发起任何网络请求**，
它只是把 `code` 通过 `postMessage({type:'wxLoginSuccess', code})` 交给父页面，
真正换取登录态的是父页面。所以纯 HTTP 直接请求 redirect_uri 拿不到 Cookie。

这里改用真实浏览器：打开文档页 → 点「立即登录」→ 勾选协议 → 截取二维码 →
后台轮询登录态 → 登录成功后导出 Cookie。浏览器在后台线程常驻，供分步调用。
"""
from __future__ import annotations

import base64
import glob
import os
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
CHROME_CANDIDATES = [
    "/moviepilot/.cloakbrowser/chromium-146.0.7680.177.5/chrome-linux/chrome",
    "/moviepilot/.cloakbrowser/chromium-1179/chrome-linux/chrome",
]
QR_REFRESH_SECONDS = 100     # 二维码约 2~3 分钟过期，超过就重截
SESSION_TIMEOUT = 15 * 60    # 整个会话最长 15 分钟


class QrLoginError(RuntimeError):
    pass


def _find_chromium() -> Optional[str]:
    for p in CHROME_CANDIDATES:
        if os.path.exists(p):
            return p
    hits = sorted(glob.glob("/moviepilot/.cloakbrowser/*/chrome-linux/chrome"))
    return hits[0] if hits else None


def _png_data_url(data: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(data).decode()


class BrowserQrLogin:
    """常驻的浏览器扫码登录会话（一个实例 = 一个后台线程 + 一个浏览器）。"""

    def __init__(self, doc_url: str):
        self.doc_url = doc_url
        self._cmd_q: "queue.Queue" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self._started_at = 0.0
        self._last_shot = 0.0

    # ---- 对外 -------------------------------------------------------------
    def start(self) -> Tuple[bytes, bool]:
        """（重新）打开登录弹窗，返回 (二维码PNG字节, 会话是否已是登录态)。"""
        self.close()
        time.sleep(0.3)
        self._thread = threading.Thread(target=self._worker, daemon=True, name="doc115-qrlogin")
        self._thread.start()
        self._started_at = time.time()
        return self._call("start", timeout=180)

    def check(self) -> Dict[str, Any]:
        """查询登录状态。返回 state ∈ wait / confirmed / expired / error。"""
        if not self._thread or not self._thread.is_alive():
            return {"state": "expired"}
        if time.time() - self._started_at > SESSION_TIMEOUT:
            self.close()
            return {"state": "expired"}
        try:
            return self._call("check", timeout=120)
        except QrLoginError as exc:
            return {"state": "error", "msg": str(exc)}

    def close(self):
        if self._thread and self._thread.is_alive():
            try:
                self._call("quit", timeout=40)
            except Exception:  # noqa: BLE001
                pass
        self._thread = None

    # ---- 内部 -------------------------------------------------------------
    def _call(self, cmd: str, timeout: float = 60) -> Any:
        box: "queue.Queue" = queue.Queue()
        self._cmd_q.put((cmd, box))
        try:
            ok, payload = box.get(timeout=timeout)
        except queue.Empty as exc:
            raise QrLoginError(f"浏览器操作超时（{cmd}）") from exc
        if not ok:
            raise QrLoginError(str(payload))
        return payload

    def _worker(self):
        exe = _find_chromium()
        if not exe:
            self._fail_all("容器内未找到 Chromium（/moviepilot/.cloakbrowser）")
            return
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            self._fail_all("未安装 playwright，无法使用扫码登录")
            return

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    executable_path=exe, headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )
                try:
                    ctx = browser.new_context(
                        user_agent=UA, viewport={"width": 1280, "height": 900}, locale="zh-CN")
                    page = ctx.new_page()
                    self._loop(ctx, page)
                finally:
                    try:
                        browser.close()
                    except Exception:  # noqa: BLE001
                        pass
        except Exception as exc:  # noqa: BLE001
            self._fail_all(f"启动浏览器失败：{exc}")

    def _loop(self, ctx, page):
        while True:
            cmd, box = self._cmd_q.get()
            if cmd == "quit":
                box.put((True, None))
                return
            try:
                if cmd == "start":
                    box.put((True, self._do_start(ctx, page)))
                elif cmd == "check":
                    box.put((True, self._do_check(ctx, page)))
                else:
                    box.put((False, f"未知指令 {cmd}"))
            except Exception as exc:  # noqa: BLE001
                box.put((False, str(exc)))

    def _fail_all(self, msg: str):
        # 把后续所有请求都回以同一个错误
        while True:
            try:
                _, box = self._cmd_q.get_nowait()
                box.put((False, msg))
            except queue.Empty:
                break
        self._cmd_q.put(("quit", _ErrorBox(msg)))

    # ---- 具体动作 ---------------------------------------------------------
    def _do_start(self, ctx, page) -> Tuple[bytes, bool]:
        page.goto(self.doc_url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(4000)
        if self._has_uid(ctx):
            return b"", True
        page.locator("text=立即登录").first.click(timeout=8000)
        page.wait_for_timeout(2500)
        # 勾选协议，否则不显示二维码
        page.locator("text=我已阅读并接受").first.click(timeout=5000, force=True)
        page.wait_for_timeout(4000)
        shot = self._shoot_qr(page)
        self._last_shot = time.time()
        return shot, False

    def _shoot_qr(self, page) -> bytes:
        frame = None
        for _ in range(20):
            frame = next((f for f in page.frames if "qrconnect" in f.url), None)
            if frame:
                break
            page.wait_for_timeout(1000)
        if not frame:
            raise QrLoginError("未找到二维码 iframe（腾讯页面可能已改版）")
        for _ in range(15):
            try:
                img = frame.locator("img.js_qrcode_img").first
                if img.count() and img.get_attribute("src"):
                    break
            except Exception:  # noqa: BLE001
                pass
            page.wait_for_timeout(1000)
        return frame.locator("body").first.screenshot()

    def _has_uid(self, ctx) -> bool:
        try:
            return any(c.get("name") == "uid" for c in ctx.cookies())
        except Exception:  # noqa: BLE001
            return False

    def _do_check(self, ctx, page) -> Dict[str, Any]:
        cookies: List[Dict[str, Any]] = ctx.cookies()
        names = {c.get("name") for c in cookies}
        if "uid" in names:
            parts = [f"{c['name']}={c['value']}" for c in cookies
                     if c.get("domain") and "qq.com" in c["domain"]]
            return {"state": "confirmed", "cookie": "; ".join(parts), "count": len(parts)}
        if time.time() - self._last_shot > QR_REFRESH_SECONDS:
            try:
                shot = self._shoot_qr(page)
                self._last_shot = time.time()
                return {"state": "wait", "qr_base64": _png_data_url(shot), "refreshed": True}
            except Exception:  # noqa: BLE001
                return {"state": "wait"}
        return {"state": "wait"}


class _ErrorBox:
    """给 _fail_all 用的占位盒子（避免后续 _call 永久阻塞）。"""

    def __init__(self, msg: str):
        self._msg = msg

    def put(self, item):
        pass

    def get(self, timeout=None):
        return (False, self._msg)
