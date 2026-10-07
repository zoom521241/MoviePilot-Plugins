"""腾讯文档「微信扫码登录」——纯 HTTP 实现，不需要浏览器。

流程（与网页一致）：
  1. 请求 qrconnect 页面 -> 拿到 uuid，二维码图片地址为
     ``https://open.weixin.qq.com/connect/qrcode/{uuid}``；
  2. 轮询 ``https://long.open.weixin.qq.com/connect/l/qrconnect`` ->
     wx_errcode: 408 未扫描 / 404 已扫描待确认 / 405 已确认（带 wx_code）；
  3. 带 wx_code 请求 redirect_uri -> docs.qq.com 下发登录 Cookie（TOK / SID / uid …）。

二维码**扫过一次即失效**，需要换新码：调用 restart() 或重新 start()。
"""
from __future__ import annotations

import http.cookiejar
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
QRCONNECT = "https://open.weixin.qq.com/connect/qrconnect"
QRCODE_IMG = "https://open.weixin.qq.com/connect/qrcode/{uuid}"
POLL_URL = "https://long.open.weixin.qq.com/connect/l/qrconnect"
APPID = "wx02b8ff0031cec148"
REDIRECT_URI = ("https://docs.qq.com/scenario/bind-wx-quick-login.html"
                "?from=@tencent/docs-scenario-component-auth-provider")
STATE = "docs.qq.com"

# 轮询状态
WAIT = "wait"            # 未扫描
SCANNED = "scanned"      # 已扫描，待手机确认
CONFIRMED = "confirmed"  # 已确认（拿到 code）
EXPIRED = "expired"      # 二维码过期


class QrLoginError(RuntimeError):
    pass


