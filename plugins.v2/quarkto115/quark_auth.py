# -*- coding: utf-8 -*-
"""夸克网盘扫码登录与凭证管理。

基于夸克官方 CAS 扫码接口实现。接口与参数参考社区项目 xiaoya-alist 的
``glue_python/quark_cookie/quark_cookie.py``，在此基础上补齐了插件场景需要的
状态机、凭证校验与手动 cookie 兜底能力。

设计上刻意不依赖 MoviePilot 的任何模块，只用标准库与 ``requests``，
这样可以脱离宿主单独跑通与测试。

登录流程（五步）::

    1. getTokenForQrcodeLogin        -> token
    2. 用 token 拼二维码内容供 APP 扫码
    3. getServiceTicketByQrcodeToken -> service_ticket（轮询）
    4. pan.quark.cn/account/info     -> 主 cookie
    5. drive-pc.quark.cn/.../config  -> 补充 cookie（__puus 等）
"""

import time
import uuid
from typing import Optional, Tuple

import requests

# 夸克网页端固定的扫码参数
CLIENT_ID = "532"
CAS_VERSION = "1.2"

# 客户端标识，需与网页端保持一致，否则接口返回 401
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "quark-cloud-drive/2.5.20 Chrome/100.0.4896.160 Electron/18.3.5.4-b478491100 "
    "Safari/537.36 Channel/pckk_other_ch"
)
REFERER = "https://pan.quark.cn/"
ORIGIN = "https://pan.quark.cn"

TOKEN_URL = "https://uop.quark.cn/cas/ajax/getTokenForQrcodeLogin"
TICKET_URL = "https://uop.quark.cn/cas/ajax/getServiceTicketByQrcodeToken"
ACCOUNT_URL = "https://pan.quark.cn/account/info"
CONFIG_URL = "https://drive-pc.quark.cn/1/clouddrive/config"
LIST_URL = "https://drive-pc.quark.cn/1/clouddrive/file/sort"

# 扫码状态
STATUS_SUCCESS = 2000000
STATUS_WAITING = 50004001
STATUS_EXPIRED = 50004002

# 网盘业务接口的成功状态码，与 CAS 登录接口不同，切勿混用
API_SUCCESS = 200

# 轮询结果状态
STATE_PENDING = "pending"
STATE_SUCCESS = "success"
STATE_EXPIRED = "expired"
STATE_ERROR = "error"


def _cookie_to_string(cookies) -> str:
    """把响应中的 cookie 转换为请求头可用的字符串。"""
    return "; ".join(f"{c.name}={c.value}" for c in cookies)


