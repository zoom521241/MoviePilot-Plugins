"""
RDhub（rdhub115.cc）115 网盘资源源客户端

站点定位：115 分享资源分发平台，按 TMDB ID 提供「分发」与「库存」两类资源，
两类都直接给出 115 分享链接（或可通过 share-preview 换取分享码）。

接入方式：
  1. 过浏览器门禁（browser-challenge / browser-verify，SHA-256 可本地复现）
  2. 账号密码登录换取 access_token / refresh_token
  3. 按 TMDB ID 查询资源，统一转换成插件内部使用的 PanSou 结构：
     {"title": 资源标题, "url": 115 分享链接, "tmdb_id": ..., "source": "rdhub"}

筛选口径（可配置）：
  - 原盘/蓝光镜像（REMUX、BDMV、BDISO、原盘、ISO）直接排除
  - 4K / 2160p 优先，中文（简繁/中字/国语/双语）优先
"""
import hashlib
import re
import time
from typing import Any, Dict, List, Optional

import requests

from app.log import logger

from ..utils import name_rank

# 站点默认地址（可在配置里改）
DEFAULT_BASE_URL = "https://www.rdhub115.cc"

# 固定指纹，必须与请求头 UA 一致（服务端会按 UA 参与 proof 校验）
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
)
_LANG = "zh-CN"
_SCREEN = ("1920", "1080", "24")
_BP_SALT = "rdhub_bp_2026"

# season_episode 形如 S03E14 / S01E117,S23E115-S23E117
_EPISODE_RE = re.compile(r"S(\d{1,3})E(\d{1,4})", re.IGNORECASE)
_SEASON_ONLY_RE = re.compile(r"S(\d{1,3})(?!E\d)", re.IGNORECASE)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class RDHubError(Exception):
    """RDhub 调用异常"""

    def __init__(self, message: str, status: Optional[int] = None, code: str = ""):
        super().__init__(message)
        self.status = status
        self.code = code


