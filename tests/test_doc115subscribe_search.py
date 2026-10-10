"""0.11.0 parser / index / document-client / QR regressions; synthetic data only."""
import socket
import unittest
from unittest.mock import Mock, patch

import test_doc115subscribe_parser as base
import test_doc115subscribe_qr as qrbase

parser, client_module, index_module = base.parser, base.client_module, base.index_module
resource, FakeClient, sheet, pb = base.resource, base.FakeClient, base.sheet, base.pb
qr = qrbase.qr


class BannerAndMergeTests(unittest.TestCase):
    def test_click_here_link_row_is_not_banner(self):
        grid = [["片名", "链接"], ["Synthetic Film", "点击这里"], ["Synthetic Two", "点击这里"]]
        hrefs = [[None, None], [None, "https://115.com/s/SYNA"], [None, "https://115.com/s/SYNB"]]
        recs = parser.parse_sheet("s", "电影", grid, hrefs)
        self.assertEqual([r["title"] for r in recs], ["Synthetic Film", "Synthetic Two"])

    def test_data_row_with_banner_word_in_other_column_is_kept(self):
        grid = [["片名", "备注", "链接"], ["Synthetic Film", "资源列表见目录", "https://115.com/s/SYNA"]]
        self.assertEqual(len(parser.parse_sheet("s", "电影", grid, [])), 1)

    def test_banner_without_name_still_bundles(self):
        grid = [["打包链接，点我直达"], ["Synthetic A"], ["Synthetic B"]]
        hrefs = [["https://115.com/s/BUNDLE"], [None], [None]]
        recs = parser.parse_sheet("s", "老电影", grid, hrefs)
        self.assertEqual([r["title"] for r in recs], ["Synthetic A", "Synthetic B"])
        self.assertTrue(all(r["sheet_bundle"] for r in recs))

    def test_merged_title_is_inherited_by_adjacent_row(self):
        grid = [["片名", "规格", "链接"],
                ["Synthetic Film", "4K", "https://115.com/s/SYNA"],
                ["", "1080P", "https://115.com/s/SYNB"],
                ["", "", ""],
                ["", "720P", "https://115.com/s/SYNC"]]
        recs = parser.parse_sheet("s", "电影", grid, [])
        self.assertEqual([(r["title"], r.get("title_inherited", False)) for r in recs],
                         [("Synthetic Film", False), ("Synthetic Film", True)])

    def test_multiple_hyperlinks_in_one_cell_all_become_links(self):
        grid = [["片名", "链接"], ["Synthetic Film", "下载"]]
        hrefs = [[None, None], [None, ["https://115.com/s/SYNA", "magnet:?xt=urn:btih:" + "a" * 40]]]
        rec = parser.parse_sheet("s", "电影", grid, hrefs)[0]
        self.assertEqual([k for k, _ in rec["links"]], ["115_share", "magnet"])


class YearCellTests(unittest.TestCase):
    def test_year_column_formats(self):
        for value, year in (("2019", "2019"), ("2019.0", "2019"), ("2019年", "2019"), ("2019-05-01", "2019"),
                            ("2019/5/1", "2019"), ("43586", "2019"), ("abc", ""), ("", ""), ("123", "")):
            with self.subTest(value=value):
                self.assertEqual(parser.year_from_cell(value), year)

    def test_numeric_cell_float_noise(self):
        nums = [2019.0000000001, 2.5]
        self.assertEqual(client_module._cell_value(2, 129, [], [], nums), "2019")
        self.assertEqual(client_module._cell_value(2, 130, [], [], nums), "2.5")
        grid = [["片名", "年份", "链接"], ["Synthetic", "2019.0", "https://115.com/s/SYNA"]]
        self.assertEqual(parser.parse_sheet("s", "电影", grid, [])[0]["year"], "2019")


