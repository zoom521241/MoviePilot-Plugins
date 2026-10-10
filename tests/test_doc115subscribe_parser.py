"""Synthetic parser/index/matching regressions. No MoviePilot, network or real resources."""
import base64
import importlib
import json
import sys
import tempfile
import types
import unittest
import zlib
from pathlib import Path
from unittest.mock import patch

PLUGIN = Path(__file__).resolve().parents[1] / "plugins.v3" / "doc115subscribe"
PACKAGE = "_doc115_parser_testpkg"
if PACKAGE not in sys.modules:
    package = types.ModuleType(PACKAGE)
    package.__path__ = [str(PLUGIN)]
    sys.modules[PACKAGE] = package
parser = importlib.import_module(PACKAGE + ".doc_parser")
client_module = importlib.import_module(PACKAGE + ".doc_client")
index_module = importlib.import_module(PACKAGE + ".doc_index")
sync = importlib.import_module(PACKAGE + ".subscribe_sync")
links = importlib.import_module(PACKAGE + ".link_router")


def resource(title="Synthetic Film", year="2025", tmdbid="550", **values):
    rec = {"sheet_id": "synthetic-sheet", "sheet": "最新电影", "kind": "movie", "row": 1,
           "title": title, "year": year, "tmdbid": tmdbid, "media_type": "movie",
           "qtext": "1080P 中字", "spec": "", "links": [("115_share", "https://115.com/s/SYNTHETIC")],
           "bundle": False, "sheet_bundle": False, "no_link": False}
    rec.update(values)
    return rec


def sheet(*titles):
    return {"grid": [["片名", "链接", "TMDB"]] +
                    [[title, f"https://115.com/s/SYNTHETIC{i}", "550"] for i, title in enumerate(titles)],
            "hrefs": []}


class FakeClient:
    doc_id = "SyntheticDocument"

    def __init__(self, data, doc_id=None):
        self.data = data
        if doc_id:
            self.doc_id = doc_id

    def fetch_sheet_list(self):
        return [{"id": sid, "name": name} for sid, (name, _) in self.data.items()]

    def fetch_sheet(self, sid):
        data = self.data[sid][1]
        if isinstance(data, Exception):
            raise data
        return data


def varint(number):
    result = bytearray()
    while number > 127:
        result.append(number & 127 | 128)
        number >>= 7
    result.append(number)
    return bytes(result)


def pb(field, value):
    return varint(field << 3 | 2) + varint(len(value)) + value


