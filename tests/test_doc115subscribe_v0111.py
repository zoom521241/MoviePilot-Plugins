"""0.11.1 regressions (synthetic data only): unknown-type batches, small-file ID conflicts, fast search, 1080p."""
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from test_doc115subscribe_organization import org
from test_doc115subscribe_ledger import TaskLedger, ledger_module
import test_doc115subscribe_parser as base

parser, index_module = base.parser, base.index_module

FOLDER = "/115-影视/115-downloads/电影/合成电影:黎明[中字].Synthetic.Dawn.2016.2160p"
MAIN = FOLDER + "/Synthetic.Dawn.2016.2160p.mkv"
AD = FOLDER + "/【更多资源请访问】.MKV"


def movie_batch(**fields):
    return {"title": "合成电影：黎明[中字].Synthetic.Dawn.2016.2160p", "year": "2016", "type": "unknown",
            "target_type": "movie", "kind": "magnet", "source_storage": "115网盘Plus", "final_storage": "115网盘Plus",
            "final_path": "/115-影视/115-downloads/电影", **fields}


def movie_event(path, fid, success=True, stamp=2000):
    return {"title": "合成电影：黎明", "year": "2016", "type": "电影", "tmdb_id": 9001, "status": success,
            "date": stamp, "time_is_observed": True, "src": path,
            "src_fileitem": {"path": path, "storage": "115网盘Plus", "fileid": fid}}


class UnknownTypeIdentityTests(unittest.TestCase):
    def test_unknown_document_type_does_not_conflict_with_mp_movie(self):
        self.assertTrue(org.identity_matches(movie_batch(), movie_event(MAIN, "1")))

    def test_target_type_still_rejects_real_type_conflict(self):
        tv_event = dict(movie_event(MAIN, "1"), type="电视剧")
        self.assertFalse(org.identity_matches(movie_batch(), tv_event))

    def test_explicit_document_type_wins_over_target(self):
        self.assertFalse(org.identity_matches(movie_batch(type="tv", target_type="movie"), movie_event(MAIN, "1")))


class SmallFileConflictTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="doc115-synthetic-v0111-")
        self.addCleanup(self.temp.cleanup)
        self.ledger = TaskLedger(Path(self.temp.name) / "t.sqlite3")
        with patch.object(ledger_module.time, "time", return_value=1000):
            self.batch_id = self.ledger.claim_resource("synthetic-dawn", movie_batch(), generation=1)["batch"]["id"]

    def scan(self, ad_id):
        items = [{"source_path": MAIN, "storage": "115网盘Plus", "file_id": "1", "size": 40 * 2**30, "name": "Synthetic.Dawn.2016.2160p.mkv"},
                 {"source_path": AD, "storage": "115网盘Plus", "file_id": ad_id, "size": 600_000, "name": "【更多资源请访问】.MKV"}]
        # 与 runtime 一致：先按小视频阈值（线上 10MB）把广告小视频标成非必要
        return self.ledger.set_manifest(self.batch_id, org.classify_optional_media(items, 10), complete=True)

    def test_ad_file_id_change_keeps_manifest_complete_and_success(self):
        self.scan("10")
        batch = self.scan("11")
        self.assertTrue(batch["manifest_conflicts"])
        self.assertTrue(batch["manifest_complete"])
        projection = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "1"), movie_event(AD, "11", success=False)])
        self.assertEqual((projection["organization_status"], projection["organized_count"], projection["organized_total"]), ("success", 1, 1))

    def test_required_file_id_change_still_blocks_completeness(self):
        self.scan("10")
        items = [{"source_path": MAIN, "storage": "115网盘Plus", "file_id": "2", "size": 40 * 2**30}]
        batch = self.ledger.set_manifest(self.batch_id, items, complete=True)
        self.assertFalse(batch["manifest_complete"])
        self.assertIn("manifest_file_identity_conflict", batch["manifest_reason"])

    def test_legacy_batch_marked_incomplete_by_ad_conflict_recovers(self):
        self.scan("10")
        self.scan("11")
        # 模拟 0.11.0 写下的状态：附带文件冲突也把清单标成了不完整
        self.ledger.update(self.batch_id, manifest_complete=False, manifest_reason="manifest_file_identity_conflict",
                           manifest_snapshot_ready=True)
        projection = self.ledger.record_evidence(self.batch_id, [movie_event(MAIN, "1")])
        self.assertEqual(projection["organization_status"], "success")


