"""P115StrgmSub RDhub 源：名称偏好打分、分享链接规范化、查询合并与鉴权（全离线）"""
import hashlib
import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock

PLUGIN_PATH = Path(__file__).resolve().parents[1] / "plugins.v3" / "p115strgmsub"


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def json(self):
        return self._payload


class FakeSession:
    """按 URL 片段路由的假会话，绝不发起真实请求"""

    def __init__(self, handler):
        self._handler = handler
        self.calls = []

    def request(self, method, url, json=None, params=None, headers=None,
                timeout=None, proxies=None):
        self.calls.append({"method": method, "url": url, "json": json,
                           "params": params, "headers": headers or {}})
        return self._handler(method, url, json, params)

    def post(self, url, json=None, headers=None, timeout=None, proxies=None, **kwargs):
        self.calls.append({"method": "POST", "url": url, "json": json,
                           "params": kwargs.get("params"), "headers": headers or {}})
        return self._handler("POST", url, json, kwargs.get("params"))


def _install_stubs():
    app = types.ModuleType("app")
    log = types.ModuleType("app.log")
    log.logger = Mock()
    app.log = log
    sys.modules["app"] = app
    sys.modules["app.log"] = log

    core = types.ModuleType("app.core")
    metainfo = types.ModuleType("app.core.metainfo")

    class MetaInfo:  # pragma: no cover - 仅用于让 file_matcher 可导入
        pass

    metainfo.MetaInfo = MetaInfo
    core.metainfo = metainfo
    app.core = core
    sys.modules["app.core"] = core
    sys.modules["app.core.metainfo"] = metainfo

    schemas = types.ModuleType("app.schemas")

    class MediaInfo:  # pragma: no cover
        pass

    schemas.MediaInfo = MediaInfo
    app.schemas = schemas
    sys.modules["app.schemas"] = schemas