class NormalizeAndSearchTests(unittest.TestCase):
    def test_normalize_title(self):
        self.assertEqual(parser.normalize_title("复仇者联盟：终局之战"), parser.normalize_title("复仇者联盟 终局之战"))
        self.assertEqual(parser.normalize_title("Ｆａｓｔ　＆　Ｆｕｒｉｏｕｓ"), "fastfurious")
        self.assertEqual(parser.normalize_title("洛基 第二季"), "洛基s2")
        self.assertEqual(parser.normalize_title("Loki Season 2"), "lokis2")
        self.assertEqual(parser.normalize_title("沙丘 第二部"), "沙丘2")
        self.assertEqual(parser.normalize_title("第十二集"), "e12")
        self.assertEqual(parser.normalize_title("《流浪地球》【4K】"), "流浪地球4k")

    def test_examples(self):
        recs = [resource(title="复仇者联盟：终局之战", row=1), resource(title="沙丘 第二部", row=2),
                resource(title="沙丘21", row=3)]
        self.assertEqual([r["title"] for r in parser.search(recs, "复仇者联盟 终局之战")], ["复仇者联盟：终局之战"])
        self.assertEqual([r["title"] for r in parser.search(recs, "沙丘2")], ["沙丘 第二部"])

    def test_score_order_exact_prefix_contains_and_quality_secondary(self):
        recs = [resource(title="Synthetic Film Returns", row=1), resource(title="The Synthetic Film", row=2),
                resource(title="Synthetic Film", row=3, qtext="720P"), resource(title="Synthetic Film", row=4, qtext="4K 中字")]
        self.assertEqual([r["row"] for r in parser.search(recs, "synthetic film")], [4, 3, 1, 2])

    def test_year_bonus(self):
        recs = [resource(title="Synthetic", year="2019", row=1), resource(title="Synthetic", year="2025", row=2)]
        self.assertEqual([r["row"] for r in parser.search(recs, "Synthetic 2025")], [2, 1])
        self.assertEqual([r["row"] for r in parser.search([resource(title="Synthetic 1917", year="")], "1917")], [1])

    def test_traditional_conversion_is_optional(self):
        with patch.object(parser, "_T2S", None):
            self.assertEqual(parser.normalize_title("復仇者"), "復仇者")


class SearchPageTests(unittest.TestCase):
    def index(self, records):
        idx = index_module.DocIndex(FakeClient({}))
        idx._set_records(records)
        return idx

    def test_sort_options_match_and_page_clamp(self):
        idx = self.index([resource(title="Synthetic Film", year="2019", row=1, qtext="720P"),
                          resource(title="Synthetic Film：Two", year="2025", row=2, qtext="4K 中字"),
                          resource(title="Synthetic Film Three", year="", row=3, qtext="1080P")])
        rel = idx.search_page("synthetic film", page=1, page_size=10, sort="relevance")
        self.assertEqual(rel["records"][0]["row"], 1)
        self.assertEqual(rel["records"][0]["match"], "Synthetic Film")
        self.assertEqual([r["row"] for r in idx.search_page("synthetic film", sort="year_desc")["records"]], [2, 1, 3])
        self.assertEqual([r["row"] for r in idx.search_page("synthetic film", sort="year_asc")["records"]], [1, 2, 3])
        self.assertEqual(idx.search_page("synthetic film", sort="quality")["records"][0]["row"], 2)
        clamped = idx.search_page("synthetic film", page=99, page_size=2)
        self.assertEqual((clamped["page"], clamped["total_pages"], len(clamped["records"])), (2, 2, 1))
        self.assertEqual(idx.search_page("synthetic film", page=0)["page"], 1)
        self.assertEqual(idx.search_page("nothing", page=5)["page"], 1)
        with self.assertRaises(ValueError):
            idx.search_page("x", sort="random")

    def test_caller_signature(self):
        idx = self.index([resource()])
        result = idx.search_page("Synthetic", media_type="all", quality="all", subtitle="all", link_kind="all",
                                 page=1, page_size=10, sort="relevance")
        self.assertEqual(result["total"], 1)


class BuildTests(unittest.TestCase):
    def test_sheet_with_only_header_clears_old_records(self):
        old = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic A")), "s2": ("电视剧", sheet("Synthetic B"))}))
        old.build()
        idx = index_module.DocIndex(FakeClient({"s1": ("电影", {"grid": [["片名", "链接", "TMDB"]], "hrefs": []}),
                                              "s2": ("电视剧", sheet("Synthetic B"))}))
        summary = idx.build(previous=old)
        self.assertEqual([r["title"] for r in idx.records], ["Synthetic B"])
        self.assertFalse(idx.sheets[0]["stale"])
        self.assertEqual(idx.sheets[0]["count"], 0)
        self.assertEqual(summary["stale_sheet_count"], 0)

    def test_long_stale_sheet_is_marked_expired(self):
        old = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic A")), "s2": ("电视剧", sheet("Synthetic B"))}))
        old.build()
        old.sheets[1]["last_success_at"] -= 15 * 86400
        idx = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic A")),
                                              "s2": ("电视剧", client_module.DocError("synthetic failure"))}))
        summary = idx.build(previous=old)
        self.assertEqual(summary["expired_sheet_count"], 1)
        self.assertTrue(summary["stale_sheets"][0]["expired"])
        self.assertGreaterEqual(summary["stale_sheets"][0]["stale_days"], 15)
        fresh = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic A")),
                                                "s2": ("电视剧", client_module.DocError("synthetic failure"))}))
        self.assertEqual(fresh.build(previous=idx)["expired_sheet_count"], 1)