class TencentDocsQrLogin:
    def __init__(self):
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._jar))
        self.uuid: str = ""
        self.last: str = ""
        self.diag: str = ""   # 换 Cookie 失败时的诊断信息，便于排查

    # -- 底层 ---------------------------------------------------------------
    def _open(self, url: str, referer: str = "https://docs.qq.com/") -> bytes:
        return self._open_resp(url, referer)[1]

    def _open_resp(self, url: str, referer: str = "https://docs.qq.com/") -> Tuple[int, bytes]:
        req = urllib.request.Request(url, headers={
            "User-Agent": UA,
            "Referer": referer,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        try:
            with self._opener.open(req, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            try:
                return exc.code, exc.read()
            except Exception:  # noqa: BLE001
                return exc.code, b""

    def _qq_cookies(self) -> Dict[str, str]:
        return {c.name: c.value for c in self._jar if c.domain and "qq.com" in c.domain}

    def _cookie_str(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self._qq_cookies().items())

    # -- 1. 生成二维码 ------------------------------------------------------
    def start(self) -> Dict[str, str]:
        params = {
            "appid": APPID,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "scope": "snsapi_login",
            "self_redirect": "true",
            "stylelite": "0",
            "state": STATE,
            "lang": "cn",
            "color_scheme": "light",
        }
        url = QRCONNECT + "?" + urllib.parse.urlencode(params) + "#wechat_redirect"
        html = self._open(url).decode("utf-8", "ignore")
        # 页面里二维码地址形如 /connect/qrcode/09163W0v39POFa1V
        m = (re.search(r"connect/qrcode/([A-Za-z0-9_\-]+)", html)
             or re.search(r'["\']?uuid["\']?\s*[:=]\s*["\']([A-Za-z0-9_\-]{12,})', html))
        if not m:
            raise QrLoginError("未能从登录页解析出二维码 uuid（腾讯可能已改版）")
        self.uuid = m.group(1)
        self.last = ""
        self.diag = ""
        return {"uuid": self.uuid, "qr_url": QRCODE_IMG.format(uuid=self.uuid)}

    def restart(self) -> Dict[str, str]:
        """作废当前二维码，重新生成一个新的（旧码扫过一次即失效，必须换新）。"""
        self.uuid = ""
        self.last = ""
        self.diag = ""
        return self.start()

    def qr_image(self) -> bytes:
        """下载二维码图片（JPEG）。"""
        if not self.uuid:
            raise QrLoginError("请先调用 start()")
        return self._open(QRCODE_IMG.format(uuid=self.uuid),
                          referer="https://open.weixin.qq.com/")

    # -- 2. 轮询扫码结果 ----------------------------------------------------
    def poll(self) -> Dict[str, Optional[str]]:
        if not self.uuid:
            raise QrLoginError("请先调用 start()")
        url = (f"{POLL_URL}?uuid={self.uuid}&last={self.last}"
               f"&_={int(time.time() * 1000)}")
        txt = self._open(url, referer="https://open.weixin.qq.com/").decode("utf-8", "ignore")
        err = re.search(r"wx_errcode\s*=\s*(\d+)", txt)
        code = re.search(r"wx_code\s*=\s*'([^']*)'", txt)
        self.last = (err.group(1) if err else "")
        if code and code.group(1):
            return {"state": CONFIRMED, "code": code.group(1), "raw": txt}
        if not err:
            return {"state": WAIT, "code": None, "raw": txt}
        e = err.group(1)
        if e == "408":
            return {"state": WAIT, "code": None, "raw": txt}
        if e in ("404", "403"):
            return {"state": SCANNED, "code": None, "raw": txt}
        if e == "402":
            return {"state": EXPIRED, "code": None, "raw": txt}
        return {"state": WAIT, "code": None, "raw": txt}

    # -- 3. 换取登录 Cookie -------------------------------------------------
    def _finish_variants(self, wx_code: str) -> List[Tuple[str, str, str]]:
        """(描述, 完整URL, Referer) 候选。真实流程是 open.weixin.qq.com 的 iframe
        跳到 redirect_uri，所以优先用 open.weixin.qq.com 作为来源。"""
        q = urllib.parse.quote(wx_code)
        base = f"{REDIRECT_URI}&code={q}&state={STATE}"
        return [
            ("iframe来源", base, "https://open.weixin.qq.com/"),
            ("iframe来源+wx_appid", base + f"&wx_appid={APPID}", "https://open.weixin.qq.com/"),
            ("docs来源", base, "https://docs.qq.com/"),
        ]

    def finish(self, wx_code: str) -> str:
        """用 wx_code 走 redirect_uri，收集 docs.qq.com 的登录 Cookie。"""
        diagnostics: List[str] = []
        for label, url, referer in self._finish_variants(wx_code):
            try:
                status, body = self._open_resp(url, referer=referer)
            except Exception as exc:  # noqa: BLE001
                diagnostics.append(f"[{label}] 请求异常 {exc}")
                continue
            cks = self._qq_cookies()
            if "uid" in cks:
                self.diag = f"[{label}] 成功，Cookie 数={len(cks)}"
                return self._cookie_str()
            snippet = body[:120].decode("utf-8", "ignore").replace("\n", " ") if body else ""
            diagnostics.append(
                f"[{label}] HTTP {status}；已获 Cookie={sorted(cks)[:8]}；响应片段={snippet!r}")
        self.diag = " || ".join(diagnostics)
        raise QrLoginError("登录未成功（未拿到 uid）。诊断：" + self.diag)

    def login(self, on_qr, timeout: int = 300, interval: float = 2.0) -> str:
        """一站式：生成二维码 -> 回调 on_qr(qr_url) -> 轮询 -> 返回 Cookie。"""
        info = self.start()
        on_qr(info["qr_url"])
        deadline = time.time() + timeout
        while time.time() < deadline:
            res = self.poll()
            if res["state"] == CONFIRMED and res["code"]:
                return self.finish(res["code"])
            if res["state"] == EXPIRED:
                info = self.restart()
                on_qr(info["qr_url"])
            time.sleep(interval)
        raise QrLoginError("扫码登录超时")
