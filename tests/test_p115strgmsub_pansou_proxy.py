"""P115StrgmSub PanSou 客户端：内网代理绕过与失败语义（全离线，使用合成数据）"""
import importlib.util
import json
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

    def json(self):
        return self._payload


def _install_stubs(post_mock):
    """注入 app.log 与 requests 桩，保证不产生任何真实网络请求"""
    app = types.ModuleType("app")
    log = types.ModuleType("app.log")
    log.logger = Mock()
    app.log = log
    sys.modules["app"] = app
    sys.modules["app.log"] = log

    requests = types.ModuleType("requests")

    class Timeout(Exception):
        pass

    class RequestException(Exception):
        pass

    requests.exceptions = types.SimpleNamespace(
        Timeout=Timeout, RequestException=RequestException,
        ConnectionError=RequestException,
    )
    requests.post = post_mock
    sys.modules["requests"] = requests


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "pansou_under_test", PLUGIN_PATH / "clients" / "pansou.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SYNTHETIC_PAYLOAD = {
    "code": 0,
    "message": "success",
    "data": {
        "total": 2,
        "results": [
            {
                "title": "测试剧集 (2026) S01E02 4K WEB-DL",
                "datetime": "2026-01-02T00:00:00Z",
                "links": [
                    {"type": "115", "url": "https://115.test/s/aaa", "password": "1234"},
                    {"type": "quark", "url": "https://pan.quark.test/s/bbb"},
                ],
            },
            {
                "title": "测试剧集 (2026) S01E03 1080p",
                "datetime": "2026-01-03T00:00:00Z",
                "links": [{"type": "115", "url": "https://115.test/s/ccc"}],
            },
            {
                "title": "完全无关的片子 (1999)",
                "datetime": "2026-01-01T00:00:00Z",
                "links": [{"type": "115", "url": "https://115.test/s/ddd"}],
            },
        ],
    },
}


class PanSouProxyTest(unittest.TestCase):
    PROXY = {"http": "http://proxy.test:7893", "https": "http://proxy.test:7893"}

    def setUp(self):
        self.post = Mock(return_value=FakeResponse(SYNTHETIC_PAYLOAD))
        _install_stubs(self.post)
        sys.modules.pop("pansou_under_test", None)
        self.mod = _load_module()

    def _client(self, base_url, proxy=PROXY):
        return self.mod.PanSouClient(
            base_url=base_url,
            auth_enabled=False,
            proxy=dict(proxy) if proxy else None,
        )

    def _sent_proxies(self):
        self.assertEqual(self.post.call_count, 1, "应当且仅应当发出一次请求")
        return self.post.call_args.kwargs.get("proxies")

    # ---- 内网地址必须直连 ----
    def test_lan_ipv4_skips_proxy(self):
        client = self._client("http://192.168.31.95:9000/")
        self.assertIsNone(client._proxies)
        client.search(keyword="测试剧集", cloud_types=["115"])
        self.assertIsNone(self._sent_proxies())

    def test_loopback_skips_proxy(self):
        client = self._client("http://127.0.0.1:9000")
        self.assertIsNone(client._proxies)
        client.search(keyword="测试剧集", cloud_types=["115"])
        self.assertIsNone(self._sent_proxies())

    def test_lan_class_a_skips_proxy(self):
        client = self._client("http://10.0.0.8:9000")
        self.assertIsNone(client._proxies)

    def test_docker_hostname_skips_proxy(self):
        client = self._client("http://pansou:80")
        self.assertIsNone(client._proxies)

    def test_local_suffix_skips_proxy(self):
        client = self._client("http://nas.local:9000")
        self.assertIsNone(client._proxies)

    # ---- 公网地址仍走代理 ----
    def test_public_domain_keeps_proxy(self):
        client = self._client("https://so.example.com/")
        self.assertEqual(client._proxies, self.PROXY)
        client.search(keyword="测试剧集", cloud_types=["115"])
        self.assertEqual(self._sent_proxies(), self.PROXY)

    def test_public_ip_keeps_proxy(self):
        client = self._client("http://8.8.8.8:9000")
        self.assertEqual(client._proxies, self.PROXY)

    def test_no_proxy_configured(self):
        client = self._client("http://192.168.31.95:9000/", proxy=None)
        self.assertIsNone(client._proxies)

    # ---- 解析行为（合成数据）----
    def test_parse_only_115_and_title_filtered(self):
        client = self._client("http://192.168.31.95:9000/")
        result = client.search(keyword="测试剧集", cloud_types=["115"], limit=20)
        self.assertIsNone(result.get("error"))
        items = result["results"].get("115网盘", [])
        titles = [item["title"] for item in items]
        # 无关键帧的「完全无关的片子」应被标题匹配过滤掉
        self.assertEqual(len(items), 2)
        self.assertTrue(all("测试剧集" in t for t in titles))
        # 密码字段应被带出（结果按更新时间倒序，按标题定位而非按下标）
        e02 = next(i for i in items if "S01E02" in i["title"])
        self.assertEqual(e02.get("password"), "1234")
        e03 = next(i for i in items if "S01E03" in i["title"])
        self.assertNotIn("password", e03)

    # ---- 请求级失败必须可辨识，不能伪装成「没有资源」----
    def test_http_502_returns_error_not_empty(self):
        self.post.return_value = FakeResponse({"message": "Bad Gateway"}, status_code=502)
        client = self._client("http://192.168.31.95:9000/")
        result = client.search(keyword="测试剧集", cloud_types=["115"])
        self.assertIn("error", result)
        self.assertIn("502", result["error"])
        self.assertNotIn("results", result)

    def test_timeout_returns_error(self):
        self.post.side_effect = sys.modules["requests"].exceptions.Timeout()
        client = self._client("http://192.168.31.95:9000/")
        result = client.search(keyword="测试剧集", cloud_types=["115"])
        self.assertIn("error", result)

    def test_search_115_swallows_error_but_logs(self):
        self.post.return_value = FakeResponse({"message": "Bad Gateway"}, status_code=502)
        client = self._client("http://192.168.31.95:9000/")
        self.assertEqual(client.search_115(keyword="测试剧集"), [])


class SearchHandlerErrorTest(unittest.TestCase):
    """_pansou_search 在 error 时应返回空列表并留下告警，而不是静默"""

    def test_pansou_search_warns_on_error(self):
        post = Mock(return_value=FakeResponse({"message": "Bad Gateway"}, status_code=502))
        _install_stubs(post)
        sys.modules.pop("pansou_under_test", None)
        mod = _load_module()

        source = (PLUGIN_PATH / "handlers" / "search.py").read_text(encoding="utf-8")
        # 该分支必须在返回值前显式记录 error，避免把请求失败当成「确实没有资源」
        self.assertIn("PanSou 搜索失败", source)
        err_branch = source.split("PanSou 搜索失败")[0].rsplit("if ", 1)[-1]
        self.assertIn("error", err_branch)

        client = mod.PanSouClient(
            base_url="http://192.168.31.95:9000/", auth_enabled=False, proxy=None
        )
        result = client.search(keyword="测试剧集", cloud_types=["115"])
        self.assertIn("error", result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