class ParserTests(unittest.TestCase):
    def test_headerless_keeps_first_and_ignores_long_url_column(self):
        rows = [["1", "你的名字", "https://115.com/s/SYNTHETICLONGURL1"],
                ["2", "第二部电影", "https://115.com/s/SYNTHETICLONGURL2"]]
        records = parser.parse_sheet("s", "电影", rows, [])
        self.assertEqual([r["title"] for r in records], ["你的名字", "第二部电影"])

    def test_real_name_containing_header_word_is_preserved(self):
        records = parser.parse_sheet("s", "电影", sheet("你的名字", "名字里的秘密")["grid"], [])
        self.assertEqual(len(records), 2)
        self.assertFalse(parser.is_name_head("你的名字"))

    def test_numeric_movie_title_is_preserved(self):
        records = parser.parse_sheet("s", "电影", sheet("1917")["grid"], [])
        self.assertEqual(records[0]["title"], "1917")
        self.assertEqual(records[0]["year"], "")

    def test_short_tmdb_ids(self):
        grid = [["片名", "TMDB", "链接"], ["Synthetic One", "1", "https://115.com/s/SYNTHETIC1"],
                ["Synthetic Other", "550", "https://115.com/s/SYNTHETIC2"]]
        self.assertEqual([r["tmdbid"] for r in parser.parse_sheet("s", "电影", grid, [])], ["1", "550"])

    def test_explicit_year_column(self):
        grid = [["片名", "年份", "链接"], ["Synthetic", "2025", "https://115.com/s/SYNTHETIC"]]
        self.assertEqual(parser.parse_sheet("s", "电影", grid, [])[0]["year"], "2025")

    def test_tmdb_url_extracts_id_and_type_from_href(self):
        grid = [["片名", "TMDB", "链接"], ["Synthetic Series", "详情", "https://115.com/s/SYNTHETIC"]]
        hrefs = [[None] * 3, [None, "https://www.themoviedb.org/tv/550-synthetic?language=zh-CN", None]]
        rec = parser.parse_sheet("s", "电影", grid, hrefs)[0]
        self.assertEqual((rec["tmdbid"], rec["media_type"]), ("550", "tv"))

    def test_tmdb_url_does_not_use_language_year_as_id(self):
        rec = parser.parse_sheet("s", "电影", [["片名", "TMDB", "链接"],
             ["Synthetic", "https://www.themoviedb.org/zh-CN/movie/550-test?year=2025", "https://115.com/s/SYNTHETIC"]], [])[0]
        self.assertEqual(rec["tmdbid"], "550")

    def test_quality_terms_do_not_imply_movie_or_4k(self):
        self.assertEqual(parser.classify_sheet("4K电视剧"), "tv")
        self.assertEqual(parser.media_type_of("4K原盘", "Synthetic"), "unknown")
        self.assertEqual(parser.media_type_of("最新电影", "Synthetic S01E02"), "tv")
        self.assertFalse(parser.is_4k(resource(qtext="1080P 蓝光 REMUX 杜比视界")))
        self.assertTrue(parser.is_4k(resource(qtext="2160P 中字")))

    def test_hidden_native_links_survive_rich_text(self):
        for href in ("magnet:?xt=urn:btih:" + "a" * 40,
                     "ed2k://|file|synthetic.mkv|123|" + "a" * 32 + "|/"):
            rich = pb(3, pb(3, pb(1, b"Download")) + pb(7, pb(11, pb(1, href.encode()))))
            text, all_links = client_module._extract_rich(rich)
            self.assertEqual((text, all_links), ("Download", [href]))
            actual = all_links[0]
            rec = parser.parse_sheet("s", "电影", [["片名", "链接"], ["Synthetic", "Download"]],
                                     [[None, None], [None, actual]])[0]
            self.assertEqual(rec["links"][0][1], href)

    def test_decode_selects_structurally_valid_data_segment(self):
        # A large style/other segment precedes a small actual cell-data segment.
        pool = pb(1, pb(1, b"Synthetic"))
        real = pb(19, pb(5, pool))
        block = pb(1, pb(5, pb(1, b"x" * 12000)) + pb(5, real))
        decoded = client_module._decode_block(base64.b64encode(zlib.compress(block)).decode())
        self.assertEqual(decoded[1], ["Synthetic"])


class LinkAndSourceTests(unittest.TestCase):
    def test_exact_115_hosts(self):
        for url in ("https://115.com/s/SYNTHETIC", "https://www.115cdn.com/s/SYNTHETIC?password=abcd"):
            self.assertEqual(links.classify_link(url), "115_share")
        for url in ("https://115.com.evil.invalid/s/SYNTHETIC", "https://evil.invalid/115.com/s/SYNTHETIC",
                    "https://evil.invalid/?next=https://115.com/s/SYNTHETIC", "https://user@115.com/s/SYNTHETIC",
                    "https://115.com/s/SYNTHETIC/unsafe", "https://115.com:9999/s/SYNTHETIC"):
            self.assertNotEqual(links.classify_link(url), "115_share")

    def test_document_urls_require_exact_domain(self):
        self.assertEqual(client_module.TencentDocsClient.parse_doc_id("https://docs.qq.com/sheet/Synthetic?tab=s1"), ("Synthetic", "s1"))
        self.assertEqual(client_module.TencentDocsClient.parse_doc_id("Synthetic"), ("Synthetic", None))
        for url in ("https://docs.qq.com.evil.invalid/sheet/Synthetic", "https://evil.invalid/docs.qq.com/sheet/Synthetic",
                    "https://user@docs.qq.com/sheet/Synthetic", "", "docs.qq.com/sheet/Synthetic"):
            with self.assertRaises(client_module.DocError):
                client_module.TencentDocsClient.parse_doc_id(url)

    def test_normalized_native_and_html_links(self):
        self.assertEqual(links.normalize_url("https://magnet:?xt=urn:btih:a&amp;dn=test"), "magnet:?xt=urn:btih:a&dn=test")
        # 同格提取码补进 ?password=，全角逗号不进入链接
        self.assertEqual(links.extract_links("转存：https://115.com/s/SYNTHETIC，提取码 abcd")[0][1],
                         "https://115.com/s/SYNTHETIC?password=abcd")