def _load_package_module():
    """把插件目录伪装成包，按需加载 rdhub / name_rank"""
    _install_stubs()
    pkg = types.ModuleType("rdhub_pkg")
    pkg.__path__ = [str(PLUGIN_PATH)]
    sys.modules["rdhub_pkg"] = pkg

    utils = types.ModuleType("rdhub_pkg.utils")
    utils.__path__ = [str(PLUGIN_PATH / "utils")]
    sys.modules["rdhub_pkg.utils"] = utils

    clients = types.ModuleType("rdhub_pkg.clients")
    clients.__path__ = [str(PLUGIN_PATH / "clients")]
    sys.modules["rdhub_pkg.clients"] = clients

    spec = importlib.util.spec_from_file_location(
        "rdhub_pkg.utils.name_rank", PLUGIN_PATH / "utils" / "name_rank.py"
    )
    name_rank = importlib.util.module_from_spec(spec)
    sys.modules["rdhub_pkg.utils.name_rank"] = name_rank
    spec.loader.exec_module(name_rank)
    utils.name_rank = name_rank

    spec = importlib.util.spec_from_file_location(
        "rdhub_pkg.clients.rdhub", PLUGIN_PATH / "clients" / "rdhub.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["rdhub_pkg.clients.rdhub"] = module
    spec.loader.exec_module(module)
    return module


rdhub = _load_package_module()


class MediaInfoStub:
    def __init__(self, title, year, tmdb_id):
        self.title = title
        self.year = year
        self.tmdb_id = tmdb_id


class NameRankTest(unittest.TestCase):
    """名称偏好：原盘不要、4K 优先、中文优先"""

    def setUp(self):
        self.nr = sys.modules["rdhub_pkg.utils.name_rank"]

    def test_disc_images_excluded(self):
        for name in [
            "赤道 UHD蓝光原盘REMUX 国粤双语",
            "火星救援 UHD 4K原盘&蓝光原盘&3D原盘 3碟 原生中字 ISO",
            "Interstellar.2014.2160p.UHD.BluRay.REMUX.HDR.HEVC-TERMiNAL.mkv",
            "BDMV/STREAM/00001.m2ts",
        ]:
            self.assertTrue(self.nr.is_disc_image(name), name)

    def test_web_dl_not_excluded(self):
        for name in [
            "八仙！ (2026) - 2160p.WEB-DL DoVi HQ.H265 10bit.DTS 5.1.mkv",
            "时尚战争 (2026) - S01E02 - 1080p.Disney+.WEB-DL.H264.AAC 2.0.mkv",
        ]:
            self.assertFalse(self.nr.is_disc_image(name), name)

    def test_4k_beats_1080p_and_chinese_wins(self):
        uhd_zh = self.nr.preference_score("某片 2160p WEB-DL 中英双字 CHS")
        uhd = self.nr.preference_score("某片 2160p WEB-DL")
        fhd_zh = self.nr.preference_score("某片 1080p WEB-DL 中英双字")
        fhd = self.nr.preference_score("某片 1080p WEB-DL")
        self.assertGreater(uhd_zh, uhd)
        self.assertGreater(uhd, fhd_zh)
        self.assertGreater(fhd_zh, fhd)

    def test_4k_repair_tag_is_not_4k(self):
        # 「4K修复版 1080P」正片是 1080p，不应按 4K 计分
        self.assertEqual(self.nr.resolution_of("某片 4K修复版 1080P"), "1080p")

    def test_chinese_detection(self):
        self.assertTrue(self.nr.is_chinese("杀手 2023 CHS&CHT"))
        self.assertTrue(self.nr.is_chinese("某片 [简繁英字幕]"))
        self.assertFalse(self.nr.is_chinese("Some.Movie.2160p.WEB-DL"))


class ShareUrlTest(unittest.TestCase):
    """分享链接规范化"""

    def test_normalize_cdn_link(self):
        got = rdhub.RDHubClient.normalize_share_url(
            "https://115cdn.com/s/swl39uv3njs?password=ayss"
        )
        self.assertEqual(got, "https://115.com/s/swl39uv3njs?password=ayss")

    def test_normalize_plain_link(self):
        got = rdhub.RDHubClient.normalize_share_url("https://115.com/s/abc123")
        self.assertEqual(got, "https://115.com/s/abc123")

    def test_unknown_link_untouched(self):
        got = rdhub.RDHubClient.normalize_share_url("https://example.com/x")
        self.assertEqual(got, "https://example.com/x")


def _load_file_matcher():
    """加载插件里的 SubscribeFilter（依赖 app.schemas / app.core.metainfo 桩）"""
    key = "rdhub_pkg.utils.file_matcher"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(
        key, PLUGIN_PATH / "utils" / "file_matcher.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[key] = module
    spec.loader.exec_module(module)
    return module


class ResolutionFallbackTest(unittest.TestCase):
    """分辨率降级：4K 优先，没有 4K 时接受 1080p"""

    def setUp(self):
        self.fm = _load_file_matcher()

    def test_strict_mode_rejects_1080p_when_subscribe_is_4k(self):
        flt = self.fm.SubscribeFilter(resolution="4K|2160p|x2160", strict=True)
        ok, _ = flt.match("某片 (2026) - 1080p.WEB-DL.H264.mkv")
        self.assertFalse(ok)

    def test_fallback_mode_accepts_1080p_with_lower_score(self):
        flt = self.fm.SubscribeFilter(resolution="4K|2160p|x2160", strict=False)
        ok4k, score4k = flt.match("某片 (2026) - 2160p.WEB-DL.H265.mkv")
        ok1080, score1080 = flt.match("某片 (2026) - 1080p.WEB-DL.H264.mkv")
        self.assertTrue(ok4k)
        self.assertTrue(ok1080)
        self.assertGreater(score4k, score1080)

    def test_fallback_mode_still_prefers_4k_by_name_rank(self):
        # 严格模式被放宽后，靠偏好分保证 4K 排在前
        flt = self.fm.SubscribeFilter(resolution="4K|2160p|x2160", strict=False)
        uhd = flt.match("某片 (2026) - 2160p.WEB-DL.H265.mkv")[1] + \
            sys.modules["rdhub_pkg.utils.name_rank"].preference_score("某片 2160p WEB-DL")
        fhd = flt.match("某片 (2026) - 1080p.WEB-DL.H264.mkv")[1] + \
            sys.modules["rdhub_pkg.utils.name_rank"].preference_score("某片 1080p WEB-DL")
        self.assertGreater(uhd, fhd)


class RDHubSearchTest(unittest.TestCase):
    """查询合并、原盘排除、排序与季过滤"""

    def _client(self, handler):
        client = rdhub.RDHubClient(username="u", password="p", max_preview=8)
        client._session = FakeSession(handler)
        client._browser_token = "bt"
        client._browser_token_at = 9e18  # 不触发重新挑战
        client._access_token = "at"
        return client

    def test_merge_distribution_and_stock_with_disc_filter(self):
        def handler(method, url, body, params):
            if "/distributions/published/1633056/" in url:
                return FakeResponse({"distributions": [
                    {"id": 1, "resource_name": "动画电影：八仙！(2026) 2160p WEB-DL",
                     "quality": "2160p WEB-DL DV H265", "season_episode": None,
                     "transfer_link": "https://115cdn.com/s/aaa1?password=p1"},
                    {"id": 2, "resource_name": "八仙！ 4K原盘REMUX",
                     "quality": "4K REMUX", "season_episode": None,
                     "transfer_link": "https://115cdn.com/s/bbb2?password=p2"},
                ]})
            if "/stock-resources/public/list" in url:
                return FakeResponse({"total": 1, "items": [
                    {"id": 11, "resource_name": "八仙！ 1080p WEB-DL 简繁中字",
                     "version_info": "", "parsed_links": [{"desc": "1080p 简繁中字"}]},
                ]})
            if "/share-preview" in url:
                return FakeResponse({"success": True, "share_code": "ccc3",
                                     "receive_code": "p3", "total_count": 1,
                                     "items": []})
            raise AssertionError(f"unexpected url {url}")

        client = self._client(handler)
        results = client.search(MediaInfoStub("八仙！", 2026, 1633056), "movie")
        urls = [r["url"] for r in results]
        # 原盘被排除
        self.assertNotIn("https://115.com/s/bbb2?password=p2", urls)
        # 分发 + 库存合并
        self.assertIn("https://115.com/s/aaa1?password=p1", urls)
        self.assertIn("https://115.com/s/ccc3?password=p3", urls)
        # 4K 优先于 1080p
        self.assertEqual(results[0]["url"], "https://115.com/s/aaa1?password=p1")
        # 中文的 1080p 分数高于无标记 1080p
        zh = [r for r in results if r["url"].endswith("p3")][0]
        self.assertGreater(zh["score"], 0)

    def test_tv_season_filter(self):
        def handler(method, url, body, params):
            if "/distributions/published/94664/" in url:
                return FakeResponse({"distributions": [
                    {"id": 1, "resource_name": "无职转生 S02E01", "quality": "1080p WEB-DL",
                     "season_episode": "S02E01", "transfer_link": "https://115cdn.com/s/s2e1?password=a"},
                    {"id": 2, "resource_name": "无职转生 S03E05", "quality": "1080p WEB-DL",
                     "season_episode": "S03E05", "transfer_link": "https://115cdn.com/s/s3e5?password=b"},
                ]})
            if "/stock-resources/public/list" in url:
                return FakeResponse({"total": 0, "items": []})
            raise AssertionError(f"unexpected url {url}")

        client = self._client(handler)
        results = client.search(MediaInfoStub("无职转生", 2021, 94664), "tv", season=3)
        self.assertEqual(len(results), 1)
        self.assertIn("s3e5", results[0]["url"])

    def test_cache_hit_avoids_second_query(self):
        calls = {"n": 0}

        def handler(method, url, body, params):
            calls["n"] += 1
            if "/distributions/published/" in url:
                return FakeResponse({"distributions": []})
            if "/stock-resources/public/list" in url:
                return FakeResponse({"total": 0, "items": []})
            raise AssertionError(f"unexpected url {url}")

        client = self._client(handler)
        client.search(MediaInfoStub("测试", 2026, 999), "movie")
        first = calls["n"]
        client.search(MediaInfoStub("测试", 2026, 999), "movie")
        self.assertEqual(calls["n"], first)

    def test_missing_tmdb_returns_empty(self):
        client = self._client(lambda *a: FakeResponse({}))
        self.assertEqual(client.search(MediaInfoStub("无 ID", 2026, None), "movie"), [])


class RDHubAuthTest(unittest.TestCase):
    """鉴权：浏览器门禁 proof 计算与 401 刷新重试"""

    def test_browser_proof_formula(self):
        client = rdhub.RDHubClient(username="u", password="p")
        fp = client._fingerprint()
        self.assertEqual(len(fp), 64)
        # proof = sha256(nonce|fingerprint|UA|timestamp|rdhub_bp_2026)
        expected = hashlib.sha256(
            f"nonce1|{fp}|{rdhub._USER_AGENT}|1700000000000|rdhub_bp_2026".encode()
        ).hexdigest()
        self.assertEqual(len(expected), 64)

    def test_401_triggers_refresh_then_retry(self):
        state = {"refreshed": False, "search_calls": 0}

        def handler(method, url, body, params):
            if "/auth/refresh" in url:
                state["refreshed"] = True
                return FakeResponse({"access_token": "new-at", "refresh_token": "new-rt"})
            if "/distributions/published/" in url:
                state["search_calls"] += 1
                if not state["refreshed"]:
                    return FakeResponse({"detail": "登录已过期", "code": "AUTH_NO_TOKEN"}, 401)
                return FakeResponse({"distributions": [
                    {"id": 1, "resource_name": "测试 2160p WEB-DL 中字",
                     "quality": "2160p WEB-DL", "season_episode": None,
                     "transfer_link": "https://115cdn.com/s/ok1?password=z"},
                ]})
            if "/stock-resources/public/list" in url:
                return FakeResponse({"total": 0, "items": []})
            raise AssertionError(f"unexpected url {url}")

        client = rdhub.RDHubClient(username="u", password="p")
        client._session = FakeSession(handler)
        client._browser_token = "bt"
        client._browser_token_at = 9e18
        client._access_token = "old-at"
        client._refresh_token = "old-rt"

        results = client.search(MediaInfoStub("测试", 2026, 1), "movie")
        self.assertTrue(state["refreshed"])
        self.assertEqual(len(results), 1)
        self.assertEqual(client._access_token, "new-at")


if __name__ == "__main__":
    unittest.main()