def jsonp(payload):
    import json
    return ("clientVarsCallback(" + json.dumps(payload) + ")").encode()


class Body:
    def __init__(self, data):
        self.data = data

    def read(self):
        return self.data


class DocClientTests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(socket.socket, "connect", side_effect=AssertionError("NETWORK BLOCKED")))

    def test_extract_rich_returns_all_links(self):
        a, b = "https://115.com/s/SYNA", "magnet:?xt=urn:btih:" + "b" * 40
        rich = pb(3, pb(3, pb(1, b"x")) + pb(7, pb(11, pb(1, a.encode()))) + pb(7, pb(11, pb(1, b.encode()))))
        self.assertEqual(client_module._extract_rich(rich), ("x", [a, b]))
        self.assertEqual(client_module._cell_hrefs(6, 0, [("x", [a, b])]), [a, b])

    def test_expired_cookie_raises_clear_error(self):
        c = client_module.TencentDocsClient("Synthetic", cookie="uid=synthetic")
        with patch.object(client_module.urllib.request, "urlopen",
                          return_value=Body(jsonp({"clientVars": {"isLogin": False, "collab_client_vars": {}}}))):
            with self.assertRaisesRegex(client_module.DocError, "腾讯文档登录已失效，请重新扫码登录"):
                c.fetch_sheet_list()

    def test_timeout_retries_with_backoff_then_succeeds(self):
        c = client_module.TencentDocsClient("Synthetic")
        c.sleep = Mock()
        payload = jsonp({"clientVars": {"collab_client_vars": {"header": [{"d": [{"id": "s1", "name": "电影"}]}]}}})
        with patch.object(client_module.urllib.request, "urlopen",
                          side_effect=[socket.timeout("timed out"), socket.timeout("timed out"), Body(payload)]) as opened:
            self.assertEqual(c.fetch_sheet_list(), [{"id": "s1", "name": "电影"}])
        self.assertEqual(opened.call_count, 3)
        self.assertEqual([call.args[0] for call in c.sleep.call_args_list], [1.0, 2.0])

    def test_timeout_retry_is_bounded_and_other_errors_not_retried(self):
        c = client_module.TencentDocsClient("Synthetic")
        c.sleep = Mock()
        with patch.object(client_module.urllib.request, "urlopen", side_effect=socket.timeout("timed out")) as opened:
            with self.assertRaises(client_module.DocError):
                c.fetch_sheet_list()
        self.assertEqual(opened.call_count, 3)
        with patch.object(client_module.urllib.request, "urlopen", side_effect=OSError("refused")) as opened:
            with self.assertRaises(client_module.DocError):
                c.fetch_sheet_list()
        self.assertEqual(opened.call_count, 1)

    def test_missing_max_col_falls_back_and_pages_are_spaced(self):
        c = client_module.TencentDocsClient("Synthetic")
        c.sleep = Mock()
        calls = []
        def raw(tab, start=0, end=0, end_col=63):
            calls.append((start, end, end_col))
            return {}, {"max_row": 1000} if not calls[1:] else {"block_datas": []}
        with patch.object(c, "_opendoc_raw", side_effect=raw):
            result = c.fetch_sheet("s1")
        self.assertTrue(result["meta"]["col_fallback"])
        self.assertEqual([call[2] for call in calls[1:]], [63, 63])
        c.sleep.assert_called_once_with(client_module.CHUNK_INTERVAL)


class QrWorkerTests(unittest.TestCase):
    def test_worker_start_timeout_raises_instead_of_returning_unusable_worker(self):
        with patch.object(qr.threading.Thread, "start"), patch.object(qr, "WORKER_START_TIMEOUT", 0):
            with self.assertRaisesRegex(qr.QrLoginError, "超时"):
                qr._Worker()

    def test_expired_qr_reloads_login_page(self):
        worker = qr._Worker.__new__(qr._Worker)
        worker._session_id = "current"
        worker._ctx = Mock()
        worker._ctx.cookies.return_value = []
        worker._last_shot = qr.time.time()
        worker._qr_born = qr.time.time() - qr.QR_EXPIRE_SECONDS - 1
        worker._open_login = Mock(return_value=(b"new", False))
        result = worker._check("current")
        self.assertTrue(result["refreshed"] and result["reloaded"])
        worker._open_login.assert_called_once()


if __name__ == "__main__":
    unittest.main()