class SubscriptionTests(unittest.TestCase):
    sub = {"title": "Synthetic Film", "year": "2025", "tmdbid": "550"}

    def test_conflicting_tmdb_never_falls_back_to_same_title(self):
        self.assertEqual(sync.subscription_candidates([resource(tmdbid="999")], self.sub), [])

    def test_conflicting_year_excluded_even_with_equal_tmdb(self):
        self.assertEqual(sync.subscription_candidates([resource(year="2019")], self.sub), [])

    def test_embedded_years_match_and_conflicts_exclude(self):
        rec = resource(title="Synthetic Film (2025)", year="", tmdbid="")
        self.assertEqual(sync.subscription_candidates([rec], self.sub), [rec])
        self.assertEqual(sync.subscription_candidates([resource(title="Synthetic Film 2019", year="", tmdbid="")], self.sub), [])
        rec = resource(title="Synthetic Film 2025", year="", tmdbid="")
        self.assertEqual(sync.subscription_candidates(sync.SubscriptionMatcher([rec]), self.sub), [rec])

    def test_bare_year_in_real_title_is_preserved_and_not_inferred_as_release_year(self):
        title = "Synthetic Class of 1984"
        self.assertEqual(parser.extract_year(title), "")
        rec = resource(title=title, year="", tmdbid="")
        sub = {"title": title, "year": "2025"}
        self.assertEqual(sync.subscription_candidates(sync.SubscriptionMatcher([rec]), sub), [rec])
        self.assertEqual(sync.subscription_candidates(sync.SubscriptionMatcher([rec]), {"title": "Synthetic Class of", "year": "2025"}), [])

    def test_missing_identity_can_fallback_to_exact_title(self):
        rec = resource(year="", tmdbid="")
        self.assertEqual(sync.subscription_candidates([rec], self.sub), [rec])

    def test_arbitrary_prefix_and_sequel_rejected(self):
        for title in ("Synthetic Film 2", "Synthetic Film Extended Story", "Synthetic Film (Part II)"):
            self.assertEqual(sync.subscription_candidates([resource(title=title, tmdbid="")], self.sub), [])

    def test_release_suffix_can_match(self):
        rec = resource(title="Synthetic Film 2025 4K 中字", year="", tmdbid="")
        self.assertEqual(sync.subscription_candidates([rec], self.sub), [rec])
        rec = resource(title="Synthetic Film (2025) [4K 中字]", year="", tmdbid="")
        self.assertEqual(sync.subscription_candidates([rec], self.sub), [rec])

    def test_tv_id_namespace_is_separate(self):
        rec = resource(media_type="tv")
        self.assertEqual(sync.subscription_candidates([rec], self.sub), [])
        self.assertEqual(sync.movie_records([rec]), [])

    def test_title_tv_markers_override_movie_kind(self):
        rec = resource(title="Synthetic S01", media_type="")
        self.assertEqual(sync.movie_records([rec]), [])

    def test_unusable_best_does_not_hide_fallback(self):
        bad = resource(qtext="4K 中字", bundle=True)
        good = resource(row=2)
        third = resource(qtext="720P", row=3)
        candidates = sync.subscription_candidates([bad, third, good], self.sub)
        self.assertEqual(candidates, [good, third])
        self.assertEqual(sync.match_subscriptions([bad, good], [self.sub]), [(self.sub, good)])
        self.assertEqual(sync.subscription_candidates(sync.SubscriptionMatcher([bad, third, good]), self.sub), candidates)

    def test_linkless_and_unsafe_resources_are_not_usable(self):
        for rec in (resource(no_link=True), resource(sheet_bundle=True), resource(links=[]),
                    resource(links=[("115_share", "https://evil.invalid/115.com/s/SYNTHETIC")])):
            self.assertEqual(sync.subscription_candidates([rec], self.sub), [])

    def test_preindexed_matcher_preserves_strict_identity_and_media_types(self):
        good = resource(tmdbid="", year="")
        records = [resource(tmdbid="999"), resource(year="2019"), resource(media_type="tv"),
                   resource(title="Synthetic Film 2", tmdbid=""), good]
        self.assertEqual(sync.subscription_candidates(sync.SubscriptionMatcher(records), self.sub), [good])