class FastSearchTests(unittest.TestCase):
    def build(self, n=30000):
        recs = [{"sheet_id": "s", "sheet": "电影", "row": i, "title": f"合成片{i} Synthetic.{i}.2019.1080p",
                 "qtext": "1080P", "links": [("115_share", f"https://115.com/s/sw{i}")]} for i in range(n)]
        recs += [{"sheet_id": "t", "sheet": "蚂蚁和 rb4k", "row": 1, "title": "闪电侠 第九季", "qtext": "1080P蓝光REMUX[106GB] 电视剧",
                  "links": [("115_share", "https://115.com/s/flash9")]},
                 {"sheet_id": "t", "sheet": "星火 4K", "row": 2, "title": "闪电侠", "year": "2023", "qtext": "4K蓝光原盘[简繁]",
                  "links": [("115_share", "https://115.com/s/flash4k")]}]
        idx = index_module.DocIndex(None)
        idx._set_records(recs)
        return idx

    def test_1080p_filter_finds_1080p_tv_rows(self):
        idx = self.build(10)
        titles = [r["title"] for r in idx.search_page("闪电侠", quality="1080p")["records"]]
        self.assertEqual(titles, ["闪电侠 第九季"])
        self.assertEqual([r["title"] for r in idx.search_page("闪电侠", quality="4k")["records"]], ["闪电侠"])

    def test_1080_regex_does_not_hit_other_numbers(self):
        self.assertFalse(parser.is_1080({"title": "合成片 10800 部合集", "qtext": ""}))
        self.assertTrue(parser.is_1080({"title": "x", "qtext": "1080i HDTV"}))

    def test_filters_and_pages_reuse_one_scan(self):
        idx = self.build()
        idx.warm_search()
        with patch.object(parser, "score_key", wraps=parser.score_key) as scorer:
            first = idx.search_page("合成片", page=1)
            scans = scorer.call_count
            idx.search_page("合成片", quality="1080p")
            idx.search_page("合成片", page=2, sort="year_desc")
            idx.search_page("合成片", media_type="movie", link_kind="share")
            self.assertEqual(scorer.call_count, scans)
        self.assertGreater(first["total"], 10)

    def test_warm_search_is_fast_per_keyword(self):
        idx = self.build()
        idx.warm_search()
        start = time.perf_counter()
        for kw in ("合成片29999", "闪电侠", "不存在的片名", "Synthetic 2019"):
            idx.search_page(kw)
        self.assertLess(time.perf_counter() - start, 2.0)

    def test_refresh_invalidates_cached_hits(self):
        idx = self.build(5)
        self.assertEqual(idx.search_page("闪电侠")["total"], 2)
        idx._set_records([{"sheet_id": "s", "sheet": "电影", "row": 1, "title": "闪电侠 第十季", "qtext": "",
                           "links": [("115_share", "https://115.com/s/x")]}])
        self.assertEqual(idx.search_page("闪电侠")["total"], 1)

    def test_scores_match_reference_scorer(self):
        idx = self.build(20)
        for kw in ("闪电侠", "闪电侠 2023", "合成片1 1080p", "Synthetic.3"):
            fast = [(r["title"], r["score"]) for r in idx.search_page(kw, page_size=100)["records"]]
            ref = sorted(((parser.score_title(r, kw)[0], r) for r in idx.records if parser.score_title(r, kw)[0]),
                         key=lambda h: (-h[0], -parser.quality_score(h[1]), h[1].get("row", 0)))
            self.assertEqual(fast, [(r["title"], s) for s, r in ref][:100], kw)
            for row in idx.search_page(kw, page_size=100)["records"]:
                self.assertEqual(row["match"], parser.score_title(row, kw)[1])


if __name__ == "__main__":
    unittest.main()