class QuarkAuth:
    """夸克网盘扫码登录与凭证管理。"""

    def __init__(self, timeout: int = 15):
        """初始化登录器。

        :param timeout: 单次 HTTP 请求超时秒数
        """
        self.timeout = timeout
        self._session = requests.Session()

    # ------------------------------------------------------------------ #
    # 扫码登录
    # ------------------------------------------------------------------ #
    def fetch_login_token(self) -> Optional[str]:
        """获取扫码用的 token。

        :return: token 字符串，失败返回 None
        """
        try:
            resp = self._session.get(
                TOKEN_URL,
                params={
                    "client_id": CLIENT_ID,
                    "v": CAS_VERSION,
                    "request_id": str(uuid.uuid4()),
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            data = resp.json()
            if data.get("status") != STATUS_SUCCESS:
                return None
            return (data.get("data") or {}).get("members", {}).get("token")
        except Exception:
            return None

    @staticmethod
    def build_qrcode_url(token: str) -> str:
        """根据 token 构造二维码内容。

        :param token: fetch_login_token 返回的 token
        :return: 二维码中应编码的 URL
        """
        return (
            f"https://su.quark.cn/4_eMHBJ?token={token}&client_id={CLIENT_ID}"
            f"&ssb=weblogin&uc_param_str=&uc_biz_str=S%3Acustom%7COPT%3ASAREA%400"
            f"%7COPT%3AIMMERSIVE%401%7COPT%3ABACK_BTN_STYLE%400"
        )

    def poll_once(self, token: str) -> Tuple[str, str]:
        """轮询一次扫码状态。

        :param token: 二维码对应的 token
        :return: (状态, cookie 或错误信息)。状态为 STATE_SUCCESS 时第二个值是 cookie
        """
        try:
            resp = self._session.get(
                TICKET_URL,
                params={
                    "client_id": CLIENT_ID,
                    "v": CAS_VERSION,
                    "token": token,
                    "request_id": str(uuid.uuid4()),
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return STATE_ERROR, f"HTTP {resp.status_code}"
            data = resp.json()
            status = data.get("status")
            if status == STATUS_SUCCESS:
                ticket = (data.get("data") or {}).get("members", {}).get("service_ticket")
                if not ticket:
                    return STATE_ERROR, "未取到 service_ticket"
                cookie = self.exchange_cookie(ticket)
                if cookie:
                    return STATE_SUCCESS, cookie
                return STATE_ERROR, "凭证换取失败"
            if status == STATUS_WAITING:
                return STATE_PENDING, "等待扫码"
            if status == STATUS_EXPIRED:
                return STATE_EXPIRED, "二维码已过期"
            return STATE_ERROR, f"未知状态 {status}"
        except Exception as err:
            return STATE_ERROR, str(err)

    def exchange_cookie(self, service_ticket: str) -> Optional[str]:
        """用 service_ticket 换取完整 cookie。

        :param service_ticket: 扫码成功后得到的票据
        :return: 完整 cookie 字符串，失败返回 None
        """
        try:
            resp = self._session.get(
                ACCOUNT_URL,
                params={"st": service_ticket, "lw": "scan"},
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            cookie = _cookie_to_string(resp.cookies)
            if not cookie:
                return None
            # 补充 __puus 等字段，缺失会导致后续接口鉴权失败
            extra = self._session.get(
                CONFIG_URL,
                params={"pr": "ucpro", "fr": "pc", "uc_param_str": ""},
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": REFERER,
                    "Cookie": cookie,
                },
                timeout=self.timeout,
            )
            if extra.status_code == 200:
                extra_cookie = _cookie_to_string(extra.cookies)
                if extra_cookie:
                    cookie = f"{cookie}; {extra_cookie}"
            return cookie
        except Exception:
            return None

    def wait_for_login(self, token: str, timeout: int = 300, interval: float = 2.0) -> Tuple[str, str]:
        """阻塞等待扫码完成，供脚本或非交互场景使用。

        :param token: 二维码 token
        :param timeout: 最长等待秒数
        :param interval: 轮询间隔秒数
        :return: 同 poll_once
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            state, payload = self.poll_once(token)
            if state in (STATE_SUCCESS, STATE_EXPIRED, STATE_ERROR):
                return state, payload
            time.sleep(interval)
        return STATE_EXPIRED, "等待超时"

    # ------------------------------------------------------------------ #
    # 凭证校验
    # ------------------------------------------------------------------ #
    def validate(self, cookie: str) -> bool:
        """校验 cookie 是否仍然有效。

        通过列根目录接口探测；注意必须携带 pr/fr 参数，否则恒返回 401。

        :param cookie: 待校验的 cookie
        :return: 有效返回 True
        """
        if not cookie:
            return False
        try:
            resp = self._session.get(
                LIST_URL,
                params={
                    "pdir_fid": "0",
                    "_page": 1,
                    "_size": 1,
                    "_fetch_total": 0,
                    "_fetch_sub_dirs": 0,
                    "_sort": "file_type:asc,updated_at:desc",
                    "pr": "ucpro",
                    "fr": "pc",
                },
                headers={
                    "User-Agent": USER_AGENT,
                    "Referer": REFERER,
                    "Origin": ORIGIN,
                    "Cookie": cookie,
                },
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return False
            return resp.json().get("status") == API_SUCCESS
        except Exception:
            return False

    def close(self) -> None:
        """关闭底层会话释放连接。"""
        try:
            self._session.close()
        except Exception:
            pass