class RDHubClient:
    """RDhub 客户端"""

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        username: str = "",
        password: str = "",
        access_token: str = "",
        refresh_token: str = "",
        proxy: Any = None,
        on_token_update: Optional[Any] = None,
        exclude_disc: bool = True,
        max_preview: int = 8,
        timeout: int = 20,
        cache_ttl: int = 900,
    ):
        """
        :param base_url: 站点地址，如 https://www.rdhub115.cc
        :param username: 站点账号
        :param password: 站点密码
        :param access_token: 已保存的 access_token（可留空，自动登录获取）
        :param refresh_token: 已保存的 refresh_token
        :param proxy: MP 代理配置（字符串或 dict）
        :param on_token_update: Token 变更回调，用于持久化到插件配置
        :param exclude_disc: 是否排除原盘/蓝光镜像
        :param max_preview: 单次查询最多换取多少个分享码（控制请求量）
        :param timeout: 请求超时（秒）
        :param cache_ttl: 查询结果缓存时间（秒）
        """
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.username = (username or "").strip()
        self.password = (password or "").strip()
        self._access_token = (access_token or "").strip()
        self._refresh_token = (refresh_token or "").strip()
        self._on_token_update = on_token_update
        self.exclude_disc = bool(exclude_disc)
        self.max_preview = max(1, int(max_preview or 8))
        self.timeout = max(5, int(timeout or 20))
        self.cache_ttl = max(0, int(cache_ttl or 0))

        self._browser_token: str = ""
        self._browser_token_at: float = 0.0
        self._cache: Dict[str, Any] = {}
        self._session = requests.Session()
        if proxy:
            self._proxies = proxy if isinstance(proxy, dict) else {"http": proxy, "https": proxy}
        else:
            self._proxies = None

    # ------------------------------------------------------------------
    # 基础请求
    # ------------------------------------------------------------------
    @property
    def is_ready(self) -> bool:
        """是否具备可用配置"""
        return bool(self.username and self.password) or bool(self._access_token)

    def _url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url}/api{path}"

    def _headers(self, with_browser_token: bool = True) -> Dict[str, str]:
        headers = {
            "User-Agent": _USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Origin": self.base_url,
            "Referer": f"{self.base_url}/",
        }
        if with_browser_token and self._browser_token:
            headers["X-Browser-Token"] = self._browser_token
        if self._access_token:
            headers["Authorization"] = f"Bearer {self._access_token}"
        return headers

    def _request(self, method: str, path: str, json_body: Any = None,
                 params: Optional[Dict[str, Any]] = None, with_auth: bool = True,
                 retry_auth: bool = True) -> Any:
        """
        统一请求入口：自动补浏览器令牌与 Bearer，401 时刷新 Token 后重试一次
        """
        if with_auth:
            self._ensure_browser_token()
            self._ensure_access_token()

        url = self._url(path)
        try:
            resp = self._session.request(
                method=method,
                url=url,
                json=json_body,
                params=params,
                headers=self._headers(with_browser_token=with_auth),
                timeout=self.timeout,
                proxies=self._proxies,
            )
        except requests.RequestException as e:
            raise RDHubError(f"请求失败：{e}")

        if resp.status_code == 401 and with_auth and retry_auth:
            if self._refresh_access_token():
                return self._request(method, path, json_body=json_body, params=params,
                                     with_auth=with_auth, retry_auth=False)
            if self._login():
                return self._request(method, path, json_body=json_body, params=params,
                                     with_auth=with_auth, retry_auth=False)
            raise RDHubError("登录已失效，请检查账号密码", status=401, code="AUTH_NO_TOKEN")

        if resp.status_code == 403:
            body = self._safe_json(resp)
            code = (body or {}).get("code") or (body or {}).get("reason") or ""
            if code == "BROWSER_PROOF_INVALID" or "浏览器" in str((body or {}).get("detail", "")):
                # 浏览器令牌失效，重置后重试一次
                self._browser_token = ""
                self._browser_token_at = 0.0
                if retry_auth:
                    return self._request(method, path, json_body=json_body, params=params,
                                         with_auth=with_auth, retry_auth=False)
            raise RDHubError(
                f"浏览器校验未通过：{(body or {}).get('detail') or resp.text[:120]}",
                status=403, code=code,
            )

        if resp.status_code >= 400:
            body = self._safe_json(resp)
            detail = (body or {}).get("detail") if isinstance(body, dict) else None
            raise RDHubError(f"接口返回 {resp.status_code}：{detail or resp.text[:160]}",
                             status=resp.status_code)

        return self._safe_json(resp)

    @staticmethod
    def _safe_json(resp: Any) -> Any:
        try:
            return resp.json()
        except Exception:
            return None

    # ------------------------------------------------------------------
    # 浏览器门禁 + 登录
    # ------------------------------------------------------------------
    def _fingerprint(self) -> str:
        return _sha256("|".join([_USER_AGENT, _LANG, _SCREEN[0], _SCREEN[1], _SCREEN[2]]))

    def _ensure_browser_token(self) -> None:
        """浏览器门禁令牌（服务端与 IP/时间绑定，缓存 20 分钟）"""
        if self._browser_token and (time.time() - self._browser_token_at) < 1200:
            return
        self._browser_token = self._obtain_browser_token()
        self._browser_token_at = time.time()

    def _obtain_browser_token(self) -> str:
        challenge = self._request("GET", "/auth/browser-challenge", with_auth=False)
        if not isinstance(challenge, dict) or not challenge.get("nonce"):
            raise RDHubError("无法获取浏览器校验挑战", code="challenge_failed")
        nonce = challenge.get("nonce") or ""
        challenge_key = challenge.get("challenge_key") or ""
        fingerprint = self._fingerprint()
        timestamp = int(time.time() * 1000)
        proof = _sha256(f"{nonce}|{fingerprint}|{_USER_AGENT}|{timestamp}|{_BP_SALT}")
        result = self._request(
            "POST",
            "/auth/browser-verify",
            json_body={
                "challenge_key": challenge_key,
                "nonce": nonce,
                "fingerprint": fingerprint,
                "timestamp": timestamp,
                "proof": proof,
                "user_agent": _USER_AGENT,
            },
            with_auth=False,
        )
        token = (result or {}).get("browser_token") if isinstance(result, dict) else ""
        if not token:
            raise RDHubError("浏览器校验失败，未能获取令牌", code="proof_mismatch")
        return token

    def _ensure_access_token(self) -> None:
        if not self._access_token:
            if not self._login():
                raise RDHubError("RDhub 未登录：请在插件配置中填写站点账号密码", code="AUTH_NO_TOKEN")

    def _login(self) -> bool:
        """账号密码登录"""
        if not self.username or not self.password:
            logger.warning("RDhub 未配置账号密码，无法登录")
            return False
        self._ensure_browser_token()
        # 登录需要带浏览器令牌，但此时还没有 Bearer；单独走一次请求
        resp = self._session.post(
            self._url("/auth/login"),
            json={"username": self.username, "password": self.password},
            headers={**self._headers(with_browser_token=True), "x-host": self.base_url.split("://")[-1]},
            timeout=self.timeout,
            proxies=self._proxies,
        )
        if resp.status_code == 403:
            body = self._safe_json(resp) or {}
            if body.get("code") == "BROWSER_PROOF_INVALID":
                self._browser_token = ""
                self._browser_token_at = 0.0
                self._ensure_browser_token()
                resp = self._session.post(
                    self._url("/auth/login"),
                    json={"username": self.username, "password": self.password},
                    headers={**self._headers(with_browser_token=True),
                             "x-host": self.base_url.split("://")[-1]},
                    timeout=self.timeout,
                    proxies=self._proxies,
                )
        if resp.status_code != 200:
            body = self._safe_json(resp) or {}
            logger.error(f"RDhub 登录失败（{resp.status_code}）：{body.get('detail') or resp.text[:160]}")
            return False

        data = self._safe_json(resp) or {}
        access = data.get("access_token") or ""
        refresh = data.get("refresh_token") or ""
        if not access:
            logger.error("RDhub 登录响应缺少 access_token")
            return False
        self._set_tokens(access, refresh)
        logger.info("RDhub 登录成功")
        return True

    def _refresh_access_token(self) -> bool:
        if not self._refresh_token:
            return False
        try:
            resp = self._session.post(
                self._url("/auth/refresh"),
                json={"refresh_token": self._refresh_token},
                headers=self._headers(with_browser_token=True),
                timeout=self.timeout,
                proxies=self._proxies,
            )
        except requests.RequestException as e:
            logger.warning(f"RDhub 刷新 Token 请求失败：{e}")
            return False
        if resp.status_code != 200:
            return False
        data = self._safe_json(resp) or {}
        access = data.get("access_token") or ""
        if not access:
            return False
        self._set_tokens(access, data.get("refresh_token") or self._refresh_token)
        return True

    def _set_tokens(self, access: str, refresh: str) -> None:
        self._access_token = access
        self._refresh_token = refresh or self._refresh_token
        if self._on_token_update:
            try:
                self._on_token_update({
                    "access_token": self._access_token,
                    "refresh_token": self._refresh_token,
                    "token_expires_at": time.time() + 3300,
                })
            except Exception as e:
                logger.debug(f"RDhub Token 持久化失败：{e}")

    # ------------------------------------------------------------------
    # 资源查询
    # ------------------------------------------------------------------
    def _cache_get(self, key: str) -> Optional[Any]:
        if not self.cache_ttl:
            return None
        hit = self._cache.get(key)
        if not hit:
            return None
        ts, value = hit
        if time.time() - ts > self.cache_ttl:
            self._cache.pop(key, None)
            return None
        return value

    def _cache_set(self, key: str, value: Any) -> None:
        if not self.cache_ttl:
            return
        # 控制缓存规模
        if len(self._cache) > 256:
            self._cache.clear()
        self._cache[key] = (time.time(), value)

    @staticmethod
    def _normalize_media_type(media_type: Any) -> str:
        text = str(getattr(media_type, "value", media_type) or "").lower()
        if "tv" in text or "电视" in text or "剧" in text:
            return "tv"
        return "movie"

    @staticmethod
    def _parse_episodes(text: str) -> List[tuple]:
        """从 season_episode / 描述里解析出 [(season, episode), ...]"""
        result: List[tuple] = []
        if not text:
            return result
        for match in _EPISODE_RE.finditer(text):
            try:
                season = int(match.group(1))
                episode = int(match.group(2))
            except (TypeError, ValueError):
                continue
            result.append((season, episode))
        return result

    def get_distributions(self, tmdb_id: Any, media_type: Any) -> List[Dict[str, Any]]:
        """
        查询「分发」资源（按集推送，链接为明文 115 分享）

        :return: [{"resource_name", "season_episode", "quality", "url", "published_at"}]
        """
        if not tmdb_id:
            return []
        mt = self._normalize_media_type(media_type)
        try:
            data = self._request(
                "GET", f"/v1/distributions/published/{tmdb_id}/{mt}/distributions"
            )
        except RDHubError as e:
            logger.warning(f"RDhub 分发查询失败（TMDB {tmdb_id}）：{e}")
            return []

        items = data.get("distributions") if isinstance(data, dict) else data
        results: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            url = (item.get("transfer_link") or item.get("original_link") or "").strip()
            if not url or "********" in url:
                continue
            results.append({
                "resource_id": item.get("id"),
                "resource_name": item.get("resource_name") or "",
                "season_episode": item.get("season_episode") or "",
                "quality": item.get("quality") or "",
                "url": self.normalize_share_url(url),
                "published_at": item.get("published_at") or item.get("created_at") or "",
                "channel": "distribution",
                "size": 0,
            })
        return results

    def search_stock(self, tmdb_id: Any, media_type: Any) -> List[Dict[str, Any]]:
        """
        查询「库存」资源（用户投稿，含 4K 与原盘，需要 share-preview 换分享码）

        :return: [{"resource_id", "resource_name", "parsed_links", ...}]
        """
        if not tmdb_id:
            return []
        mt = self._normalize_media_type(media_type)
        try:
            data = self._request(
                "GET",
                "/v1/stock-resources/public/list",
                params={"page": 1, "page_size": 20, "tmdb_id": tmdb_id, "media_type": mt},
            )
        except RDHubError as e:
            logger.warning(f"RDhub 库存查询失败（TMDB {tmdb_id}）：{e}")
            return []

        items = (data or {}).get("items") if isinstance(data, dict) else None
        results: List[Dict[str, Any]] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            results.append({
                "resource_id": item.get("id"),
                "resource_name": item.get("resource_name") or "",
                "version_info": item.get("version_info") or "",
                "season_summary": item.get("season_summary") or "",
                "parsed_links": item.get("parsed_links") or [],
                "published_at": item.get("distributed_at") or item.get("created_at") or "",
                "channel": "stock",
            })
        return results

    def preview_share(self, resource_id: Any, link_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        把库存资源的一条链接换成 115 分享码

        :return: {"share_code", "receive_code", "total_count", "items"}
        """
        try:
            data = self._request(
                "POST",
                f"/v1/stock-resources/public/{resource_id}/share-preview",
                json_body={"share_code": "", "receive_code": "", "link_index": link_index,
                           "cid": "0", "offset": 0, "limit": 20},
            )
        except RDHubError as e:
            logger.warning(f"RDhub 分享预览失败（资源 {resource_id} / link {link_index}）：{e}")
            return None
        if not isinstance(data, dict) or not data.get("success"):
            return None
        share_code = (data.get("share_code") or "").strip()
        if not share_code:
            return None
        return {
            "share_code": share_code,
            "receive_code": (data.get("receive_code") or "").strip(),
            "total_count": data.get("total_count") or 0,
            "items": data.get("items") or [],
        }

    # ------------------------------------------------------------------
    # 对外统一入口
    # ------------------------------------------------------------------
    def search(self, mediainfo: Any, media_type: Any, season: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        按 TMDB ID 查询资源，返回插件内部统一结构

        :param mediainfo: MP MediaInfo（使用 tmdb_id / title / year）
        :param media_type: MediaType
        :param season: 电视剧季号
        :return: [{"title", "url", "tmdb_id", "source", "score", "quality", "desc"}]
        """
        tmdb_id = getattr(mediainfo, "tmdb_id", None)
        title = getattr(mediainfo, "title", "") or ""
        year = getattr(mediainfo, "year", None) or ""
        mt = self._normalize_media_type(media_type)
        season = int(season) if season else None

        if not tmdb_id:
            logger.info(f"RDhub：{title} 缺少 TMDB ID，跳过")
            return []

        cache_key = f"{tmdb_id}|{mt}|{season or 0}"
        cached = self._cache_get(cache_key)
        if cached is not None:
            logger.info(f"RDhub：命中缓存 {len(cached)} 条（TMDB {tmdb_id}）")
            return cached

        if not self.is_ready:
            logger.warning("RDhub：未配置账号密码，跳过查询")
            return []

        logger.info(f"RDhub 查询：{title} ({year}) TMDB {tmdb_id} 类型 {mt}"
                    + (f" 季 {season}" if season else ""))

        candidates: List[Dict[str, Any]] = []

        # 1) 分发通道（明文链接、带集号、不消耗搜索配额）
        for item in self.get_distributions(tmdb_id, mt):
            desc = " ".join([item.get("resource_name", ""), item.get("quality", "")])
            if self.exclude_disc and name_rank.is_disc_image(desc):
                logger.info(f"RDhub：跳过原盘资源 {desc[:60]}")
                continue
            if mt == "tv" and season is not None:
                episodes = self._parse_episodes(item.get("season_episode") or desc)
                if episodes and not any(ep[0] == season for ep in episodes):
                    continue
            candidates.append({
                "title": self._build_title(title, year, item.get("season_episode"), item.get("quality")),
                "url": item.get("url"),
                "tmdb_id": tmdb_id,
                "source": "rdhub",
                "quality": item.get("quality") or "",
                "season_episode": item.get("season_episode") or "",
                "score": name_rank.preference_score(desc),
                "desc": desc.strip(),
            })

        # 2) 库存通道（可能含 4K 版本，需要换分享码）
        stock_items = self.search_stock(tmdb_id, mt)
        previewed = 0
        for item in stock_items:
            desc = " ".join([item.get("resource_name", ""), item.get("version_info", "")])
            if self.exclude_disc and name_rank.is_disc_image(desc):
                logger.info(f"RDhub：跳过原盘库存 {desc[:60]}")
                continue
            links = item.get("parsed_links") or []
            if not links:
                continue
            for index, link in enumerate(links):
                if previewed >= self.max_preview:
                    break
                link_desc = (link.get("desc") or "") if isinstance(link, dict) else ""
                full_desc = f"{desc} {link_desc}".strip()
                if self.exclude_disc and name_rank.is_disc_image(full_desc):
                    continue
                if mt == "tv" and season is not None:
                    episodes = self._parse_episodes(link_desc)
                    if episodes and not any(ep[0] == season for ep in episodes):
                        continue
                preview = self.preview_share(item.get("resource_id"), index)
                previewed += 1
                if not preview:
                    continue
                url = self._build_share_url(preview["share_code"], preview["receive_code"])
                candidates.append({
                    "title": self._build_title(title, year, link_desc, item.get("version_info")),
                    "url": url,
                    "tmdb_id": tmdb_id,
                    "source": "rdhub",
                    "quality": item.get("version_info") or "",
                    "season_episode": link_desc,
                    "score": name_rank.preference_score(full_desc),
                    "desc": full_desc,
                })
            if previewed >= self.max_preview:
                break

        # 去重（同一分享只保留一次）
        deduped: List[Dict[str, Any]] = []
        seen = set()
        for item in candidates:
            key = item.get("url")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)

        # 排序：偏好分数高者优先，其次按链接里的发布时间（已由服务端排序）
        deduped.sort(key=lambda x: x.get("score") or 0, reverse=True)

        for item in deduped[:10]:
            logger.info(f"RDhub 候选：{item.get('desc', '')[:80]} | 分数 {item.get('score')}")

        self._cache_set(cache_key, deduped)
        logger.info(f"RDhub：共 {len(deduped)} 个候选（TMDB {tmdb_id}）")
        return deduped

    @staticmethod
    def _build_share_url(share_code: str, receive_code: str) -> str:
        if receive_code:
            return f"https://115.com/s/{share_code}?password={receive_code}"
        return f"https://115.com/s/{share_code}"

    @staticmethod
    def normalize_share_url(url: str) -> str:
        """
        把站点给出的 115 分享链接规范成插件通用的 https://115.com/s/{code}?password={pwd}

        站点可能给 115cdn.com 域名或带额外查询参数，统一后再交给 p115client 解析。
        """
        if not url:
            return ""
        match = re.search(r"115(?:cdn)?\.com/s/([A-Za-z0-9]+)", url)
        if not match:
            return url
        share_code = match.group(1)
        pwd = ""
        pwd_match = re.search(r"[?&#]password=([^&\s]+)", url)
        if pwd_match:
            pwd = pwd_match.group(1)
        return RDHubClient._build_share_url(share_code, pwd)

    @staticmethod
    def _build_title(title: str, year: Any, extra: Optional[str], quality: Optional[str]) -> str:
        parts = [p for p in [title, f"({year})" if year else "", extra or "", quality or ""] if p]
        return " ".join(parts).strip()