class IndexTests(unittest.TestCase):
    def build_index(self):
        idx = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic A")),
                                              "s2": ("电视剧", sheet("Synthetic B"))}))
        idx.build()
        return idx

    def test_partial_failure_preserves_previous_sheet_and_metadata(self):
        old = self.build_index()
        idx = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic New")),
                                              "s2": ("电视剧", client_module.DocError("synthetic failure"))}))
        summary = idx.build(previous=old)
        self.assertEqual([r["title"] for r in idx.records], ["Synthetic New", "Synthetic B"])
        self.assertEqual(summary["stale_sheet_count"], 1)
        self.assertEqual(len(summary["errors"]), 1)
        self.assertEqual(idx.sheets[1]["last_success_at"], old.sheets[1]["last_success_at"])

    def test_all_failed_does_not_mutate_valid_index(self):
        idx = self.build_index()
        previous_version, previous_records = idx.index_version, list(idx.records)
        idx.client = FakeClient({"s1": ("电影", client_module.DocError("synthetic failure")),
                                 "s2": ("电视剧", client_module.DocError("synthetic failure"))})
        with self.assertRaises(client_module.DocError):
            idx.build()
        self.assertEqual(idx.index_version, previous_version)
        self.assertEqual(idx.records, previous_records)

    def test_empty_sheet_preserves_old_while_other_succeeds(self):
        old = self.build_index()
        idx = index_module.DocIndex(FakeClient({"s1": ("电影", {"grid": [], "hrefs": []}),
                                              "s2": ("电视剧", sheet("Synthetic Updated"))}))
        idx.build(previous=old)
        self.assertEqual([r["title"] for r in idx.records], ["Synthetic A", "Synthetic Updated"])
        self.assertTrue(idx.sheets[0]["stale"])

    def test_all_empty_rejected(self):
        idx = index_module.DocIndex(FakeClient({"s": ("电影", {"grid": [], "hrefs": []})}))
        with self.assertRaises(client_module.DocError):
            idx.build()

    def test_wrong_source_never_preserves_old_records(self):
        old = self.build_index()
        idx = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic Other")),
                                              "s2": ("电视剧", client_module.DocError("failure"))}, "OtherDocument"))
        idx.build(previous=old)
        self.assertEqual([r["title"] for r in idx.records], ["Synthetic Other"])

    def test_cache_source_and_version_survive_atomic_roundtrip(self):
        idx = self.build_index()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            idx.save(path)
            loaded = index_module.DocIndex.load(path, expected_doc_id=idx.source_doc_id)
            self.assertEqual(loaded.index_version, idx.index_version)
            self.assertEqual(loaded.records, idx.records)
            self.assertIsNone(index_module.DocIndex.load(path, expected_doc_id="OtherDocument"))
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload.pop("source_doc_id")
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertIsNone(index_module.DocIndex.load(path))

    def test_failed_atomic_replace_preserves_disk_and_cleans_temp(self):
        idx = self.build_index()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "index.json"
            idx.save(path)
            original = path.read_bytes()
            with patch.object(index_module.os, "replace", side_effect=OSError("synthetic full disk")):
                with self.assertRaises(OSError):
                    idx.save(path)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).glob("*.tmp")), [])

    def test_stable_resource_id_survives_reordering_but_versions_change(self):
        idx = self.build_index()
        first_id, version = idx.records[0]["record_id"], idx.index_version
        idx.client = FakeClient({"s2": ("电视剧", sheet("Synthetic B")), "s1": ("电影", sheet("Synthetic A"))})
        idx.build()
        self.assertNotEqual(idx.index_version, version)
        self.assertEqual(idx.get_record(first_id)["title"], "Synthetic A")
        other = index_module.DocIndex(FakeClient({"s1": ("电影", sheet("Synthetic A"))}, "OtherSource"))
        other.build()
        self.assertNotEqual(other.records[0]["record_id"], first_id)

    def test_server_filter_precedes_limit_and_pagination_reports_total(self):
        idx = index_module.DocIndex(FakeClient({}))
        records = [resource(title=f"Synthetic {i}", row=i, qtext="1080P 蓝光 REMUX", media_type="movie") for i in range(40)]
        records += [resource(title=f"Synthetic TV {i}", row=100 + i, qtext="4K 中字", media_type="tv") for i in range(15)]
        idx._set_records(records)
        result = idx.search_page("Synthetic", media_type="tv", quality="4k", page=2, page_size=10)
        self.assertEqual((result["total"], len(result["records"])), (15, 5))
        self.assertTrue(all(rec["media_type"] == "tv" for rec in result["records"]))
        self.assertEqual(result["records"][0]["index_version"], idx.index_version)
        self.assertEqual(idx.search_page("Synthetic", media_type="movie", quality="4k")["total"], 0)


if __name__ == "__main__":
    unittest.main()
